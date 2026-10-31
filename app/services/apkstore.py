"""Play Store links → APKPure APK/XAPK variants.

The Play Store page carries only a package name, so the file list comes from
APKPure's ``/download`` page: one row per ABI (``arm64-v8a``, ``armeabi-v7a``,
``universal`` …) with a version, a size and a direct CDN URL.

That page sits behind Cloudflare. It is fetched through byparr, and the
resulting cookies plus the browser user-agent are remembered, because
``cf_clearance`` is bound to that exact pair. The CDN download then runs with
the remembered pair; on ``403`` the page is solved again for a fresh one.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

import aiohttp

from app.config import Config
from app.core import human
from app.services.formats import FormatOption

log = logging.getLogger("leechx.apkstore")

APK_MEDIA_HOSTS = ("d.apkpure.com", "data.winudf.com", "download.apkpure.com")
PLAY_HOSTS = ("play.google.com", "play.googleusercontent.com")
_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")

# صفحهٔ APKPure و کوکی‌هایش زیاد عمر نمی‌کنند؛ برای همان بازه کش می‌شوند.
PAGE_TTL = 300.0
SESSION_TTL = 20 * 60.0
_MAX_PAGES = 32
_MAX_SESSIONS = 128

_SESSIONS: dict[str, Session] = {}
_PAGES: dict[str, tuple[float, ApkPage]] = {}
_FETCH_LOCKS: dict[str, asyncio.Lock] = {}


# ── مدل‌ها ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class ApkLink:
    """یک نسخهٔ قابل دانلود (ABI + فرمت + حجم)."""

    url: str
    abi: str
    version: str
    version_code: str
    ext: str
    size: int | None

    @property
    def code(self) -> str:
        """کلید پایدار برای callback؛ فقط حروف/ارقام/خط تیره."""
        base = re.sub(r"[^a-z0-9]+", "-", (self.abi or self.ext or "apk").lower()).strip("-")
        return base or "apk"

    @property
    def label(self) -> str:
        parts = [self.abi or self.ext.upper()]
        if self.size:
            parts.append(human.human_bytes(self.size))
        elif self.version:
            parts.append(self.version)
        return " · ".join(part for part in parts if part)


@dataclass(frozen=True)
class Session:
    """کوکی و UA لازم برای گرفتن فایل از CDN."""

    cookie: str
    user_agent: str
    referer: str
    created: float

    def fresh(self, ttl: float = SESSION_TTL) -> bool:
        return bool(self.cookie) and time.monotonic() - self.created < ttl


@dataclass
class ApkPage:
    package: str
    title: str
    page_url: str
    version: str = ""
    links: list[ApkLink] = field(default_factory=list)
    cookie: str = ""
    user_agent: str = ""
    fetched_at: float = field(default_factory=time.monotonic)


# ── تشخیص لینک ────────────────────────────────────────────────
def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").rstrip(".").lower()
    except ValueError:
        return ""


def _query_id(query: str) -> str:
    try:
        values = parse_qs(query or "").get("id") or []
    except ValueError:
        return ""
    return values[0].strip() if values else ""


def package_of(url: str) -> str | None:
    """نام بستهٔ اندروید از لینک Play Store / market:// / APKPure."""
    raw = (url or "").strip()
    if not raw:
        return None
    low = raw.lower()
    if low.startswith("market://"):
        try:
            pkg = _query_id(urlsplit(raw).query)
        except ValueError:
            return None
        return pkg if _PACKAGE_RE.match(pkg) else None

    host = _host(raw)
    if not host:
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None

    if any(host == h or host.endswith("." + h) for h in PLAY_HOSTS):
        if not parts.path.startswith("/store/apps"):
            return None
        pkg = _query_id(parts.query)
        return pkg if _PACKAGE_RE.match(pkg) else None

    if host == "apkpure.com" or host.endswith(".apkpure.com"):
        segments = [unquote(seg) for seg in parts.path.split("/") if seg]
        for seg in reversed(segments):
            if seg.lower() in {"download", "apk", "xapk", "apks", "versions"}:
                continue
            if _PACKAGE_RE.match(seg):
                return seg
        return None
    return None


def is_apk_page(url: str) -> bool:
    return package_of(url) is not None


def is_apk_media(url: str) -> bool:
    host = _host(url)
    return any(host == h or host.endswith("." + h) for h in APK_MEDIA_HOSTS)


