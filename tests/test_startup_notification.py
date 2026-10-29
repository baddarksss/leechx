"""Owner-facing startup/restart notification behavior."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.app import _notify_startup_owners
from app.version import __version__


@pytest.mark.asyncio
async def test_startup_notification_reaches_each_unique_owner(monkeypatch):
    async def get_user(user_id):
        return SimpleNamespace(lang={42: "en", 77: "ru"}.get(user_id, "fa"))

    monkeypatch.setattr("app.bot.app.repo.get_user", get_user)

    class Bot:
        def __init__(self):
            self.sent = []

        async def send_message(self, *, chat_id, text):
            self.sent.append((chat_id, text))

    bot = Bot()
    await _notify_startup_owners(bot, [77, 42, 77, 0])

    assert [chat_id for chat_id, _ in bot.sent] == [42, 77]
    assert all(__version__ in body for _, body in bot.sent)
    assert "The bot is ready" in bot.sent[0][1]
    assert "готов к работе" in bot.sent[1][1]


@pytest.mark.asyncio
async def test_unreachable_owner_does_not_break_other_startup_notifications(monkeypatch):
    async def get_user(_user_id):
        return None

    monkeypatch.setattr("app.bot.app.repo.get_user", get_user)

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
