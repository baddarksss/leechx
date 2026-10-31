"""لایهٔ دانلود — پوششی نازک و کنترل‌شده روی yt-dlp و دانلود مستقیم HTTP.

نکته‌های مهم:
* همهٔ کارهای سنگین در ترد جدا اجرا می‌شوند تا حلقهٔ asyncio قفل نشود.
* هر کار پوشهٔ مخصوص خودش را دارد و بعد از آپلود پاک می‌شود.
* لغو کار با یک ``asyncio.Event`` انجام می‌شود؛ هوک پیشرفت استثنا می‌دهد
  و yt-dlp دانلود را متوقف می‌کند.
"""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import aiohttp
import yt_dlp
from yt_dlp.extractor.generic import GenericIE
from yt_dlp.utils import DownloadError, ExtractorError, js_to_json, parse_resolution

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
_EPORNER_SLUG_TITLE = re.compile(
    r"^https?://(?:www\.)?eporner\.com/video-[A-Za-z0-9]+/([A-Za-z0-9-]+)/?",
    re.IGNORECASE,
)

# ── VK ────────────────────────────────────────────────────────
# yt-dlp sometimes returns an empty playlist for `wall` posts and does not
# recognize the `vk.ru` domain at all. We read the wall page with a crawler
# user-agent (which gets the OG tags instead of a captcha), find the real video
# id in `video_ext.php?...oid=...&id=...`, and hand that video URL to yt-dlp.
_VK_WALL = re.compile(
    r"^https?://(?:(?:m|new)\.)?vk(?:video)?\.(?:com|ru)/wall(?P<id>-?\d+_\d+)",
    re.IGNORECASE,
)
_VK_VIDEO = re.compile(
    r"^https?://(?:(?:m|new)\.)?vk(?:video)?\.(?:com|ru)/(?:video|clip)(?P<id>-?\d+_\d+)",
    re.IGNORECASE,
)
_VK_WALL_RU = re.compile(r"^(https?://)(?:(?:m|new)\.)?vk\.ru/wall", re.IGNORECASE)
_CRAWLER_UAS = (
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Twitterbot/1.0",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
)

# TNAFlix serves different HTML per locale (`/es/...`) and the generic extractor
# loses the real resolutions there; the canonical path is `/...`.
_TNAFLIX_LOCALE = re.compile(
    r"^(https?://(?:www\.)?tnaflix\.com)/(?:en|es|de|fr|it|pt|pl|ru|ja|ko|zh|nl|tr|ar|hi|id|th|vi|sv|cs|el|hu|ro|uk|da|fi|no)/",
    re.IGNORECASE,
)

# Resolution hidden in the file name (`...-1080p.mp4`).
_HEIGHT_HINT = re.compile(r"(?<![\d.])(\d{3,4})p(?![\d])", re.IGNORECASE)
_M3U8_URL = re.compile(r"https?://[^\"'\s<>\\]+\.m3u8[^\"'\s<>\\]*", re.IGNORECASE)
_MANIFEST_SUFFIXES = (".m3u8", ".mpd")
_MANIFEST_PROTOCOLS = ("m3u8", "m3u8_native", "dash", "http_dash_segments", "http_dash")
# Aggregators that label the file host next to the player (pornhoarder: "hosted on doodstream").
# DoodStream/playmogo players sit behind an interactive Turnstile widget, so the
# media URL cannot be obtained without a browser session (see 5.6.8 notes).
_CAPTCHA_HOST = re.compile(
    r"hosted on\s*(?:<[^>]+>\s*)?(?:doodstream|dood|playmogo)"
    r"|playmogo\.com/e/|/pass_md5/|doodstream\.com/e/",
    re.IGNORECASE,
)


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def vk_wall_url(url: str) -> str | None:
    """Canonical `https://vk.com/wall...` for a VK wall link, if it is one."""
    match = _VK_WALL.match(url or "")
    if not match:
        return None
    return f"https://vk.com/wall{match.group('id')}"


def vk_video_url(url: str) -> str | None:
    """Canonical `https://vk.com/video...` for a VK video link, if it is one."""
    match = _VK_VIDEO.match(url or "")
    if not match:
        return None
    return f"https://vk.com/video{match.group('id')}"


def vk_video_ref(html: str) -> tuple[str, str] | None:
    """`(owner_id, video_id)` from the wall page HTML (OG/embed tags)."""
    for raw in re.findall(r"video_ext\.php\?[^\"'\s<>]+", html or "", re.IGNORECASE):
        query = parse_qs(urlparse(raw.replace("&amp;", "&")).query)
        owner = (query.get("oid") or [""])[0]
        video = (query.get("id") or [""])[0]
        if re.fullmatch(r"-?\d+", owner) and video.isdigit():
            return owner, video
    match = re.search(r"\bvideo(-?\d+_\d+)\b", html or "")
    if match:
        owner, _, video = match.group(1).partition("_")
        return owner, video
    return None


def extractor_url(url: str) -> str:
    """Extractor-friendly URL: fixes embed-only sites and locale/alias paths."""
    clean = (url or "").split("#", 1)[0].strip()
    clean = _VK_WALL_RU.sub(r"\1vk.com/wall", clean)
    clean = _TNAFLIX_LOCALE.sub(r"\1/", clean)
    match = _EMBED_VIDEO.match(clean)
    if match:
        return f"https://www.eporner.com/embed/{match.group(1)}/"
    return clean


def is_eporner_extractor(extractor: str | None) -> bool:
    return (extractor or "").casefold().startswith(("eporner", "gallery-dl:eporner"))


def fallback_title(url: str, title: str | None) -> str:
    """صفحهٔ امبد عنوان ندارد؛ از اسلاگ آدرس عنوان خوانا می‌سازیم."""
    clean = (title or "").strip()
    if clean and clean.casefold() not in {"untitled", "media", "video"}:
        return clean
    match = _EPORNER_SLUG_TITLE.match(url or "")
    if match:
        slug = match.group(1).replace("-", " ").strip()
        if slug:
            return slug[:1].upper() + slug[1:]
    return clean or "media"


def _is_av1_format(fmt: dict) -> bool:
    return (fmt.get("vcodec") or "").casefold().startswith(("av01", "av1"))


