"""Cache, topics and audit regressions, never contacts a real Telegram account."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from app.db import repo
from app.db.base import session
from app.db.models import MediaCacheEntry
from app.services.admin_group import TOPICS, AdminGroup
from app.services.cache import (
    MEDIA_TTL,
    PUBLIC_CACHE_USER_ID,
    CacheHub,
    fingerprint,
    safe_source,
    shared_fingerprint,
)
from app.services.downloader import DownloadResult
from app.services.formats import FormatOption
from app.services.jobs import JobTask
from app.services.runtime_settings import RuntimeSettings


class MockForumBot:
    def __init__(self):
        self.created = []
        self.sent = []
        self.copied = []
        self.deleted = []
        self.next_id = 90

    async def create_forum_topic(self, chat_id, name):
        self.next_id += 1
        self.created.append((chat_id, name, self.next_id))
        return SimpleNamespace(message_thread_id=self.next_id)

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))
        self.next_id += 1
        return SimpleNamespace(message_id=self.next_id)

    async def copy_message(self, **kwargs):
        self.copied.append(kwargs)
        self.next_id += 1
        return SimpleNamespace(message_id=self.next_id)

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


@pytest.fixture()
async def forum(db):
    settings = RuntimeSettings(db)
    await settings.load()
    hub = AdminGroup(db, settings)
    bot = MockForumBot()
    hub.attach(bot)
    topics = await hub.configure(-100123456789, "Private LeechX operations")
    return hub, bot, topics


@pytest.mark.asyncio
async def test_single_forum_creates_all_five_topics_and_is_idempotent(forum):
    hub, bot, topics = forum
    assert set(topics) == set(TOPICS)
    assert len(topics) == 5
    assert all(isinstance(mid, int) and mid > 0 for mid in topics.values())
    second = await hub.configure(-100123456789, "Private LeechX operations")
    assert second == topics
    assert len(bot.created) == 5
    status = hub.status()
    assert status["topics"] == topics
    assert await hub.send("cache", "ready")
    assert bot.sent[-1][0] == -100123456789
    assert bot.sent[-1][2]["message_thread_id"] == topics["cache"]
    assert await hub.send("security", "ready")
    assert bot.sent[-1][2]["message_thread_id"] == topics["security"]


@pytest.mark.asyncio
async def test_event_audit_persisted_and_routed_to_appropriate_topics(forum):
    hub, bot, topics = forum
    await hub.audit("security", "setting_updated", user_id=42, details="key=proxy (value hidden)")
    assert bot.sent[-1][2]["message_thread_id"] == topics["security"]
    assert "42" in bot.sent[-1][1]
    assert "setting_updated" in bot.sent[-1][1]
    await hub.audit("job", "done", user_id=42, details="task=one")
    assert bot.sent[-1][2]["message_thread_id"] == topics["logs"]
    assert await hub.cache_event("media", "HIT", "hash123")
    assert bot.sent[-1][2]["message_thread_id"] == topics["cache"]
    await hub.record_log("ERROR", "handler", "unexpected exception", user_id=42)
    assert bot.sent[-1][2]["message_thread_id"] == topics["logs"]


@pytest.mark.asyncio
async def test_metadata_probe_cache_is_user_scoped_and_singleflight(forum):
    hub, bot, topics = forum
    cache = CacheHub(hub)
    calls = []
    gate = asyncio.Event()

    async def fetch(url):
        calls.append(url)
        await gate.wait()
        return SimpleNamespace(title="title", url=url)

    a = asyncio.create_task(cache.probe(5, "https://example.com/v?token=SECRET", fetch))
    await asyncio.sleep(.01)
    b = asyncio.create_task(cache.probe(5, "https://example.com/v?token=SECRET", fetch))
    gate.set()
    one, two = await asyncio.gather(a, b)
    assert one is two
    assert len(calls) == 1
    assert (await cache.probe(5, "https://example.com/v?token=SECRET", fetch)) is one
    await cache.probe(6, "https://example.com/v?token=SECRET", fetch)
    assert len(calls) == 2
    cache_messages = [msg for _, msg, meta in bot.sent if meta.get("message_thread_id") == topics["cache"]]
    assert not any("SECRET" in msg for msg in cache_messages)
    assert any("HIT" in msg for msg in cache_messages)


def make_task(user_id=10, mode="video", name=""):
    return JobTask(
        id="abcd1234", user_id=user_id, chat_id=user_id,
        url="https://www.youtube.com/watch?v=public",
        option=FormatOption(kind="video", code="best", label="best", selector="bv*+ba/b"),
        title="Public video", mode=mode, custom_name=name,
    )


@pytest.mark.asyncio
async def test_telegram_media_cache_roundtrip_and_owner_isolation(db, forum, tmp_path):
    hub, bot, topics = forum
    cache = CacheHub(hub)
    task = make_task()
    path = tmp_path / "public.mp4"
    path.write_bytes(b"x" * 32)
    result = DownloadResult(path=path, title="Public video", mime="video/mp4", size=32)
    msg = SimpleNamespace(message_id=42)
    await cache.record_delivery(bot, task, result, msg)
    assert len(bot.copied) == 1
    first = bot.copied[0]
    assert first["chat_id"] == hub.chat_id
    assert first["message_thread_id"] == topics["cache"]
    assert "youtube.com" not in first["caption"]
    key = fingerprint(task.user_id, task.url, task.option.selector, task.mode, task.custom_name)
    row = await repo.get_media_cache(key, task.user_id, hub.chat_id)
    assert row is not None and row.size == 32
    assert row.expires_at > int(time.time())
    assert await cache.cached_delivery(bot, make_task(user_id=11)) is None
    assert len(bot.copied) == 1
    assert await cache.cached_delivery(bot, make_task(mode="document")) is None
    assert len(bot.copied) == 1
    assert await cache.cached_delivery(bot, make_task(name="Custom filename")) is None
    assert len(bot.copied) == 1
    assert await cache.cached_delivery(bot, task) == 32
    assert len(bot.copied) == 2
    assert bot.copied[-1]["from_chat_id"] == hub.chat_id
    assert bot.copied[-1]["chat_id"] == task.chat_id
    assert bot.copied[-1]["message_id"] == row.message_id
    assert "Public video" in bot.copied[-1]["caption"]
    assert row.mode == "video"


@pytest.mark.asyncio
async def test_expired_media_cache_metadata_cleanup_preserves_group_archive(db, forum, tmp_path):
    hub, bot, topics = forum
    cache = CacheHub(hub)
    key = fingerprint(42, "https://example.com", "b", "video", "")
    await repo.put_media_cache(key, 42, hub.chat_id, 987, "video", "video.mp4", 42, 24 * 3600)
    async with session() as s:
        await s.execute(update(MediaCacheEntry).where(MediaCacheEntry.cache_key == key).values(
            expires_at=int(time.time()) - 1
        ))
        await s.commit()
    assert await cache.clear_expired(bot) == 1
    # Expiring lookup metadata must never delete the archived Telegram message.
    assert bot.deleted == []
    assert await repo.get_media_cache(key, 42, hub.chat_id) is None


@pytest.mark.asyncio
async def test_cache_db_disabled_without_group(db):
    settings = RuntimeSettings(db)
    await settings.load()
    hub = AdminGroup(db, settings)
    bot = MockForumBot()
    cache = CacheHub(hub)
    task = make_task()
    assert not await cache.cached_delivery(bot, task)
    path = Path(db.tmp_dir) / "dummy.mp4"
    path.write_bytes(b"x")
    await cache.record_delivery(bot, task,
        DownloadResult(path=path, title="x", size=1), SimpleNamespace(message_id=9))
    assert bot.copied == []


def test_private_fingerprint_preserves_legacy_cache_keys():
    parts = [7, "https://example.com/video", "720", "video", ""]
    old_serialization = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    assert fingerprint(*parts) == hashlib.sha256(old_serialization.encode()).hexdigest()


def test_cache_fingerprints_are_private_and_no_secrets_in_topic():
    url = "https://user:pass@service.example/video?q=SECRET"
    safe = safe_source(url)
    assert "pass" not in safe and "SECRET" not in safe and "user" not in safe
    assert safe.startswith("https://service.example/video")
    key1 = fingerprint(1, url, "720", "video", "")
    assert key1 != fingerprint(2, url, "720", "video", "")
    assert key1 != fingerprint(1, url, "1080", "video", "")
    assert key1 != fingerprint(1, url, "720", "document", "")
    assert MEDIA_TTL <= 24 * 3600


@pytest.mark.asyncio
async def test_job_cache_hit_skips_downloader_and_updates_bytes(db, forum):
    from app.services.filestore import FileStore
    from app.services.jobs import JobManager
    from app.services.ratelimit import RateLimiter
    hub, bot, topics = forum
    store = FileStore(db.files_dir, db.tmp_dir)
    cache = CacheHub(hub)
    task = make_task(user_id=10)
    task.status_message_id = 500
    key = fingerprint(task.user_id, task.url, task.option.selector, task.mode, task.custom_name)
    await repo.put_media_cache(
        key, task.user_id, hub.chat_id, 1122, task.mode, "cached.mp4", 256, 3600
    )
    class NeverDownload:
        def __init__(self):
            self.calls = 0
        async def download(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("cache-hit must not download again")
    class Bot(MockForumBot):
        async def edit_message_text(self, **kwargs):
            self.sent.append(("EDIT", kwargs.get("text"), kwargs))
    downloader=NeverDownload()
    manager=JobManager(db, RuntimeSettings(db), store, downloader, None, RateLimiter(0), hub)
    manager.cache=cache
    manager.bot=Bot()
    await manager.submit(task)
    await manager._run(task)
    assert downloader.calls == 0
    assert any(x["message_id"] == 1122 for x in manager.bot.copied)
    row=await repo.get_job(task.id)
    assert row.status == "done"
    assert row.size == 256
    assert manager.active_count == 0


@pytest.mark.asyncio
async def test_change_group_does_not_reuse_cache_from_old_group(db, forum, tmp_path):
    hub, bot, topics = forum
    cache = CacheHub(hub)
    task=make_task(user_id=10)
    path=tmp_path/"video.mp4"
    path.write_bytes(b"x")
    await cache.record_delivery(bot,task,
        DownloadResult(path=path,title="x",size=1),SimpleNamespace(message_id=77))
    original_group=hub.chat_id
    assert await cache.cached_delivery(bot, task)
    await hub.configure(-100333333, "Another private group")
    assert hub.chat_id != original_group
    assert not await cache.cached_delivery(bot, task)


@pytest.mark.asyncio
async def test_cache_error_falls_back_without_throwing(db, forum):
    from telegram.error import BadRequest
    hub,bot,topics=forum
    cache=CacheHub(hub)
    task=make_task()
    key=fingerprint(task.user_id,task.url,task.option.selector,task.mode,task.custom_name)
    await repo.put_media_cache(
        key,task.user_id,hub.chat_id,555,task.mode,"broken.mp4",100,3600
    )
    async def missing_copy(**kwargs):
        raise BadRequest("Message to copy not found")
    bot.copy_message=missing_copy
    assert await cache.cached_delivery(bot,task) is None
    assert await repo.get_media_cache(key,task.user_id,hub.chat_id) is None


@pytest.mark.asyncio
async def test_topic_missing_never_leaks_log_to_general_chat(db):
    hub = AdminGroup(db, RuntimeSettings(db))
    bot = MockForumBot()
    hub.attach(bot)
    await hub.settings.set("admin_group_id", "-100123456789")
    assert await hub.send("security", "private security event") is False
    assert bot.sent == []


@pytest.mark.asyncio
async def test_direct_link_access_log_is_rate_limited_and_keeps_token_private(db):
    from aiohttp.test_utils import TestClient, TestServer

    from app.services.filestore import FileStore
    from app.services.link_server import LinkServer
    from app.services.linktoken import make_token
    class Audit:
        def __init__(self): self.entries = []
        async def audit(self, category, action, user_id, details):
            self.entries.append((category, action, user_id, details))
    audit = Audit()
    store = FileStore(db.files_dir, db.tmp_dir)
    server = LinkServer(db, RuntimeSettings(db), store, hub=audit)
    path = store.link_path("cachehttp", "file.mp4")
    path.write_bytes(b"video-abc")
    await repo.create_shared("cachehttp", 42, str(path), path.name, "video/mp4", 9, 3600)
    token = make_token("cachehttp", db.link_secret, 3600)
    async with TestClient(TestServer(server.build_app())) as client:
        first = await client.get(f"/f/{token}")
        assert first.status == 200
        assert await first.read() == b"video-abc"
        second = await client.get(f"/f/{token}", headers={"Range":"bytes=0-2"})
        assert second.status == 206
        assert await second.read() == b"vid"
        # ثبت آدیت در انتهای handler و پس از ارسال پاسخ انجام می‌شود؛
        # تا وقتی سرور زنده است فرصت بدهیم handler تمام شود (وگرنه در
        # shutdown کنسل می‌شود و آدیت هرگز ثبت نمی‌شود).
        for _ in range(200):
            if audit.entries:
                break
            await asyncio.sleep(0.01)
    assert len(audit.entries) == 1
    assert audit.entries[0][0] == "link_http"
    assert audit.entries[0][2] == 42
    assert token not in audit.entries[0][-1]


@pytest.mark.asyncio
async def test_public_media_cache_is_reused_across_users(db, forum, tmp_path):
    hub, bot, topics = forum
    cache = CacheHub(hub)
    first = make_task(user_id=10)
    first.public_cache = True
    path = tmp_path / "public.mp4"
    path.write_bytes(b"public-video-bytes")
    result = DownloadResult(
        path=path, title="Public video", mime="video/mp4", size=18
    )

    await cache.record_delivery(bot, first, result, SimpleNamespace(message_id=72))
    key = shared_fingerprint(
        first.url, first.option.selector, first.mode, first.custom_name
    )
    row = await repo.get_media_cache(key, PUBLIC_CACHE_USER_ID, hub.chat_id)
    assert row is not None and row.size == 18
    assert "کاربر:" not in bot.copied[0]["caption"]
    assert "کش عمومی" in bot.copied[0]["caption"]

    second = make_task(user_id=11)
    second.public_cache = True
    assert await cache.cached_delivery(bot, second) == 18
    assert bot.copied[-1]["from_chat_id"] == hub.chat_id
    assert bot.copied[-1]["chat_id"] == 11
    assert bot.copied[-1]["message_id"] == row.message_id


@pytest.mark.asyncio
async def test_shared_delivery_with_custom_cover_is_cached_privately(db, forum, tmp_path):
    """A chosen cover must not disable caching; it only makes the entry private."""
    hub, bot, topics = forum
    cache = CacheHub(hub)
    task = make_task(user_id=10)
    task.public_cache = True
    task.custom_thumbnail = b"\xff\xd8fake-jpeg"
    path = tmp_path / "covered.mp4"
    path.write_bytes(b"covered-video")
    result = DownloadResult(path=path, title="Public video", mime="video/mp4", size=13)

    await cache.record_delivery(bot, task, result, SimpleNamespace(message_id=77))

    assert len(bot.copied) == 1  # cached, not silently dropped
    private_key = fingerprint(
        task.user_id, task.url, task.option.selector, task.mode, task.custom_name
    )
    assert await repo.get_media_cache(private_key, task.user_id, hub.chat_id) is not None
    shared_key = shared_fingerprint(
        task.url, task.option.selector, task.mode, task.custom_name
    )
    assert await repo.get_media_cache(shared_key, PUBLIC_CACHE_USER_ID, hub.chat_id) is None

    # The owner gets a cache hit, another user does not.
    assert await cache.cached_delivery(bot, task) == 13
    other = make_task(user_id=11)
    other.public_cache = True
    assert await cache.cached_delivery(bot, other) is None