def package_from_media(url: str) -> str | None:
    """بسته را از مسیر base64 شدهٔ ``d.apkpure.com/b/XAPK/<pkg>_<code>_<hash>``."""
    if not is_apk_media(url):
        return None
    try:
        path = urlsplit(url).path
    except ValueError:
        return None
    token = path.rstrip("/").rsplit("/", 1)[-1]
    if not token:
        return None
    padded = token + "=" * (-len(token) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return None
    match = re.match(r"(.+?)_\d+(?:_|$)", decoded)
    return match.group(1) if match else None


# ── پارس صفحه ─────────────────────────────────────────────────
_SIZE_UNITS = {
    "b": 1,
    "kb": 1024,
    "mb": 1024 ** 2,
    "gb": 1024 ** 3,
}


def parse_size(raw: str) -> int | None:
    match = re.search(r"([\d.,]+)\s*(B|KB|MB|GB)", raw or "", re.I)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    return int(value * _SIZE_UNITS[match.group(2).lower()]) or None


def _strip_tags(raw: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw or "")).strip()


def _title_of(html: str) -> str:
    for pattern in (r"<h1[^>]*>(.*?)</h1>", r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)'):
        match = re.search(pattern, html, re.S | re.I)
        if match:
            title = _strip_tags(match.group(1))
            title = re.sub(r"\s*[-–|]\s*(?:APK|XAPK).*$", "", title, flags=re.I).strip()
            if title:
                return title
    return ""


def _abi_of(html: str, start: int) -> str:
    """عنوان گروه ABI که بلوک دانلود در آن قرار دارد."""
    pos = html.rfind('class="group-title"', 0, start)
    if pos < 0:
        return ""
    end = html.find("</div>", pos)
    if end < 0:
        return ""
    block = html[pos:end]
    marker = block.rfind("</svg>")
    if marker >= 0:
        block = block[marker + len("</svg>"):]
    abi = _strip_tags(block)
    if len(abi) > 40:
        return ""
    # «arm64-v8a, armeabi-v7a, x86…» یعنی یک فایل چندمعماری (universal).
    parts = [part.strip() for part in re.split(r"[,/]", abi) if part.strip()]
    if len(parts) > 1:
        return "universal"
    return parts[0] if parts else ""


def parse_page(html: str, package: str, page_url: str = "") -> ApkPage | None:
    """صفحهٔ دانلود APKPure را به فهرست نسخه‌ها تبدیل می‌کند."""
    if not html or not package:
        return None
    page = ApkPage(package=package, title=_title_of(html) or package, page_url=page_url)

    marker = f'data-dt-app="{package}"'
    starts = [match.start() for match in re.finditer(r'<div class="apk"\s+' + re.escape(marker), html)]
    if not starts:
        starts = [
            match.start()
            for match in re.finditer(r'<div class="apk"\s+[^>]*' + re.escape(marker), html)
        ]

    used: set[str] = set()
    for start in starts:
        button = html.find("download-btn", start)
        if button < 0:
            continue
        close = html.find("</a>", button)
        chunk = html[start: close + 4 if close >= 0 else start + 3000]
        href = re.search(r'class="download-btn"\s+href="([^"]+)"', chunk)
        if not href:
            # ویژگی‌ها ممکن است جای دیگری بیایند.
            href = re.search(r'href="(https://d\.apkpure\.com/[^"]+)"', chunk)
        if not href:
            continue
        url = href.group(1).replace("&amp;", "&").strip()
        if not url.startswith(("http://", "https://")):
            url = urljoin(page_url or "https://apkpure.com/", url)

        tag = re.search(r'data-tag="([A-Za-z]+)"', chunk)
        ext = (tag.group(1) if tag else "apk").lower()
        name = re.search(r'class="name[^"]*">([^<]+)', chunk)
        version = _strip_tags(name.group(1)) if name else ""
        code = re.search(r'class="code[^"]*">\(?(\d+)\)?', chunk)
        size = re.search(r'class="size[^"]*">([^<]+)', chunk)

        link = ApkLink(
            url=url,
            abi=_abi_of(html, start),
            version=version,
            version_code=code.group(1) if code else "",
            ext=ext,
            size=parse_size(size.group(1)) if size else None,
        )
        if not link.url:
            continue
        base_code = link.code
        if base_code in used:
            continue
        used.add(base_code)
        page.links.append(link)

    if not page.links:
        return None
    page.links.sort(key=_variant_rank)
    page.version = next((link.version for link in page.links if link.version), "")
    return page


