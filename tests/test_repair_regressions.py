"""Regression tests for problems reproduced on the live bot.

No live bot, secrets, or external network access is needed.
"""
from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from app.bot.flows import admin as admin_flow, start as start_flow
from app.bot.states import ST_BAN, set_state
from app.core import errors, urlcheck
from app.db import repo
from app.services.downloader import DownloadResult, Progress, map_error
from app.services.drafts import Draft, DraftStore
from app.services.filestore import FileStore
from app.services.link_server import LinkServer
from app.services.linktoken import make_token
from app.services.runtime_settings import RuntimeSettings
from app.services.uploader import Uploader


def make_fake_update():
    texts = []
    class Msg:
        effective_attachment = None
        text = None
        async def reply_text(self, body, **kwargs):
            texts.append(body)
            return self
    message = Msg()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=42, username="qa", first_name="QA"),
        effective_message=message,
        callback_query=None,
    ), texts


@pytest.mark.asyncio
async def test_cancel_drops_form_and_all_pending_choices():
    update, texts = make_fake_update()
    drafts = DraftStore()
    drafts.put(Draft(id="mine", user_id=42, chat_id=42, url="https://x.org", title="x"))
    drafts.put(Draft(id="other", user_id=99, chat_id=99, url="https://x.org", title="x"))
    class Jobs:
        def tasks_for_user(self, user_id):
            return []
    context = SimpleNamespace(
        bot_data={"services": SimpleNamespace(jobs=Jobs(), drafts=drafts)},
        user_data={"lang": "fa"},
    )
    set_state(context, ST_BAN)
    await start_flow.cmd_cancel(update, context)
    assert context.user_data.get("state") is None
    assert drafts.get("mine") is None
    assert drafts.get("other") is not None
    assert "لغو" in texts[-1]


@pytest.mark.asyncio
async def test_cancel_without_active_operation_explains_idle():
    update, texts = make_fake_update()
    class Jobs:
        def tasks_for_user(self, uid):
            return []
    context = SimpleNamespace(
        bot_data={"services": SimpleNamespace(jobs=Jobs(), drafts=DraftStore())},
        user_data={"lang":"fa"},
    )
    await start_flow.cmd_cancel(update,context)
    assert "هیچ عملیات" in texts[-1]


@pytest.mark.asyncio
async def test_forwarded_document_is_routed_to_file_flow(monkeypatch):
    update, _ = make_fake_update()
    update.effective_message.effective_attachment = SimpleNamespace(file_size=100)
    context = SimpleNamespace(user_data={})
    calls = []
    async def fake_handle(update, context):
        calls.append("file")
    monkeypatch.setattr("app.bot.flows.files.handle_file",fake_handle)
    await admin_flow.handle_forwarded(update,context)
    assert calls == ["file"]


@pytest.mark.asyncio
async def test_forwarded_text_routes_without_admin_ban(monkeypatch):
    update, _ = make_fake_update()
    update.effective_message.text = "https://example.com/file.mp4"
    context = SimpleNamespace(user_data={})
    calls = []
    async def fake_handle(update, context):
        calls.append("text")
    monkeypatch.setattr("app.bot.flows.text_router.on_text",fake_handle)
    await admin_flow.handle_forwarded(update,context)
    assert calls == ["text"]


def test_classify_http_errors_instead_of_unsupported():
    assert isinstance(map_error(Exception("HTTP Error 404: Not Found")), errors.ResourceNotFound)
    assert isinstance(map_error(Exception("HTTP Error 403: Forbidden")), errors.AccessDenied)
    assert isinstance(map_error(Exception("Connection timed out")), errors.DownloadTimeout)
    assert isinstance(map_error(Exception("Unsupported URL")), errors.UnsupportedUrl)
    e = errors.IncompleteDownload("missing bytes")
    assert map_error(e) is e


