"""توابع دسترسی به داده — تنها جایی که کوئری نوشته می‌شود."""
from __future__ import annotations

import time
from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.db.base import session
from app.db.models import (
    Admin,
    DebugToken,
    Job,
    LogEntry,
    MediaCacheEntry,
    Report,
    Setting,
    SharedFile,
    StatEvent,
    TrafficCounter,
    User,
)


# ── آرشیو کش رسانه در سوپرگروه ─────────────────────────────
async def get_media_cache(key: str, user_id: int, group_id: int) -> MediaCacheEntry | None:
    async with session() as s:
        return (await s.execute(
            select(MediaCacheEntry).where(
                MediaCacheEntry.cache_key == key,
                MediaCacheEntry.user_id == user_id,
                MediaCacheEntry.group_id == group_id,
                MediaCacheEntry.expires_at > int(time.time()),
            )
        )).scalar_one_or_none()


async def put_media_cache(
    key: str, user_id: int, group_id: int, message_id: int,
    mode: str, filename: str, size: int, ttl: int,
) -> None:
    ts = int(time.time())
    async with session() as s:
        entry = await s.get(MediaCacheEntry, key)
        if entry is None:
            entry = MediaCacheEntry(
                cache_key=key, user_id=user_id, group_id=group_id,
                message_id=message_id, mode=mode, filename=filename,
                size=size, created_at=ts, expires_at=ts + ttl,
            )
            s.add(entry)
        else:
            entry.user_id = user_id
            entry.group_id = group_id
            entry.message_id = message_id
            entry.mode = mode
            entry.filename = filename
            entry.size = size
            entry.expires_at = ts + ttl
        await s.commit()


async def delete_media_cache(key: str) -> None:
    async with session() as s:
        await s.execute(delete(MediaCacheEntry).where(MediaCacheEntry.cache_key == key))
        await s.commit()


async def expired_media_cache(now_ts: int | None = None) -> Sequence[MediaCacheEntry]:
    ts = int(time.time()) if now_ts is None else now_ts
    async with session() as s:
        return (await s.execute(
            select(MediaCacheEntry).where(MediaCacheEntry.expires_at <= ts)
        )).scalars().all()


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


async def set_lang(user_id: int, lang: str, *, selected: bool = True) -> None:
    values = {"lang": lang}
    if selected:
        values["language_selected"] = True
    async with session() as s:
        await s.execute(update(User).where(User.id == user_id).values(**values))
        await s.commit()


async def set_banned(user_id: int, banned: bool) -> None:
    async with session() as s:
        await s.execute(update(User).where(User.id == user_id).values(is_banned=banned))
        await s.commit()


async def bump_downloads(user_id: int) -> None:
    async with session() as s:
        await s.execute(update(User).where(User.id == user_id).values(downloads=User.downloads + 1))
        await s.commit()


async def bump_uploads(user_id: int) -> None:
    async with session() as s:
        await s.execute(update(User).where(User.id == user_id).values(uploads=User.uploads + 1))
        await s.commit()


async def set_user_preferences(
    user_id: int,
    *,
    default_mode: str,
    default_destination: str,
) -> None:
    if default_mode not in {"video", "document"}:
        raise ValueError("default_mode must be 'video' or 'document'")
    if default_destination not in {"telegram", "link"}:
        raise ValueError("default_destination must be 'telegram' or 'link'")
    async with session() as s:
        user = await s.get(User, user_id)
        if user is None:
            user = User(
                id=user_id,
                default_mode=default_mode,
                default_destination=default_destination,
            )
            s.add(user)
        else:
            user.default_mode = default_mode
            user.default_destination = default_destination
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


async def user_shared(user_id: int, limit: int = 5, offset: int = 0) -> Sequence[SharedFile]:
    now = int(time.time())
    async with session() as s:
        return (await s.execute(
            select(SharedFile).where(
                SharedFile.user_id == user_id, SharedFile.expires_at > now
            ).order_by(SharedFile.created_at.desc(), SharedFile.id.desc())
            .limit(max(1, min(limit, 20))).offset(max(0, offset))
        )).scalars().all()


async def count_user_shared(user_id: int) -> int:
    now = int(time.time())
    async with session() as s:
        return int(await s.scalar(
            select(func.count()).select_from(SharedFile).where(
                SharedFile.user_id == user_id, SharedFile.expires_at > now
            )
        ) or 0)


async def get_user_shared(file_id: str, user_id: int) -> SharedFile | None:
    async with session() as s:
        return (await s.execute(
            select(SharedFile).where(
                SharedFile.id == file_id, SharedFile.user_id == user_id,
                SharedFile.expires_at > int(time.time()),
            )
        )).scalar_one_or_none()


