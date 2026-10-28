"""تست جریان‌ها بدون شبکه تلگرام/اینترنت.

هدف: مطمئن شویم مسیر «لینک → کیفیت → صف» و «لینک مستقیم → صف بدون کیفیت»
و همچنین دکمه‌های کیفیت درست کار می‌کنند.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.flows import callbacks as callbacks_flow
from app.bot.flows import link as link_flow
from app.services.downloader import MediaInfo
from app.services.drafts import DraftStore
from app.services.ratelimit import RateLimiter

VIDEO_FORMATS = [
    {"height": h, "ext": "mp4", "vcodec": "avc1", "acodec": "none", "tbr": 1000, "format_id": str(h)}
    for h in (360, 720, 1080)
]


class FakeMessage:
    def __init__(self, texts: list[str] | None = None, kwargs: list[dict] | None = None) -> None:
        self.texts: list[str] = texts if texts is not None else []
        self.kwargs: list[dict] = kwargs if kwargs is not None else []
        self.chat_id = 1
        self.message_id = 10

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)
        self.kwargs.append(kwargs)
        return FakeMessage(self.texts, self.kwargs)

    async def edit_text(self, text, **kwargs):
        self.texts.append(text)
        self.kwargs.append(kwargs)


class FakeQuery:
    def __init__(self, message: FakeMessage) -> None:
        self.message = message
        self.answers: list[str | None] = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append(text)


class FakeDownloader:
    def __init__(self, info: MediaInfo) -> None:
        self.info = info
        self.probed: list[str] = []

    async def probe(self, url: str) -> MediaInfo:
        self.probed.append(url)
        return self.info


class FakeJobs:
    def __init__(self) -> None:
        self.tasks: list = []

    async def submit(self, task) -> int:
        self.tasks.append(task)
        return 1

    def cancel(self, job_id: str, user_id: int) -> bool:  # pragma: no cover - استفاده نشده
        return False


def make_update(query: FakeQuery | None = None, user_id: int = 1):
    message = query.message if query else FakeMessage()
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, username="u", first_name="U", is_bot=False),
        effective_chat=SimpleNamespace(id=user_id),
        effective_message=message,
        callback_query=query,
    )


def make_context(info: MediaInfo):
    jobs = FakeJobs()
    services = SimpleNamespace(
        cfg=SimpleNamespace(per_user_concurrency=1, max_height=0),
        settings=SimpleNamespace(daily_quota=0, nsfw_enabled=True, ttl_hours=6.0),
        limiter=RateLimiter(0),
        sites=SimpleNamespace(is_nsfw_url=lambda url: False),
        downloader=FakeDownloader(info),
        drafts=DraftStore(),
        jobs=jobs,
    )
    context = SimpleNamespace(
        user_data={"lang": "fa"},
        bot_data={"services": services},
        bot=None,
    )
    return context, services, jobs


@pytest.mark.asyncio
async def test_direct_link_skips_quality_selection():
    info = MediaInfo(url="https://cdn.example.com/movie.mp4", title="movie.mp4", direct=True,
                     ext="mp4", mime="video/mp4", filesize=1024)
    update = make_update()
    context, services, jobs = make_context(info)

    await link_flow.handle_link(update, context, "https://cdn.example.com/movie.mp4")

    assert len(jobs.tasks) == 1
    task = jobs.tasks[0]
    assert task.kind == "direct"
    assert task.option.kind == "direct"
    assert task.user_id == 1
    assert len(services.drafts) == 0          # هیچ پیش‌نویسی ساخته نمی‌شود
    assert update.effective_message.texts[0]  # پیام «در حال بررسی»
    assert "q|" not in update.effective_message.texts[-1]


@pytest.mark.asyncio
async def test_quality_menu_then_selection_enqueues_job():
    info = MediaInfo(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="Never Gonna Give You Up",
        duration=213,
        uploader="Rick Astley",
        formats=VIDEO_FORMATS,
    )
    update = make_update()
    context, services, jobs = make_context(info)

    await link_flow.handle_link(update, context, info.url)

    assert len(services.drafts) == 1
    draft = next(iter(services.drafts._items.values()))
    assert draft.lang == "fa"
    assert draft.title == "Never Gonna Give You Up"

    markup = update.effective_message.kwargs[-1]["reply_markup"]
    buttons = [btn for row in markup.inline_keyboard for btn in row if btn.callback_data]
    video_buttons = [btn for btn in buttons if btn.callback_data.startswith("q|")]
    assert {b.callback_data.split("|")[2] for b in video_buttons} >= {"360", "720", "1080", "mp3", "m4a"}

    # کاربر دکمهٔ 720p را می‌زند
    chosen = next(b.callback_data for b in video_buttons if b.callback_data.split("|")[2] == "720")
    query = FakeQuery(update.effective_message)
    callback_update = make_update(query)
    _, _, code, kind = chosen.split("|")

    await callbacks_flow._on_quality(callback_update, context, [draft.id, code, kind])

    assert len(jobs.tasks) == 1
    task = jobs.tasks[0]
    assert task.option.code == "720"
    assert task.option.kind == "video"
    assert task.kind == "link"
    assert task.user_id == 1
    assert task.lang == "fa"
    assert len(services.drafts) == 0          # پیش‌نویس مصرف می‌شود


@pytest.mark.asyncio
async def test_quality_selection_from_other_user_is_rejected():
    info = MediaInfo(url="https://x.com/a", title="t", formats=VIDEO_FORMATS)
    update = make_update()
    context, services, jobs = make_context(info)
    await link_flow.handle_link(update, context, info.url)
    draft = next(iter(services.drafts._items.values()))

    query = FakeQuery(FakeMessage())
    other = make_update(query, user_id=999)
    await callbacks_flow._on_quality(other, context, [draft.id, "720", "v"])

    assert jobs.tasks == []
    assert query.answers  # پیام «منقضی شده» به کاربر غریبه


@pytest.mark.asyncio
async def test_daily_quota_is_per_user(monkeypatch):
    info = MediaInfo(url="https://cdn.example.com/a.mp4", title="a.mp4", direct=True,
                     ext="mp4", mime="video/mp4")
    context, services, jobs = make_context(info)
    services.settings.daily_quota = 1

    async def fake_events(user_id: int, kind: str, ts: int) -> float:
        return 1.0 if user_id == 1 else 0.0

    monkeypatch.setattr("app.bot.flows.link.repo.user_events_since", fake_events)

    blocked = make_update(user_id=1)
    await link_flow.handle_link(blocked, context, info.url)
    assert jobs.tasks == []
    assert "سهمیه" in blocked.effective_message.texts[-1]

    allowed = make_update(user_id=2)
    await link_flow.handle_link(allowed, context, info.url)
    assert len(jobs.tasks) == 1
    assert jobs.tasks[0].user_id == 2
