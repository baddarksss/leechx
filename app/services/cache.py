"""Two real caches: short-lived per-user metadata and Telegram media archives.

Telegram media archives use copy_message (no file re-upload on cache hit).
Keep all private/cookie-dependent content scoped to its original user.
Never store token-bearing URLs or credentials in group messages or cache keys.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from telegram.error import TelegramError

from app.db import repo

if TYPE_CHECKING:
    from app.services.admin_group import AdminGroup

log = logging.getLogger("leechx.cache")
PROBE_TTL = 600
MEDIA_TTL = 24 * 3600  # Telegram deleteMessage normally allows only ~48 hours
MAX_PROBES = 1000
PUBLIC_CACHE_USER_ID = 0  # Telegram user IDs are positive; 0 marks public shared media.


def fingerprint(user_id: int, url: str, selector: str, mode: str, custom_name: str) -> str:
    # Preserve the original compact per-user serialization so existing cache rows keep hitting.
    raw = json.dumps(
        [user_id, url, selector, mode, custom_name], ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def shared_fingerprint(url: str, selector: str, mode: str, custom_name: str) -> str:
    """Cache key for explicitly approved public, cookie-free media."""
    raw = json.dumps(
        ["public", url, selector, mode, custom_name], ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def safe_source(url: str) -> str:
    """Avoid retaining signed query parameters or embedded credentials in group logs."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        return urlunsplit((parts.scheme, host, parts.path[:120], "", ""))
    except ValueError:
        return "(invalid URL)"


class CacheHub:
    def __init__(self, group: AdminGroup) -> None:
        self.group = group
        self._probes: OrderedDict[tuple[int, str], tuple[float, Any]] = OrderedDict()
        self._inflight: dict[tuple[int, str], asyncio.Task] = {}

    async def probe(self, user_id: int, url: str, fetch):
        key = (user_id, url)
        now = time.monotonic()
        item = self._probes.get(key)
        if item and item[0] > now:
            self._probes.move_to_end(key)
            await self.group.cache_event("metadata", "HIT", safe_source(url))
            return item[1]
        if item:
            self._probes.pop(key, None)
        existing = self._inflight.get(key)
        if existing:
            return await asyncio.shield(existing)
        async def do_fetch():
            info = await fetch(url)
            self._probes[key] = (time.monotonic() + PROBE_TTL, info)
            self._probes.move_to_end(key)
            while len(self._probes) > MAX_PROBES:
                self._probes.popitem(last=False)
            return info
        task = asyncio.create_task(do_fetch())
        self._inflight[key] = task
        try:
            result = await asyncio.shield(task)
            await self.group.cache_event("metadata", "MISS/STORE", safe_source(url))
            return result
        finally:
            if self._inflight.get(key) is task:
                self._inflight.pop(key, None)

    async def cached_delivery(self, bot, task) -> int | None:
        """حجم فایلِ تحویل‌شده از کش، یا ``None`` اگر نسخهٔ کش‌شده‌ای نبود."""
        group_id = self.group.chat_id
        if not group_id or not self.group.topic_id("cache"):
            return None
        shared = bool(getattr(task, "public_cache", False))
        if shared:
            key = shared_fingerprint(
                task.url, task.option.selector, task.mode, task.custom_name
            )
            row = await repo.get_media_cache(key, PUBLIC_CACHE_USER_ID, group_id)
            if row is None:
                # Keep same-user cache entries from before cross-user sharing was enabled.
                key = fingerprint(
                    task.user_id, task.url, task.option.selector, task.mode, task.custom_name
                )
                row = await repo.get_media_cache(key, task.user_id, group_id)
        else:
            key = fingerprint(
                task.user_id, task.url, task.option.selector, task.mode, task.custom_name
            )
            row = await repo.get_media_cache(key, task.user_id, group_id)
        if row is None:
            return None
        if task.cancel.is_set():
            return None
        try:
            from app.core import human
            from app.core.caption import build_caption
            copied = await bot.copy_message(
                chat_id=task.chat_id,
                from_chat_id=group_id,
                message_id=row.message_id,
                caption=build_caption(
                    human.safe_filename(task.custom_name or task.title or row.filename, 150),
                    task.url, "document" if task.mode == "document" else "video",
                ),
                parse_mode="HTML",
            )
        except TelegramError as exc:
            log.info("cache copy failed; redownload: %s", exc)
            await repo.delete_media_cache(key)
            await self.group.cache_event("media", "STALE", key[:12])
            return None
        if task.cancel.is_set():
            if task.chat_id > 0:
                try:
                    await bot.delete_message(task.chat_id, copied.message_id)
                except TelegramError:
                    pass
            return None
        sent = getattr(task, "sent_messages", None)
        if sent is not None:
            # Track the replayed message so NSFW auto-delete can remove it too.
            sent.append(copied)
        try:
            await self.group.cache_event("media", "HIT", key[:12])
        except Exception:
            log.debug("cache-hit logging failed", exc_info=True)
        return int(row.size)

    async def record_delivery(self, bot, task, result, uploaded_message) -> None:
        group_id = self.group.chat_id
        topic_id = self.group.topic_id("cache")
        if not group_id or not topic_id or not uploaded_message:
            return
        shared = bool(getattr(task, "public_cache", False))
        if shared and getattr(task, "custom_thumbnail", None):
            # Never reuse one user's chosen cover across users.
            return
        cache_user_id = PUBLIC_CACHE_USER_ID if shared else task.user_id
        if shared:
            key = shared_fingerprint(
                task.url, task.option.selector, task.mode, task.custom_name
            )
            caption = f"📦 کش عمومی رسانه | شناسه: {key[:12]}"
        else:
            key = fingerprint(
                task.user_id, task.url, task.option.selector, task.mode, task.custom_name
            )
            caption = f"📦 کش خصوصی رسانه | کاربر: {task.user_id} | شناسه: {key[:12]}"
        try:
            copied = await bot.copy_message(
                chat_id=group_id,
                from_chat_id=task.chat_id,
                message_id=uploaded_message.message_id,
                message_thread_id=topic_id,
                caption=caption,
            )
            await repo.put_media_cache(
                key, cache_user_id, group_id, copied.message_id,
                task.mode, result.path.name, result.size, MEDIA_TTL,
            )
            await self.group.cache_event("media", "STORE", f"{key[:12]} • {result.size} B")
        except Exception:
            log.warning("media caching failed, normal delivery already succeeded", exc_info=True)

    async def clear_expired(self, bot=None) -> int:
        """Expire DB lookup rows only; never delete messages from the group archive.

        ``bot`` remains an ignored compatibility argument for existing callers.
        """
        removed = 0
        rows = await repo.expired_media_cache()
        for row in rows:
            await repo.delete_media_cache(row.cache_key)
            removed += 1
        now = time.monotonic()
        for key in list(self._probes):
            if self._probes[key][0] <= now:
                del self._probes[key]
        return removed
