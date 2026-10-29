"""Regressions for delayed callback acknowledgements and transient answer failures."""
from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.error import TimedOut

from app.bot import common, update_processor


@pytest.mark.asyncio
async def test_failed_callback_answer_is_not_cached_and_can_be_retried():
    calls = 0

    async def answer(body=None, show_alert=False):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimedOut("temporary Telegram timeout")

    query = SimpleNamespace(id=f"retry-{time.time_ns()}", answer=answer)

    assert await common.safe_answer(query) is False
    assert await common.safe_answer(query, "ready") is True
    assert await common.safe_answer(query, "duplicate") is False
    assert calls == 2


@pytest.mark.asyncio
async def test_concurrent_callback_answers_are_sent_once():
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def answer(body=None, show_alert=False):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()

    query = SimpleNamespace(id=f"parallel-{time.time_ns()}", answer=answer)
    first = asyncio.create_task(common.safe_answer(query, "first"))
    await asyncio.wait_for(entered.wait(), 1)
    second = asyncio.create_task(common.safe_answer(query, "second"))
    release.set()
    first_result, second_result = await asyncio.gather(first, second)

    assert first_result is True
    assert second_result is False
    assert calls == 1


def _callback_update(user_id: int, update_id: int) -> Update:
    user = User(id=user_id, is_bot=False, first_name="QA")
    message = Message(
        message_id=update_id,
        date=datetime.now(UTC),
        chat=Chat(id=user_id, type="private"),
        from_user=user,
    )
    query = CallbackQuery(
        id=f"callback-{update_id}",
        from_user=user,
        chat_instance=str(user_id),
        message=message,
        data="m|settings",
    )
    return Update(update_id=update_id, callback_query=query)


def _message_update(user_id: int, update_id: int) -> Update:
    user = User(id=user_id, is_bot=False, first_name="QA")
    message = Message(
        message_id=update_id,
        date=datetime.now(UTC),
        chat=Chat(id=user_id, type="private"),
        from_user=user,
    )
    return Update(update_id=update_id, message=message)


@pytest.mark.asyncio
async def test_callback_ack_watchdog_starts_before_same_user_lock(monkeypatch):
    processor = update_processor.UserOrderedUpdateProcessor(limit=4)
    await processor.initialize()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    callback_acknowledged = asyncio.Event()
    callback_handler_started = asyncio.Event()
    acked_ids: list[str] = []

    async def fake_safe_answer(query, body=None, alert=False):
        acked_ids.append(query.id)
        callback_acknowledged.set()
        return True

    monkeypatch.setattr(update_processor, "safe_answer", fake_safe_answer)

    async def first_message():
        first_started.set()
        await release_first.wait()

    async def callback_handler():
        callback_handler_started.set()

    first = asyncio.create_task(processor.process_update(_message_update(42, 1), first_message()))
    await asyncio.wait_for(first_started.wait(), 1)
    callback = asyncio.create_task(
        processor.process_update(_callback_update(42, 2), callback_handler())
    )

    await asyncio.wait_for(callback_acknowledged.wait(), update_processor.CALLBACK_ACK_SECONDS + 1.0)
    assert acked_ids == ["callback-2"]
    assert not callback_handler_started.is_set()  # still queued, but spinner has stopped

    release_first.set()
    await asyncio.wait_for(asyncio.gather(first, callback), 2)
    assert callback_handler_started.is_set()
    assert processor._locks == {}
    await processor.shutdown()
