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
        settings=SimpleNamespace(
            daily_quota=0,
            nsfw_enabled=True,
            ttl_hours=6.0,
            max_links_per_user=0,
        ),
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
async def test_direct_link_shows_delivery_menu_without_quality(db):
    info = MediaInfo(url="https://cdn.example.com/movie.mp4", title="movie.mp4", direct=True,
                     ext="mp4", mime="video/mp4", filesize=1024)
    update = make_update()
    context, services, jobs = make_context(info)

    await link_flow.handle_link(update, context, "https://cdn.example.com/movie.mp4")

    assert jobs.tasks == []                    # تا انتخاب نحوهٔ تحویل کاری صف نمی‌شود
    assert len(services.drafts) == 1
    draft = next(iter(services.drafts._items.values()))
    assert draft.kind == "direct"
    assert draft.option.kind == "direct"

    markup = update.effective_message.kwargs[-1]["reply_markup"]
    buttons = [btn for row in markup.inline_keyboard for btn in row if btn.callback_data]
    callbacks = {btn.callback_data for btn in buttons}
    assert f"o|{draft.id}|format|video" in callbacks
    assert f"o|{draft.id}|format|document" in callbacks
    assert f"o|{draft.id}|destination|telegram" in callbacks
    assert f"o|{draft.id}|destination|link" in callbacks
    assert f"o|{draft.id}|r" in callbacks
    assert f"o|{draft.id}|thumbnail" in callbacks
    assert f"o|{draft.id}|start" in callbacks
    assert not any(btn.callback_data.startswith("q|") for btn in buttons)
    assert update.effective_message.texts[0]  # پیام «در حال بررسی»

    # Per-link options update in place; only the final Start queues work.
    query = FakeQuery(update.effective_message)
    callback_update = make_update(query)
    await callbacks_flow._on_delivery(callback_update, context, [draft.id, "format", "video"])
    assert jobs.tasks == []
    assert draft.send_as == "video"
    await callbacks_flow._on_delivery(callback_update, context, [draft.id, "destination", "link"])
    assert jobs.tasks == []
    assert draft.destination == "link"
    await callbacks_flow._on_delivery(callback_update, context, [draft.id, "start"])

    assert len(jobs.tasks) == 1
    task = jobs.tasks[0]
    assert task.kind == "direct"
    assert task.mode == "link"
    assert task.option.kind == "direct"
    assert task.info.direct is True
    assert task.info.ext == "mp4"
    assert task.user_id == 1
    assert len(services.drafts) == 0          # پیش‌نویس مصرف می‌شود


@pytest.mark.asyncio
async def test_quality_menu_then_selection_enqueues_job(db):
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

    assert jobs.tasks == []                   # هنوز فقط صفحهٔ تحویل نمایش داده شده
    assert draft.option.code == "720"
    assert draft.option.kind == "video"
    assert len(services.drafts) == 1

    delivery_markup = update.effective_message.kwargs[-1]["reply_markup"]
    callbacks = {
        btn.callback_data
        for row in delivery_markup.inline_keyboard
        for btn in row
        if btn.callback_data
    }
    assert f"o|{draft.id}|format|video" in callbacks
    assert f"o|{draft.id}|format|document" in callbacks
    assert f"o|{draft.id}|destination|telegram" in callbacks
    assert f"o|{draft.id}|destination|link" in callbacks
    assert f"o|{draft.id}|q" in callbacks
    assert f"o|{draft.id}|start" in callbacks

    # Choose File, then explicitly press Start to queue the job.
    delivery_update = make_update(FakeQuery(update.effective_message))
    await callbacks_flow._on_delivery(
        delivery_update, context, [draft.id, "format", "document"]
    )
    assert jobs.tasks == []
    await callbacks_flow._on_delivery(delivery_update, context, [draft.id, "start"])

    assert len(jobs.tasks) == 1
    task = jobs.tasks[0]
    assert task.option.code == "720"
    assert task.option.kind == "video"
    assert task.kind == "link"
    assert task.mode == "document"
    assert task.user_id == 1
    assert task.lang == "fa"
    assert len(services.drafts) == 0          # پیش‌نویس مصرف می‌شود


