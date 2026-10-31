"""لایهٔ دانلود — پوششی نازک و کنترل‌شده روی yt-dlp و دانلود مستقیم HTTP.

نکته‌های مهم:
* همهٔ کارهای سنگین در ترد جدا اجرا می‌شوند تا حلقهٔ asyncio قفل نشود.
* هر کار پوشهٔ مخصوص خودش را دارد و بعد از آپلود پاک می‌شود.
* لغو کار با یک ``asyncio.Event`` انجام می‌شود؛ هوک پیشرفت استثنا می‌دهد
  و yt-dlp دانلود را متوقف می‌کند.
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin

import aiohttp
import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from app.config import Config
from app.core import errors, human, urlcheck
from app.services import gallery
from app.services.cookies import CookieStore
from app.services.formats import FormatOption

log = logging.getLogger("leechx.downloader")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# بعضی سایت‌ها فقط از مسیر embed متادیتای ویدیو را می‌دهند (مثل Eporner؛
# صفحهٔ عادی برای بعضی IPها صفحهٔ verification برمی‌گرداند و hash ندارد).
_EMBED_VIDEO = re.compile(
    r"^https?://(?:www\.)?eporner\.com/video-([A-Za-z0-9]+)(?:/|$)", re.IGNORECASE
)


def extractor_url(url: str) -> str:
    """آدرس مناسب اکسترکتور؛ برای سایت‌های embed-only مسیر را بازنویسی می‌کند."""
    match = _EMBED_VIDEO.match(url or "")
    if match:
        return f"https://www.eporner.com/embed/{match.group(1)}/"
    return url

MEDIA_MIME_PREFIXES = ("video/", "audio/", "image/")
DIRECT_MIME_TYPES = {
    "application/octet-stream",
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/x-7z-compressed",
    "application/x-rar-compressed",
    "application/vnd.rar",
    "application/vnd.android.package-archive",
}


@asynccontextmanager
async def safe_http_request(session, method: str, url: str, **kwargs):
    """Validate every redirect hop before making the next direct HTTP request.

    This is defense in depth in addition to firewall/network egress restrictions.
    """
    for _ in range(7):
        if not await urlcheck.is_safe_public_url(url):
            raise errors.UnsupportedUrl("Non-public or unsafe download URL")
        response = await session.request(method, url, allow_redirects=False, **kwargs)
        if response.status in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.release()
            if not location:
                raise errors.UnsupportedUrl("Redirect without Location")
            url = urljoin(url, location)
            method = "GET" if response.status == 303 else method
            continue
        try:
            yield response
        finally:
            response.release()
        return
    raise errors.UnsupportedUrl("Too many redirects")


def is_direct_mime(ctype: str) -> bool:
    """آیا این Content-Type یک فایل قابل تحویل مستقیم است؟"""
    ctype = (ctype or "").split(";")[0].strip().lower()
    return ctype.startswith(MEDIA_MIME_PREFIXES) or ctype in DIRECT_MIME_TYPES


# ─────────────────────────────────────────────────────────────
#  مدل‌ها
# ─────────────────────────────────────────────────────────────
@dataclass
class MediaInfo:
    url: str
    title: str
    duration: int | None = None
    uploader: str | None = None
    thumbnail: str | None = None
    extractor: str = ""
    is_live: bool = False
    formats: list[dict] = field(default_factory=list)
    direct: bool = False
    ext: str = ""
    mime: str = ""
    filesize: int | None = None
    playlist: bool = False
    # لینک‌هایی که yt-dlp نمی‌فهمد و با gallery-dl (عکس/آلبوم) دانلود می‌شوند
    gallery: bool = False


@dataclass
class DownloadResult:
    path: Path
    title: str
    duration: int | None = None
    width: int | None = None
    height: int | None = None
    mime: str = "application/octet-stream"
    size: int = 0
    thumbnail: Path | None = None
    is_audio: bool = False
    # آلبوم/گالری: همهٔ فایل‌های دانلودشده؛ ``path`` اولین فایل است.
    parts: list[Path] = field(default_factory=list)
    gallery: bool = False

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()

    @property
    def count(self) -> int:
        return len(self.parts) if self.parts else 1


@dataclass
class Progress:
    stage: str = "queued"      # queued | downloading | postprocessing | uploading | done | failed
    pct: float = 0.0
    downloaded: int = 0
    downloaded_bytes_total: int = 0
    total: int = 0
    speed: float = 0.0
    eta: int | None = None
    uploaded: int = 0
    uploaded_bytes_total: int = 0
    note: str = ""

    def reset_download(self) -> None:
        self.stage = "downloading"
        self.pct = 0.0
        self.downloaded = 0
        self.downloaded_bytes_total = 0
        self.total = 0
        self.speed = 0.0
        self.eta = None


# ─────────────────────────────────────────────────────────────
#  ابزار
# ─────────────────────────────────────────────────────────────
def _cookie_file(cfg: Config, url: str) -> Path | None:
    host = urlcheck.host_of(url)
    if not host:
        return None
    candidates = [
        cfg.cookies_dir / f"{host}.txt",
        cfg.cookies_dir / f"{host.split('.')[0]}.txt",
        cfg.cookies_dir / "cookies.txt",
    ]
    for path in candidates:
        try:
            if path.is_file() and path.stat().st_size > 0:
                return path
        except OSError:
            continue
    return None


def _base_opts(cfg: Config, url: str, cookie: Path | None = None) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "cachedir": False,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 4,
        "http_headers": {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
        "windowsfilenames": os.name == "nt",
        "overwrites": True,
        "trim_file_name": 120,
    }
    cookie = cookie or _cookie_file(cfg, url)
    if cookie:
        opts["cookiefile"] = str(cookie)
    if cfg.proxy.strip():
        opts["proxy"] = cfg.proxy.strip()
    return opts


def _pick_output(workdir: Path, candidates: list[str]) -> Path | None:
    for raw in reversed(candidates):
        path = Path(raw)
        if path.is_file() and path.stat().st_size > 0:
            return path
    files = [
        p
        for p in workdir.rglob("*")
        if p.is_file()
        and p.suffix not in (".part", ".ytdl", ".temp")
        and not p.name.startswith(".")
        and not p.name.startswith("thumb")
    ]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _mime_for(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


def map_error(exc: BaseException) -> errors.LeechError:
    """تبدیل خطاهای yt-dlp/aiohttp به خطای قابل‌نمایش."""
    if isinstance(exc, aiohttp.ClientPayloadError):
        return errors.IncompleteDownload(str(exc)[:150])
    if isinstance(exc, TimeoutError):
        return errors.DownloadTimeout("Timeout")
    if isinstance(exc, errors.LeechError):
        return exc
    text = str(exc)
    low = text.lower()
    if "unsupported url" in low or "no suitable extractor" in low:
        return errors.UnsupportedUrl("Unsupported URL")
    if "private video" in low or "private" in low and "login" in low:
        return errors.UnsupportedUrl("Private content")
    if "sign in" in low or "login required" in low or "cookies" in low:
        return errors.UnsupportedUrl("Login required")
    if "age" in low and ("restrict" in low or "confirm" in low):
        return errors.UnsupportedUrl("Age restricted")
    if "geo" in low and ("restrict" in low or "block" in low):
        return errors.UnsupportedUrl("Geo restricted")
    if "live event" in low or "is live" in low or "live stream" in low:
        return errors.LiveUnsupported()
    if "http error 404" in low or "404: not found" in low or "not found" in low:
        return errors.ResourceNotFound("404")
    if "http error 403" in low or "403: forbidden" in low:
        return errors.AccessDenied("403")
    if "timed out" in low or "timeout" in low:
        return errors.DownloadTimeout("Timeout")
    return errors.UnsupportedUrl(text[:180] or exc.__class__.__name__)


async def fetch_thumbnail(url: str | None, dest: Path, proxy: str = "") -> Path | None:
    """دانلود کاور (اختیاری) برای آپلود قشنگ‌تر."""
    if not url:
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": USER_AGENT}) as sess:
            async with sess.get(url, proxy=proxy or None) as resp:
                if resp.status != 200:
                    return None
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "image" not in ctype:
                    return None
                data = await resp.content.read(6 * 1024 * 1024)
        if len(data) < 512:
            return None
        dest.write_bytes(data)
        return dest
    except (TimeoutError, aiohttp.ClientError, OSError):
        return None


# ─────────────────────────────────────────────────────────────
#  دانلودر
# ─────────────────────────────────────────────────────────────
class Downloader:
    def __init__(self, cfg: Config, cookies: CookieStore | None = None) -> None:
        self.cfg = cfg
        self.cookies = cookies

    def cookie_for(self, url: str) -> Path | None:
        """فایل کوکی مناسب این لینک (اگر ادمین آپلود کرده باشد)."""
        if self.cookies is not None:
            found = self.cookies.find_for_url(url)
            if found is not None:
                return found
        return _cookie_file(self.cfg, url)

    # ── بررسی لینک ──────────────────────────────────────────
    async def probe(self, url: str, depth: int = 0) -> MediaInfo:
        if not await urlcheck.is_safe_public_url(url):
            raise errors.UnsupportedUrl("Invalid or non-public URL")

        if urlcheck.looks_direct(url):
            direct = await self._probe_direct(url)
            if direct is not None:
                return direct

        try:
            return await asyncio.to_thread(self._probe_blocking, url)
        except errors.LeechError as exc:
            # yt-dlp ویدیو-محور است؛ اگر سایت عکس/آلبوم باشد gallery-dl را امتحان کن.
            if gallery.available() and gallery.supports(url):
                log.info("yt-dlp probe failed (%s) for %s; trying gallery-dl", exc.key, url)
                return await asyncio.to_thread(self._probe_gallery, url)
            raise
        except (DownloadError, ExtractorError) as exc:
            raise map_error(exc) from exc
        except Exception as exc:  # noqa: BLE001 — هر خطای دیگری هم باید به کاربر برسد
            log.exception("probe failed for %s", url)
            raise map_error(exc) from exc

    def _probe_gallery(self, url: str) -> MediaInfo:
        """بررسی سبک لینک گالری؛ بدون درخواست شبکه تا لینک سریع پاسخ بگیرد."""
        name = gallery.extractor_name(url)
        if not name:
            raise errors.UnsupportedUrl("Unsupported URL")
        return MediaInfo(
            url=url,
            title=gallery.display_title(url),
            extractor=f"gallery-dl:{name}",
            gallery=True,
        )

    def _probe_blocking(self, url: str) -> MediaInfo:
        target = extractor_url(url)
        opts = _base_opts(self.cfg, target, self.cookie_for(target))
        opts.update({"skip_download": True, "extract_flat": False})
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target, download=False)

        if not isinstance(info, dict):
            raise errors.UnsupportedUrl("Empty metadata")

        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
            if not entries:
                raise errors.UnsupportedUrl("Empty playlist")
            first = entries[0]
            if not first.get("formats") and first.get("url"):
                raise errors.UnsupportedUrl("Playlist item requires a second pass")
            first.setdefault("webpage_url", first.get("url") or url)
            first["_playlist"] = True
            info = first

        if info.get("is_live"):
            raise errors.LiveUnsupported()

        return MediaInfo(
            # برای لینک‌های embed-only، آدرس اصلی کاربر نمایش داده شود.
            url=url if target != url else (info.get("webpage_url") or url),
            title=human.safe_filename(info.get("title") or "media", 150),
            duration=int(info["duration"]) if info.get("duration") else None,
            uploader=info.get("uploader") or info.get("channel") or info.get("creator"),
            thumbnail=info.get("thumbnail"),
            extractor=str(info.get("extractor_key") or info.get("extractor") or ""),
            is_live=bool(info.get("is_live")),
            formats=list(info.get("formats") or []),
            ext=info.get("ext") or "",
            playlist=bool(info.get("_playlist")),
        )

    async def _probe_direct(self, url: str) -> MediaInfo | None:
        """آیا این URL یک فایل قابل دانلود مستقیم است؟ (بدون استخراج yt-dlp)"""
        timeout = aiohttp.ClientTimeout(total=20)
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"}
        retry_statuses = (403, 405, 501)  # بعضی CDNها HEAD را دوست ندارند
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
                try:
                    async with safe_http_request(sess, "HEAD", url) as resp:
                        status = resp.status
                        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                        length = resp.headers.get("Content-Length")
                        final = str(resp.url)
                except aiohttp.ClientError:
                    status, ctype, length, final = 0, "", None, url

                if status >= 400 and status not in retry_statuses:
                    return None
                if status < 400 and ctype and not is_direct_mime(ctype):
                    return None
                if not ctype or status == 0 or status >= 400:
                    async with safe_http_request(sess, "GET", url, headers={"Range": "bytes=0-0"}) as resp:
                        if resp.status >= 400:
                            return None
                        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                        length = resp.headers.get("Content-Range", "").rpartition("/")[2] or length
                        final = str(resp.url)
        except (TimeoutError, aiohttp.ClientError, OSError):
            return None

        if not is_direct_mime(ctype):
            return None
        if not await urlcheck.is_safe_public_url(final):
            raise errors.UnsupportedUrl("Unsafe redirect destination")

        name = urlcheck.filename_from_url(final, "download")
        return MediaInfo(
            url=final,
            title=human.safe_filename(unquote(name), 150),
            direct=True,
            ext=Path(name).suffix.lower().lstrip("."),
            mime=ctype,
            filesize=int(length) if length and str(length).isdigit() else None,
        )

    # ── دانلود ──────────────────────────────────────────────
    async def download(
        self,
        url: str,
        option: FormatOption,
        workdir: Path,
        progress: Progress,
        cancel: asyncio.Event,
        info: MediaInfo | None = None,
    ) -> DownloadResult:
        workdir.mkdir(parents=True, exist_ok=True)

        if info is not None and info.gallery:
            return await self._download_gallery(url, workdir, progress, cancel, info)

        if info is not None and info.direct:
            return await self._download_direct(url, workdir, progress, cancel, info)

        try:
            return await asyncio.to_thread(
                self._download_blocking, url, option, workdir, progress, cancel
            )
        except errors.LeechError as exc:
            # بعضی لینک‌های عکس/آلبوم در مرحلهٔ دانلود هم «unsupported» می‌دهند.
            if exc.key == "unsupported" and gallery.available() and gallery.supports(url):
                log.info("yt-dlp download unsupported for %s; falling back to gallery-dl", url)
                return await self._download_gallery(
                    url, workdir, progress, cancel, info or MediaInfo(url=url, title="")
                )
            raise

    async def _download_gallery(
        self,
        url: str,
        workdir: Path,
        progress: Progress,
        cancel: asyncio.Event,
        info: MediaInfo,
    ) -> DownloadResult:
        result = await gallery.download(
            url,
            workdir,
            progress,
            cancel,
            title=info.title,
            cookie=self.cookie_for(url),
            proxy=self.cfg.proxy,
        )
        if not result.paths:
            raise errors.UnsupportedUrl("Gallery download produced no file")
        first = result.paths[0]
        size = result.size
        return DownloadResult(
            path=first,
            title=human.safe_filename(result.title or info.title or first.stem, 150),
            mime=_mime_for(first),
            size=size,
            is_audio=_mime_for(first).startswith("audio/"),
            parts=list(result.paths),
            gallery=True,
        )

    def _download_blocking(
        self,
        url: str,
        option: FormatOption,
        workdir: Path,
        progress: Progress,
        cancel: asyncio.Event,
    ) -> DownloadResult:
        progress.reset_download()
        target = extractor_url(url)
        finished: list[str] = []
        per_file_downloaded: dict[str, int] = {}
        downloaded_bytes_total = 0

        def hook(status: dict) -> None:
            nonlocal downloaded_bytes_total
            if cancel.is_set():
                raise errors.JobCancelled()
            if status.get("status") == "downloading":
                total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
                done = max(0, int(status.get("downloaded_bytes") or 0))
                info_dict = status.get("info_dict") or {}
                filename = status.get("tmpfilename") or status.get("filename") or ""
                format_id = info_dict.get("format_id") or ""
                file_key = f"{filename}|{format_id}" if filename or format_id else "default"
                previous = per_file_downloaded.get(file_key, 0)
                downloaded_bytes_total += done - previous if done >= previous else done
                per_file_downloaded[file_key] = done
                progress.stage = "downloading"
                progress.downloaded = done
                progress.downloaded_bytes_total = downloaded_bytes_total
                progress.total = int(total or 0)
                progress.speed = float(status.get("speed") or 0)
                progress.eta = status.get("eta")
                if total:
                    progress.pct = min(99.9, done * 100.0 / total)
            elif status.get("status") == "finished":
                progress.stage = "postprocessing"
                progress.pct = 100.0
                filename = status.get("filename")
                if filename:
                    finished.append(filename)

        opts = _base_opts(self.cfg, target, self.cookie_for(target))
        opts.update(
            {
                "format": option.selector,
                "outtmpl": {"default": str(workdir / "%(title).120B [%(id)s].%(ext)s")},
                "paths": {"home": str(workdir), "temp": str(workdir / ".tmp")},
                "progress_hooks": [hook],
                "noprogress": True,
                "postprocessors": [],
            }
        )
        if option.kind == "video":
            opts["merge_output_format"] = "mp4"
        elif option.code == "mp3":
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ]
        elif option.code == "m4a":
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "m4a", "preferredquality": "0"}
            ]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target, download=True)
        except DownloadError as exc:
            if cancel.is_set():
                raise errors.JobCancelled() from exc
            raise map_error(exc) from exc
        except errors.JobCancelled:
            raise
        except Exception as exc:  # noqa: BLE001
            if cancel.is_set():
                raise errors.JobCancelled() from exc
            log.exception("download failed for %s", url)
            raise map_error(exc) from exc

        if cancel.is_set():
            raise errors.JobCancelled()

        info = info if isinstance(info, dict) else {}
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
            info = entries[0] if entries else {}

        requested = info.get("requested_downloads") or []
        candidates = list(finished)
        for item in requested:
            if isinstance(item, dict) and item.get("filepath"):
                candidates.append(item["filepath"])

        output = _pick_output(workdir, candidates)
        if output is None:
            raise errors.UnsupportedUrl("Download produced no file")

        size = output.stat().st_size
        width = info.get("width")
        height = info.get("height")
        mime = _mime_for(output)
        is_audio = option.kind == "audio" or mime.startswith("audio/")

        return DownloadResult(
            path=output,
            title=human.safe_filename(info.get("title") or output.stem, 150),
            duration=int(info["duration"]) if info.get("duration") else None,
            width=int(width) if width else None,
            height=int(height) if height else None,
            mime=mime,
            size=size,
            is_audio=is_audio,
        )

    async def _download_direct(
        self,
        url: str,
        workdir: Path,
        progress: Progress,
        cancel: asyncio.Event,
        info: MediaInfo,
    ) -> DownloadResult:
        if not await urlcheck.is_safe_public_url(url):
            raise errors.UnsupportedUrl("Invalid or non-public download URL")
        progress.reset_download()
        name = human.safe_filename(urlcheck.filename_from_url(url, "download"), 120)
        if info.ext and not name.lower().endswith("." + info.ext.lower()):
            name = f"{name}.{info.ext}"
        dest = workdir / name

        timeout = aiohttp.ClientTimeout(total=None, sock_read=120, connect=30)
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
                async with safe_http_request(sess, "GET", url) as resp:
                    if not await urlcheck.is_safe_public_url(str(resp.url)):
                        raise errors.UnsupportedUrl("Unsafe redirect destination")
                    if resp.status == 404:
                        raise errors.ResourceNotFound("404")
                    if resp.status in (401, 403):
                        raise errors.AccessDenied(str(resp.status))
                    if resp.status >= 400:
                        raise errors.UnsupportedUrl(f"HTTP {resp.status}")
                    total = int(resp.headers.get("Content-Length") or 0)
                    progress.total = total
                    with dest.open("wb") as fh:
                        async for chunk in resp.content.iter_chunked(1024 * 512):
                            if cancel.is_set():
                                raise errors.JobCancelled()
                            fh.write(chunk)
                            progress.downloaded += len(chunk)
                            progress.downloaded_bytes_total += len(chunk)
                            if total:
                                progress.pct = min(99.9, progress.downloaded * 100.0 / total)
                    if not progress.downloaded or (total and progress.downloaded != total):
                        raise errors.IncompleteDownload(
                            f"expected {total} bytes, received {progress.downloaded}"
                        )
        except errors.LeechError:
            raise
        except (TimeoutError, aiohttp.ClientError, OSError) as exc:
            raise map_error(exc) from exc

        if cancel.is_set():
            raise errors.JobCancelled()

        progress.pct = 100.0
        size = dest.stat().st_size
        mime = _mime_for(dest)
        return DownloadResult(
            path=dest,
            title=human.safe_filename(dest.stem, 150),
            mime=info.mime or mime,
            size=size,
            is_audio=mime.startswith("audio/"),
        )
