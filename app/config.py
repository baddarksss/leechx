"""تنظیمات برنامه — خوانده‌شده از متغیرهای محیطی و فایل .env.

اصل طراحی: هر چیزی که «اپراتور» باید ست کند در env است، و هر چیزی که
«ادمین» می‌خواهد در زمان اجرا عوض کند در جدول settings دیتابیس ذخیره
می‌شود (نگاه کن به ``app/services/runtime_settings.py``).
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


def _split_ids(raw: str) -> list[int]:
    out: list[int] = []
    for part in (raw or "").replace(";", ",").replace(" ", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── هویت ────────────────────────────────────────────────
    bot_token: str = ""
    owner_ids: str = ""
    admin_ids: str = ""
    bot_username: str = ""

    # ── مسیرها / دیتابیس ────────────────────────────────────
    database_url: str = ""
    data_dir: Path = BASE_DIR / "data"

    # ── لینک مستقیم ─────────────────────────────────────────
    public_base_url: str = "http://127.0.0.1:8080"
    link_secret: str = ""
    link_ttl_hours: float = 6.0

    # ── وب‌سرور ─────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8080

    # ── محدودیت‌ها ──────────────────────────────────────────
    max_upload_mb: int = 2000
    max_link_file_mb: int = 2000
    per_user_concurrency: int = 1
    workers: int = 2
    rate_limit_seconds: float = 3.0
    daily_quota: int = 0
    max_height: int = 0

    # ── دانلود ──────────────────────────────────────────────
    proxy: str = ""
    cookies_dir: Path = BASE_DIR / "data" / "cookies"
    telegram_api_url: str = ""
    telegram_api_file_url: str = ""
    telegram_api_id: str = ""
    telegram_api_hash: str = ""

    # ── رفتار ───────────────────────────────────────────────
    default_lang: str = "fa"
    nsfw_enabled: bool = True
    log_level: str = "INFO"
    cleanup_interval_seconds: int = 300

    # ── دیپلوی/بروزرسانی ────────────────────────────────────
    # دستور اختیاری برای ری‌استارت (مثلاً "docker compose restart" یا
    # "systemctl restart leechx"). خالی = جایگزینی فرآیند با os.execv.
    update_restart_command: str = ""
    # حداکثر حجم ZIP سورس برای آپلود از داخل ربات (مگابایت)
    max_source_zip_mb: int = 80
    # حداکثر عمر توکن عیب‌یابی (ساعت)
    debug_token_max_hours: int = 24

    # ── تعداد ادمین‌های قابل افزودن (0 = بی‌نهایت) ───────────
    max_admins: int = 20

    @field_validator("data_dir", "cookies_dir", mode="before")
    @classmethod
    def _expand_path(cls, v):
        if isinstance(v, str) and v.strip():
            return Path(v).expanduser()
        return v

    # ── مقادیر مشتق‌شده ─────────────────────────────────────
    @property
    def owners(self) -> list[int]:
        return _split_ids(self.owner_ids)

    @property
    def extra_admins(self) -> list[int]:
        return _split_ids(self.admin_ids)

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url.strip():
            return self.database_url.strip()
        return f"sqlite+aiosqlite:///{(self.data_dir / 'leechx.db').as_posix()}"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_link_bytes(self) -> int:
        return self.max_link_file_mb * 1024 * 1024

    @property
    def uses_local_api(self) -> bool:
        return bool(self.telegram_api_url.strip())

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.files_dir, self.tmp_dir, self.cookies_dir):
            path.mkdir(parents=True, exist_ok=True)

    def resolve_secret(self) -> str:
        """کلید امضای لینک‌ها؛ اگر ست نشده باشد یک بار ساخته و ذخیره می‌شود."""
        if self.link_secret.strip():
            return self.link_secret.strip()
        secret_file = self.data_dir / ".link_secret"
        if secret_file.exists():
            value = secret_file.read_text(encoding="utf-8").strip()
            if value:
                return value
        value = secrets.token_urlsafe(48)
        secret_file.write_text(value, encoding="utf-8")
        try:  # فقط مالک بتواند بخواند (روی ویندوز نادیده گرفته می‌شود)
            secret_file.chmod(0o600)
        except OSError:
            pass
        return value

    def validate_runtime(self) -> list[str]:
        problems: list[str] = []
        token = self.bot_token.strip()
        if not token:
            problems.append("BOT_TOKEN خالی است.")
        elif ":" not in token or len(token) < 20:
            problems.append("BOT_TOKEN شکل درستی ندارد (باید شبیه 123456:ABC-DEF... باشد).")
        # OWNER_IDS اجباری نیست: اولین /start مالک را تعیین می‌کند.
        if self.workers < 1:
            problems.append("WORKERS باید حداقل ۱ باشد.")
        if self.per_user_concurrency < 1:
            problems.append("PER_USER_CONCURRENCY باید حداقل ۱ باشد.")
        if self.port <= 0 or self.port > 65535:
            problems.append("PORT نامعتبر است.")
        return problems


@lru_cache(maxsize=1)
def get_config() -> Config:
    cfg = Config()
    cfg.ensure_dirs()
    cfg = cfg.model_copy(update={"link_secret": cfg.resolve_secret()})
    return cfg


def load_config() -> Config:
    """نسخهٔ تازه (برای تست‌ها که env را عوض می‌کنند)."""
    get_config.cache_clear()
    return get_config()
