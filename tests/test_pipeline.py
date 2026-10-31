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
from app.services import splitter
from app.services.downloader import Downloader, DownloadResult
from app.services.filestore import FileStore
from app.services.formats import FormatOption
from app.services.jobs import JobManager, JobTask
from app.services.ratelimit import RateLimiter
from app.services.runtime_settings import RuntimeSettings

PAYLOAD = b"leechx-test" * 20_000  # ~۲۲۰KB


@pytest.fixture(autouse=True)
def allow_local_test_server(monkeypatch):
    """The integration fixture explicitly serves on localhost."""
    async def _allow_fixture_url(url):
        return True
    monkeypatch.setattr("app.services.downloader.urlcheck.is_safe_public_url", _allow_fixture_url)


class StubUploader:
    def __init__(self) -> None:
        self.results = []
        self.progress = []

    async def send(self, bot, chat_id, result, progress, source_url="", **kwargs):
        self.results.append(result)
        self.progress.append(progress.uploaded)
        return SimpleNamespace(message_id=1)


class StubBot:
    def __init__(self) -> None:
        self.edits: list[str] = []

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs.get("text", ""))


class SplitStubUploader(StubUploader):
    """آپلودر تست که پارت‌های تقسیم‌شده را مثل Uploader واقعی می‌سازد."""

    def part_result(self, parent, path):
        return DownloadResult(
            path=path,
            title=parent.title,
            mime=parent.mime,
            size=path.stat().st_size,
        )


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


@pytest.fixture()
async def binary_server():
    """فایل غیرویدیو (PDF) برای تست تقسیم بایتی."""

    async def handler(request: web.Request) -> web.Response:
        return web.Response(body=PAYLOAD, content_type="application/pdf")

    app = web.Application()
    app.router.add_get("/archive.pdf", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
    yield f"http://127.0.0.1:{port}/archive.pdf"
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
    traffic = await repo.traffic_totals()
    assert traffic["source_download_bytes"] == len(PAYLOAD)
    # The stub uploader does not consume the InputFile; successful-send fallback
    # still uses the exact size of the delivered file payload.
    assert traffic["telegram_upload_bytes"] == len(PAYLOAD)
    assert traffic["downloaded_bytes"] == len(PAYLOAD)
    assert traffic["uploaded_bytes"] == len(PAYLOAD)
    assert traffic["total_bytes"] == 2 * len(PAYLOAD)

    # هیچ فایلی از کار باقی نمانده است
    assert not (store.jobs / "pipe1").exists()
    assert manager.active_count == 0
    assert manager.limiter.active_count(42) == 0


@pytest.mark.asyncio
async def test_oversized_file_is_split_and_uploaded_in_parts(db, binary_server, monkeypatch):
    cfg = db
    store = FileStore(cfg.files_dir, cfg.tmp_dir)
    downloader = Downloader(cfg)
    uploader = SplitStubUploader()
    settings = RuntimeSettings(cfg)
    await settings.load()

    limit = 100_000
    monkeypatch.setattr("app.services.jobs.upload_limit", lambda *_args: limit)
    manager = JobManager(cfg, settings, store, downloader, uploader, RateLimiter(0))
    manager.bot = StubBot()

    info = await downloader.probe(binary_server)
    task = JobTask(
        id="split1",
        user_id=44,
        chat_id=44,
        url=binary_server,
        option=FormatOption(kind="direct", code="direct", label="direct", selector=""),
        title=info.title,
        info=info,
        lang="fa",
        mode="document",
    )

    await manager.submit(task)
    await manager._run(task)

    cap = splitter.usable_bytes(limit)
    expected = splitter.planned_parts(len(PAYLOAD), cap)
    assert expected >= 2
    assert len(uploader.results) == expected
    assert all(part.size <= cap for part in uploader.results)
    assert sum(part.size for part in uploader.results) == len(PAYLOAD)

    job = await repo.get_job("split1")
    assert job.status == "done"
    assert job.size == len(PAYLOAD)
    assert not (store.jobs / "split1").exists()
    assert manager.limiter.active_count(44) == 0


@pytest.mark.asyncio
async def test_link_mode_stores_shared_file_and_cleans_job_dir(db, file_server):
    cfg = db
    store = FileStore(cfg.files_dir, cfg.tmp_dir)
    downloader = Downloader(cfg)
    uploader = StubUploader()
    settings = RuntimeSettings(cfg)
    await settings.load()

    manager = JobManager(cfg, settings, store, downloader, uploader, RateLimiter(0))
    manager.bot = StubBot()

    info = await downloader.probe(file_server)
    task = JobTask(
        id="pipe3",
        user_id=43,
        chat_id=43,
        url=file_server,
        option=FormatOption(kind="direct", code="direct", label="direct", selector=""),
        title=info.title,
        info=info,
        lang="fa",
        mode="link",
    )

    await manager.submit(task)
    await manager._run(task)

    assert uploader.results == []            # در حالت لینک چیزی به تلگرام آپلود نمی‌شود
    shared = await repo.get_shared("pipe3")
    assert shared is not None
    assert shared.size == len(PAYLOAD)
    traffic = await repo.traffic_totals()
    assert traffic["source_download_bytes"] == len(PAYLOAD)
    assert traffic["telegram_upload_bytes"] == 0
    assert traffic["direct_link_serve_bytes"] == 0
    assert traffic["downloaded_bytes"] == len(PAYLOAD)
    assert traffic["uploaded_bytes"] == 0
    assert store.link_path("pipe3", shared.name).exists()
    assert not (store.jobs / "pipe3").exists()  # پوشهٔ کار پاک شده
    assert manager.active_count == 0
    assert manager.limiter.active_count(43) == 0


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
