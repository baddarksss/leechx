import asyncio
import os
import time
from types import SimpleNamespace

import pytest

from app.services.drafts import Draft, DraftStore
from app.services.filestore import FileStore, dir_size
from app.services.formats import AUDIO_MP3
from app.services.jobs import JobManager, JobTask
from app.services.ratelimit import RateLimiter


def make_draft(store: DraftStore, user_id=1, ttl=0):
    draft = Draft(
        id=store.new_id(),
        user_id=user_id,
        chat_id=user_id,
        url="https://x.com/a",
        title="t",
    )
    if ttl:
        draft.created_at = time.time() - ttl
    store.put(draft)
    return draft


def test_filestore_job_and_link_dirs(tmp_path):
    store = FileStore(tmp_path / "files", tmp_path / "tmp")
    job = store.job_dir("abc")
    assert job.is_dir()
    (job / "a.bin").write_bytes(b"x" * 100)
    assert dir_size(job) == 100

    link = store.link_path("f1", "movie.mp4")
    link.write_bytes(b"y" * 50)
    assert link.is_file()

    store.drop_job_dir("abc")
    assert not job.exists()

    store.drop_link_dir("f1")
    assert not link.parent.exists()


def test_filestore_purge_old(tmp_path):
    store = FileStore(tmp_path / "files", tmp_path / "tmp")
    old = store.job_dir("old")
    (old / "x.bin").write_bytes(b"z" * 10)
    new = store.job_dir("new")
    past = time.time() - 7200
    os.utime(old, (past, past))

    removed, freed = store.purge_older_than(3600)
    assert removed == 1
    assert freed == 10
    assert not old.exists()
    assert new.exists()


def test_draft_store_owner_and_ttl():
    store = DraftStore(max_items=3, ttl=60)
    draft = make_draft(store, user_id=7)
    assert store.get(draft.id, 7) is draft
    assert store.get(draft.id, 8) is None
    assert store.pop(draft.id, 7) is draft
    assert store.get(draft.id) is None


def test_draft_store_expiry_and_capacity():
    store = DraftStore(max_items=2, ttl=10)
    stale = make_draft(store, ttl=100)
    assert store.get(stale.id) is None

    a = make_draft(store, user_id=1)
    make_draft(store, user_id=2)
    c = make_draft(store, user_id=3)
    assert len(store) == 2
    assert store.get(a.id) is None
    assert store.get(c.id) is c


def test_rate_limiter():
    limiter = RateLimiter(0.2)
    assert limiter.hit(1) == 0.0
    wait = limiter.hit(1)
    assert wait > 0
    time.sleep(0.25)
    assert limiter.hit(1) == 0.0
    assert limiter.hit(2) == 0.0


def test_rate_limiter_slots():
    limiter = RateLimiter(0)
    assert limiter.acquire_slot(1, 1) is True
    assert limiter.acquire_slot(1, 1) is False
    limiter.release_slot(1)
    assert limiter.acquire_slot(1, 1) is True
    limiter.release_slot(1)
    limiter.release_slot(1)
    assert limiter.active_count(1) == 0
    assert limiter.acquire_slot(2, 0) is True


# ── صف کار ─────────────────────────────────────────────────
def make_task(job_id: str, user_id: int = 1) -> JobTask:
    return JobTask(
        id=job_id,
        user_id=user_id,
        chat_id=user_id,
        url="https://x.com/a",
        option=AUDIO_MP3,
        title="t",
    )


def make_manager(per_user: int = 1) -> JobManager:
    return JobManager(
        cfg=SimpleNamespace(per_user_concurrency=per_user),
        settings=None,
        store=None,
        downloader=None,
        uploader=None,
        limiter=RateLimiter(0),
    )


def test_take_next_respects_per_user_slots():
    manager = make_manager(per_user=1)
    a, b, c = make_task("a", 1), make_task("b", 1), make_task("c", 2)
    for task in (a, b, c):
        manager._tasks[task.id] = task
        manager._queue.append(task)

    assert manager._take_next() is a          # کاربر ۱ ظرفیت دارد
    assert manager._take_next() is c          # کاربر ۱ پر است → نوبت کاربر ۲
    assert manager._take_next() is None
    assert [t.id for t in manager._queue] == ["b"]
    assert manager.limiter.active_count(1) == 1


def test_take_next_parallel_for_same_user():
    manager = make_manager(per_user=2)
    a, b = make_task("a", 1), make_task("b", 1)
    for task in (a, b):
        manager._tasks[task.id] = task
        manager._queue.append(task)

    assert manager._take_next() is a
    assert manager._take_next() is b
    assert manager.limiter.active_count(1) == 2


@pytest.mark.asyncio
async def test_canceled_queue_task_is_skipped():
    manager = make_manager()
    finished: list[str] = []

    async def fake_finish(task: JobTask) -> None:
        finished.append(task.id)

    manager._finish_canceled = fake_finish  # type: ignore[method-assign]
    task = make_task("x")
    manager._tasks[task.id] = task
    manager._queue.append(task)
    task.canceled_by_user = True
    task.cancel.set()

    assert manager._take_next() is None
    await asyncio.sleep(0)
    assert finished == ["x"]
    assert manager.limiter.active_count(task.user_id) == 0


def test_draft_carries_language():
    draft = Draft(id="d1", user_id=1, chat_id=1, url="u", title="t", lang="en")
    assert draft.lang == "en"
    assert Draft(id="d2", user_id=1, chat_id=1, url="u", title="t").lang == "fa"
