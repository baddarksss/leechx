"""کمکی‌های نمایش اعداد/زمان و نام فایل."""
from __future__ import annotations

import re

_UNITS = ("B", "KB", "MB", "GB", "TB")


def human_bytes(num: float | int | None) -> str:
    if not num or num < 0:
        return "0 B"
    value = float(num)
    for unit in _UNITS:
        if value < 1024 or unit == _UNITS[-1]:
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}".replace(".0 ", " ")
        value /= 1024
    return f"{value:.1f} TB"


def human_speed(bps: float | None) -> str:
    if not bps:
        return "—"
    return f"{human_bytes(bps)}/s"


def human_duration(seconds: float | int | None) -> str:
    if not seconds or seconds < 0:
        return "—"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def human_eta(seconds: float | int | None) -> str:
    if seconds is None or seconds < 0 or seconds > 86400 * 7:
        return "—"
    return human_duration(seconds)


def progress_bar(pct: float, width: int = 10) -> str:
    """Green squares for completed steps and neutral squares for the remainder."""
    pct = max(0.0, min(100.0, float(pct or 0)))
    filled = int(width * pct / 100 + 0.5)
    cells = ["🟩"] * filled + ["⬜"] * (width - filled)
    return " ".join(cells)


_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SPACES = re.compile(r"\s+")


def safe_filename(name: str, max_len: int = 120) -> str:
    name = (name or "file").strip()
    name = _ILLEGAL.sub("_", name)
    name = _SPACES.sub(" ", name).strip(" .")
    if not name:
        name = "file"
    if len(name) > max_len:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 8:
            keep = max_len - len(ext) - 1
            name = stem[:keep] + "." + ext
        else:
            name = name[:max_len]
    return name


def truncate(text: str | None, limit: int = 900) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def esc(text: str | None) -> str:
    """فرار برای HTML تلگرام."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on", "بله")


def parse_int(value: str | None, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def parse_float(value: str | None, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default
