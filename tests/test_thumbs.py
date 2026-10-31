"""انتخاب تامبنیل از اسکرین‌شات‌های ویدیو.

هیچ شبکه‌ای لمس نمی‌شود؛ bot جعلی است و استخراج قاب‌ها ماک می‌شود.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import thumbs
from app.services.downloader import DownloadResult
from app.services.jobs import JobManager, JobTask


# ── زمان‌های رندوم فاصله‌دار ─────────────────────────────────
def test_shot_times_are_spaced_and_in_range():
    times = thumbs.shot_times(120.0)
    assert len(times) == thumbs.SHOTS
    assert times == sorted(times)
    assert all(0 <= t < 120 for t in times)
    # بازه‌های مساوی فابری-floor تداخل نمی‌کنند
    for a, b in zip(times, times[1:], strict=False):
        assert b - a >= 0.5


def test_shot_times_handles_short_and_zero_duration():
    assert thumbs.shot_times(0) == []
    assert thumbs.shot_times(-5) == []
    short = thumbs.shot_times(3.0)
    assert short and len(short) < thumbs.SHOTS  # قاب کمتر ولی کلاه‌برداری نمی‌کنیم
    two = thumbs.shot_times(8.0, count=10)
    assert len(two) >= 2


def test_shot_times_randomness_spreads_across_video():
    a = thumbs.shot_times(300.0)
    b = thumbs.shot_times(300.0)
    assert a != b  # تایم‌ها تصادفی‌اند
    slots = [i * 30 for i in range(10)]
    # هر قاب داخل بازهٔ خودش است؛ نزدیک هم نیستند
    for t, start in zip(a, slots, strict=False):
        assert start <= t < start + 30


def test_aria2c_opts_without_binary():
    opts = thumbs.aria2c_opts()
    if opts:  # اگر aria2c نصب باشد؛ در ماشین تست معمولاً نیست
        assert opts["external_downloader"]["default"] == "aria2c"
        assert "native" in opts["external_downloader"].values()
    else:
        assert opts == {}


# ── اتصال به صف کار ─────────────────────────────────────────
class FakeBot:
    def __init__(self) -> None:
        self.albums: list[list[bytes]] = []
        self.panel: dict | None = None
        self.deleted: list[tuple[int, int]] = []
        self._next = 400

    async def send_media_group(self, chat_id, media):
        self.albums.append([
            getattr(m.media, "input_file_content", m.media) for m in media
        ])
        out = []
        for _ in media:
            self._next += 1
            out.append(SimpleNamespace(message_id=self._next))
        return out

    async def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        self._next += 1
        self.panel = {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        return SimpleNamespace(message_id=self._next)

    async def delete_message(self, chat_id, message_id):
        self.deleted.append((chat_id, message_id))


def _make_task(job_id: str = "j1", chat_id: int = 7, user_id: int = 7) -> JobTask:
    task = JobTask(
        id=job_id,
        user_id=user_id,
        chat_id=chat_id,
        url="https://www.pornhub.com/view_video.php?viewkey=x",
        option=SimpleNamespace(selector="", label="240"),
        title="clip",
        lang="fa",
    )
    task.info = SimpleNamespace(duration=120)
    return task


def _make_result(tmp_path: Path) -> DownloadResult:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"\x00" * 2048)
    return DownloadResult(
        path=path, title="clip", mime="video/mp4", size=2048, duration=120
    )


@pytest.mark.asyncio
async def test_picker_sends_album_and_reply_chooses_cover(tmp_path: Path, monkeypatch):
    shot_files = []
    for i in range(3):
        shot = tmp_path / f"shot-{i}.jpg"
        shot.write_bytes(b"\xff\xd8" + b"\x00" * 400)
        shot_files.append(shot)

    async def fake_extract(video, times, workdir, cancel=None):
        return shot_files

    monkeypatch.setattr(thumbs, "extract_shots", fake_extract)
    settings = SimpleNamespace(thumb_wait_seconds=5)
    manager = JobManager(
        cfg=SimpleNamespace(), settings=settings, store=SimpleNamespace(),
        downloader=None, uploader=None, limiter=SimpleNamespace(),
    )
    bot = FakeBot()
    manager.bot = bot
    task = _make_task()
    manager._tasks[task.id] = task
    result = _make_result(tmp_path)

    runner = asyncio.ensure_future(
        manager._offer_thumb_shots(task, result, tmp_path, 120, 5)
    )
    await asyncio.sleep(0.05)
    # آلبوم + پنل آماده‌اند؛ حالا ریپلای روی قاب دوم
    second_id = task.shots[1][0]
    assert manager.thumb_note_reply(7, second_id, 7) == "picked"
    await runner

    assert bot.albums and all(m[:2] == b"\xff\xd8" for m in bot.albums[-1])
    assert "تامبنیل" in bot.panel["text"]
    # قاب انتخابی → تامبنیل کار
    assert task.custom_thumbnail == shot_files[1].read_bytes()
    # آلبوم و پنل بعد از انتخاب پاک می‌شوند
    for mid, _shot in task.shots:
        assert (7, mid) in bot.deleted
    assert len(bot.deleted) >= 3 + 1


@pytest.mark.asyncio
async def test_no_choice_after_wait_uses_default_cover(tmp_path: Path, monkeypatch):
    shot = tmp_path / "shot-0.jpg"
    shot.write_bytes(b"\xff\xd8" + b"\x00" * 400)

    async def fake_extract(video, times, workdir, cancel=None):
        return [shot]

    monkeypatch.setattr(thumbs, "extract_shots", fake_extract)
    settings = SimpleNamespace(thumb_wait_seconds=2)
    manager = JobManager(
        cfg=SimpleNamespace(), settings=settings, store=SimpleNamespace(),
        downloader=None, uploader=None, limiter=SimpleNamespace(),
    )
    manager.bot = FakeBot()
    task = _make_task()
    manager._tasks[task.id] = task
    result = _make_result(tmp_path)

    await manager._offer_thumb_shots(task, result, tmp_path, 120, 2)

    # بدون انتخاب → تامبنیل دست‌کم‌گرفته نشده (کاور سایت/قاب پیشفرض می‌ماند)
    assert task.custom_thumbnail is None


@pytest.mark.asyncio
async def test_skip_button_finishes_without_choice(tmp_path: Path, monkeypatch):
    shot = tmp_path / "shot-0.jpg"
    shot.write_bytes(b"\xff\xd8" + b"\x00" * 400)

    async def fake_extract(video, times, workdir, cancel=None):
        return [shot]

    monkeypatch.setattr(thumbs, "extract_shots", fake_extract)
    settings = SimpleNamespace(thumb_wait_seconds=60)
    manager = JobManager(
        cfg=SimpleNamespace(), settings=settings, store=SimpleNamespace(),
        downloader=None, uploader=None, limiter=SimpleNamespace(),
    )
    manager.bot = FakeBot()
    task = _make_task()
    manager._tasks[task.id] = task
    result = _make_result(tmp_path)

    runner = asyncio.ensure_future(
        manager._offer_thumb_shots(task, result, tmp_path, 120, 60)
    )
    await asyncio.sleep(0.05)
    assert manager.thumb_skip(task.id, 7) is True
    # انتخابِ کاربر دیگری رد می‌شود
    assert manager.thumb_skip(task.id, 9) is False
    await runner
    assert task.custom_thumbnail is None


@pytest.mark.asyncio
async def test_reply_from_other_user_is_ignored(tmp_path: Path, monkeypatch):
    shot = tmp_path / "shot-0.jpg"
    shot.write_bytes(b"\xff\xd8" + b"\x00" * 400)

    async def fake_extract(video, times, workdir, cancel=None):
        return [shot]

    monkeypatch.setattr(thumbs, "extract_shots", fake_extract)
    settings = SimpleNamespace(thumb_wait_seconds=30)
    manager = JobManager(
        cfg=SimpleNamespace(), settings=settings, store=SimpleNamespace(),
        downloader=None, uploader=None, limiter=SimpleNamespace(),
    )
    manager.bot = FakeBot()
    task = _make_task()
    manager._tasks[task.id] = task
    result = _make_result(tmp_path)

    runner = asyncio.ensure_future(
        manager._offer_thumb_shots(task, result, tmp_path, 120, 30)
    )
    await asyncio.sleep(0.05)
    assert manager.thumb_note_reply(7, task.shots[0][0], 9) == "wrong_user"
    # درخواستِ ناشناس هم رد می‌شود
    assert manager.thumb_note_reply(7, 987654, 9) is None
    assert manager.thumb_skip(task.id, 7) is True
    await runner
    assert task.custom_thumbnail is None


@pytest.mark.asyncio
async def test_wait_zero_builds_only_default_cover(tmp_path: Path):
    settings = SimpleNamespace(thumb_wait_seconds=0)
    manager = JobManager(
        cfg=SimpleNamespace(), settings=settings, store=SimpleNamespace(),
        downloader=None, uploader=None, limiter=SimpleNamespace(),
    )
    bot = FakeBot()
    manager.bot = bot
    task = _make_task()
    manager._tasks[task.id] = task
    result = _make_result(tmp_path)

    # استخراج واقعی بدون ffmpeg شکست می‌خورد ولی ما فقط مسیر call را می‌خواهیم
    async def fake_single(video, times, workdir, cancel=None):
        workdir.mkdir(parents=True, exist_ok=True)
        shot = workdir / "shot-01.jpg"
        shot.write_bytes(b"\xff\xd8" + b"\x00" * 400)
        return [shot]

    import app.services.thumbs as live

    original = live.extract_shots
    live.extract_shots = fake_single
    try:
        await manager._maybe_pick_thumbnail(task, result, tmp_path)
    finally:
        live.extract_shots = original

    assert bot.albums == []  # آلبومی فرستاده نشده
    assert task.custom_thumbnail is not None  # قاب پیشفرض ساخته شد
