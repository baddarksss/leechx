"""حذف خودکار محتوای بزرگسال: تشخیص، تایمر و اتصال به صف کار.

این تست‌ها هیچ شبکه‌ای لمس نمی‌کنند: bot جعلی است و ``sleep`` تزریق می‌شود.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import nsfwguard
from app.services.downloader import DownloadResult, Progress
from app.services.jobs import JobManager, JobTask
from app.services.nsfwguard import (
    clamp_seconds,
    is_nsfw,
    is_nsfw_extractor,
    looks_like_nsfw_url,
)
from app.services.runtime_settings import RuntimeSettings
from app.services.uploader import Uploader


# ── تشخیص ───────────────────────────────────────────────────
def test_clamp_seconds_keeps_safe_window():
    assert clamp_seconds(0) == 5
    assert clamp_seconds(-1) == 5
    assert clamp_seconds(30) == 30
    assert clamp_seconds(5_000) == 600
    assert clamp_seconds(None) == 30
    assert clamp_seconds("abc") == 30


def test_nsfw_extractors_are_recognized():
    assert is_nsfw_extractor("pornhub")
    assert is_nsfw_extractor("PornHub:playlist")
    assert is_nsfw_extractor("e621")
    assert not is_nsfw_extractor("youtube")
    assert not is_nsfw_extractor("")
    assert not is_nsfw_extractor(None)


def test_is_nsfw_uses_site_index_and_extractor(monkeypatch):
    monkeypatch.setattr(
        nsfwguard,
        "sites",
        SimpleNamespace(is_nsfw_url=lambda url: "adult.example" in url),
    )
    assert is_nsfw("https://adult.example/v/1")
    assert is_nsfw("https://youtube.com/watch?v=1", extractor="pornhub")
    assert not is_nsfw("https://youtube.com/watch?v=1", extractor="youtube")


def test_is_nsfw_survives_site_index_failure(monkeypatch):
    def boom(_url):
        raise RuntimeError("index unavailable")

    monkeypatch.setattr(nsfwguard, "sites", SimpleNamespace(is_nsfw_url=boom))
    # الگوی میزبان حتی بدون ایندکس هم محتوای بزرگسال را می‌شناسد
    assert is_nsfw("https://www.xnxx.com/video/1")
    assert not is_nsfw("https://www.youtube.com/watch?v=1")


def test_looks_like_nsfw_url_matches_host_labels():
    # دامنه‌هایی که واژهٔ «porn/xxx/...» ندارند ولی در فهرست اکسترکتورها هستند
    assert looks_like_nsfw_url("https://www.xnxx.com/video/1")
    assert looks_like_nsfw_url("https://e621.net/posts/1")
    assert looks_like_nsfw_url("https://sub.onlyfans.com/x")
    assert not looks_like_nsfw_url("https://youtube.com/watch?v=1")
    assert not looks_like_nsfw_url("")
    # ورودی غیرعادی نباید خطا بدهد
    assert looks_like_nsfw_url("not a url") is False


# ── تنظیمات ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_nsfw_autodelete_is_off_by_default(db):
    settings = RuntimeSettings(db)
    await settings.load()
    assert settings.nsfw_autodelete is False
    assert settings.nsfw_autodelete_seconds == 30

    await settings.set("nsfw_autodelete_enabled", True)
    await settings.set("nsfw_autodelete_seconds", 1)
    assert settings.nsfw_autodelete is True
    assert settings.nsfw_autodelete_seconds == 5  # حداقل امن

    snap = settings.snapshot()
    assert snap["nsfw_autodelete_enabled"] is True
    assert snap["nsfw_autodelete_seconds"] == 5


# ── تایمر حذف ───────────────────────────────────────────────
class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.edits: list[tuple[int, str]] = []
        self.deleted: list[tuple[int, int]] = []
        self._next_id = 900

    async def send_message(self, chat_id, text, **kwargs):
        self._next_id += 1
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})
        return SimpleNamespace(message_id=self._next_id)

    async def edit_message_text(self, chat_id, message_id, text, **kwargs):
        self.edits.append((message_id, text))

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


@pytest.mark.asyncio
async def test_private_chat_deletes_every_part_after_countdown():
    bot = FakeBot()
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    await nsfwguard.cleanup_messages(
        bot,
        chat_id=7,
        message_ids=[11, 12],
        lang="fa",
        seconds=10,
        sleep=fake_sleep,
    )

    assert len(bot.sent) == 1
    notice = bot.sent[0]
    assert notice["reply_to_message_id"] == 11
    assert "10" in notice["text"]
    assert "نسخهٔ خصوصی" not in notice["text"]
    assert sum(slept) == pytest.approx(10)
    assert bot.deleted == [(7, 11), (7, 12)]
    # اعلان بعد از حذف به «حذف شد» تغییر می‌کند
    assert bot.edits[-1][1] == nsfwguard.text.t("fa", "nsfw_autodelete_done")
    assert len(bot.edits) > 1  # شمارش معکوس ویرایش شده است


@pytest.mark.asyncio
async def test_group_chat_is_never_touched():
    bot = FakeBot()

    async def fake_sleep(_seconds: float) -> None:
        return None

    await nsfwguard.cleanup_messages(
        bot,
        chat_id=-100123,
        message_ids=[31],
        lang="en",
        seconds=5,
        sleep=fake_sleep,
    )

    # Group topics are an immutable archive: no notice, no deletion.
    assert bot.sent == []
    assert bot.deleted == []


# ── اتصال به صف کار ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_job_schedules_cleanup_for_sent_parts(monkeypatch):
    seen: list[dict] = []

    async def fake_cleanup(bot, **kwargs):
        seen.append(kwargs)

    monkeypatch.setattr(nsfwguard, "cleanup_messages", fake_cleanup)
    manager = JobManager(
        cfg=SimpleNamespace(),
        settings=SimpleNamespace(),
        store=SimpleNamespace(),
        downloader=None,
        uploader=None,
        limiter=SimpleNamespace(),
    )
    manager.bot = FakeBot()
    task = JobTask(
        id="job1",
        user_id=7,
        chat_id=7,
        url="https://www.pornhub.com/view_video.php?viewkey=1",
        option=SimpleNamespace(selector="", label="720"),
        title="clip",
    )
    task.sent_messages = [SimpleNamespace(message_id=5), SimpleNamespace(message_id=6)]

    assert manager._schedule_nsfw_cleanup(task, 30) is True
    await asyncio.gather(*manager._nsfw_tasks)

    assert seen and seen[0]["message_ids"] == [5, 6]
    assert seen[0]["chat_id"] == 7
    assert "copy_dm" not in seen[0]
    assert "user_id" not in seen[0]


@pytest.mark.asyncio
async def test_job_never_schedules_cleanup_for_groups(monkeypatch):
    async def fake_cleanup(bot, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("group cleanup must not run")

    monkeypatch.setattr(nsfwguard, "cleanup_messages", fake_cleanup)
    manager = JobManager(
        cfg=SimpleNamespace(),
        settings=SimpleNamespace(),
        store=SimpleNamespace(),
        downloader=None,
        uploader=None,
        limiter=SimpleNamespace(),
    )
    manager.bot = FakeBot()
    task = JobTask(
        id="job-group",
        user_id=7,
        chat_id=-100123,
        url="https://www.pornhub.com/view_video.php?viewkey=1",
        option=SimpleNamespace(selector="", label="720"),
        title="clip",
    )
    task.sent_messages = [SimpleNamespace(message_id=5)]

    assert manager._schedule_nsfw_cleanup(task, 30) is False
    assert not manager._nsfw_tasks


# ── آپلودر همهٔ پیام‌ها را گزارش می‌کند ─────────────────────
class FakeUploadBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def send_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        return SimpleNamespace(message_id=101)

    async def send_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return SimpleNamespace(message_id=102)


@pytest.mark.asyncio
async def test_uploader_collects_sent_messages_and_spoiler(cfg, tmp_path: Path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00" * 4096)
    result = DownloadResult(
        path=path, title="clip", mime="video/mp4", size=4096, duration=3
    )
    uploader = Uploader(cfg, SimpleNamespace(max_upload_bytes=50 * 1024 * 1024))
    bot = FakeUploadBot()
    sent = []

    message = await uploader.send(
        bot, 7, result, Progress(), "https://example.com/v", sent=sent, spoiler=True
    )

    assert message.message_id == 101
    assert [m.message_id for m in sent] == [101]
    assert bot.calls[0][1]["has_spoiler"] is True


@pytest.mark.asyncio
async def test_uploader_skips_spoiler_when_not_requested(cfg, tmp_path: Path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00" * 4096)
    result = DownloadResult(path=path, title="clip", mime="video/mp4", size=4096)
    uploader = Uploader(cfg, SimpleNamespace(max_upload_bytes=50 * 1024 * 1024))
    bot = FakeUploadBot()
    sent = []

    await uploader.send(bot, 7, result, Progress(), sent=sent)

    assert [m.message_id for m in sent] == [101]
    assert bot.calls[0][1]["has_spoiler"] is None
