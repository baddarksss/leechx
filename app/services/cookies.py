"""مدیریت فایل کوکی برای سایت‌هایی که لاگین می‌خواهند (یوتیوب، اینستاگرام…).

قالب استاندارد همان «Netscape HTTP Cookie File» است که افزونه‌های مرورگر
(Get cookies.txt، EditThisCookie) و ``yt-dlp --cookies-from-browser`` تولید
می‌کنند. خروجی JSON بعضی افزونه‌ها هم پذیرفته و خودکار تبدیل می‌شود.

هر فایل با نام ``<site>.txt`` داخل ``COOKIES_DIR`` ذخیره می‌شود و هنگام
دانلود، بر اساس دامنهٔ لینک انتخاب می‌شود. ادمین از پنل ربات می‌تواند
فایل اضافه، بررسی یا حذف کند.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from app.core import human
from app.core.urlcheck import host_of

MAX_COOKIE_BYTES = 2 * 1024 * 1024
_NAME_RE = re.compile(r"[^a-z0-9_-]+")

# دامنه/برند → نام فایل پیشنهادی
BRAND_NAMES: tuple[tuple[str, str], ...] = (
    ("youtube", "youtube"),
    ("youtu.be", "youtube"),
    ("googlevideo", "youtube"),
    ("instagram", "instagram"),
    ("cdninstagram", "instagram"),
    ("tiktok", "tiktok"),
    ("twitter", "twitter"),
    ("x.com", "twitter"),
    ("facebook", "facebook"),
    ("fb.watch", "facebook"),
    ("soundcloud", "soundcloud"),
    ("vimeo", "vimeo"),
    ("twitch", "twitch"),
    ("reddit", "reddit"),
    ("spotify", "spotify"),
    ("pinterest", "pinterest"),
    ("linkedin", "linkedin"),
    ("dailymotion", "dailymotion"),
    ("bilibili", "bilibili"),
    ("aparat", "aparat"),
    ("pornhub", "pornhub"),
    ("xvideos", "xvideos"),
    ("xhamster", "xhamster"),
)


class CookieError(ValueError):
    """فایل کوکی معتبر نیست."""


@dataclass(frozen=True)
class CookieFile:
    name: str
    path: Path
    size: int
    modified: int
    domains: tuple[str, ...]
    expired: int = 0

    @property
    def filename(self) -> str:
        return f"{self.name}.txt"


def _sanitize_name(name: str) -> str:
    clean = _NAME_RE.sub("-", (name or "").strip().lower()).strip("-_")
    return clean[:40]


def _cookie_lines(data: str) -> list[list[str]]:
    """خطوط معتبر Netscape؛ پیشوند ``#HttpOnly_`` هم پشتیبانی می‌شود."""
    rows: list[list[str]] = []
    for line in (data or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            rows.append(parts)
    return rows


def parse_domains(data: str) -> list[str]:
    """دامنه‌های موجود در یک فایل Netscape را برمی‌گرداند."""
    domains: list[str] = []
    for parts in _cookie_lines(data):
        domain = parts[0].strip().lstrip(".").lower()
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def count_expired(data: str, now: float | None = None) -> int:
    """تعداد کوکی‌هایی که تاریخ انقضایشان گذشته است (0 = سشن)."""
    current = time.time() if now is None else now
    expired = 0
    for parts in _cookie_lines(data):
        try:
            expires = int(float(parts[4] or 0))
        except (TypeError, ValueError):
            continue
        if 0 < expires < current:
            expired += 1
    return expired


def _json_to_netscape(text: str) -> str:
    """تبدیل خروجی JSON افزونه‌ها (EditThisCookie و مشابه) به Netscape."""
    try:
        payload = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise CookieError("invalid JSON") from exc

    if isinstance(payload, dict):
        payload = payload.get("cookies") or payload.get("Cookies") or []
    if not isinstance(payload, list):
        raise CookieError("JSON is not a cookie list")

    lines = ["# Netscape HTTP Cookie File"]
    for item in payload:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or item.get("host") or "").strip()
        name = str(item.get("name") or "").strip()
        if not domain or not name:
            continue
        path = str(item.get("path") or "/") or "/"
        secure = "TRUE" if item.get("secure") else "FALSE"
        expires = item.get("expirationDate") or item.get("expires") or item.get("expiry") or 0
        try:
            expires = int(float(expires))
        except (TypeError, ValueError):
            expires = 0
        host_only = item.get("hostOnly")
        include_sub = "FALSE" if host_only is True else "TRUE"
        if not domain.startswith(".") and host_only is not True:
            domain = "." + domain
        lines.append(
            "\t".join([domain, include_sub, path, secure, str(expires), name, str(item.get("value") or "")])
        )

    if len(lines) < 2:
        raise CookieError("no cookies in JSON")
    return "\n".join(lines) + "\n"


