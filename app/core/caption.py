"""ساخت کپشن رسانه: عنوان + منبع + هشتگ.

کپشن بخشی از همان پیام رسانه است (نه پیام جدا) و سقف تلگرام ۱۰۲۴ کاراکتر
دارد؛ پس ابتدا دنباله (منبع/هشتگ) ساخته می‌شود و عنوان در فضای باقی‌مانده
کوتاه می‌شود.
"""
from __future__ import annotations

import re
from html import escape

from app.core import human
from app.core.urlcheck import host_of

CAPTION_LIMIT = 1024

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


def build_caption(
    title: str,
    source_url: str = "",
    kind: str = "video",
    extra_tags: str = "",
) -> str:
    """کپشن HTML آماده برای ``caption`` تلگرام."""
    tags = hashtags_for(source_url, kind, extra_tags)
    tail: list[str] = []
    if source_url:
        href = escape(source_url, quote=True)
        tail.append(f'<a href="{href}">🔗 Source</a>')
    if tags:
        tail.append(human.esc(tags))
    tail_text = "\n".join(tail)

    room = CAPTION_LIMIT - len(tail_text) - (1 if tail_text else 0)
    if room < 40 and source_url:
        # عنوان مهم‌تر از لینک منبع است؛ لینک را کنار می‌گذاریم.
        tail = [human.esc(tags)] if tags else []
        tail_text = "\n".join(tail)
        room = CAPTION_LIMIT - len(tail_text) - (1 if tail_text else 0)

    title_html = ""
    if title:
        if len(title) > max(1, room - 7):
            title = human.truncate(title, max(8, room - 7))
        title_html = f"<b>{human.esc(title)}</b>"

    body = f"{title_html}\n{tail_text}".strip()
    return body[:CAPTION_LIMIT]
