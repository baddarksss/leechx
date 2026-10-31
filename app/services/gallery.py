"""موتور دانلود گالری/آلبوم با gallery-dl.

yt-dlp برای ویدیو ساخته شده است؛ سایت‌های عکس و آلبوم (اینستاگرام، پینترست،
توییتر، Pixiv، Danbooru، Kemono و بخشی از سایت‌های بزرگسال) را نمی‌فهمد.
``gallery-dl`` دقیقاً همین جا را پر می‌کند.

این ماژول سه کار می‌کند:

* **تشخیص پشتیبانی** با ``gallery_dl.extractor.find`` (بدون شبکه).
* **بررسی سریع** لینک و ساختن عنوان نمایشی.
* **دانلود** با اجرای gallery-dl در یک subprocess؛ این‌طور می‌توانیم لغو،
  مهلت زمانی و پیشرفت را بدون قفل‌کردن event loop مدیریت کنیم.

اگر بسته نصب نباشد، همهٔ توابع بی‌صدا «پشتیبانی نمی‌شود» برمی‌گردانند تا
بقیهٔ ربات مثل قبل کار کند.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.core import errors, human

log = logging.getLogger("leechx.gallery")

IMAGE_EXT = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff",
    ".avif", ".heic", ".jxl",
}
VIDEO_EXT = {
    ".mp4", ".m4v", ".mov", ".webm", ".mkv", ".ts", ".avi", ".flv", ".wmv",
}
AUDIO_EXT = {".mp3", ".m4a", ".opus", ".ogg", ".flac", ".wav"}
MEDIA_EXT = IMAGE_EXT | VIDEO_EXT | AUDIO_EXT

SKIP_SUFFIX = {".part", ".tmp", ".ytdl", ".json", ".txt", ".db", ".sqlite"}
SKIP_DIRS = {"__pycache__", ".git"}

DEFAULT_MAX_ITEMS = 50
MAX_ITEMS_LIMIT = 200
DOWNLOAD_TIMEOUT = 1800.0
POLL_INTERVAL = 0.6

try:  # نبودِ بسته نباید ربات را از کار بیندازد
    from gallery_dl import extractor as _gdl_extractor
    from gallery_dl import version as _gdl_version

    AVAILABLE = True
except Exception:  # noqa: BLE001
    _gdl_extractor = None
    _gdl_version = None
    AVAILABLE = False


def available() -> bool:
    """آیا بستهٔ gallery-dl نصب است؟"""
    return AVAILABLE


def version() -> str:
    if not AVAILABLE:
        return "not installed"
    return str(getattr(_gdl_version, "__version__", "") or "installed")


def max_items() -> int:
    raw = os.environ.get("GALLERY_MAX_ITEMS", "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_ITEMS
    return max(1, min(MAX_ITEMS_LIMIT, value))


def extractor_name(url: str) -> str:
    """نام دستهٔ اکسترکتور (مثل ``instagram``) یا رشتهٔ خالی."""
    if not AVAILABLE or not url:
        return ""
    try:
        found = _gdl_extractor.find(url)
    except Exception:  # noqa: BLE001 — الگوی بد نباید خطا بدهد
        return ""
    if found is None:
        return ""
    return str(
        getattr(found, "category", "")
        or getattr(found, "basecategory", "")
        or type(found).__name__
    ).lower()


def supports(url: str) -> bool:
    """آیا gallery-dl این لینک را می‌شناسد؟"""
    return bool(extractor_name(url))


def display_title(url: str) -> str:
    """عنوان نمایشی سبک از خود URL (بدون درخواست شبکه)."""
    try:
        parts = [p for p in urlsplit(url).path.split("/") if p]
        raw = unquote(parts[-1]) if parts else urlsplit(url).netloc
    except Exception:  # noqa: BLE001
        raw = url
    raw = re.sub(r"\.(jpe?g|png|webp|gif|mp4|m4v|mov|webm)$", "", raw, flags=re.I)
    return human.safe_filename(raw or "gallery", 120)


@dataclass
class GalleryResult:
    paths: list[Path] = field(default_factory=list)
    title: str = ""
    extractor: str = ""

    @property
    def size(self) -> int:
        return sum(path.stat().st_size for path in self.paths if path.exists())


def _natural_key(path: Path) -> tuple:
    parts = re.split(r"(\d+)", path.name.lower())
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in parts)


def _collect(dest: Path) -> list[Path]:
    found: list[Path] = []
    if not dest.exists():
        return found
    for path in dest.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIX:
            continue
        if path.suffix.lower() not in MEDIA_EXT:
            continue
        if path.stat().st_size <= 0:
            continue
        found.append(path)
    found.sort(key=_natural_key)
    return found


def _build_command(
    url: str,
    dest: Path,
    *,
    cookie: Path | None,
    proxy: str,
    limit: int,
) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "gallery_dl",
        "-D",
        str(dest),
        "-d",
        str(dest),
        "-q",
        "--config-ignore",
        "--no-mtime",
        "--no-part",
        "-R",
        "2",
        "--http-timeout",
        "30",
        "--range",
        f"1-{limit}",
    ]
    if cookie is not None:
        cmd += ["-C", str(cookie)]
    if proxy:
        cmd += ["--proxy", proxy]
    cmd.append(url)
    return cmd


def _map_failure(output: str) -> errors.LeechError:
    low = (output or "").lower()
    if "404" in low or "not found" in low:
        return errors.ResourceNotFound("404")
    if "403" in low or "forbidden" in low:
        return errors.AccessDenied("403")
    if "401" in low or "unauthorized" in low or "login" in low or "cookies" in low:
        return errors.UnsupportedUrl("Login or cookies required")
    if "timed out" in low or "timeout" in low:
        return errors.DownloadTimeout("gallery-dl timeout")
    return errors.UnsupportedUrl((output or "gallery-dl failed").strip().splitlines()[-1][:200])


async def download(
    url: str,
    workdir: Path,
    progress,
    cancel: asyncio.Event,
    *,
    title: str = "",
    cookie: Path | None = None,
    proxy: str = "",
) -> GalleryResult:
    """دانلود همهٔ فایل‌های یک لینک گالری در ``workdir``.

    فایل‌ها تا سقف ``GALLERY_MAX_ITEMS`` (پیش‌فرض ۵۰) دانلود می‌شوند تا یک
    پروفایل با هزاران عکس سرور را پر نکند.
    """
    if not AVAILABLE:
        raise errors.UnsupportedUrl("gallery-dl is not installed")

    workdir.mkdir(parents=True, exist_ok=True)
    limit = max_items()
    cmd = _build_command(url, workdir, cookie=cookie, proxy=proxy, limit=limit)
    log.info("gallery-dl start: %s (limit=%d, cookie=%s)", url, limit, bool(cookie))

    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    progress.stage = "downloading"
    progress.pct = 0.0
    progress.downloaded = 0
    progress.downloaded_bytes_total = 0
    progress.total = 0
    progress.speed = 0.0
    progress.eta = None

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(workdir),
            env=env,
        )
    except OSError as exc:
        raise errors.UnsupportedUrl(f"gallery-dl could not start: {exc}") from exc

    started = time.monotonic()
    last_count = 0
    try:
        while True:
            if cancel.is_set():
                raise errors.JobCancelled()
            if time.monotonic() - started > DOWNLOAD_TIMEOUT:
                raise errors.DownloadTimeout("gallery-dl took too long")
            try:
                await asyncio.wait_for(proc.wait(), timeout=POLL_INTERVAL)
                break
            except TimeoutError:
                files = _collect(workdir)
                if len(files) != last_count:
                    last_count = len(files)
                    progress.downloaded = sum(p.stat().st_size for p in files)
                    progress.downloaded_bytes_total = progress.downloaded
                    # تعداد فایل مبنای درصد است؛ حجم کل از قبل معلوم نیست.
                    progress.pct = min(95.0, last_count * 100.0 / limit)
                    progress.stage = "downloading"

            if proc.returncode is not None:
                break

        output = b""
        if proc.stdout is not None:
            try:
                output = await asyncio.wait_for(proc.stdout.read(), timeout=10)
            except (TimeoutError, OSError):
                output = b""
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass

    if cancel.is_set():
        raise errors.JobCancelled()

    text = output.decode("utf-8", "replace").strip()
    files = _collect(workdir)
    if not files:
        raise _map_failure(text or f"gallery-dl exited with {proc.returncode}")

    progress.pct = 100.0
    progress.downloaded = sum(p.stat().st_size for p in files)
    progress.downloaded_bytes_total = progress.downloaded
    log.info("gallery-dl done: %d files, %d bytes", len(files), progress.downloaded)
    return GalleryResult(
        paths=files,
        title=human.safe_filename(title or display_title(url), 150),
        extractor=extractor_name(url),
    )
