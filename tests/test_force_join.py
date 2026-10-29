"""عضویت اجباری: ذخیرهٔ مقصدها، بررسی عضویت، کش و رفتار fail-open."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from telegram.error import TelegramError

from app.services.force_join import CACHE_SECONDS, ForceJoin, JoinTarget
from app.services.runtime_settings import RuntimeSettings


class FakeBot:
    id = 999

    def __init__(self, statuses: dict[int, str] | None = None, failing: set[int] | None = None) -> None:
        self.statuses = statuses or {}
        self.failing = failing or set()
        self.calls: list[tuple[int, int]] = []

    async def get_chat_member(self, chat_id, user_id):
        self.calls.append((chat_id, user_id))
        if chat_id in self.failing:
            raise TelegramError("chat not found")
        return SimpleNamespace(status=self.statuses.get(chat_id, "left"), is_member=False)

    async def get_chat(self, chat_id):
        return SimpleNamespace(
            id=chat_id,
            title=f"chat {chat_id}",
            username=f"chan{chat_id}",
            invite_link="",
        )


async def make_service(db, **values):
    settings = RuntimeSettings(db)
    await settings.load()
    for key, value in values.items():
        await settings.set(key, value)
    return settings, ForceJoin(settings)


def target(chat_id: int, title: str = "chan") -> JoinTarget:
    return JoinTarget(chat_id=chat_id, title=title, username=f"u{chat_id}")


def test_join_target_url_prefers_invite_link():
    assert JoinTarget(1, "t", username="chan").url() == "https://t.me/chan"
    assert JoinTarget(1, "t", username="chan", link="https://t.me/+x").url() == "https://t.me/+x"
    assert JoinTarget(1, "t").url() == ""


def test_join_target_roundtrip_and_bad_input():
    row = JoinTarget(5, "Title", username="name", link="https://t.me/+a")
    assert JoinTarget.from_json(row.to_json()) == row
    assert JoinTarget.from_json({"chat_id": "not-a-number"}) is None


@pytest.mark.asyncio
async def test_targets_are_stored_as_json_and_deduplicated(db):
    settings, join = await make_service(db, force_join_enabled=True)
    await join.add(target(1, "first"))
    await join.add(target(2, "second"))
    await join.add(target(1, "first-updated"))

    saved = json.loads(settings.get_str("force_join_chats"))
    assert [row["chat_id"] for row in saved] == [2, 1]
    assert [item.title for item in join.active_targets()] == ["second", "first-updated"]

    removed = await join.remove(2)
    assert removed is not None and removed.chat_id == 2
    assert [item.chat_id for item in join.targets] == [1]
    assert await join.remove(2) is None


@pytest.mark.asyncio
async def test_invalid_json_does_not_break_targets(db):
    _settings, join = await make_service(db, force_join_enabled=True)
    await _settings.set("force_join_chats", "{not json")
    assert join.targets == []
    assert await join.missing(FakeBot(), 1) == ([], True)


@pytest.mark.asyncio
async def test_disabled_force_join_allows_everyone(db):
    _settings, join = await make_service(db, force_join_chats=json.dumps([target(1).to_json()]))
    assert join.enabled is False
    assert await join.missing(FakeBot(), 7) == ([], True)


@pytest.mark.asyncio
async def test_missing_returns_only_unjoined_targets_and_caches(db):
    chats = json.dumps([target(1).to_json(), target(2).to_json()])
    _settings, join = await make_service(db, force_join_enabled=True, force_join_chats=chats)
    bot = FakeBot({1: "member", 2: "left"})

    missing, complete = await join.missing(bot, 7)
    assert [row.chat_id for row in missing] == [2]
    assert complete is True
    assert len(bot.calls) == 2

    # نتیجه تا CACHE_SECONDS در حافظه می‌ماند؛ درخواست تازه‌ای به تلگرام نمی‌رود.
    bot.statuses[2] = "member"
    missing_again, complete_again = await join.missing(bot, 7)
    assert [row.chat_id for row in missing_again] == [2]
    assert complete_again is True
    assert len(bot.calls) == 2

    missing_after_clear, _ = await join.missing(bot, 7, use_cache=False)
    assert missing_after_clear == []
    assert len(bot.calls) == 4
    assert CACHE_SECONDS > 0


@pytest.mark.asyncio
async def test_restricted_member_counts_as_joined(db):
    chats = json.dumps([target(1).to_json()])
    _settings, join = await make_service(db, force_join_enabled=True, force_join_chats=chats)

    class RestrictedBot(FakeBot):
        async def get_chat_member(self, chat_id, user_id):
            return SimpleNamespace(status="restricted", is_member=True)

    assert await join.missing(RestrictedBot(), 7) == ([], True)


@pytest.mark.asyncio
async def test_telegram_error_fails_open(db):
    chats = json.dumps([target(1).to_json()])
    _settings, join = await make_service(db, force_join_enabled=True, force_join_chats=chats)
    bot = FakeBot(failing={1})

    missing, complete = await join.missing(bot, 7)
    assert missing == []
    assert complete is False


@pytest.mark.asyncio
async def test_resolve_builds_target_from_chat(db):
    _settings, join = await make_service(db)
    bot = FakeBot()
    built = await join.resolve(bot, "12345")
    assert built.chat_id == 12345
    assert built.username == "chan12345"
    with pytest.raises(ValueError):
        await join.resolve(bot, "   ")


@pytest.mark.asyncio
async def test_check_access_reports_non_admin_bot(db):
    chats = json.dumps([target(1).to_json()])
    _settings, join = await make_service(db, force_join_enabled=True, force_join_chats=chats)

    class AdminCheckBot(FakeBot):
        async def get_chat_member(self, chat_id, user_id):
            return SimpleNamespace(status="member")

    results = await join.check_access(AdminCheckBot())
    assert results and results[0][1] is False
    assert "member" in results[0][2]


@pytest.mark.asyncio
async def test_clear_cache_for_single_user(db):
    chats = json.dumps([target(1).to_json()])
    _settings, join = await make_service(db, force_join_enabled=True, force_join_chats=chats)
    bot = FakeBot({1: "left"})
    await join.missing(bot, 7)
    await join.missing(bot, 8)
    assert set(join._cache) == {7, 8}
    join.clear_cache(7)
    assert set(join._cache) == {8}
    join.clear_cache()
    assert join._cache == {}
