"""Serialize stateful updates but acknowledge callback taps before queued work."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress

from telegram import Update
from telegram.ext import BaseUpdateProcessor

from app.bot.common import safe_answer

log = logging.getLogger("leechx.update_processor")
CALLBACK_ACK_SECONDS = 0.35
SLOW_CALLBACK_SECONDS = 2.0


async def _ack_if_slow(query, user_id: int | None) -> None:
    """Stop Telegram's spinner even while an update waits for the per-user lock/gate."""
    await asyncio.sleep(CALLBACK_ACK_SECONDS)
    if await safe_answer(query):
        log.warning("callback acknowledged by watchdog before handler; user_id=%s", user_id)


class UserOrderedUpdateProcessor(BaseUpdateProcessor):
    def __init__(self, limit: int = 48) -> None:
        super().__init__(limit)
        self._locks: dict[int, tuple[asyncio.Lock, int]] = {}

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        self._locks.clear()

    async def do_process_update(self, update: object, coroutine) -> None:
        started = time.monotonic()
        is_update = isinstance(update, Update)
        query = update.callback_query if is_update else None
        user = update.effective_user if is_update else None
        user_id = user.id if user is not None else None
        watchdog = (
            asyncio.create_task(_ack_if_slow(query, user_id), name="callback-ack-watchdog")
            if query is not None
            else None
        )

        try:
            if user_id is None:
                await coroutine
                return

            existing = self._locks.get(user_id)
            lock, refs = existing if existing else (asyncio.Lock(), 0)
            self._locks[user_id] = (lock, refs + 1)
            wait_started = time.monotonic()
            try:
                async with lock:
                    wait_seconds = time.monotonic() - wait_started
                    if query is not None and wait_seconds >= CALLBACK_ACK_SECONDS:
                        log.warning(
                            "callback waited %.3fs for same-user update lock; user_id=%s",
                            wait_seconds,
                            user_id,
                        )
                    await coroutine
            finally:
                current = self._locks.get(user_id)
                if current is not None:
                    current_lock, refs = current
                    if refs == 1:
                        self._locks.pop(user_id, None)
                    else:
                        self._locks[user_id] = (current_lock, refs - 1)
        finally:
            if watchdog is not None:
                watchdog.cancel()
                with suppress(asyncio.CancelledError):
                    await watchdog
            if query is not None:
                elapsed = time.monotonic() - started
                if elapsed >= SLOW_CALLBACK_SECONDS:
                    log.warning(
                        "callback update processing took %.3fs; user_id=%s",
                        elapsed,
                        user_id,
                    )
