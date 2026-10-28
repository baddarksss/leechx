"""تست آپلودر: کپشن روی همان پیام رسانه و حالت document."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.downloader import DownloadResult, Progress
from app.services.uploader import Uploader


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def send_video(self, **kwargs):
        self.calls.append(("video", kwargs))
        return SimpleNamespace(message_id=1)

    async def send_document(self, **kwargs):
        self.calls.append(("document", kwargs))
        return SimpleNamespace(message_id=2)

    async def send_audio(self, **kwargs):  # pragma: no cover - استفاده نشده
        self.calls.append(("audio", kwargs))
        return SimpleNamespace(message_id=3)


def make_uploader() -> Uploader:
    cfg = SimpleNamespace(uses_local_api=False)
    settings = SimpleNamespace(max_upload_bytes=10_000_000)
    return Uploader(cfg, settings)


def make_result(tmp_path) -> DownloadResult:
    path = tmp_path / "Clip [abc123].mp4"
    path.write_bytes(b"video-bytes" * 100)
    return DownloadResult(
        path=path,
        title="Real Title",
        mime="video/mp4",
        size=path.stat().st_size,
    )


@pytest.mark.asyncio
async def test_video_caption_is_attached_to_media_message(tmp_path):
    bot = FakeBot()
    result = make_result(tmp_path)

    await make_uploader().send(
        bot,
        chat_id=1,
        result=result,
        progress=Progress(),
        source_url="https://youtu.be/abc",
        filename=result.path.name,
    )

    kind, kwargs = bot.calls[0]
    assert kind == "video"
    assert kwargs["caption"].startswith("<b>Real Title</b>")
    assert "#YouTube" in kwargs["caption"]
    assert "#Video" in kwargs["caption"]
    assert 'href="https://youtu.be/abc"' in kwargs["caption"]
    assert kwargs["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_document_mode_forces_send_document(tmp_path):
    bot = FakeBot()
    result = make_result(tmp_path)

    await make_uploader().send(
        bot,
        chat_id=1,
        result=result,
        progress=Progress(),
        source_url="https://youtu.be/abc",
        as_document=True,
        filename="My Clip.mp4",
    )

    kind, kwargs = bot.calls[0]
    assert kind == "document"
    assert kwargs["document"].filename == "My Clip.mp4"
    assert kwargs["caption"]


@pytest.mark.asyncio
async def test_non_playable_video_goes_as_document(tmp_path):
    bot = FakeBot()
    result = make_result(tmp_path)
    result.path = result.path.with_suffix(".mkv")
    result.path.write_bytes(b"matroska" * 100)
    result.size = result.path.stat().st_size
    result.mime = "video/x-matroska"

    await make_uploader().send(
        bot,
        chat_id=1,
        result=result,
        progress=Progress(),
        filename=result.path.name,
    )

    assert bot.calls[0][0] == "document"
