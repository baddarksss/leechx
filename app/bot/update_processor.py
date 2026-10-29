"""Serialize a user's stateful updates while processing distinct users concurrently.

Numeric PTB concurrent_updates alone lets /cancel race with form submissions.
"""
from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import BaseUpdateProcessor


class UserOrderedUpdateProcessor(BaseUpdateProcessor):
    def __init__(self, limit: int = 48) -> None:
        super().__init__(limit)
        self._locks: dict[int, tuple[asyncio.Lock, int]] = {}

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        self._locks.clear()

    async def do_process_update(self, update: object, coroutine) -> None:
        if not isinstance(update, Update) or update.effective_user is None:
            await coroutine
            return
        uid = update.effective_user.id
        existing = self._locks.get(uid)
        lock, refs = existing if existing else (asyncio.Lock(), 0)
        self._locks[uid] = (lock, refs + 1)
        try:
            async with lock:
                await coroutine
        finally:
            current, refs = self._locks[uid]
            if refs == 1:
                del self._locks[uid]
            else:
                self._locks[uid] = (current, refs - 1)
