"""Regression tests for progress finalization and slow-mode notices."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.bot.common import rate_limit_notice
from app.services.jobs import JobManager, JobTask
from app.services.ratelimit import RateLimiter


class EditBot:
    def __init__(self):
        self.edits = []
        self.sent = []

    async def edit_message_text(self, **kwargs):
        await asyncio.sleep(0.01)
        self.edits.append(kwargs)

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=1)


@pytest.mark.asyncio
async def test_final_message_cannot_be_overwritten_by_stale_progress():
    manager = JobManager(None, None, None, None, None, None)
    bot = EditBot()
    manager.bot = bot
    task = JobTask(
        id="progress1", user_id=7, chat_id=7, url="https://example.com/v",
        option=SimpleNamespace(selector="best", label="best"), title="video",
        status_message_id=99,
    )
    task.progress.stage = "uploading"
    task.progress.total = 100
    task.progress.uploaded = 100

    await asyncio.gather(
        manager._edit_progress(task, force=True),
        manager._edit_final(task, "done"),
    )
    assert bot.edits[-1]["text"] == "done"
    edit_count = len(bot.edits)
    await manager._edit_progress(task, force=True)
    assert len(bot.edits) == edit_count


@pytest.mark.asyncio
async def test_first_slow_mode_block_gets_an_immediate_notice():
    limiter = RateLimiter(30)
    assert limiter.hit(42) == 0
    wait = limiter.hit(42)
    assert wait > 0

    bot = EditBot()
    update = SimpleNamespace(effective_chat=SimpleNamespace(id=42))
    context = SimpleNamespace(bot=bot)
    sent = await rate_limit_notice(update, context, f"Wait {wait} seconds")

    assert sent is True
    assert len(bot.sent) == 1
    assert bot.sent[0]["chat_id"] == 42
    assert bot.sent[0]["text"] == f"Wait {wait} seconds"


@pytest.mark.asyncio
async def test_vip_jobs_bypass_per_user_concurrency_slots():
    limiter = RateLimiter(0)
    assert limiter.acquire_slot(42, 1) is True  # ordinary job already active
    manager = JobManager(
        SimpleNamespace(per_user_concurrency=1), None, None, None, None, limiter
    )
    vip_task = JobTask(
        id="vip-queued", user_id=42, chat_id=42, url="https://example.com/v",
        option=SimpleNamespace(selector="best", label="best"), title="video", vip=True,
    )
    manager._tasks[vip_task.id] = vip_task
    manager._queue.append(vip_task)

    assert manager._take_next() is vip_task
    # VIP work is governed by global workers, not the normal per-user slot cap.
    assert limiter.active_count(42) == 1
    assert vip_task.slot_acquired is False

    ordinary = JobTask(
        id="ordinary-queued", user_id=42, chat_id=42, url="https://example.com/v",
        option=SimpleNamespace(selector="best", label="best"), title="video",
    )
    manager._tasks[ordinary.id] = ordinary
    manager._queue.append(ordinary)
    assert manager._take_next() is None  # VIP dequeue did not release the ordinary slot.
    limiter.release_slot(42)
    assert manager._take_next() is ordinary
    assert ordinary.slot_acquired is True