@pytest.mark.asyncio
async def test_url_security_rejects_private_hosts(monkeypatch):
    assert not await urlcheck.is_safe_public_url("http://127.0.0.1:8080/test.mp4")
    assert not await urlcheck.is_safe_public_url("http://10.0.0.2/s")
    assert not await urlcheck.is_safe_public_url("http://[::1]/")
    assert not await urlcheck.is_safe_public_url("http://localhost:8888")
    assert not await urlcheck.is_safe_public_url("http://metadata.google.internal/")
    assert not await urlcheck.is_safe_public_url("http://user:pass@public.example/x")
    async def private_dns(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.5", 80))]
    monkeypatch.setattr("asyncio.get_running_loop", lambda: SimpleNamespace(getaddrinfo=private_dns))
    assert not await urlcheck.is_safe_public_url("https://attacker.example/file")
    async def public_dns(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.1.1.1", 443))]
    monkeypatch.setattr("asyncio.get_running_loop", lambda: SimpleNamespace(getaddrinfo=public_dns))
    assert await urlcheck.is_safe_public_url("https://example.com/file.mp4")


@pytest.mark.asyncio
async def test_large_file_input_is_lazy_stream(tmp_path):
    path=tmp_path/"large.mp4"
    path.write_bytes(b"x"*1024*1024)
    result=DownloadResult(path=path,title="large",mime="video/mp4",size=path.stat().st_size)
    progress=Progress()
    class Bot:
        async def send_document(self, **kwargs):
            input_file=kwargs["document"]
            assert not isinstance(input_file.input_file_content,bytes)
            assert input_file.input_file_content.read() == b"x"*1024*1024
            return SimpleNamespace(message_id=2)
    uploader=Uploader(SimpleNamespace(uses_local_api=False),
                      SimpleNamespace(max_upload_bytes=2*1024*1024))
    await uploader.send(Bot(),42,result,progress,as_document=True)
    assert progress.uploaded==path.stat().st_size


@pytest.mark.asyncio
async def test_link_file_size_integrity_and_invalid_range(db):
    store=FileStore(db.files_dir,db.tmp_dir)
    server=LinkServer(db,RuntimeSettings(db),store)
    path=store.link_path("repair1","x.bin")
    path.write_bytes(b"12345678")
    await repo.create_shared("repair1", 42, str(path), "x.bin","application/octet-stream",8,3600)
    token=make_token("repair1",db.link_secret,3600)
    async with TestClient(TestServer(server.build_app())) as client:
        healthy=await client.get(f"/f/{token}",headers={"Range":"bytes=1-3"})
        assert healthy.status==206
        assert await healthy.read()==b"234"
        assert healthy.headers["Cache-Control"]=="private, no-store"
        invalid=await client.get(f"/f/{token}",headers={"Range":"bytes=100-120"})
        assert invalid.status==416
        assert invalid.headers["Content-Range"]=="bytes */8"
        path.write_bytes(b"1234")
        corrupt=await client.get(f"/f/{token}")
        assert corrupt.status==503


@pytest.mark.asyncio
async def test_link_sibling_directory_is_blocked(db):
    store=FileStore(db.files_dir,db.tmp_dir)
    sibling=store.root/"links-trap"/"secret"
    sibling.parent.mkdir(parents=True,exist_ok=True)
    sibling.write_bytes(b"hidden")
    server=LinkServer(db,RuntimeSettings(db),store)
    await repo.create_shared("wrongpath",42,str(sibling),"secret","text/plain",6,3600)
    token=make_token("wrongpath",db.link_secret,3600)
    async with TestClient(TestServer(server.build_app())) as client:
        result=await client.get(f"/f/{token}")
        assert result.status==403


@pytest.mark.asyncio
async def test_same_user_updates_are_serial_but_other_users_run_concurrently():
    import asyncio
    from datetime import UTC, datetime
    from telegram import Chat, Message, Update, User
    from app.bot.update_processor import UserOrderedUpdateProcessor

    def make_update(uid, mid):
        user = User(id=uid, is_bot=False, first_name="QA")
        msg = Message(message_id=mid, date=datetime.now(UTC),
                      chat=Chat(id=uid, type="private"), from_user=user)
        return Update(update_id=mid, message=msg)

    processor = UserOrderedUpdateProcessor(4)
    await processor.initialize()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()
    other_started = asyncio.Event()
    order = []

    async def first():
        order.append("first")
        first_started.set()
        await release_first.wait()

    async def second():
        order.append("second")
        second_started.set()

    async def other():
        order.append("other")
        other_started.set()

    a = asyncio.create_task(processor.process_update(make_update(41, 1), first()))
    await asyncio.wait_for(first_started.wait(), 2)
    b = asyncio.create_task(processor.process_update(make_update(41, 2), second()))
    c = asyncio.create_task(processor.process_update(make_update(43, 3), other()))
    await asyncio.wait_for(other_started.wait(), 2)
    assert not second_started.is_set()
    release_first.set()
    await asyncio.wait_for(asyncio.gather(a, b, c), 2)
    assert order.index("second") > order.index("first")
    assert processor._locks == {}
    await processor.shutdown()


@pytest.mark.asyncio
async def test_direct_downloader_rejects_truncated_body(monkeypatch, tmp_path, db):
    import asyncio
    from app.services.downloader import Downloader, MediaInfo
    from app.services.formats import FormatOption
    async def safe_url(url): return True
    monkeypatch.setattr("app.services.downloader.urlcheck.is_safe_public_url", safe_url)
    class Content:
        async def iter_chunked(self, size):
            yield b"abc"  # server advertised 10 bytes
    class Response:
        status=200
        url="https://test.example/video.mp4"
        headers={"Content-Length": "10"}
        content=Content()
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return False
        def release(self): pass
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return False
        async def request(self,*args,**kwargs): return Response()
    monkeypatch.setattr("app.services.downloader.aiohttp.ClientSession", lambda **kwargs: Session())
    downloader=Downloader(db)
    info=MediaInfo(url="https://test.example/video.mp4",title="video.mp4",
                   direct=True,ext="mp4",mime="video/mp4")
    with pytest.raises(errors.IncompleteDownload):
        await downloader.download(info.url,
            FormatOption(kind="direct", code="direct", label="direct", selector=""),
            tmp_path, Progress(), asyncio.Event(), info)


@pytest.mark.asyncio
async def test_generated_link_respects_size_limit(db, tmp_path):
    from app.services.downloader import Downloader
    from app.services.jobs import JobManager, JobTask
    from app.services.formats import FormatOption
    from app.services.ratelimit import RateLimiter
    store=FileStore(db.files_dir,db.tmp_dir)
    settings=RuntimeSettings(db)
    settings._cache["max_link_mb"]="1"
    manager=JobManager(db,settings,store,Downloader(db),None,RateLimiter(0))
    path=tmp_path/"oversize.mp4"
    path.write_bytes(b"x"*(1024*1024+1))
    result=DownloadResult(path=path,title="oversize",mime="video/mp4",size=path.stat().st_size)
    task=JobTask(id="limit-1",user_id=42,chat_id=42,url="https://example.com/a",
                 option=FormatOption(kind="direct",code="direct",label="direct",selector=""),
                 title="oversize",mode="link")
    with pytest.raises(errors.FileTooLargeForLink):
        await manager._deliver_link(task,result)
    assert path.exists()
    assert not (store.links/"limit-1").exists()
