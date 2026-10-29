"""Owner-facing startup/restart notification behavior."""
from __future__ import annotations

import pytest

from app.bot.app import _notify_startup_owners
from app.version import __version__


@pytest.mark.asyncio
async def test_startup_notification_reaches_each_unique_owner():
    class Bot:
        def __init__(self):
            self.sent = []

        async def send_message(self, *, chat_id, text):
            self.sent.append((chat_id, text))

    bot = Bot()
    await _notify_startup_owners(bot, [77, 42, 77, 0])

    assert [chat_id for chat_id, _ in bot.sent] == [42, 77]
    assert all(__version__ in body for _, body in bot.sent)
    assert all("ready" in body.lower() or "آماده" in body or "готов" in body for _, body in bot.sent)


@pytest.mark.asyncio
async def test_unreachable_owner_does_not_break_other_startup_notifications():
    class Bot:
        def __init__(self):
            self.attempted = []

        async def send_message(self, *, chat_id, text):
            self.attempted.append(chat_id)
            if chat_id == 42:
                raise RuntimeError("owner chat unavailable")

    bot = Bot()
    await _notify_startup_owners(bot, [42, 77])
    assert bot.attempted == [42, 77]
