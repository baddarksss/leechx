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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import aiohttp
import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from app.config import Config
from app.core import errors, human, urlcheck
from app.services.formats import FormatOption

log = logging.getLogger("leechx.downloader")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

MEDIA_MIME_PREFIXES = ("video/", "audio/", "image/")


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

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()


@dataclass
class Progress:
    stage: str = "queued"      # queued | downloading | postprocessing | uploading | done | failed
    pct: float = 0.0
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    eta: int | None = None
    uploaded: int = 0
    note: str = ""

    def reset_download(self) -> None:
        self.stage = "downloading"
        self.pct = 0.0
        self.downloaded = 0
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


def _base_opts(cfg: Config, url: str) -> dict[str, Any]:
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
    cookie = _cookie_file(cfg, url)
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
    if "http error 404" in low or "not found" in low:
        return errors.UnsupportedUrl("Not found")
    if "http error 403" in low:
        return errors.UnsupportedUrl("Forbidden (403)")
    if "timed out" in low or "timeout" in low:
        return errors.UnsupportedUrl("Timeout")
    if isinstance(exc, errors.LeechError):
        return exc
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
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    # ── بررسی لینک ──────────────────────────────────────────
    async def probe(self, url: str, depth: int = 0) -> MediaInfo:
        if not urlcheck.is_valid_url(url):
            raise errors.UnsupportedUrl("Invalid URL")

        if urlcheck.looks_direct(url):
            direct = await self._probe_direct(url)
            if direct is not None:
                return direct

        try:
            return await asyncio.to_thread(self._probe_blocking, url)
        except errors.LeechError:
            raise
        except (DownloadError, ExtractorError) as exc:
            raise map_error(exc) from exc
        except Exception as exc:  # noqa: BLE001 — هر خطای دیگری هم باید به کاربر برسد
            log.exception("probe failed for %s", url)
            raise map_error(exc) from exc

    def _probe_blocking(self, url: str) -> MediaInfo:
        opts = _base_opts(self.cfg, url)
        opts.update({"skip_download": True, "extract_flat": False})
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

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
            url=info.get("webpage_url") or url,
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
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
                try:
                    async with sess.head(url, allow_redirects=True) as resp:
                        status = resp.status
                        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                        length = resp.headers.get("Content-Length")
                        final = str(resp.url)
                except aiohttp.ClientError:
                    status, ctype, length, final = 0, "", None, url
                if status >= 400 or (ctype and not ctype.startswith(MEDIA_MIME_PREFIXES) and "octet-stream" not in ctype):
                    return None
                if not ctype:
                    async with sess.get(url, allow_redirects=True, headers={"Range": "bytes=0-0"}) as resp:
                        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                        length = resp.headers.get("Content-Range", "").rpartition("/")[2] or length
                        final = str(resp.url)
        except (TimeoutError, aiohttp.ClientError, OSError):
            return None

        if not ctype.startswith(MEDIA_MIME_PREFIXES) and "octet-stream" not in ctype:
            return None

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

        if info is not None and info.direct:
            return await self._download_direct(url, workdir, progress, cancel, info)

        return await asyncio.to_thread(
            self._download_blocking, url, option, workdir, progress, cancel
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
        finished: list[str] = []

        def hook(status: dict) -> None:
            if cancel.is_set():
                raise errors.JobCancelled()
            if status.get("status") == "downloading":
                total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
                done = status.get("downloaded_bytes") or 0
                progress.stage = "downloading"
                progress.downloaded = int(done)
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

        opts = _base_opts(self.cfg, url)
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
                info = ydl.extract_info(url, download=True)
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

        if size > self.cfg.max_link_bytes and option.kind == "video":
            # سقف نهایی در زمان آپلود هم بررسی می‌شود؛ اینجا فقط برای پیام بهتر
            pass

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
        progress.reset_download()
        name = human.safe_filename(urlcheck.filename_from_url(url, "download"), 120)
        if info.ext and not name.lower().endswith("." + info.ext.lower()):
            name = f"{name}.{info.ext}"
        dest = workdir / name

        timeout = aiohttp.ClientTimeout(total=None, sock_read=120, connect=30)
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
                async with sess.get(url, allow_redirects=True) as resp:
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
                            if total:
                                progress.pct = min(99.9, progress.downloaded * 100.0 / total)
        except errors.LeechError:
            raise
        except (TimeoutError, aiohttp.ClientError, OSError) as exc:
            raise errors.UnsupportedUrl(str(exc)[:150]) from exc

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
