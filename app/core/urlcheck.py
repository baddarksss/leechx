"""کار با لینک‌ها: استخراج، تشخیص لینک مستقیم، دامنه."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

MEDIA_EXTENSIONS = {
    # video
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".m4v", ".3gp", ".ts", ".mts", ".wmv", ".mpeg", ".mpg",
    # audio
    ".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus", ".wma", ".alac", ".aiff",
    # image
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    # archive / docs (پیش‌فرض برای لینک مستقیم)
    ".zip", ".rar", ".7z", ".pdf", ".epub", ".apk", ".exe", ".iso", ".tar", ".gz",
}

_ARCHIVE_HINTS = (".zip", ".rar", ".7z", ".tar", ".gz", ".iso")

_BAD_SCHEMES = ("tg://", "javascript:", "data:", "file:", "ftp://")


def extract_urls(text: str | None) -> list[str]:
    """همهٔ لینک‌های http(s) یک متن را برمی‌گرداند (بدون تکرار، حداکثر ۵)."""
    if not text:
        return []
    found = URL_RE.findall(text)
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in found:
        url = raw.rstrip(".,؛;:!?)]}\"'»")
        if not url or url in seen:
            continue
        if url.lower().startswith(_BAD_SCHEMES):
            continue
        seen.add(url)
        cleaned.append(url)
        if len(cleaned) >= 5:
            break
    return cleaned


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False


def host_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def path_extension(url: str) -> str:
    try:
        path = urlparse(url).path
    except ValueError:
        return ""
    return Path(unquote(path)).suffix.lower()


def looks_direct(url: str) -> bool:
    """آیا به‌احتمال زیاد یک فایل مستقیم است؟ (بدون درخواست شبکه)"""
    ext = path_extension(url)
    if ext in MEDIA_EXTENSIONS:
        return True
    return False


def looks_archive(url: str) -> bool:
    return path_extension(url) in _ARCHIVE_HINTS


def filename_from_url(url: str, fallback: str = "download") -> str:
    try:
        name = Path(unquote(urlparse(url).path)).name
    except ValueError:
        name = ""
    return name or fallback
