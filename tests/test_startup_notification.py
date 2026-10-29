"""Owner-facing startup/restart notification behavior."""
from __future__ import annotations

import pytest

from app.bot.app import _notify_startup_owners
from app.version import __version__


@pytest.mark.asyncio
async def test_startup_notification_reaches_each_unique_owner_in_persian(monkeypatch):
    async def unexpected_lookup(_user_id):
        raise AssertionError("admin notification must not consult a saved user locale")

    monkeypatch.setattr("app.bot.app.repo.get_user", unexpected_lookup)

    class Bot:
        def __init__(self):
            self.sent = []

        async def send_message(self, *, chat_id, text):
            self.sent.append((chat_id, text))

    bot = Bot()
    await _notify_startup_owners(bot, [77, 42, 77, 0])

    assert [chat_id for chat_id, _ in bot.sent] == [42, 77]
    assert all(__version__ in body for _, body in bot.sent)
    assert bot.sent[0][1] == bot.sent[1][1]
    assert "The bot is ready" not in bot.sent[0][1]
    assert "готов к работе" not in bot.sent[0][1]
    assert "ربات پس از راه‌اندازی مجدد آماده است" in bot.sent[0][1]


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