async def pop_user_shared(file_id: str, user_id: int) -> str | None:
    """Atomically revoke one owned, unexpired link; return the stored path."""
    async with session() as s:
        result = await s.execute(
            delete(SharedFile).where(
                SharedFile.id == file_id,
                SharedFile.user_id == user_id,
                SharedFile.expires_at > int(time.time()),
            ).returning(SharedFile.path)
        )
        row = result.first()
        await s.commit()
        return row[0] if row is not None else None


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


# ── ترافیک رسانه ───────────────────────────────────────────
TRAFFIC_FIELDS = (
    "source_download_bytes",
    "telegram_receive_bytes",
    "telegram_upload_bytes",
    "direct_link_serve_bytes",
)


async def record_traffic(
    *,
    source_download_bytes: int = 0,
    telegram_receive_bytes: int = 0,
    telegram_upload_bytes: int = 0,
    direct_link_serve_bytes: int = 0,
) -> None:
    """Atomically add file-payload bytes to lifetime counters.

    These are content bytes, not HTTP headers or other protocol overhead.
    ``init_db`` creates the singleton row before the bot starts serving traffic.
    """
    amounts = {
        "source_download_bytes": max(0, int(source_download_bytes or 0)),
        "telegram_receive_bytes": max(0, int(telegram_receive_bytes or 0)),
        "telegram_upload_bytes": max(0, int(telegram_upload_bytes or 0)),
        "direct_link_serve_bytes": max(0, int(direct_link_serve_bytes or 0)),
    }
    changes = {key: amount for key, amount in amounts.items() if amount}
    if not changes:
        return
    async with session() as s:
        result = await s.execute(
            update(TrafficCounter)
            .where(TrafficCounter.id == 1)
            .values(**{
                key: getattr(TrafficCounter, key) + amount
                for key, amount in changes.items()
            })
        )
        if not result.rowcount:
            # Defensive recovery if a manually edited database lost the singleton.
            row = TrafficCounter(id=1, **amounts)
            s.add(row)
        await s.commit()


async def traffic_totals() -> dict[str, int]:
    """Return exact lifetime counters plus downloaded/uploaded/combined totals."""
    async with session() as s:
        row = await s.get(TrafficCounter, 1)
        values = {
            key: int(getattr(row, key, 0) or 0) if row is not None else 0
            for key in TRAFFIC_FIELDS
        }
    values["downloaded_bytes"] = (
        values["source_download_bytes"] + values["telegram_receive_bytes"]
    )
    values["uploaded_bytes"] = (
        values["telegram_upload_bytes"] + values["direct_link_serve_bytes"]
    )
    values["total_bytes"] = values["downloaded_bytes"] + values["uploaded_bytes"]
    return values


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


async def count_active_users(days: int = 7) -> int:
    """کاربرانی که در بازهٔ اخیر حداقل یک‌بار ربات را باز کرده‌اند."""
    cutoff = int(time.time()) - max(1, days) * 86400
    async with session() as s:
        return int(
            (
                await s.scalar(
                    select(func.count()).select_from(User).where(User.last_seen >= cutoff)
                )
            )
            or 0
        )


async def count_banned_users() -> int:
    async with session() as s:
        return int(
            (
                await s.scalar(
                    select(func.count()).select_from(User).where(User.is_banned.is_(True))
                )
            )
            or 0
        )


async def count_active_shared() -> int:
    """لینک‌های مستقیمی که هنوز منقضی نشده‌اند."""
    now_ts = int(time.time())
    async with session() as s:
        return int(
            (
                await s.scalar(
                    select(func.count())
                    .select_from(SharedFile)
                    .where(SharedFile.expires_at > now_ts)
                )
            )
            or 0
        )


async def count_active_job_users() -> int:
    """تعداد کاربرانی که همین حالا کار در صف/در حال اجرا دارند."""
    async with session() as s:
        return int(
            (
                await s.scalar(
                    select(func.count(func.distinct(Job.user_id))).where(
                        Job.status.in_(("queued", "running"))
                    )
                )
            )
            or 0
        )


