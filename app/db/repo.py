"""توابع دسترسی به داده — تنها جایی که کوئری نوشته می‌شود."""
from __future__ import annotations

import time
from collections.abc import Sequence

from sqlalchemy import delete, func, select, update

from app.db.base import session
from app.db.models import Admin, Job, Setting, SharedFile, StatEvent, User


# ── کاربران ────────────────────────────────────────────────
async def upsert_user(
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    lang: str | None = None,
) -> User:
    ts = int(time.time())
    async with session() as s:
        user = await s.get(User, user_id)
        if user is None:
            user = User(
                id=user_id,
                username=username,
                first_name=first_name,
                lang=lang or "fa",
                created_at=ts,
                last_seen=ts,
            )
            s.add(user)
            await s.commit()
            return user

        # نوشتن روی دیتابیس در هر پیام برای ربات شلوغ گران است؛
        # فقط وقتی چیزی عوض شده یا ۲ دقیقه گذشته باشد به‌روزرسانی می‌کنیم.
        changed = (
            (username is not None and user.username != username)
            or (first_name is not None and user.first_name != first_name)
            or (lang is not None and user.lang != lang)
            or (ts - user.last_seen) > 120
        )
        if changed:
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
            if lang:
                user.lang = lang
            user.last_seen = ts
            await s.commit()
        return user


async def get_user(user_id: int) -> User | None:
    async with session() as s:
        return await s.get(User, user_id)


async def set_lang(user_id: int, lang: str) -> None:
    async with session() as s:
        await s.execute(update(User).where(User.id == user_id).values(lang=lang))
        await s.commit()


async def set_banned(user_id: int, banned: bool) -> None:
    async with session() as s:
        await s.execute(update(User).where(User.id == user_id).values(is_banned=banned))
        await s.commit()


async def bump_downloads(user_id: int) -> None:
    async with session() as s:
        await s.execute(update(User).where(User.id == user_id).values(downloads=User.downloads + 1))
        await s.commit()


async def count_users() -> int:
    async with session() as s:
        return int((await s.scalar(select(func.count()).select_from(User))) or 0)


async def all_user_ids() -> list[int]:
    async with session() as s:
        return [row[0] for row in (await s.execute(select(User.id))).all()]


async def find_user_by_username(username: str) -> User | None:
    handle = (username or "").strip().lstrip("@").lower()
    if not handle:
        return None
    async with session() as s:
        return (
            await s.execute(select(User).where(func.lower(User.username) == handle).limit(1))
        ).scalars().first()


# ── ادمین‌ها ───────────────────────────────────────────────
async def add_admin(user_id: int, added_by: int | None, note: str | None = None) -> None:
    async with session() as s:
        if await s.get(Admin, user_id) is None:
            s.add(Admin(user_id=user_id, added_by=added_by, note=note))
            await s.commit()


async def remove_admin(user_id: int) -> bool:
    async with session() as s:
        row = await s.get(Admin, user_id)
        if row is None:
            return False
        await s.delete(row)
        await s.commit()
        return True


async def is_db_admin(user_id: int) -> bool:
    async with session() as s:
        return await s.get(Admin, user_id) is not None


async def list_admins() -> Sequence[Admin]:
    async with session() as s:
        return (await s.execute(select(Admin).order_by(Admin.created_at))).scalars().all()


async def count_admins() -> int:
    async with session() as s:
        return int((await s.scalar(select(func.count()).select_from(Admin))) or 0)


# ── تنظیمات زمان اجرا ─────────────────────────────────────
async def get_setting(key: str) -> str | None:
    async with session() as s:
        row = await s.get(Setting, key)
        return row.value if row else None


async def set_setting(key: str, value: str) -> None:
    async with session() as s:
        row = await s.get(Setting, key)
        if row is None:
            s.add(Setting(key=key, value=str(value), updated_at=int(time.time())))
        else:
            row.value = str(value)
            row.updated_at = int(time.time())
        await s.commit()


async def all_settings() -> dict[str, str]:
    async with session() as s:
        rows = (await s.execute(select(Setting))).scalars().all()
        return {r.key: r.value for r in rows}


# ── کارها ──────────────────────────────────────────────────
async def create_job(
    job_id: str,
    user_id: int,
    chat_id: int,
    url: str,
    kind: str = "link",
    selector: str = "",
    quality: str = "",
    title: str | None = None,
) -> None:
    async with session() as s:
        s.add(
            Job(
                id=job_id,
                user_id=user_id,
                chat_id=chat_id,
                url=url,
                kind=kind,
                selector=selector,
                quality=quality,
                title=title,
                status="queued",
            )
        )
        await s.commit()


