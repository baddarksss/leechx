"""Permanent admin controls, cancelable file transfers and owned shared links."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from app.bot import keyboards as kb
from app.bot.flows import user_links
from app.db import repo
from app.services.downloader import DownloadResult, MediaInfo
from app.services.filestore import FileStore
from app.services.formats import FormatOption
from app.services.jobs import JobManager, JobTask
from app.services.link_server import LinkServer
from app.services.linktoken import make_token
from app.services.ratelimit import RateLimiter
from app.services.runtime_settings import RuntimeSettings
from app.services.telegram_transfers import FileLinkTransfers


class Message:
    def __init__(self):
        self.texts = []
        self.markups = []
        self.chat_id = 42
        self.message_id = 12

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)
        self.markups.append(kwargs.get("reply_markup"))
        return self

    async def edit_text(self, text, **kwargs):
        self.texts.append(text)
        self.markups.append(kwargs.get("reply_markup"))


class Query:
    def __init__(self, msg, user_id=42):
        self.message = msg
        self.answered = []

    async def answer(self, message=None, show_alert=False):
        self.answered.append(message)


def update(user_id=42, query=None):
    msg = query.message if query else Message()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, username="qa", first_name="QA"),
        effective_chat=SimpleNamespace(id=user_id),
        effective_message=msg,
        callback_query=query,
    )


def test_admin_reply_keyboard_persistent():
    menu = kb.admin_persistent_menu("fa")
    labels = {button.text for row in menu.keyboard for button in row}
    assert menu.is_persistent and menu.resize_keyboard
    assert "👑 پنل ادمین" in labels
    assert "📨 گزارش‌ها" in labels
    assert "🔗 لینک‌های من" in labels
    assert "✖️ لغو عملیات" in labels


@pytest.mark.asyncio
async def test_link_list_view_and_delete_owned_file(db):
    store = FileStore(db.files_dir, db.tmp_dir)
    settings = RuntimeSettings(db)
    service = SimpleNamespace(cfg=db, store=store, settings=settings)
    context = SimpleNamespace(bot_data={"services": service}, user_data={"lang": "fa"})
    path = store.link_path("abc123", "owned.mp4")
    path.write_bytes(b"a" * 100)
    await repo.create_shared("abc123", 42, str(path), "owned.mp4", "video/mp4", 100, 3600)
    token = make_token("abc123", db.link_secret, 3600)
    server = LinkServer(db, settings, store)
    async with TestClient(TestServer(server.build_app())) as client:
        assert (await client.get(f"/f/{token}")).status == 200
        view = update()
        await user_links.cmd_links(view, context)
        assert "owned.mp4" in view.effective_message.texts[-1]
        assert "u|ask|abc123|0" in str(view.effective_message.markups[-1])
        malicious = update(41, Query(view.effective_message))
        await user_links.on_callback(malicious, context, ["del", "abc123", "0"])
        assert path.exists()
        assert await repo.count_user_shared(42) == 1
        owner = update(42, Query(view.effective_message))
        await user_links.on_callback(owner, context, ["ask", "abc123", "0"])
        assert "حذف قطعی" in str(view.effective_message.markups[-1])
        await user_links.on_callback(owner, context, ["del", "abc123", "0"])
        assert await repo.count_user_shared(42) == 0
        assert not path.exists()
        assert (await client.get(f"/f/{token}")).status == 404


@pytest.mark.asyncio
async def test_user_links_only_return_own_records(db):
    store = FileStore(db.files_dir, db.tmp_dir)
    for file_id, user_id in [("mine1", 42), ("other1", 41)]:
        target = store.link_path(file_id, file_id + ".txt")
        target.write_bytes(b"x")
        await repo.create_shared(file_id, user_id, str(target), target.name, "text/plain", 1, 3600)
    assert [row.id for row in await repo.user_shared(42)] == ["mine1"]
    assert await repo.pop_user_shared("other1", 42) is None
    assert await repo.get_user_shared("other1", 42) is None
    assert await repo.count_user_shared(41) == 1


@pytest.mark.asyncio
async def test_telegram_attachment_transfer_stream_and_create_link(db, tmp_path):
    source = tmp_path / "original.bin"
    source.write_bytes(b"data-0123456789" * 10000)
    size = source.stat().st_size
    store = FileStore(db.files_dir, db.tmp_dir)
    settings = RuntimeSettings(db)
    service = SimpleNamespace(cfg=db, store=store, settings=settings, admin_group=None)
    manager = FileLinkTransfers(service)
    manager.svc = service
    msg = Message()
    request = update()
    request.effective_message = msg
    class Attachment:
        mime_type = "application/octet-stream"
        async def get_file(self):
            return SimpleNamespace(file_path=str(source))
    item = await manager.start(request, "fa", Attachment(), "original.bin", size)
    await asyncio.wait_for(item.job, 5)
    assert not manager.tasks_for_user(42)
    assert await repo.count_user_shared(42) == 1
    row = await repo.get_shared(item.id)
    assert Path(row.path).read_bytes() == source.read_bytes()
    assert "لینک مستقیم آماده" in msg.texts[-1]
    assert any("لغو" in str(markup) for markup in msg.markups if markup)


@pytest.mark.asyncio
async def test_cancel_telegram_transfer_before_file_download(db):
    store = FileStore(db.files_dir, db.tmp_dir)
    service = SimpleNamespace(cfg=db, store=store, settings=RuntimeSettings(db), admin_group=None)
    manager = FileLinkTransfers(service)
    started = asyncio.Event()
    class Attachment:
        async def get_file(self):
            started.set()
            await asyncio.Event().wait()
    request = update()
    item = await manager.start(request, "fa", Attachment(), "slow.bin", 1000)
    await asyncio.wait_for(started.wait(), 2)
    assert not manager.cancel(item.id, 41)  # another user cannot cancel
    assert manager.cancel(item.id, 42)
    await asyncio.wait_for(item.job, 3)
    assert "لغو" in request.effective_message.texts[-1]
    assert not (store.links / item.id).exists()
    assert await repo.get_shared(item.id) is None


@pytest.mark.asyncio
async def test_upload_cancel_aborts_task_and_keeps_cancel_button(db):
    store = FileStore(db.files_dir, db.tmp_dir)
    settings = RuntimeSettings(db)
    uploaded = asyncio.Event()
    class Downloader:
        async def download(self, url, option, workdir, progress, cancel, info):
            path = workdir / "clip.mp4"
            path.write_bytes(b"x" * 80)
            progress.pct = 100.0
            return DownloadResult(path=path, title="clip", mime="video/mp4", size=80)
    class Uploader:
        async def send(self, *args, **kwargs):
            uploaded.set()
            await asyncio.Event().wait()
    class Bot:
        def __init__(self):
            self.last_markup = None
        async def edit_message_text(self, **kwargs):
            self.last_markup = kwargs.get("reply_markup")
    manager = JobManager(db, settings, store, Downloader(), Uploader(), RateLimiter(0))
    bot = Bot()
    manager.bot = bot
    task = JobTask(
        id="cancelupload", user_id=42, chat_id=42, url="https://example.com/clip",
        option=FormatOption(kind="direct", code="direct", label="direct", selector=""),
        title="clip", info=MediaInfo(url="https://example.com/clip", title="clip"),
        status_message_id=123, mode="video",
    )
    await manager.submit(task)
    run = asyncio.create_task(manager._run(task))
    await asyncio.wait_for(uploaded.wait(), 2)
    assert "x|cancelupload" in str(bot.last_markup)
    assert not manager.cancel(task.id, 99)
    assert manager.cancel(task.id, 42)
    await asyncio.wait_for(run, 3)
    row = await repo.get_job(task.id)
    assert row.status == "canceled"
    assert manager.active_count == 0
    assert not (store.jobs / task.id).exists()


@pytest.mark.asyncio
async def test_admin_shortcut_works_from_persistent_keyboard(monkeypatch):
    from app.bot.flows import admin as admin_flow
    from app.bot.flows import text_router
    from app.bot.states import ST_BAN, set_state
    up = update()
    up.effective_message.text = "👑 پنل ادمین"
    context = SimpleNamespace(user_data={"lang": "fa", "is_admin": True})
    set_state(context, ST_BAN)
    calls = []
    async def show_panel(update, context):
        calls.append("admin")
    monkeypatch.setattr(admin_flow, "show_panel", show_panel)
    await text_router.on_text(up, context)
    assert calls == ["admin"]
    assert context.user_data.get("state") is None


@pytest.mark.asyncio
async def test_copy_link_button_provides_actual_signed_url(db):
    store = FileStore(db.files_dir, db.tmp_dir)
    path = store.link_path("copy123", "test.mp4")
    path.write_bytes(b"x")
    await repo.create_shared("copy123", 42, str(path), path.name, "video/mp4", 1, 3600)
    context = SimpleNamespace(
        bot_data={"services": SimpleNamespace(cfg=db, store=store)},
        user_data={"lang": "fa"}
    )
    up = update()
    await user_links.cmd_links(up, context)
    buttons = [btn for row in up.effective_message.markups[-1].inline_keyboard for btn in row]
    copied = next(btn.copy_text.text for btn in buttons if btn.copy_text)
    opened = next(btn.url for btn in buttons if btn.url)
    assert copied == opened
    assert "/f/" in copied


@pytest.mark.asyncio
async def test_remote_telegram_attachment_stream_progress(db):
    from aiohttp import web
    payload = b"123456789" * 60000
    async def stream(request):
        return web.Response(body=payload, content_type="application/octet-stream")
    app = web.Application()
    app.router.add_get("/file", stream)
    async with TestClient(TestServer(app)) as client:
        url = str(client.make_url("/file"))
        store = FileStore(db.files_dir, db.tmp_dir)
        service = SimpleNamespace(
            cfg=db, store=store, settings=RuntimeSettings(db), admin_group=None
        )
        manager = FileLinkTransfers(service)
        class Attachment:
            mime_type = "application/octet-stream"
            async def get_file(self):
                return SimpleNamespace(file_path=url)
        up = update()
        item = await manager.start(up, "fa", Attachment(), "remote.bin", len(payload))
        await asyncio.wait_for(item.job, 5)
        row = await repo.get_shared(item.id)
        assert row is not None
        assert Path(row.path).read_bytes() == payload
        assert any("%" in t for t in up.effective_message.texts)
        assert "لینک مستقیم آماده" in up.effective_message.texts[-1]


@pytest.mark.asyncio
async def test_cancel_remote_transfer_during_stream(db):
    from aiohttp import web
    started = asyncio.Event()
    resume = asyncio.Event()
    async def slow(request):
        response = web.StreamResponse()
        await response.prepare(request)
        await response.write(b"x" * 10000)
        started.set()
        try:
            await asyncio.wait_for(resume.wait(), 2)
            await response.write(b"y" * 10000)
            await response.write_eof()
        except (TimeoutError, ConnectionResetError):
            pass
        return response
    app = web.Application()
    app.router.add_get("/slow", slow)
    async with TestClient(TestServer(app)) as client:
        url = str(client.make_url("/slow"))
        store = FileStore(db.files_dir, db.tmp_dir)
        service = SimpleNamespace(
            cfg=db, store=store, settings=RuntimeSettings(db), admin_group=None
        )
        manager = FileLinkTransfers(service)
        class Attachment:
            async def get_file(self):
                return SimpleNamespace(file_path=url)
        up = update()
        item = await manager.start(up, "fa", Attachment(), "slow.bin", 20000)
        await asyncio.wait_for(started.wait(), 2)
        assert manager.cancel(item.id, 42)
        await asyncio.wait_for(item.job, 3)
        resume.set()
        assert await repo.get_shared(item.id) is None
        assert not (store.links / item.id).exists()
        assert "لغو" in up.effective_message.texts[-1]


@pytest.mark.asyncio
async def test_shared_links_are_private_chat_only(db):
    context = SimpleNamespace(
        bot_data={"services": SimpleNamespace(cfg=db)},
        user_data={"lang": "fa"},
    )
    up = update()
    up.effective_chat.type = "group"
    await user_links.cmd_links(up, context)
    assert "گفت‌وگوی خصوصی" in up.effective_message.texts[-1]
    assert all(markup is None for markup in up.effective_message.markups)


def test_upload_reader_stops_on_cancel(tmp_path):
    from app.core.errors import JobCancelled
    from app.services.uploader import ProgressReader
    fh = (tmp_path / "sample.bin")
    fh.write_bytes(b"123456")
    counts = []
    stop = asyncio.Event()
    with fh.open("rb") as handle:
        reader = ProgressReader(handle, counts.append, stop)
        assert reader.read(3) == b"123"
        assert counts == [3]
        stop.set()
        with pytest.raises(JobCancelled):
            reader.read(3)
        assert handle.tell() == 3
