"""تنظیمات قابل‌تغییر در زمان اجرا (از پنل ادمین).

env فقط مقادیر اولیه را می‌دهد؛ مقدار نهایی از جدول settings خوانده می‌شود
تا ادمین بدون ری‌استارت بتواند رفتار ربات را عوض کند.
"""
from __future__ import annotations

from typing import Any

from app.config import Config
from app.core.human import parse_bool, parse_float, parse_int
from app.db import repo

# کلید → (نوع، برچسب فارسی)
SCHEMA: dict[str, tuple[str, str]] = {
    "link_ttl_hours": ("float", "اعتبار لینک (ساعت)"),
    "max_upload_mb": ("int", "حداکثر حجم آپلود (MB)"),
    "max_link_mb": ("int", "حداکثر حجم فایل لینک (MB)"),
    "rate_limit_seconds": ("float", "فاصلهٔ بین درخواست‌ها (ثانیه)"),
    "daily_quota": ("int", "سهمیهٔ روزانه (0=بی‌نهایت)"),
    "maintenance": ("bool", "حالت تعمیر"),
    "nsfw_enabled": ("bool", "سایت‌های بزرگسال"),
}


class RuntimeSettings:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._cache: dict[str, str] = {}

    async def load(self) -> None:
        self._cache = await repo.all_settings()

    # ── خواندن ─────────────────────────────────────────────
    def _raw(self, key: str) -> str | None:
        return self._cache.get(key)

    def _default(self, key: str) -> Any:
        return {
            "link_ttl_hours": self.cfg.link_ttl_hours,
            "max_upload_mb": self.cfg.max_upload_mb,
            "max_link_mb": self.cfg.max_link_file_mb,
            "rate_limit_seconds": self.cfg.rate_limit_seconds,
            "daily_quota": self.cfg.daily_quota,
            "maintenance": False,
            "nsfw_enabled": self.cfg.nsfw_enabled,
        }.get(key)

    def get_float(self, key: str) -> float:
        return parse_float(self._raw(key), float(self._default(key) or 0))

    def get_int(self, key: str) -> int:
        return parse_int(self._raw(key), int(self._default(key) or 0))

    def get_bool(self, key: str) -> bool:
        default = bool(self._default(key))
        raw = self._raw(key)
        return parse_bool(raw, default) if raw is not None else default

    # ── ویژگی‌های پرکاربرد ────────────────────────────────
    @property
    def ttl_hours(self) -> float:
        return max(0.05, self.get_float("link_ttl_hours"))

    @property
    def ttl_seconds(self) -> int:
        return int(self.ttl_hours * 3600)

    @property
    def max_upload_bytes(self) -> int:
        return max(1, self.get_int("max_upload_mb")) * 1024 * 1024

    @property
    def max_link_bytes(self) -> int:
        return max(1, self.get_int("max_link_mb")) * 1024 * 1024

    @property
    def rate_limit_seconds(self) -> float:
        return max(0.0, self.get_float("rate_limit_seconds"))

    @property
    def daily_quota(self) -> int:
        return max(0, self.get_int("daily_quota"))

    @property
    def maintenance(self) -> bool:
        return self.get_bool("maintenance")

    @property
    def nsfw_enabled(self) -> bool:
        return self.get_bool("nsfw_enabled")

    # ── نوشتن ──────────────────────────────────────────────
    async def set(self, key: str, value: Any) -> None:
        if key not in SCHEMA:
            raise KeyError(key)
        if isinstance(value, bool):
            text = "1" if value else "0"
        else:
            text = str(value).strip()
        await repo.set_setting(key, text)
        self._cache[key] = text

    async def toggle(self, key: str) -> bool:
        new_value = not self.get_bool(key)
        await self.set(key, new_value)
        return new_value

    def label(self, key: str) -> str:
        return SCHEMA.get(key, (None, key))[1]

    def snapshot(self) -> dict[str, Any]:
        return {
            "link_ttl_hours": self.ttl_hours,
            "max_upload_mb": self.max_upload_bytes // (1024 * 1024),
            "max_link_mb": self.max_link_bytes // (1024 * 1024),
            "rate_limit_seconds": self.rate_limit_seconds,
            "daily_quota": self.daily_quota,
            "maintenance": self.maintenance,
            "nsfw_enabled": self.nsfw_enabled,
        }