def with_av1_variants(formats: list[dict] | None) -> list[dict]:
    """نسخه‌های AV1 اپورنر را به لیست فرمت‌ها اضافه می‌کند.

    سایت این نسخه‌ها را روی CDN دارد (``...-av1.mp4``) ولی در JSON امبد
    فهرست نمی‌کند؛ پس از روی نسخهٔ MP4 هر ارتفاع می‌سازیم.
    """
    formats = [f for f in (formats or []) if isinstance(f, dict)]
    existing = {int(f.get("height") or 0) for f in formats if _is_av1_format(f)}
    out = list(formats)
    for fmt in formats:
        if _is_av1_format(fmt):
            continue
        try:
            height = int(fmt.get("height") or 0)
        except (TypeError, ValueError):
            height = 0
        src = str(fmt.get("url") or "")
        if height <= 0 or height in existing or not src.lower().endswith(".mp4"):
            continue
        av1 = dict(fmt)
        av1["format_id"] = f"{fmt.get('format_id') or height}-av1"
        av1["url"] = src[:-4] + "-av1.mp4"
        av1["vcodec"] = "av01.0.08M.08"
        av1["format_note"] = f"{fmt.get('format_note') or f'{height}p'} (AV1)"
        av1["filesize"] = None
        av1["filesize_approx"] = None
        av1["synthetic"] = True
        out.append(av1)
        existing.add(height)
    return out


def _is_manifest(fmt: dict) -> bool:
    """Is this format an HLS/DASH manifest? (HEAD would not return a size)"""
    protocol = str(fmt.get("protocol") or "").casefold()
    if protocol.startswith(_MANIFEST_PROTOCOLS):
        return True
    path = str(fmt.get("url") or "").casefold().split("?", 1)[0]
    return path.endswith(_MANIFEST_SUFFIXES)


def infer_heights(formats: list[dict] | None) -> list[dict]:
    """Fill missing resolutions from the file name / note / format id.

    Some extractors (e.g. TNAFlix through the generic extractor) return formats
    without a height while the URL clearly says `...-1080p.mp4`; without this the
    menu collapses them into `0 MP4`, `1 MP4`, ...
    """
    for fmt in formats or []:
        if not isinstance(fmt, dict):
            continue
        if str(fmt.get("vcodec") or "").casefold() == "none":
            continue
        if _int_or_zero(fmt.get("height")) > 0:
            continue
        hint = " ".join(str(fmt.get(key) or "") for key in ("url", "format_note", "format_id"))
        match = _HEIGHT_HINT.search(hint)
        if not match:
            continue
        height = int(match.group(1))
        if not 100 <= height <= 4320:
            continue
        fmt["height"] = height
        if _int_or_zero(fmt.get("width")) <= 0:
            fmt["width"] = round(height * 16 / 9)
    return formats


# ─── KVS (Kernel Video Sharing) ───────────────────────────────
# بعضی سایت‌های KVS نام متغیر flashvars را تصادفی می‌کنند و اکسترکتور
# عمومی yt-dlp («Unable to extract flashvars») شکست می‌خورد. اینجا خودمان
# همان آبجکت را پیدا و آدرس‌ها را با الگوریتم رسمی KVS باز می‌کنیم.

def is_kvs_error(reason: str | None) -> bool:
    text = (reason or "").casefold()
    return any(marker in text for marker in ("flashvars", "kt_player", "kvs player"))


def _js_objects(html: str):
    """همهٔ آبجکت‌های ``var x = {...};`` را با پرانتزهای متوازن برمی‌گرداند."""
    for match in re.finditer(r"var\s+(\w+)\s*=\s*\{", html):
        start = match.end() - 1
        depth = 0
        quote = ""
        escaped = False
        for index in range(start, len(html)):
            char = html[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
                continue
            if char in "'\"":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    yield match.group(1), html[start:index + 1]
                    break


def _kvs_flashvars(html: str) -> dict | None:
    for _name, block in _js_objects(html):
        if "video_url" not in block or "license_code" not in block:
            continue
        try:
            data = json.loads(js_to_json(block))
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get("video_url") and data.get("license_code"):
            return data
    return None


def _duration_seconds(raw: str | None) -> int | None:
    text = (raw or "").strip()
    if text.isdigit():
        return int(text) or None
    parts = text.split(":")
    if 2 <= len(parts) <= 3 and all(p.isdigit() for p in parts):
        seconds = 0
        for part in parts:
            seconds = seconds * 60 + int(part)
        return seconds or None
    return None


def _html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def parse_kvs(html: str, url: str) -> MediaInfo | None:
    """صفحهٔ KVS را به MediaInfo تبدیل می‌کند؛ اگر KVS نبود ``None``."""
    flashvars = _kvs_flashvars(html)
    if flashvars is None:
        return None

    license_code = str(flashvars.get("license_code") or "")
    formats: list[dict] = []
    for key, value in flashvars.items():
        if not re.fullmatch(r"video_(?:url|alt_url\d*)", key):
            continue
        if not isinstance(value, str) or "/get_file/" not in value:
            continue
        real = GenericIE._kvs_get_real_url(value, license_code)
        label = str(flashvars.get(f"{key}_text") or key)
        resolution = parse_resolution(label) or parse_resolution(value) or {}
        fmt: dict = {
            "format_id": label,
            "url": urljoin(url, real),
            "ext": "mp4",
            "vcodec": None,
            "http_headers": {"Referer": url},
            "kvs": True,
            **resolution,
        }
        formats.append(fmt)
    if not formats:
        return None

    formats.sort(key=lambda f: (int(f.get("height") or 0), f["format_id"]))
    thumbnail = str(flashvars.get("preview_url") or "")
    og_image = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html)
    if og_image:
        thumbnail = og_image.group(1)
    duration = _duration_seconds(str(flashvars.get("duration") or ""))
    if duration is None:
        duration = _duration_seconds(
            (re.search(r"Duration:\s*(?:<[^>]+>)?\s*([\d:]+)", html) or [None, ""])[1]
        )

    return MediaInfo(
        url=url,
        title=human.safe_filename(
            str(flashvars.get("video_title") or "").strip() or _html_title(html) or "media",
            150,
        ),
        duration=duration,
        thumbnail=urljoin(url, thumbnail) if thumbnail else None,
        extractor="KVS",
        formats=formats,
        ext="mp4",
    )


