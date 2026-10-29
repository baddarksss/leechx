"""مدل‌های دیتابیس."""
from __future__ import annotations

import time

from sqlalchemy import BigInteger, Boolean, Float, Index, Integer, String, Text, false
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> int:
    return int(time.time())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lang: Mapped[str] = mapped_column(String(8), default="fa")
    language_selected: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    downloads: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    uploads: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    default_mode: Mapped[str] = mapped_column(
        String(16), default="video", server_default="video", nullable=False
    )
    default_destination: Mapped[str] = mapped_column(
        String(16), default="telegram", server_default="telegram", nullable=False
    )
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    last_seen: Mapped[int] = mapped_column(Integer, default=now)


class Admin(Base):
    __tablename__ = "admins"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    kind: Mapped[str] = mapped_column(String(16), default="link")   # link | direct
    url: Mapped[str] = mapped_column(Text)
    selector: Mapped[str] = mapped_column(String(64), default="")
    quality: Mapped[str] = mapped_column(String(32), default="")
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now, index=True)
    started_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finished_at: Mapped[int | None] = mapped_column(Integer, nullable=True)


Index("ix_jobs_user_created", Job.user_id, Job.created_at)


class SharedFile(Base):
    __tablename__ = "shared_files"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    path: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    downloads: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    last_access: Mapped[int | None] = mapped_column(Integer, nullable=True)


class MediaCacheEntry(Base):
    """Telegram-group cache, scoped to the requester for private-source safety."""
    __tablename__ = "media_cache"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    group_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    mode: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[int] = mapped_column(Integer, default=now)


class TrafficCounter(Base):
    """Lifetime file-payload counters; values stay exact integer bytes."""

    __tablename__ = "traffic_counters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    source_download_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    telegram_receive_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    telegram_upload_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    direct_link_serve_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )


class StatEvent(Base):
    """رویدادهای سبک برای آمار — عمداً بدون کلید خارجی تا با حذف کاربر پاک نشود."""
    __tablename__ = "stat_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[int] = mapped_column(Integer, default=now, index=True)


class LogEntry(Base):
    """خطای/رویداد مهم برای بخش «لاگ‌ها» و تاپیک لاگ گروه ادمین."""

    __tablename__ = "bot_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), index=True, default="ERROR")
    source: Mapped[str] = mapped_column(String(64), default="bot")
    message: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now, index=True)


class Report(Base):
    """گزارش کاربر: سایت پشتیبانی‌نشده یا پیام به ادمین."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), index=True, default="unsupported")
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now, index=True)


class DebugToken(Base):
    """توکن موقت دسترسی عیب‌یابی — فقط هش ذخیره می‌شود."""

    __tablename__ = "debug_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(64), default="")
    scopes: Mapped[str] = mapped_column(String(64), default="read")
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    last_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