def normalize_cookie_data(data: str | bytes) -> str:
    """اعتبارسنجی و یکسان‌سازی؛ خروجی همیشه Netscape است."""
    if isinstance(data, bytes):
        if len(data) > MAX_COOKIE_BYTES:
            raise CookieError("file is too large")
        try:
            data = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                data = data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise CookieError("file is not UTF-8 text") from exc

    data = (data or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if not data.strip():
        raise CookieError("empty file")
    if "\x00" in data:
        raise CookieError("binary file")
    if len(data.encode("utf-8")) > MAX_COOKIE_BYTES:
        raise CookieError("file is too large")

    stripped = data.lstrip()
    if "<html" in stripped[:400].lower() or stripped[:200].lower().startswith("<!doctype"):
        raise CookieError("HTML page, not a cookie file")
    if stripped.startswith(("[", "{")):
        data = _json_to_netscape(stripped)

    if not _cookie_lines(data):
        raise CookieError("no cookie lines")
    if "Netscape HTTP Cookie File" not in data.splitlines()[0]:
        data = "# Netscape HTTP Cookie File\n" + data
    return data


def looks_like_cookie_text(data: str | bytes) -> bool:
    try:
        normalize_cookie_data(data)
        return True
    except CookieError:
        return False


def infer_name(domains: list[str], fallback: str = "cookies") -> str:
    """نام فایل مناسب از روی دامنه‌ها (youtube، instagram، …)."""
    for domain in domains:
        low = domain.lower()
        for needle, name in BRAND_NAMES:
            if needle in low:
                return name
    for domain in domains:
        labels = [p for p in domain.lower().split(".") if p]
        if len(labels) >= 2:
            name = _sanitize_name(labels[-2])
            if name:
                return name
    return _sanitize_name(fallback) or "cookies"


class CookieStore:
    """فایل‌های کوکی روی دیسک — تنها منبع حقیقت برای دانلودر."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, tuple[int, int, CookieFile]] = {}

    # ── خواندن ──────────────────────────────────────────────
    def list_files(self) -> list[CookieFile]:
        found: list[CookieFile] = []
        try:
            paths = sorted(self.folder.glob("*.txt"))
        except OSError:
            return []
        for path in paths:
            try:
                stat = path.stat()
            except OSError:
                continue
            cached = self._cache.get(path.stem)
            if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
                found.append(cached[2])
                continue
            try:
                data = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            cookie = CookieFile(
                name=path.stem,
                path=path,
                size=stat.st_size,
                modified=int(stat.st_mtime),
                domains=tuple(parse_domains(data)),
                expired=count_expired(data),
            )
            self._cache[path.stem] = (stat.st_mtime_ns, stat.st_size, cookie)
            found.append(cookie)
        found.sort(key=lambda c: c.modified, reverse=True)
        return found

    def get(self, name: str) -> CookieFile | None:
        safe = _sanitize_name(name)
        if not safe:
            return None
        for cookie in self.list_files():
            if cookie.name == safe:
                return cookie
        return None

    def find_for_url(self, url: str) -> Path | None:
        """بهترین فایل کوکی برای این لینک (بر اساس دامنه‌های داخل فایل)."""
        host = host_of(url)
        if not host:
            return None
        files = self.list_files()
        best: CookieFile | None = None
        best_score = 0
        for cookie in files:
            for domain in cookie.domains:
                if host == domain or host.endswith("." + domain):
                    if len(domain) > best_score:
                        best, best_score = cookie, len(domain)
        if best is not None:
            return best.path

        # فایل‌هایی که دامنه‌شان قابل‌خواندن نبود: تطبیق با نام فایل + نام برند
        for cookie in files:
            stem = cookie.name.lower()
            if host == stem or host.startswith(stem + ".") or host.endswith("." + stem):
                return cookie.path
            for needle, name in BRAND_NAMES:
                if name == stem and needle in host:
                    return cookie.path
        return None

    # ── نوشتن ───────────────────────────────────────────────
    def save(self, name: str, data: str | bytes) -> CookieFile:
        normalized = normalize_cookie_data(data)
        safe = _sanitize_name(name) or infer_name(parse_domains(normalized))
        if not safe:
            raise CookieError("invalid name")
        target = self.folder / f"{safe}.txt"
        tmp = self.folder / f".{safe}.{os.getpid()}.tmp"
        try:
            tmp.write_text(normalized, encoding="utf-8")
            try:
                tmp.chmod(0o600)
            except OSError:
                pass
            tmp.replace(target)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise CookieError(f"could not write cookie file: {exc}") from exc

        self._cache.pop(safe, None)
        cookie = self.get(safe)
        if cookie is None:  # pragma: no cover — فقط اگر فایل بلافاصله ناپدید شود
            raise CookieError("cookie file disappeared")
        return cookie

    def save_text(self, data: str | bytes, name: str = "") -> CookieFile:
        """ذخیره با نام خودکار از دامنه‌ها."""
        normalized = normalize_cookie_data(data)
        return self.save(name or infer_name(parse_domains(normalized)), normalized)

    def delete(self, name: str) -> bool:
        safe = _sanitize_name(name)
        if not safe:
            return False
        self._cache.pop(safe, None)
        path = self.folder / f"{safe}.txt"
        try:
            if path.is_file():
                path.unlink()
                return True
        except OSError:
            return False
        return False

    # ── بررسی / نمایش ───────────────────────────────────────
    def age_days(self, cookie: CookieFile) -> int:
        return max(0, int((time.time() - cookie.modified) // 86400))

    def problems(self, cookie: CookieFile) -> list[str]:
        """بررسی سلامت فایل کوکی — لیست خالی یعنی سالم است."""
        if not cookie.path.is_file():
            return ["file missing"]
        try:
            data = cookie.path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            return [str(exc)[:120]]

        problems: list[str] = []
        lines = _cookie_lines(data)
        if not lines:
            problems.append("no cookie lines")
        if not parse_domains(data):
            problems.append("no domains")
        if lines and cookie.expired >= len(lines):
            problems.append("all cookies expired")
        return problems

    def describe(self, cookie: CookieFile) -> str:
        """خط خلاصه برای پنل ادمین."""
        domains = ", ".join(cookie.domains[:3]) or "—"
        if len(cookie.domains) > 3:
            domains += "…"
        return (
            f"<b>{human.esc(cookie.name)}</b> · {cookie.size / 1024:.1f}KB · "
            f"{self.age_days(cookie)}d · <code>{human.esc(domains)}</code>"
        )