def _kvs_pick(formats: list[dict], option: FormatOption) -> dict | None:
    """فرمت KVS متناظر با گزینهٔ منو را پیدا می‌کند (یا بهترین را)."""
    usable = [f for f in (formats or []) if f.get("url")]
    if not usable:
        return None
    if option.selector:
        for fmt in usable:
            if fmt.get("format_id") == option.selector:
                return fmt
    if option.height:
        same = [f for f in usable if int(f.get("height") or 0) == option.height]
        if same:
            return same[-1]
    return max(usable, key=lambda f: int(f.get("height") or 0))


# ─── HLS (صفحهٔ کلادفلری + امبد pack‌شده) ─────────────────────
# بعضی سایت‌های تیوب پشت «چالش مدیریت‌شدهٔ Cloudflare» هستند و ویدیو داخل
# iframe امبدی با جاوااسکریپت فشرده‌شده (Dean Edwards packer) قرار دارد.
# اینجا صفحه را با byparr باز می‌کنیم، پک را خودمان باز می‌کنیم و HLS را
# بومی دانلود می‌کنیم؛ چون پلی‌لیست‌ها/سگمنت‌ها پسوندهای غیررسمی دارند
# (مثل ``.txt`` و ``.woff2``) و yt-dlp آن‌ها را نمی‌فهمد.

