"""ساخت کپشن رسانه: عنوان، لینک‌شده به آدرس همان ویدیو.

کپشن بخشی از همان پیام رسانه است (نه پیام جدا) و سقف تلگرام ۱۰۲۴ کاراکتر
دارد. کل کپشن یک لینک است: با زدن روی عنوان، آدرس سایت باز می‌شود. هیچ متن
اضافه‌ای (برچسب «Source» یا هشتگ) به کپشن اضافه نمی‌شود.
"""
from __future__ import annotations

import re
from html import escape

from app.core import human
from app.core.urlcheck import host_of

CAPTION_LIMIT = 1024

# هزینهٔ تگ‌های ثابت اطراف عنوان: ``<a href="">`` + ``</a>`` + ``<b>`` + ``</b>``
_LINK_OVERHEAD = 22
_BOLD_OVERHEAD = 7

_BRAND_TAGS: tuple[tuple[str, str], ...] = (
    ("youtu.be", "YouTube"),
    ("youtube", "YouTube"),
    ("instagram", "Instagram"),
    ("tiktok", "TikTok"),
    ("twitter", "Twitter"),
    ("x.com", "Twitter"),
    ("facebook", "Facebook"),
    ("fb.watch", "Facebook"),
    ("soundcloud", "SoundCloud"),
    ("vimeo", "Vimeo"),
    ("twitch", "Twitch"),
    ("reddit", "Reddit"),
    ("spotify", "Spotify"),
    ("pinterest", "Pinterest"),
    ("snapchat", "Snapchat"),
    ("linkedin", "LinkedIn"),
    ("dailymotion", "Dailymotion"),
    ("bilibili", "Bilibili"),
    ("aparat", "Aparat"),
    ("vk.com", "VK"),
    ("ok.ru", "OK"),
)

_KIND_TAGS = {
    "video": "Video",
    "audio": "Audio",
    "image": "Photo",
    "photo": "Photo",
    "document": "File",
    "link": "File",
    "direct": "File",
}

_TAG_RE = re.compile(r"[^A-Za-z0-9_]")


def _clean_tag(tag: str) -> str:
    tag = (tag or "").strip()
    if not tag:
        return ""
    tag = tag if tag.startswith("#") else f"#{tag}"
    body = _TAG_RE.sub("", tag[1:])
    return f"#{body}" if body else ""


def hashtags_for(url: str | None, kind: str = "video", extra: str = "") -> str:
    """هشتگ‌های مناسب برای چسباندن به کپشن رسانه."""
    tags: list[str] = []
    host = host_of(url or "")
    if host:
        for needle, name in _BRAND_TAGS:
            if needle in host:
                tags.append(f"#{name}")
                break
        else:
            labels = [p for p in host.split(".") if p]
            base = labels[-2] if len(labels) >= 2 else labels[0]
            cleaned = _clean_tag(base)
            if cleaned:
                tags.append(cleaned)

        low = (url or "").lower()
        if "/shorts/" in low:
            tags.append("#Shorts")
        elif "/reel" in low:
            tags.append("#Reels")
        elif "tiktok.com" in host:
            tags.append("#Trending")

    kind_tag = _KIND_TAGS.get((kind or "").lower())
    if kind_tag:
        tags.append(f"#{kind_tag}")

    for piece in (extra or "").replace(",", " ").split():
        cleaned = _clean_tag(piece)
        if cleaned:
            tags.append(cleaned)

    unique: list[str] = []
    for tag in tags:
        if tag.lower() not in {t.lower() for t in unique}:
            unique.append(tag)
    return " ".join(unique)


def _fit_escaped(text: str, room: int) -> str:
    """متن خام را طوری کوتاه می‌کند که نسخهٔ escape‌شده در ``room`` جا شود.

    escape می‌تواند طول را زیاد کند (``&`` ← ``&amp;``)؛ کوتاه‌کردن بعد از
    escape کردن ممکن است یک entity را نصف کند و HTML تلگرام را خراب کند.
    """
    if room <= 1:
        return ""
    kept: list[str] = []
    used = 0
    for char in text:
        piece = human.esc(char)
        if used + len(piece) > room - 1:  # یک کاراکتر هم برای «…» نگه می‌داریم
            return "".join(kept).rstrip() + "…"
        kept.append(char)
        used += len(piece)
    return "".join(kept)


def build_caption(
    title: str,
    source_url: str = "",
    kind: str = "video",
    extra_tags: str = "",
) -> str:
    """کپشن HTML آماده برای ``caption`` تلگرام.

    عنوان بولد می‌شود و اگر آدرس منبع داشته باشیم، خودِ عنوان لینک همان آدرس
    است؛ پس با زدن روی کپشن، سایت باز می‌شود. ``kind`` و ``extra_tags`` برای
    سازگاری با فراخوانی‌های قبلی نگه داشته شده‌اند و هشتگی اضافه نمی‌کنند.
    """
    label = (title or "").strip() or host_of(source_url or "") or "media"
    if not source_url:
        return f"<b>{human.esc(_fit_escaped(label, CAPTION_LIMIT - _BOLD_OVERHEAD))}</b>"

    href = escape(source_url, quote=True)
    room = CAPTION_LIMIT - len(href) - _LINK_OVERHEAD
    if room < 8:
        # آدرس به‌تنهایی تقریباً کل سقف را پر می‌کند؛ لینک را کنار می‌گذاریم
        # تا عنوان قابل خواندن بماند.
        return f"<b>{human.esc(_fit_escaped(label, CAPTION_LIMIT - _BOLD_OVERHEAD))}</b>"
    fitted = human.esc(_fit_escaped(label, room))
    return f'<a href="{href}"><b>{fitted}</b></a>'

