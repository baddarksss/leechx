"""تست سخت‌سازی v5.12.3: گارد دیسک، وضعیت کش Bot API و دکمهٔ تلاش دوباره."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot import keyboards as kb
from app.bot.flows import callbacks as callbacks_flow
from app.services import telegram_transfers
from app.services.cache import CacheHub
from app.services.filestore import FileStore


# ── گارد فضای دیسک ─────────────────────────────────────────
def test_has_room_reserves_space(tmp_path):
    store = FileStore(tmp_path / "files", tmp_path / "tmp")
    store.disk_free = lambda: 1024  # type: ignore[method-assign]
    assert store.has_room(0) is True
    assert store.has_room(100) is False  # 1 GiB reserve بزرگ‌تر از فضای آزاد است


def test_has_room_allows_large_disk(tmp_path):
    store = FileStore(tmp_path / "files", tmp_path / "tmp")
    store.disk_free = lambda: 10 * 1024 * 1024 * 1024  # type: ignore[method-assign]
    assert store.has_room(2 * 1024 * 1024 * 1024) is True


# ── وضعیت کش Local Bot API ─────────────────────────────────
def test_cache_state_is_off_for_public_api():
    cfg = SimpleNamespace(uses_local_api=False, bot_token="1:a")
    assert telegram_transfers.bot_api_cache_state(cfg) == "off"


def test_cache_state_reports_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(telegram_transfers, "BOT_API_CACHE_DIR", tmp_path)
    cfg = SimpleNamespace(uses_local_api=True, bot_token="123:ABC")
    assert telegram_transfers.bot_api_cache_state(cfg) == "missing"


def test_cache_state_reports_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(telegram_transfers, "BOT_API_CACHE_DIR", tmp_path)
    (tmp_path / "123:ABC").mkdir()
    cfg = SimpleNamespace(uses_local_api=True, bot_token="123:ABC")
    assert telegram_transfers.bot_api_cache_state(cfg) == "ok"


# ── دکمهٔ تلاش دوباره ──────────────────────────────────────
def test_retry_keyboard_carries_job_id():
    markup = kb.retry_job("en", "abc123")
    assert markup.inline_keyboard[0][0].callback_data == "r|abc123"


@pytest.mark.asyncio
async def test_retry_rejects_another_users_job(monkeypatch):
    calls: list[tuple] = []

    async def fake_job(job_id: str):
        return SimpleNamespace(user_id=1, status="failed", url="https://e.com/a")

    async def fake_handle(update, context, url):
        calls.append((url,))

    async def fake_answer(query, body=None, alert=False):
        calls.append(("answer", alert))
        return True

    monkeypatch.setattr(callbacks_flow.repo, "get_job", fake_job)
    monkeypatch.setattr(callbacks_flow.link_flow, "handle_link", fake_handle)
    monkeypatch.setattr(callbacks_flow, "safe_answer", fake_answer)

    update = SimpleNamespace(
        callback_query=SimpleNamespace(message=None),
        effective_user=SimpleNamespace(id=2),
    )
    context = SimpleNamespace(
        bot_data={"services": SimpleNamespace()},
        user_data={"lang": "en"},
    )
    await callbacks_flow._on_retry(update, context, ["abc123"])
    # کاربر دیگری است → فقط هشدار، بدون شروع دوباره
    assert calls == [("answer", True)]


@pytest.mark.asyncio
async def test_retry_restarts_flow_for_owner(monkeypatch):
    calls: list[tuple] = []

    async def fake_job(job_id: str):
        return SimpleNamespace(user_id=7, status="failed", url="https://e.com/a")

    async def fake_handle(update, context, url):
        calls.append(("handle", url))

    async def fake_answer(query, body=None, alert=False):
        calls.append(("answer", alert))
        return True

    monkeypatch.setattr(callbacks_flow.repo, "get_job", fake_job)
    monkeypatch.setattr(callbacks_flow.link_flow, "handle_link", fake_handle)
    monkeypatch.setattr(callbacks_flow, "safe_answer", fake_answer)

    update = SimpleNamespace(
        callback_query=SimpleNamespace(message=None),
        effective_user=SimpleNamespace(id=7),
    )
    context = SimpleNamespace(
        bot_data={"services": SimpleNamespace()},
        user_data={"lang": "en"},
    )
    await callbacks_flow._on_retry(update, context, ["abc123"])
    assert calls[-1] == ("handle", "https://e.com/a")


@pytest.mark.asyncio
async def test_retry_ignores_running_job(monkeypatch):
    calls: list[tuple] = []

    async def fake_job(job_id: str):
        return SimpleNamespace(user_id=7, status="running", url="https://e.com/a")

    async def fake_handle(update, context, url):  # pragma: no cover - نباید صدا زده شود
        calls.append(("handle", url))

    async def fake_answer(query, body=None, alert=False):
        calls.append(("answer", alert))
        return True

    monkeypatch.setattr(callbacks_flow.repo, "get_job", fake_job)
    monkeypatch.setattr(callbacks_flow.link_flow, "handle_link", fake_handle)
    monkeypatch.setattr(callbacks_flow, "safe_answer", fake_answer)

    update = SimpleNamespace(
        callback_query=SimpleNamespace(message=None),
        effective_user=SimpleNamespace(id=7),
    )
    context = SimpleNamespace(
        bot_data={"services": SimpleNamespace()},
        user_data={"lang": "en"},
    )
    await callbacks_flow._on_retry(update, context, ["abc123"])
    assert calls == [("answer", True)]


# ── کش: قرارداد None ──────────────────────────────────────
@pytest.mark.asyncio
async def test_cached_delivery_is_none_without_cache_topic():
    group = SimpleNamespace(chat_id=0, topic_id=lambda name: None)
    hub = CacheHub(group)
    assert await hub.cached_delivery(bot=None, task=SimpleNamespace()) is None