@pytest.mark.asyncio
async def test_quality_selection_from_other_user_is_rejected(db):
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
async def test_rename_then_direct_link_mode(db):
    info = MediaInfo(url="https://cdn.example.com/clip.mp4", title="clip.mp4", direct=True,
                     ext="mp4", mime="video/mp4")
    update = make_update()
    context, services, jobs = make_context(info)
    await link_flow.handle_link(update, context, info.url)
    draft = next(iter(services.drafts._items.values()))

    await callbacks_flow._on_delivery(make_update(FakeQuery(update.effective_message)), context, [draft.id, "r"])
    assert context.user_data["state"] == "rename"

    message = FakeMessage()
    message.text = "My Clip"
    text_update = make_update()
    text_update.effective_message = message
    await link_flow.handle_rename(text_update, context)

    assert context.user_data.get("state") is None
    assert draft.custom_name == "My Clip"
    assert "My Clip.mp4" in link_flow.draft_name(draft)

    delivery_update = make_update(FakeQuery(update.effective_message))
    await callbacks_flow._on_delivery(delivery_update, context, [draft.id, "l"])

    assert len(jobs.tasks) == 1
    task = jobs.tasks[0]
    assert task.mode == "link"
    assert task.custom_name == "My Clip"
    assert task.option.kind == "direct"


@pytest.mark.asyncio
async def test_custom_thumbnail_photo_is_saved_and_passed_to_queued_job(db):
    info = MediaInfo(
        url="https://cdn.example.com/clip.mp4",
        title="clip.mp4",
        direct=True,
        ext="mp4",
        mime="video/mp4",
    )
    first_update = make_update()
    context, services, jobs = make_context(info)
    await link_flow.handle_link(first_update, context, info.url)
    draft = next(iter(services.drafts._items.values()))

    query = FakeQuery(first_update.effective_message)
    await callbacks_flow._on_delivery(
        make_update(query), context, [draft.id, "thumbnail"]
    )
    assert context.user_data["state"] == "thumbnail"

    class TelegramFile:
        async def download_as_bytearray(self):
            return bytearray(b"\xff\xd8custom-jpeg")

    class PhotoSize:
        width = 320
        height = 180
        file_size = 120
        async def get_file(self):
            return TelegramFile()

    photo_message = FakeMessage()
    photo_message.photo = [PhotoSize()]
    photo_update = make_update()
    photo_update.effective_message = photo_message
    await link_flow.handle_thumbnail(photo_update, context)

    assert draft.custom_thumbnail == b"\xff\xd8custom-jpeg"
    assert context.user_data.get("state") is None
    await callbacks_flow._on_delivery(
        make_update(FakeQuery(first_update.effective_message)),
        context,
        [draft.id, "start"],
    )
    assert jobs.tasks[0].custom_thumbnail == b"\xff\xd8custom-jpeg"


@pytest.mark.asyncio
async def test_daily_quota_is_per_user(monkeypatch, db):
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
    assert len(services.drafts) == 1
    assert next(iter(services.drafts._items.values())).user_id == 2


@pytest.mark.asyncio
async def test_non_video_defaults_to_document_automatically(db):
    info = MediaInfo(
        url="https://cdn.example.com/track.mp3",
        title="track.mp3",
        direct=True,
        ext="mp3",
        mime="audio/mpeg",
    )
    update = make_update()
    context, services, _jobs = make_context(info)
    await link_flow.handle_link(update, context, info.url)
    draft = next(iter(services.drafts._items.values()))
    assert draft.send_as == "document"
    assert not link_flow.can_send_as_video(draft)


@pytest.mark.asyncio
async def test_oversized_telegram_delivery_offers_split_then_enqueues(db):
    size = 25 * 1024 * 1024
    info = MediaInfo(
        url="https://cdn.example.com/big.mp4",
        title="big.mp4",
        direct=True,
        ext="mp4",
        mime="video/mp4",
        filesize=size,
    )
    update = make_update()
    context, services, jobs = make_context(info)
    services.cfg.uses_local_api = True
    services.settings.max_upload_bytes = 10 * 1024 * 1024
    await link_flow.handle_link(update, context, info.url)
    draft = next(iter(services.drafts._items.values()))

    query = FakeQuery(update.effective_message)
    await callbacks_flow._on_delivery(make_update(query), context, [draft.id, "start"])

    # قبل از دانلود، فقط پیشنهاد تقسیم نمایش داده می‌شود.
    assert jobs.tasks == []
    assert draft.id in services.drafts._items
    markup = update.effective_message.kwargs[-1]["reply_markup"]
    callbacks = {
        btn.callback_data
        for row in markup.inline_keyboard
        for btn in row
        if btn.callback_data
    }
    assert f"o|{draft.id}|split" in callbacks
    assert f"o|{draft.id}|nosplit" in callbacks
    assert draft.pending_mode == "video"

    # تأیید کاربر → همان انتخاب قبلی در صف قرار می‌گیرد.
    await callbacks_flow._on_delivery(make_update(query), context, [draft.id, "split"])

    assert len(jobs.tasks) == 1
    assert jobs.tasks[0].mode == "video"
    assert len(services.drafts) == 0