def _variant_rank(link: ApkLink) -> tuple:
    abi = (link.abi or "").lower()
    if "arm64" in abi or abi in {"arm64-v8a", "v8"}:
        order = 0
    elif "armeabi" in abi or abi in {"armeabi-v7a", "v7"}:
        order = 1
    elif "universal" in abi or "noarch" in abi:
        order = 2
    elif abi:
        order = 3
    else:
        order = 2
    return (order, -(link.size or 0), abi)


def option_for(link: ApkLink) -> FormatOption:
    """گزینهٔ منو برای یک نسخه؛ ``kind=video`` تا منوی کیفیت آن را نشان دهد."""
    return FormatOption(
        kind="video",
        code=link.code,
        label=link.label,
        selector="",
        ext=link.ext or "apk",
        filesize=link.size,
        codec="apk",
        media_url=link.url,
    )


def options_for(page: ApkPage) -> list[FormatOption]:
    options = [option_for(link) for link in page.links]
    # تبلیغ/نسخهٔ تکراری نباید منو را شلوغ کند.
    return options[:8]


# ── byparr ────────────────────────────────────────────────────
async def _solve(cfg: Config, url: str) -> tuple[str, str, str, str] | None:
    """``(html, final_url, cookie_header, user_agent)`` از byparr."""
    base = (cfg.byparr_url or "").strip().rstrip("/")
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
    if len(html) < 500:
        return None
    cookies = solution.get("cookies") or []
    cookie = "; ".join(
        f"{item.get('name')}={item.get('value')}"
        for item in cookies
        if isinstance(item, dict) and item.get("name")
    )
    return (
        html,
        str(solution.get("url") or url),
        cookie,
        str(solution.get("userAgent") or ""),
    )


def _lock_for(package: str) -> asyncio.Lock:
    lock = _FETCH_LOCKS.get(package)
    if lock is None:
        lock = asyncio.Lock()
        _FETCH_LOCKS[package] = lock
    return lock


async def fetch_page(cfg: Config, url: str, *, force: bool = False) -> ApkPage | None:
    """نسخه‌های یک بسته را برمی‌گرداند (کش کوتاه‌عمر برای هر بسته)."""
    package = package_of(url)
    if not package:
        return None
    cached = _PAGES.get(package)
    if cached and not force and time.monotonic() - cached[0] < PAGE_TTL:
        return cached[1]

    async with _lock_for(package):
        cached = _PAGES.get(package)
        if cached and not force and time.monotonic() - cached[0] < PAGE_TTL:
            return cached[1]
        solved = await _solve(cfg, f"https://apkpure.com/x/{package}/download")
        if solved is None:
            return cached[1] if cached else None
        html, final_url, cookie, user_agent = solved
        page = parse_page(html, package, final_url)
        if page is None:
            return cached[1] if cached else None
        page.cookie = cookie
        page.user_agent = user_agent
        _remember_page(page)
        return page


def _remember_page(page: ApkPage) -> None:
    now = time.monotonic()
    _PAGES[page.package] = (now, page)
    while len(_PAGES) > _MAX_PAGES:
        oldest = min(_PAGES, key=lambda key: _PAGES[key][0])
        _PAGES.pop(oldest, None)
    for link in page.links:
        _SESSIONS[link.url] = Session(
            cookie=page.cookie,
            user_agent=page.user_agent,
            referer=page.page_url,
            created=now,
        )
    while len(_SESSIONS) > _MAX_SESSIONS:
        oldest = min(_SESSIONS, key=lambda key: _SESSIONS[key].created)
        _SESSIONS.pop(oldest, None)


def session_for(url: str) -> Session | None:
    session = _SESSIONS.get(url)
    return session if session is not None and session.fresh() else None


async def refresh_session(cfg: Config, url: str) -> Session | None:
    """کوکی تازه برای یک فایل؛ با حل دوبارهٔ صفحهٔ برنامه."""
    old = _SESSIONS.get(url)
    package = (package_of(old.referer) if old is not None else None) or package_from_media(url)
    if not package:
        return None
    page = await fetch_page(cfg, f"https://apkpure.com/x/{package}/download", force=True)
    if page is None:
        return None
    session = _SESSIONS.get(url)
    if session is None:
        session = Session(
            cookie=page.cookie,
            user_agent=page.user_agent,
            referer=page.page_url,
            created=time.monotonic(),
        )
        _SESSIONS[url] = session
    return session if session.fresh() else None


def reset_cache() -> None:
    """برای تست‌ها: همهٔ کش‌های حافظه را پاک می‌کند."""
    _PAGES.clear()
    _SESSIONS.clear()
    _FETCH_LOCKS.clear()
