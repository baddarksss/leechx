import os
import time

from app.services.drafts import Draft, DraftStore
from app.services.filestore import FileStore, dir_size
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