_PACKED_JS = re.compile(
    r"eval\(function\(p,a,c,k,e,d\)\{.*?\}\('(.*?)',(\d+),(\d+),'(.*?)'\.split\('\|'\)",
    re.S,
)
_HLS_LINK = re.compile(r'"(hls\d*)"\s*:\s*"([^"]+)"')
_IFRAME_SRC = re.compile(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", re.I)
_PACK_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_CF_MARKERS = ("cloudflare", "challenge", "just a moment", "cf-mitigated", "http error 403")
# CDN این سایت‌ها هر اتصال را throttle می‌کنند؛ چند اتصال موازی سرعت را
# چند برابر می‌کند (اندازه‌گیری: ۰.۶MB/s تک‌اتصال ← ~۲۰MB/s با ۶ اتصال).
HLS_CONCURRENCY = 6


def looks_like_cf_block(exc: BaseException) -> bool:
    """آیا این خطا بوی چالش Cloudflare می‌دهد؟ (۴۰۳ یا صفحهٔ challenge)"""
    if getattr(exc, "key", "") == "access_denied":
        return True
    text = f"{getattr(exc, 'reason', '')} {exc}".casefold()
    return any(marker in text for marker in _CF_MARKERS)


def _unbase(text: str, base: int) -> int | None:
    value = 0
    for char in text:
        try:
            digit = _PACK_ALPHABET.index(char)
        except ValueError:
            return None
        if digit >= base:
            return None
        value = value * base + digit
    return value


def unpack_packed_js(html: str) -> str | None:
    """بدنهٔ ``eval(function(p,a,c,k,e,d)…`` را باز می‌کند (بدون اجرای JS)."""
    match = _PACKED_JS.search(html or "")
    if not match:
        return None
    payload = match.group(1).replace("\\'", "'")
    base = int(match.group(2))
    words = [word.replace("\\'", "'") for word in match.group(4).split("|")]

    def replace(token: re.Match) -> str:
        index = _unbase(token.group(0), base)
        if index is None or index >= len(words) or not words[index]:
            return token.group(0)
        return words[index]

    return re.sub(r"\b[0-9a-zA-Z]+\b", replace, payload)


def hls_links(html: str, base_url: str = "") -> dict[str, str]:
    """دیکشنری ``{"hls3": "https://…"}`` را از صفحهٔ امبد بیرون می‌کشد."""
    text = unpack_packed_js(html) or html or ""
    return {
        key: (value if value.startswith(("http://", "https://")) else urljoin(base_url, value))
        for key, value in _HLS_LINK.findall(text)
    }


def iframe_sources(html: str) -> list[str]:
    """آدرس‌های قابل‌دریافت iframeها؛ ad/recaptcha/data کنار گذاشته می‌شوند."""
    out: list[str] = []
    for raw in _IFRAME_SRC.findall(html or ""):
        src = raw.replace("&amp;", "&").replace("&#038;", "&").strip()
        low = src.casefold()
        if not src or src in out:
            continue
        if low.startswith(("javascript:", "data:", "about:")) or "recaptcha" in low:
            continue
        if not low.startswith(("http://", "https://", "//")):
            continue
        out.append(src)
    return out


def hls_master_variants(text: str, base_url: str = "") -> list[dict]:
    """واریانت‌های پلی‌لیست مادر HLS (ارتفاع/عرض/نرخ بیت/کدک)."""
    lines = (text or "").splitlines()
    out: list[dict] = []
    for index, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF:"):
            continue
        attrs = {
            key.upper(): value.strip().strip('"')
            for key, value in re.findall(r"([A-Za-z0-9-]+)=(\"[^\"]*\"|[^,]*)", line[len("#EXT-X-STREAM-INF:"):])
        }
        uri = next(
            (item.strip() for item in lines[index + 1:] if item.strip() and not item.startswith("#")),
            "",
        )
        if not uri:
            continue
        width = height = 0
        resolution = attrs.get("RESOLUTION", "")
        if "x" in resolution:
            raw_width, _, raw_height = resolution.partition("x")
            width = int(raw_width) if raw_width.isdigit() else 0
            height = int(raw_height) if raw_height.isdigit() else 0
        bandwidth = attrs.get("BANDWIDTH", "")
        try:
            fps = int(float(attrs.get("FRAME-RATE") or 0))
        except (TypeError, ValueError):
            fps = 0
        out.append(
            {
                "url": urljoin(base_url, uri) if base_url else uri,
                "height": height,
                "width": width,
                "fps": fps,
                "bandwidth": int(bandwidth) if bandwidth.isdigit() else 0,
                "codecs": attrs.get("CODECS", ""),
            }
        )
    return out


def hls_segments(text: str, base_url: str = "") -> list[str]:
    """آدرس مطلق همهٔ سگمنت‌های یک پلی‌لیست رسانه."""
    return [
        urljoin(base_url, line.strip()) if base_url else line.strip()
        for line in (text or "").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def m3u8_candidates(html: str, base_url: str = "") -> list[str]:
    """Find `.m3u8` links on a page, even inside packed JavaScript.

    MissAV keeps the master playlist inside a Dean-Edwards packed script
    (`e='8://7.6/5-4-3-2-1/d.0'`), so plain URL regexes find nothing. The
    playlist is unpacked first; entries containing `playlist` are preferred.
    """
    text = unpack_packed_js(html) or html or ""
    text = text.replace("\\/", "/").replace("&amp;", "&")
    out: list[str] = []
    sources = [text, (html or "").replace("\\/", "/").replace("&amp;", "&")]
    for source in sources:
        for raw in _M3U8_URL.findall(source):
            url = raw if raw.startswith(("http://", "https://")) else urljoin(base_url, raw)
            if url not in out:
                out.append(url)
    out.sort(key=lambda item: (0 if "playlist" in item.casefold() else 1, len(item)))
    return out


def hls_manifest_variants(text: str, base_url: str = "") -> list[dict]:
    """Variants of a manifest; a media-only playlist becomes one variant."""
    variants = hls_master_variants(text, base_url)
    if variants:
        return variants
    if "#EXTINF" in (text or ""):
        return [{"url": base_url, "height": 0, "width": 0, "fps": 0, "bandwidth": 0, "codecs": ""}]
    return []


def pick_hls_variant(variants: list[dict], height: int = 0) -> dict | None:
    """واریانت متناظر ارتفاع انتخاب‌شده (یا بهترین موجود)."""
    usable = [item for item in (variants or []) if item.get("url")]
    if not usable:
        return None
    if height:
        exact = [item for item in usable if int(item.get("height") or 0) == height]
        if exact:
            return exact[0]
        lower = [item for item in usable if 0 < int(item.get("height") or 0) <= height]
        if lower:
            return max(lower, key=lambda item: int(item.get("height") or 0))
    return max(usable, key=lambda item: (int(item.get("height") or 0), int(item.get("bandwidth") or 0)))


def _hls_formats(variants: list[dict]) -> list[dict]:
    """واریانت‌های HLS را به فرمت‌های سازگار با منوی کیفیت تبدیل می‌کند."""
    formats: list[dict] = []
    for variant in variants:
        height = int(variant.get("height") or 0)
        codecs = str(variant.get("codecs") or "")
        vcodec = next(
            (codec.strip() for codec in codecs.split(",")
             if codec.strip().lower().startswith(("avc", "hvc", "hev", "av01", "vp0", "vp9"))),
            "",
        )
        bandwidth = int(variant.get("bandwidth") or 0)
        formats.append(
            {
                "format_id": f"hls-{height or bandwidth}",
                "url": variant["url"],
                "ext": "mp4",
                "height": height,
                "width": int(variant.get("width") or 0),
                "fps": int(variant.get("fps") or 0),
                "tbr": round(bandwidth / 1000) if bandwidth else None,
                "filesize_approx": variant.get("filesize_approx"),
                "vcodec": vcodec or None,
                "acodec": "mp4a.40.2" if "mp4a" in codecs.lower() else None,
                "hls": True,
            }
        )
    formats.sort(key=lambda fmt: int(fmt.get("height") or 0))
    return formats


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


def _variant_filename(title: str, option: FormatOption) -> str:
    """نام فایل برای نسخهٔ کدک‌دار؛ مثلاً ``Title [1080p AV1].mp4``."""
    stem = human.safe_filename(title or "media", 100)
    codec = (option.codec or "").upper()
    tag = f"{option.height}p" if option.height else ""
    if codec:
        tag = f"{tag} {codec}".strip()
    ext = (option.ext or "mp4").lstrip(".")
    return f"{stem} [{tag}].{ext}" if tag else f"{stem}.{ext}"


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
    # صفحهٔ امبد (iframe) برای سایت‌های پشت Cloudflare با HLS فشرده‌شده
    embed_url: str = ""


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
            info = await asyncio.to_thread(self._probe_blocking, url)
        except errors.LeechError as exc:
            # VK wall posts must be resolved to their real video URL first;
            # gallery-dl would only return the post's photos.
            vk = await self._vk_fallback(url, exc)
            if vk is not None:
                return vk
            # yt-dlp ویدیو-محور است؛ اگر سایت عکس/آلبوم باشد gallery-dl را امتحان کن.
            if gallery.available() and gallery.supports(url):
                log.info("yt-dlp probe failed (%s) for %s; trying gallery-dl", exc.key, url)
                return await asyncio.to_thread(self._probe_gallery, url)
            kvs = await self._kvs_fallback(url, exc)
            if kvs is not None:
                return kvs
            cf = await self._cf_fallback(url, exc)
            if cf is not None:
                return cf
            raise
        except (DownloadError, ExtractorError) as exc:
            mapped = map_error(exc)
            vk = await self._vk_fallback(url, mapped)
            if vk is not None:
                return vk
            kvs = await self._kvs_fallback(url, mapped)
            if kvs is not None:
                return kvs
            cf = await self._cf_fallback(url, mapped)
            if cf is not None:
                return cf
            raise mapped from exc
        except Exception as exc:  # noqa: BLE001 — هر خطای دیگری هم باید به کاربر برسد
            log.exception("probe failed for %s", url)
            raise map_error(exc) from exc

        return await self._enrich(info)

    async def _enrich(self, info: MediaInfo) -> MediaInfo:
        """Fill missing resolutions and sizes before the quality menu is built."""
        info.formats = infer_heights(info.formats)
        await self._fill_sizes(info.formats, referer=info.url, duration=info.duration or 0)
        return info

    async def _fill_sizes(
        self,
        formats: list[dict],
        referer: str = "",
        duration: int = 0,
    ) -> None:
        """Fill unknown format sizes, without slowing the probe too much.

        * HLS/DASH: estimate from duration × advertised bitrate.
        * Direct files: try ``HEAD`` first, then ``Range: bytes=0-0`` for CDNs
          that reject HEAD. Both are bounded and run in parallel.
        """
        formats = [fmt for fmt in (formats or []) if isinstance(fmt, dict)]
        for fmt in formats:
            if fmt.get("filesize") or fmt.get("filesize_approx"):
                continue
            rate = _int_or_zero(fmt.get("tbr"))
            if rate > 0 and duration > 0:
                fmt["filesize_approx"] = int(duration * rate * 1000 / 8)

        targets = [
            fmt for fmt in formats
            if not fmt.get("filesize") and not fmt.get("filesize_approx")
            and str(fmt.get("url") or "").lower().startswith(("http://", "https://"))
            and not _is_manifest(fmt)
        ][:16]
        if not targets:
            return

        headers = {"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"}
        if referer:
            headers["Referer"] = referer
        timeout = aiohttp.ClientTimeout(total=20)
        sem = asyncio.Semaphore(6)

        async def one(fmt: dict) -> None:
            async with sem:
                url = str(fmt["url"])
                for method, extra in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
                    try:
                        async with safe_http_request(sess, method, url, headers=extra) as resp:
                            if resp.status >= 400:
                                continue
                            total = (
                                resp.headers.get("Content-Range", "").rpartition("/")[2]
                                or resp.headers.get("Content-Length")
                            )
                            if total and str(total).isdigit() and int(total) > 1024:
                                fmt["filesize"] = int(total)
                                return
                    except (errors.LeechError, aiohttp.ClientError, TimeoutError, OSError):
                        continue

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
                await asyncio.wait_for(
                    asyncio.gather(*(one(fmt) for fmt in targets)), timeout=15
                )
        except TimeoutError:
            log.debug("size lookup timed out for %s", referer or "?")
        log.debug(
            "filled sizes for %d/%d formats",
            sum(1 for f in targets if f.get("filesize")), len(targets),
        )

    async def _vk_fallback(self, url: str, exc: errors.LeechError):
        """VK wall posts: find the real video id and probe that video URL.

        yt-dlp returns an empty playlist for some wall posts from some IPs and
        rejects `vk.ru`; crawler user-agents get the OG tags without a captcha.
        """
        page_url = vk_wall_url(url)
        if page_url is None:
            return None
        try:
            ref: tuple[str, str] | None = None
            for user_agent in _CRAWLER_UAS:
                html = await self._fetch_text(page_url, user_agent)
                ref = vk_video_ref(html)
                if ref is not None:
                    break
            if ref is None:
                log.info("VK wall %s has no video", page_url)
                return None
            owner, video = ref
            video_url = f"https://vk.com/video{owner}_{video}"
            info = await asyncio.to_thread(self._probe_blocking, video_url)
            # Keep the canonical video URL: the download step must not retry the
            # wall page (which yt-dlp cannot download).
            info.url = video_url
            info.embed_url = video_url
            log.info("resolved VK wall %s -> %s", page_url, video_url)
            return await self._enrich(info)
        except errors.LeechError:
            raise
        except Exception:  # noqa: BLE001 — خطای اصلی باید به کاربر برسد
            log.warning("VK fallback failed for %s", url, exc_info=True)
            return None

    async def _fetch_text(
        self, url: str, user_agent: str, referer: str = "", timeout: int = 40,
    ) -> str:
        """Fetch HTML with a specific user-agent (crawler/browser)."""
        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
        }
        if referer:
            headers["Referer"] = referer
        client_timeout = aiohttp.ClientTimeout(total=timeout, connect=15)
        async with aiohttp.ClientSession(timeout=client_timeout, headers=headers) as sess:
            async with safe_http_request(sess, "GET", url) as resp:
                if resp.status >= 400:
                    return ""
                return await resp.text(errors="replace")

    async def _kvs_fallback(self, url: str, exc: errors.LeechError):
        """اگر خطا مربوط به KVS بود، خودمان صفحه را تفسیر می‌کنیم."""
        if not is_kvs_error(exc.reason):
            return None
        try:
            info = await self._probe_kvs(url)
        except errors.LeechError:
            raise
        except Exception:  # noqa: BLE001 — بهتر است خطای اصلی به کاربر برسد
            log.warning("KVS fallback failed for %s", url, exc_info=True)
            return None
        if info is not None:
            log.info("parsed KVS page directly for %s (%d formats)", url, len(info.formats))
        return info

    async def _probe_kvs(self, url: str) -> MediaInfo | None:
        """پارس صفحهٔ KVS و گرفتن حجم/دسترسی هر فرمت با Range 0-0."""
        timeout = aiohttp.ClientTimeout(total=35)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
        }
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
            async with safe_http_request(sess, "GET", url) as resp:
                if resp.status >= 400:
                    return None
                html = await resp.text(errors="replace")
            info = parse_kvs(html, url)
            if info is None:
                return None
            for fmt in info.formats:
                try:
                    async with safe_http_request(
                        sess, "GET", str(fmt["url"]),
                        headers={"Referer": url, "Range": "bytes=0-0"},
                    ) as media:
                        if media.status not in (200, 206):
                            continue
                        total = (
                            media.headers.get("Content-Range", "").rpartition("/")[2]
                            or media.headers.get("Content-Length")
                        )
                        if total and str(total).isdigit():
                            fmt["filesize"] = int(total)
                except (errors.LeechError, aiohttp.ClientError, TimeoutError, OSError):
                    continue
        return info

    async def _cf_fallback(self, url: str, exc: errors.LeechError):
        """اگر سایت پشت چالش Cloudflare بود، صفحه را با byparr باز می‌کنیم."""
        if not (self.cfg.byparr_url or "").strip() or not looks_like_cf_block(exc):
            return None
        page_url = (url or "").split("#", 1)[0]
        try:
            solved = await self._cf_solve(page_url)
            if solved is None:
                return None
            info = await self._parse_solved_page(page_url, *solved)
        except errors.LeechError:
            raise
        except Exception:  # noqa: BLE001 — خطای اصلی باید به کاربر برسد
            log.warning("Cloudflare fallback failed for %s", url, exc_info=True)
            return None
        if info is not None:
            log.info("resolved Cloudflare page for %s (%d formats)", url, len(info.formats))
            return await self._enrich(info)
        if _CAPTCHA_HOST.search(solved[0]):
            log.info("player behind an interactive captcha for %s", url)
            raise errors.CaptchaWall(
                "the video host (doodstream/playmogo) needs an interactive captcha"
            )
        return None

    async def _cf_solve(self, url: str) -> tuple[str, str] | None:
        """حل چالش Cloudflare با byparr؛ خروجی ``(html, user_agent)``."""
        base = (self.cfg.byparr_url or "").strip().rstrip("/")
        if not base:
            return None
        payload = {"cmd": "request.get", "url": url, "maxTimeout": 120000}
        timeout = aiohttp.ClientTimeout(total=170, connect=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as sess:
                async with sess.post(f"{base}/v1", json=payload) as resp:
                    data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, OSError, ValueError):
            log.warning("byparr request failed for %s", url, exc_info=True)
            return None
        if not isinstance(data, dict) or str(data.get("status") or "").casefold() != "ok":
            return None
        solution = data.get("solution") or {}
        html = str(solution.get("response") or "")
        if len(html) < 200:
            return None
        return html, str(solution.get("userAgent") or USER_AGENT)

    async def _parse_solved_page(
        self, page_url: str, html: str, user_agent: str
    ) -> MediaInfo | None:
        """صفحهٔ حل‌شده را به MediaInfo تبدیل می‌کند (KVS یا iframe با HLS)."""
        parsed = parse_kvs(html, page_url)
        if parsed is not None:
            return parsed

        title = _html_title(html)
        title = re.sub(r"\s*[-–|]\s*[^-–|]+\.(?:com|net|org|xxx|tv)\s*$", "", title, flags=re.I)
        og_image = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html
        )
        thumbnail = urljoin(page_url, og_image.group(1)) if og_image else None

        candidates = list(iframe_sources(html))[:5]
        masters = m3u8_candidates(html, page_url)[:4]
        if not candidates and not masters and not hls_links(html, page_url):
            return None

        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        timeout = aiohttp.ClientTimeout(total=45, connect=10)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
            for raw in candidates:
                embed_url = raw if raw.startswith(("http://", "https://")) else f"https:{raw}"
                try:
                    async with safe_http_request(
                        sess, "GET", embed_url, headers={"Referer": page_url}
                    ) as resp:
                        if resp.status >= 400:
                            continue
                        embed_html = await resp.text(errors="replace")
                except (errors.LeechError, aiohttp.ClientError, TimeoutError, OSError):
                    continue
                links = hls_links(embed_html, embed_url)
                if not links:
                    continue
                master_url = links.get("hls3") or links.get("hls2") or next(iter(links.values()))
                variants = await self._hls_variants(sess, master_url, embed_url)
                if not variants:
                    continue
                await self._hls_variant_sizes(sess, variants, embed_url)
                return MediaInfo(
                    url=page_url,
                    title=human.safe_filename(title or "media", 150),
                    thumbnail=thumbnail,
                    extractor="HLS",
                    formats=_hls_formats(variants),
                    ext="mp4",
                    embed_url=embed_url,
                )

            # No player iframe: the page itself carries the manifest (e.g. missav).
            for master_url in masters:
                variants = await self._hls_from_manifest(sess, master_url, page_url)
                if not variants:
                    continue
                await self._hls_variant_sizes(sess, variants, page_url)
                return MediaInfo(
                    url=page_url,
                    title=human.safe_filename(title or "media", 150),
                    thumbnail=thumbnail,
                    extractor="HLS",
                    formats=_hls_formats(variants),
                    ext="mp4",
                    embed_url=master_url,
                )
        return None

    async def _hls_from_manifest(self, sess, master_url: str, referer: str) -> list[dict]:
        """Read a manifest URL and return its variants (or a single media one)."""
        try:
            async with safe_http_request(
                sess, "GET", master_url, headers={"Referer": referer}
            ) as resp:
                if resp.status >= 400:
                    return []
                text = await resp.text(errors="replace")
        except (errors.LeechError, aiohttp.ClientError, TimeoutError, OSError):
            return []
        return hls_manifest_variants(text, master_url)

    async def _hls_variant_sizes(self, sess, variants: list[dict], referer: str) -> None:
        """Approximate HLS sizes as `sum(EXTINF) × bandwidth / 8`.

        The master playlist usually has no size, but the media playlist lists
        every segment duration; combined with BANDWIDTH this is close enough for
        the quality menu (and cheap: one small request per variant).
        """
        sem = asyncio.Semaphore(6)

        async def one(variant: dict) -> None:
            async with sem:
                try:
                    async with safe_http_request(
                        sess, "GET", str(variant["url"]), headers={"Referer": referer}
                    ) as resp:
                        if resp.status >= 400:
                            return
                        text = await resp.text(errors="replace")
                except (errors.LeechError, aiohttp.ClientError, TimeoutError, OSError):
                    return
            seconds = sum(float(value) for value in re.findall(r"#EXTINF:([0-9.]+)", text))
            rate = _int_or_zero(variant.get("bandwidth"))
            if seconds > 0 and rate > 0:
                variant["filesize_approx"] = int(seconds * rate / 8)

        try:
            await asyncio.wait_for(asyncio.gather(*(one(v) for v in variants)), timeout=12)
        except TimeoutError:
            log.debug("HLS size lookup timed out for %s", referer)

    async def _hls_variants(self, sess, master_url: str, referer: str) -> list[dict]:
        """پلی‌لیست مادر را می‌خواند و واریانت‌ها را برمی‌گرداند."""
        try:
            async with safe_http_request(sess, "GET", master_url, headers={"Referer": referer}) as resp:
                if resp.status >= 400:
                    return []
                text = await resp.text(errors="replace")
        except (errors.LeechError, aiohttp.ClientError, TimeoutError, OSError):
            return []
        return hls_master_variants(text, master_url)

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

        extractor = str(info.get("extractor_key") or info.get("extractor") or "")
        formats = list(info.get("formats") or [])
        if is_eporner_extractor(extractor):
            formats = with_av1_variants(formats)

        return MediaInfo(
            # برای لینک‌های embed-only، آدرس اصلی کاربر نمایش داده شود.
            url=url if target != url else (info.get("webpage_url") or url),
            title=human.safe_filename(
                fallback_title(url, info.get("title")) if target != url
                else (info.get("title") or "media"),
                150,
            ),
            duration=int(info["duration"]) if info.get("duration") else None,
            uploader=info.get("uploader") or info.get("channel") or info.get("creator"),
            thumbnail=info.get("thumbnail"),
            extractor=extractor,
            is_live=bool(info.get("is_live")),
            formats=formats,
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

        if option.kvs or (info is not None and info.extractor == "KVS" and option.kind == "audio"):
            # KVS: هر بار آدرس امضاشده را تازه می‌سازیم (کوتاه‌عمر است).
            return await self._download_kvs(
                url, option, workdir, progress, cancel,
                info or MediaInfo(url=url, title=""),
            )

        if option.hls or (info is not None and info.extractor == "HLS" and option.kind == "audio"):
            # HLS: هر بار پلی‌لیست را از صفحهٔ امبد تازه می‌خوانیم (هاست می‌چرخد).
            return await self._download_hls(
                option, workdir, progress, cancel,
                info or MediaInfo(url=url, title=""),
            )

        if option.media_url:
            # نسخه‌هایی مثل AV1 اپورنر در استخراج دوبارهٔ yt-dlp نیستند؛
            # همان آدرس مستقیم CDN را می‌گیریم ولی عنوان اصلی حفظ می‌شود.
            fallback = info or MediaInfo(url=url, title="")
            return await self._download_direct(
                option.media_url,
                workdir,
                progress,
                cancel,
                fallback,
                name=_variant_filename(fallback.title, option),
                title=fallback.title,
            )

        # VK: the wall page has no downloadable formats; use the resolved video URL.
        target = url
        if info is not None and info.extractor == "VK" and info.embed_url:
            target = info.embed_url
        try:
            return await asyncio.to_thread(
                self._download_blocking, target, option, workdir, progress, cancel
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
        name: str = "",
        title: str = "",
    ) -> DownloadResult:
        if not await urlcheck.is_safe_public_url(url):
            raise errors.UnsupportedUrl("Invalid or non-public download URL")
        progress.reset_download()
        name = name or human.safe_filename(urlcheck.filename_from_url(url, "download"), 120)
        if info.ext and not name.lower().endswith("." + info.ext.lower()):
            name = f"{name}.{info.ext}"
        dest = workdir / human.safe_filename(name, 150)

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
            title=human.safe_filename(title or dest.stem, 150),
            mime=info.mime or mime,
            size=size,
            is_audio=mime.startswith("audio/"),
        )

    async def _download_kvs(
        self,
        page_url: str,
        option: FormatOption,
        workdir: Path,
        progress: Progress,
        cancel: asyncio.Event,
        info: MediaInfo,
    ) -> DownloadResult:
        """KVS: صفحه را تازه می‌خواند، آدرس امضاشده را می‌سازد و مستقیم می‌گیرد."""
        progress.reset_download()
        timeout = aiohttp.ClientTimeout(total=None, sock_read=120, connect=30)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
        }
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
            async with safe_http_request(sess, "GET", page_url) as resp:
                if resp.status >= 400:
                    raise errors.UnsupportedUrl(f"HTTP {resp.status}")
                html = await resp.text(errors="replace")
            fresh = parse_kvs(html, page_url)
            if fresh is None:
                raise errors.UnsupportedUrl("KVS metadata missing")
            fmt = _kvs_pick(fresh.formats, option)
            if fmt is None:
                raise errors.UnsupportedUrl("KVS format missing")

            name = _variant_filename(fresh.title or info.title, option)
            # فایل میانی همیشه MP4 است؛ استخراج صدا از همین فایل انجام می‌شود.
            dest = workdir / human.safe_filename(f"{Path(name).stem}.mp4", 150)
            try:
                async with safe_http_request(
                    sess, "GET", str(fmt["url"]), headers={"Referer": page_url},
                ) as media:
                    if not await urlcheck.is_safe_public_url(str(media.url)):
                        raise errors.UnsupportedUrl("Unsafe redirect destination")
                    if media.status in (401, 403):
                        raise errors.AccessDenied(str(media.status))
                    if media.status == 404:
                        raise errors.ResourceNotFound("404")
                    if media.status >= 400:
                        raise errors.UnsupportedUrl(f"HTTP {media.status}")
                    total = int(media.headers.get("Content-Length") or 0)
                    progress.total = total
                    with dest.open("wb") as fh:
                        async for chunk in media.content.iter_chunked(1024 * 512):
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

        source = dest
        if option.kind == "audio":
            dest = await self._extract_audio(source, option.code, workdir)
            try:
                source.unlink()
            except OSError:
                pass

        size = dest.stat().st_size
        mime = _mime_for(dest)
        return DownloadResult(
            path=dest,
            title=human.safe_filename(fresh.title or info.title or dest.stem, 150),
            mime=mime,
            size=size,
            is_audio=option.kind == "audio" or mime.startswith("audio/"),
        )

    async def _download_hls(
        self,
        option: FormatOption,
        workdir: Path,
        progress: Progress,
        cancel: asyncio.Event,
        info: MediaInfo,
    ) -> DownloadResult:
        """صفحهٔ امبد را تازه می‌خواند و استریم HLS را بومی دانلود می‌کند.

        پلی‌لیست‌ها/سگمنت‌ها پسوندهای غیررسمی دارند (``.txt`` / ``.woff2``)
        و yt-dlp آن‌ها را نمی‌شناسد؛ پس خودمان سگمنت‌ها را می‌گیریم، به هم
        می‌چسبانیم و با ffmpeg بدون رمزگذاری مجدد به MP4 تبدیل می‌کنیم.
        """
        progress.reset_download()
        embed_url = info.embed_url
        timeout = aiohttp.ClientTimeout(total=None, sock_read=120, connect=30)
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"}
        variant: dict = {}

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as sess:
            if not embed_url:
                # کارهای قدیمی ممکن است آدرس امبد را نداشته باشند؛ دوباره حل کن.
                solved = await self._cf_solve(info.url)
                if solved is None:
                    raise errors.AccessDenied("403")
                fresh = await self._parse_solved_page(info.url, *solved)
                if fresh is None or not fresh.embed_url:
                    raise errors.UnsupportedUrl("HLS source missing")
                embed_url = fresh.embed_url
                info = MediaInfo(
                    url=info.url or fresh.url,
                    title=info.title or fresh.title,
                    duration=info.duration or fresh.duration,
                    thumbnail=info.thumbnail or fresh.thumbnail,
                    extractor="HLS",
                    formats=fresh.formats,
                    ext="mp4",
                    embed_url=embed_url,
                )

            async with safe_http_request(
                sess, "GET", embed_url, headers={"Referer": info.url}
            ) as resp:
                if resp.status in (401, 403):
                    raise errors.AccessDenied(str(resp.status))
                if resp.status >= 400:
                    raise errors.UnsupportedUrl(f"HTTP {resp.status}")
                embed_html = await resp.text(errors="replace")

            links = hls_links(embed_html, embed_url)
            if "#EXTM3U" in embed_html or embed_url.split("?", 1)[0].casefold().endswith(".m3u8"):
                # embed_url is already the playlist (e.g. missav, no iframe).
                master_url = embed_url
            elif links:
                master_url = links.get("hls3") or links.get("hls2") or next(iter(links.values()))
            else:
                candidates = m3u8_candidates(embed_html, embed_url)
                master_url = candidates[0] if candidates else ""
            if not master_url:
                raise errors.UnsupportedUrl("HLS links missing")
            variants = await self._hls_from_manifest(sess, master_url, embed_url)
            picked = pick_hls_variant(variants, option.height)
            if picked is None:
                raise errors.UnsupportedUrl("HLS variant missing")
            variant = picked

            async with safe_http_request(
                sess, "GET", str(variant["url"]), headers={"Referer": embed_url}
            ) as resp:
                if resp.status in (401, 403):
                    raise errors.AccessDenied(str(resp.status))
                if resp.status >= 400:
                    raise errors.UnsupportedUrl(f"HTTP {resp.status}")
                playlist = await resp.text(errors="replace")

            segments = hls_segments(playlist, str(variant["url"]))
            if not segments:
                raise errors.UnsupportedUrl("HLS playlist empty")

            name = _variant_filename(info.title or "media", option)
            stem = Path(name).stem
            part = workdir / human.safe_filename(f"{stem}.ts", 150)
            parts_dir = workdir / (f".parts-{part.stem}"[:80])
            try:
                parts_dir.mkdir(parents=True, exist_ok=True)
                semaphore = asyncio.Semaphore(HLS_CONCURRENCY)
                finished = 0

                async def fetch(index: int, segment: str) -> None:
                    nonlocal finished
                    async with semaphore:
                        if cancel.is_set():
                            raise errors.JobCancelled()
                        target = parts_dir / f"{index:05d}.part"
                        async with safe_http_request(
                            sess, "GET", segment, headers={"Referer": embed_url}
                        ) as media:
                            if media.status in (401, 403):
                                raise errors.AccessDenied(str(media.status))
                            if media.status >= 400:
                                raise errors.UnsupportedUrl(f"HTTP {media.status}")
                            with target.open("wb") as handle:
                                async for chunk in media.content.iter_chunked(1024 * 512):
                                    if cancel.is_set():
                                        raise errors.JobCancelled()
                                    handle.write(chunk)
                                    progress.downloaded += len(chunk)
                                    progress.downloaded_bytes_total += len(chunk)
                        finished += 1
                        progress.stage = "downloading"
                        progress.pct = min(99.0, finished * 100.0 / len(segments))

                tasks = [
                    asyncio.create_task(fetch(index, segment))
                    for index, segment in enumerate(segments)
                ]
                try:
                    for task in asyncio.as_completed(tasks):
                        await task
                except BaseException:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    raise

                if progress.downloaded <= 0:
                    raise errors.IncompleteDownload("empty HLS download")
                with part.open("wb") as handle:
                    for index in range(len(segments)):
                        with (parts_dir / f"{index:05d}.part").open("rb") as source:
                            shutil.copyfileobj(source, handle, 1024 * 1024)
            except (errors.JobCancelled, errors.LeechError):
                try:
                    part.unlink()
                except OSError:
                    pass
                shutil.rmtree(parts_dir, ignore_errors=True)
                raise
            except (aiohttp.ClientError, TimeoutError, OSError) as exc:
                try:
                    part.unlink()
                except OSError:
                    pass
                shutil.rmtree(parts_dir, ignore_errors=True)
                raise map_error(exc) from exc
            finally:
                shutil.rmtree(parts_dir, ignore_errors=True)

        if cancel.is_set():
            raise errors.JobCancelled()

        progress.stage = "postprocessing"
        progress.pct = 99.5
        # فایل میانی همیشه MP4 است؛ برای گزینهٔ صدا نام نهایی بعداً عوض می‌شود.
        dest = workdir / human.safe_filename(f"{stem}.mp4", 150)
        await self._remux_ts(part, dest)
        try:
            part.unlink()
        except OSError:
            pass

        if option.kind == "audio":
            audio = await self._extract_audio(dest, option.code, workdir)
            try:
                dest.unlink()
            except OSError:
                pass
            dest = audio

        size = dest.stat().st_size
        mime = _mime_for(dest)
        return DownloadResult(
            path=dest,
            title=human.safe_filename(info.title or dest.stem, 150),
            duration=info.duration,
            width=int(variant.get("width") or 0) or None,
            height=int(variant.get("height") or 0) or None,
            mime=mime,
            size=size,
            is_audio=option.kind == "audio" or mime.startswith("audio/"),
        )

    async def _remux_ts(self, source: Path, dest: Path) -> None:
        """چسباندن سگمنت‌های MPEG-TS و تبدیل بدون رمزگذاری مجدد به MP4."""
        base = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source)]
        attempts = [
            ["-c", "copy", "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart", str(dest)],
            ["-c", "copy", str(dest)],
        ]
        for extra in attempts:
            try:
                dest.unlink()
            except OSError:
                pass
            try:
                proc = await asyncio.create_subprocess_exec(
                    *base, *extra,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                await proc.wait()
            except FileNotFoundError as exc:
                raise errors.UnsupportedUrl("ffmpeg missing") from exc
            if proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 0:
                return
        raise errors.UnsupportedUrl("HLS remux failed")

    async def _extract_audio(self, source: Path, code: str, workdir: Path) -> Path:
        """استخراج صدا از فایل KVS با ffmpeg (mp3 192k یا m4a بدون تبدیل)."""
        ext = "mp3" if code == "mp3" else "m4a"
        dest = workdir / human.safe_filename(f"{source.stem}.{ext}", 150)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-vn"]
        if ext == "mp3":
            cmd += ["-c:a", "libmp3lame", "-b:a", "192k"]
        else:
            cmd += ["-c:a", "copy"]
        cmd.append(str(dest))
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            status = await proc.wait()
        except FileNotFoundError as exc:
            raise errors.UnsupportedUrl("ffmpeg missing") from exc
        if status != 0 or not dest.is_file() or dest.stat().st_size == 0:
            raise errors.UnsupportedUrl("audio extraction failed")
        return dest