# ── لاگ‌ها ─────────────────────────────────────────────────
async def add_log(
    level: str,
    source: str,
    message: str,
    user_id: int | None = None,
) -> LogEntry:
    async with session() as s:
        row = LogEntry(
            level=(level or "ERROR").upper()[:16],
            source=(source or "bot")[:64],
            message=(message or "")[:4000],
            user_id=user_id,
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


async def recent_logs(limit: int = 20) -> Sequence[LogEntry]:
    async with session() as s:
        return (
            await s.execute(select(LogEntry).order_by(LogEntry.created_at.desc()).limit(limit))
        ).scalars().all()


async def clear_logs() -> int:
    async with session() as s:
        res = await s.execute(delete(LogEntry))
        await s.commit()
        return int(res.rowcount or 0)


# ── گزارش‌ها ───────────────────────────────────────────────
async def add_report(
    kind: str,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    text: str = "",
    url: str | None = None,
) -> Report:
    async with session() as s:
        row = Report(
            kind=(kind or "unsupported")[:16],
            user_id=user_id,
            username=username,
            first_name=first_name,
            text=(text or "")[:4000],
            url=url,
            status="open",
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


async def recent_reports(limit: int = 15, status: str | None = "open") -> Sequence[Report]:
    query = select(Report).order_by(Report.created_at.desc()).limit(limit)
    if status:
        query = query.where(Report.status == status)
    async with session() as s:
        return (await s.execute(query)).scalars().all()


async def count_open_reports() -> int:
    async with session() as s:
        return int(
            (
                await s.scalar(
                    select(func.count())
                    .select_from(Report)
                    .where(Report.status == "open")
                )
            )
            or 0
        )


async def set_report_status(report_id: int, status: str = "closed") -> bool:
    async with session() as s:
        row = await s.get(Report, report_id)
        if row is None:
            return False
        row.status = status
        await s.commit()
        return True


# ── توکن‌های عیب‌یابی ──────────────────────────────────────
async def create_debug_token(
    token_hash: str,
    label: str,
    scopes: str,
    created_by: int,
    expires_at: int,
) -> DebugToken:
    async with session() as s:
        row = DebugToken(
            token_hash=token_hash,
            label=(label or "")[:64],
            scopes=(scopes or "read")[:64],
            created_by=created_by,
            created_at=int(time.time()),
            expires_at=int(expires_at),
            uses=0,
            revoked=False,
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


async def get_debug_token_by_hash(token_hash: str) -> DebugToken | None:
    async with session() as s:
        return (
            await s.execute(
                select(DebugToken).where(DebugToken.token_hash == token_hash).limit(1)
            )
        ).scalars().first()


async def get_debug_token(token_id: int) -> DebugToken | None:
    async with session() as s:
        return await s.get(DebugToken, token_id)


async def active_debug_tokens() -> Sequence[DebugToken]:
    now = int(time.time())
    async with session() as s:
        return (
            await s.execute(
                select(DebugToken)
                .where(
                    DebugToken.revoked.is_(False),
                    DebugToken.expires_at > now,
                )
                .order_by(DebugToken.created_at.desc())
            )
        ).scalars().all()


async def touch_debug_token(token_id: int) -> None:
    async with session() as s:
        await s.execute(
            update(DebugToken)
            .where(DebugToken.id == token_id)
            .values(uses=DebugToken.uses + 1, last_used=int(time.time()))
        )
        await s.commit()


async def revoke_debug_token(token_id: int) -> bool:
    async with session() as s:
        row = await s.get(DebugToken, token_id)
        if row is None:
            return False
        row.revoked = True
        await s.commit()
        return True


async def revoke_all_debug_tokens() -> int:
    async with session() as s:
        res = await s.execute(
            update(DebugToken).where(DebugToken.revoked.is_(False)).values(revoked=True)
        )
        await s.commit()
        return int(res.rowcount or 0)


async def purge_debug_tokens(now_ts: int | None = None) -> int:
    """توکن‌های منقضی/باطل‌شده را برای تمیز ماندن جدول حذف می‌کند."""
    ts = int(time.time()) if now_ts is None else now_ts
    async with session() as s:
        res = await s.execute(
            delete(DebugToken).where(
                (DebugToken.expires_at <= ts) | (DebugToken.revoked.is_(True))
            )
        )
        await s.commit()
        return int(res.rowcount or 0)


# ── مالک اول ───────────────────────────────────────────────
async def claim_owner(user_id: int) -> tuple[int, bool]:
    """اولین کسی که /start بزند مالک می‌شود؛ بقیه مالک را تغییر نمی‌دهند.

    درج با کلید یکتا انجام می‌شود تا اگر دو نفر هم‌زمان /start بزنند فقط یکی
    مالک شود (روی SQLite و Postgres یکسان کار می‌کند).

    خروجی: (شناسهٔ مالک، آیا همین کاربر الان مالک شد)
    """
    async with session() as s:
        existing = await s.get(Setting, "owner_id")
        if existing is not None and existing.value.strip().isdigit():
            return int(existing.value.strip()), False
        if existing is None:
            s.add(Setting(key="owner_id", value=str(user_id), updated_at=int(time.time())))
            try:
                await s.commit()
                return user_id, True
            except IntegrityError:
                await s.rollback()
        else:
            existing.value = str(user_id)
            existing.updated_at = int(time.time())
            await s.commit()
            return user_id, True

        row = await s.get(Setting, "owner_id")
        if row is not None and row.value.strip().isdigit():
            return int(row.value.strip()), False
        return user_id, False
