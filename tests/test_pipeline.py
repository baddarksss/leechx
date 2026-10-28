"""تست سرتاسری خط لوله (بدون تلگرام): دانلود → آپلود → پاک‌سازی.

یک وب‌سرور محلی فایل را سرو می‌کند، Downloader آن را می‌گیرد، آپلودر ماک
می‌شود و بررسی می‌کنیم که رکورد کار «done» شود و پوشهٔ کار پاک شود.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from aiohttp import web

from app.db import repo
from app.services.downloader import Downloader
from app.services.filestore import FileStore
from app.services.formats import FormatOption
from app.services.jobs import JobManager, JobTask
from app.services.ratelimit import RateLimiter
from app.services.runtime_settings import RuntimeSettings

PAYLOAD = b"leechx-test" * 20_000  # ~۲۲۰KB


class StubUploader:
    def __init__(self) -> None:
        self.results = []
        self.progress = []

    async def send(self, bot, chat_id, result, progress, source_url=""):
        self.results.append(result)
        self.progress.append(progress.uploaded)
        return SimpleNamespace(message_id=1)


class StubBot:
    def __init__(self) -> None:
        self.edits: list[str] = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs.get("text", ""))


@pytest.fixture()
async def file_server():
    async def handler(request: web.Request) -> web.Response:
        return web.Response(body=PAYLOAD, content_type="video/mp4")

    app = web.Application()
    app.router.add_get("/movie.mp4", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
    yield f"http://127.0.0.1:{port}/movie.mp4"
    await runner.cleanup()


@pytest.mark.asyncio
async def test_direct_job_full_pipeline(db, file_server):
    cfg = db
    store = FileStore(cfg.files_dir, cfg.tmp_dir)
    downloader = Downloader(cfg)
    uploader = StubUploader()
    settings = RuntimeSettings(cfg)
    await settings.load()

    manager = JobManager(cfg, settings, store, downloader, uploader, RateLimiter(0))
    bot = StubBot()
    manager.bot = bot

    info = await downloader.probe(file_server)
    assert info.direct is True
    assert info.mime == "video/mp4"
    assert info.filesize == len(PAYLOAD)

    task = JobTask(
        id="pipe1",
        user_id=42,
        chat_id=42,
        url=file_server,
        option=FormatOption(kind="direct", code="direct", label="direct", selector=""),
        title=info.title,
        info=info,
        lang="fa",
    )

    await manager.submit(task)
    await manager._run(task)

    # آپلود انجام شده و حجم درست است
    assert len(uploader.results) == 1
    assert uploader.results[0].size == len(PAYLOAD)
    assert uploader.results[0].mime == "video/mp4"

    # رکورد کار موفق است
    job = await repo.get_job("pipe1")
    assert job.status == "done"
    assert job.size == len(PAYLOAD)

    # شمارندهٔ سهمیه یک واحد است، نه بایت
    since = int(time.time()) - 60
    assert await repo.user_events_since(42, "download_done", since) == 1.0
    assert await repo.user_events_since(42, "bytes", since) == float(len(PAYLOAD))

    # هیچ فایلی از کار باقی نمانده است
    assert not (store.jobs / "pipe1").exists()
    assert manager.active_count == 0
    assert manager.limiter.active_count(42) == 0


@pytest.mark.asyncio
async def test_failed_download_marks_job_failed_and_cleans(db):
    cfg = db
    store = FileStore(cfg.files_dir, cfg.tmp_dir)
    downloader = Downloader(cfg)
    uploader = StubUploader()
    settings = RuntimeSettings(cfg)
    await settings.load()

    manager = JobManager(cfg, settings, store, downloader, uploader, RateLimiter(0))
    manager.bot = StubBot()

    from app.services.downloader import MediaInfo

    broken = "http://127.0.0.1:1/nothing.mp4"
    task = JobTask(
        id="pipe2",
        user_id=7,
        chat_id=7,
        url=broken,
        option=FormatOption(kind="direct", code="direct", label="direct", selector=""),
        title="nothing",
        info=MediaInfo(url=broken, title="nothing", direct=True, ext="mp4", mime="video/mp4"),
        lang="fa",
    )

    await manager.submit(task)
    await manager._run(task)

    job = await repo.get_job("pipe2")
    assert job.status == "failed"
    assert uploader.results == []
    assert not (store.jobs / "pipe2").exists()


@pytest.fixture()
async def odd_files_server():
    """فایل PDF (نه ویدیو) و سروری که HEAD را رد می‌کند."""

    async def pdf(request: web.Request) -> web.Response:
        return web.Response(body=b"%PDF-1.4 test", content_type="application/pdf")

    async def video(request: web.Request) -> web.Response:
        return web.Response(body=PAYLOAD, content_type="video/mp4")

    app = web.Application()
    app.router.add_get("/doc.pdf", pdf)
    app.router.add_get("/nohead.mp4", video, allow_head=False)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
    yield f"http://127.0.0.1:{port}"
    await runner.cleanup()


@pytest.mark.asyncio
async def test_probe_accepts_pdf_direct_link(db, odd_files_server):
    info = await Downloader(db).probe(f"{odd_files_server}/doc.pdf")
    assert info.direct is True
    assert info.mime == "application/pdf"
    assert info.ext == "pdf"


@pytest.mark.asyncio
async def test_probe_retries_when_head_is_rejected(db, odd_files_server):
    info = await Downloader(db).probe(f"{odd_files_server}/nohead.mp4")
    assert info.direct is True
    assert info.mime == "video/mp4"


def test_is_direct_mime():
    from app.services.downloader import is_direct_mime

    assert is_direct_mime("video/mp4")
    assert is_direct_mime("audio/mpeg; charset=utf-8")
    assert is_direct_mime("application/octet-stream")
    assert is_direct_mime("application/pdf")
    assert not is_direct_mime("text/html")
    assert not is_direct_mime("application/json")
    assert not is_direct_mime("")