async def update_job(job_id: str, **fields) -> None:
    if not fields:
        return
    async with session() as s:
        await s.execute(update(Job).where(Job.id == job_id).values(**fields))
        await s.commit()


async def get_job(job_id: str) -> Job | None:
    async with session() as s:
        return await s.get(Job, job_id)


async def recent_jobs(limit: int = 10) -> Sequence[Job]:
    async with session() as s:
        return (
            await s.execute(select(Job).order_by(Job.created_at.desc()).limit(limit))
        ).scalars().all()


async def jobs_count_today() -> tuple[int, int, int]:
    """(کل امروز، موفق، ناموفق)"""
    start = int(time.time()) - 86400
    async with session() as s:
        total = int((await s.scalar(select(func.count()).select_from(Job).where(Job.created_at >= start))) or 0)
        done = int((await s.scalar(
            select(func.count()).select_from(Job).where(Job.created_at >= start, Job.status == "done")
        )) or 0)
        failed = int((await s.scalar(
            select(func.count()).select_from(Job).where(Job.created_at >= start, Job.status == "failed")
        )) or 0)
    return total, done, failed


async def active_jobs() -> Sequence[Job]:
    async with session() as s:
        return (
            await s.execute(select(Job).where(Job.status.in_(("queued", "running"))))
        ).scalars().all()


async def fail_stale_jobs() -> int:
    """کارهایی که وسط اجرا ربات ری‌استارت شده را ناموفق علامت می‌زند."""
    async with session() as s:
        res = await s.execute(
            update(Job)
            .where(Job.status.in_(("queued", "running")))
            .values(status="failed", error="restart", finished_at=int(time.time()))
        )
        await s.commit()
        return int(res.rowcount or 0)


# ── فایل‌های به‌اشتراک‌گذاشته ──────────────────────────────
async def create_shared(
    file_id: str, user_id: int, path: str, name: str, mime: str, size: int, ttl_seconds: int
) -> SharedFile:
    ts = int(time.time())
    async with session() as s:
        row = SharedFile(
            id=file_id,
            user_id=user_id,
            path=path,
            name=name,
            mime=mime,
            size=size,
            created_at=ts,
            expires_at=ts + ttl_seconds,
        )
        s.add(row)
        await s.commit()
        return row


async def get_shared(file_id: str) -> SharedFile | None:
    async with session() as s:
        return await s.get(SharedFile, file_id)


async def touch_shared(file_id: str) -> None:
    async with session() as s:
        await s.execute(
            update(SharedFile)
            .where(SharedFile.id == file_id)
            .values(downloads=SharedFile.downloads + 1, last_access=int(time.time()))
        )
        await s.commit()


async def expired_shared(now_ts: int | None = None) -> Sequence[SharedFile]:
    now_ts = now_ts or int(time.time())
    async with session() as s:
        return (
            await s.execute(select(SharedFile).where(SharedFile.expires_at <= now_ts))
        ).scalars().all()


async def delete_shared(file_id: str) -> None:
    async with session() as s:
        await s.execute(delete(SharedFile).where(SharedFile.id == file_id))
        await s.commit()


async def count_shared() -> int:
    async with session() as s:
        return int((await s.scalar(select(func.count()).select_from(SharedFile))) or 0)


async def shared_total_size() -> int:
    async with session() as s:
        return int((await s.scalar(select(func.coalesce(func.sum(SharedFile.size), 0)))) or 0)


# ── آمار ───────────────────────────────────────────────────
async def log_event(user_id: int, kind: str, value: float = 1.0) -> None:
    async with session() as s:
        s.add(StatEvent(user_id=user_id, kind=kind, value=value))
        await s.commit()


async def events_since(ts: int) -> dict[str, float]:
    async with session() as s:
        rows = (
            await s.execute(
                select(StatEvent.kind, func.sum(StatEvent.value))
                .where(StatEvent.created_at >= ts)
                .group_by(StatEvent.kind)
            )
        ).all()
        return {k: float(v or 0) for k, v in rows}


async def user_events_since(user_id: int, kind: str, ts: int) -> float:
    """مجموع یک رویداد برای یک کاربر — پایهٔ سهمیهٔ روزانه."""
    async with session() as s:
        total = await s.scalar(
            select(func.coalesce(func.sum(StatEvent.value), 0)).where(
                StatEvent.user_id == user_id,
                StatEvent.kind == kind,
                StatEvent.created_at >= ts,
            )
        )
        return float(total or 0)


async def purge_events(older_than_days: int = 90) -> int:
    cutoff = int(time.time()) - older_than_days * 86400
    async with session() as s:
        res = await s.execute(delete(StatEvent).where(StatEvent.created_at < cutoff))
        await s.commit()
        return int(res.rowcount or 0)
