"""خطاهای دامنه — هر خطا یک «کلید پیام» قابل‌ترجمه دارد."""
from __future__ import annotations

import re

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def public_reason(reason: str, limit: int = 160) -> str:
    """دلیل خطا را برای نمایش به کاربر پاک می‌کند: بدون لینک و در یک خط."""
    text = _URL_RE.sub("", str(reason or ""))
    text = " ".join(text.split()).strip(" :;,.-")
    return text[:limit]


class LeechError(Exception):
    """خطای قابل‌نمایش به کاربر."""

    key = "unsupported"
    reason = ""

    def __init__(self, reason: str = "", key: str | None = None, **extra):
        super().__init__(reason or self.key)
        self.reason = reason
        if key:
            self.key = key
        self.extra = extra


class UnsupportedUrl(LeechError):
    key = "unsupported"


class ResourceNotFound(LeechError):
    key = "not_found"


class AccessDenied(LeechError):
    key = "access_denied"


class DownloadTimeout(LeechError):
    key = "download_timeout"


class IncompleteDownload(LeechError):
    key = "incomplete_download"


class NothingDownloadable(LeechError):
    key = "unsupported"


class TooLarge(LeechError):
    key = "too_big"


class FileTooLargeForLink(LeechError):
    key = "file_too_big_link"


class NotMedia(LeechError):
    key = "not_media"


class LiveUnsupported(LeechError):
    key = "live_unsupported"


class CaptchaWall(LeechError):
    key = "captcha_wall"


class LinkQuota(LeechError):
    """سقف لینک‌های فعال همزمان کاربر پر شده است."""

    key = "link_quota_full"


class JobCancelled(Exception):
    """کاربر کار را لغو کرد (کنترل‌شده، خطا نیست)."""


class Banned(LeechError):
    key = "banned"


class QuotaExceeded(LeechError):
    key = "quota_exceeded"


class RateLimited(LeechError):
    key = "rate_limited"


class Maintenance(LeechError):
    key = "maintenance"
