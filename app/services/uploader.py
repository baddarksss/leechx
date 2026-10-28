"""آپلود فایل در تلگرام با نمایش درصد آپلود.

``ProgressReader`` یک فایل را می‌پیچد و هر بار که PTB/httpx از آن می‌خواند
شمارنده را به‌روز می‌کند؛ به این ترتیب بدون تغییر در کتابخانه، درصد آپلود
واقعی داریم.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import BinaryIO

from telegram import InputFile, Message
from telegram.constants import ParseMode
from telegram.error import TelegramError

from app.config import Config
from app.core import errors, human
from app.services.downloader import DownloadResult, Progress
from app.services.runtime_settings import RuntimeSettings

log = logging.getLogger("leechx.uploader")

BOT_API_LIMIT = 50 * 1024 * 1024  # سقف آپلود Bot API بدون سرور محلی


class ProgressReader:
    """فایل را می‌خواند و تعداد بایت‌های خوانده‌شده را گزارش می‌کند."""

    def __init__(self, fh: BinaryIO, on_read: Callable[[int], None]) -> None:
        self._fh = fh
        self._on_read = on_read

    def read(self, size: int = -1) -> bytes:
        data = self._fh.read(size)
        if data:
            self._on_read(len(data))
        return data

    def seek(self, *args, **kwargs):
        return self._fh.seek(*args, **kwargs)

    def tell(self):
        return self._fh.tell()

    def close(self) -> None:
        self._fh.close()

    def __getattr__(self, item):
        return getattr(self._fh, item)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _caption(title: str, extra: str = "") -> str:
    text = human.esc(title)
    if extra:
        text += f"\n<code>{human.esc(extra)}</code>"
    return text[:1000]


class Uploader:
    def __init__(self, cfg: Config, settings: RuntimeSettings) -> None:
        self.cfg = cfg
        self.settings = settings

    def _check_size(self, size: int) -> None:
        limit = self.settings.max_upload_bytes
        if size > limit:
            raise errors.TooLarge(
                key="too_big",
                size=human.human_bytes(size),
                max=human.human_bytes(limit),
            )
        if size > BOT_API_LIMIT and not self.cfg.uses_local_api:
            raise errors.TooLarge(
                key="too_big",
                size=human.human_bytes(size),
                max=human.human_bytes(BOT_API_LIMIT),
            )

    async def send(
        self,
        bot,
        chat_id: int,
        result: DownloadResult,
        progress: Progress,
        source_url: str = "",
    ) -> Message:
        self._check_size(result.size)
        progress.stage = "uploading"
        progress.pct = 0.0
        progress.uploaded = 0
        progress.total = result.size

        def on_read(n: int) -> None:
            progress.uploaded += n
            if progress.total:
                progress.pct = min(99.9, progress.uploaded * 100.0 / progress.total)

        thumb_path = result.thumbnail
        caption = _caption(result.title, source_url)
        fh = result.path.open("rb")
        reader = ProgressReader(fh, on_read)
        filename = result.path.name
        input_file = InputFile(reader, filename=filename)

        thumb_handle = None
        thumb_file = None
        try:
            if thumb_path and thumb_path.exists():
                thumb_handle = thumb_path.open("rb")
                thumb_file = InputFile(thumb_handle, filename="thumb.jpg")

            common = {"caption": caption, "parse_mode": ParseMode.HTML}

            if result.is_audio or result.mime.startswith("audio/"):
                return await bot.send_audio(
                    chat_id=chat_id,
                    audio=input_file,
                    title=result.title[:64],
                    duration=result.duration or 0,
                    filename=filename,
                    **common,
                )

            if result.mime.startswith("image/"):
                return await bot.send_photo(chat_id=chat_id, photo=input_file, **common)

            if result.mime.startswith("video/"):
                extra = {}
                if result.width and result.height:
                    extra["width"] = result.width
                    extra["height"] = result.height
                return await bot.send_video(
                    chat_id=chat_id,
                    video=input_file,
                    duration=result.duration or 0,
                    supports_streaming=True,
                    thumbnail=thumb_file,
                    filename=filename,
                    **extra,
                    **common,
                )

            return await bot.send_document(
                chat_id=chat_id,
                document=input_file,
                filename=filename,
                thumbnail=thumb_file,
                **common,
            )
        except TelegramError as exc:
            msg = str(exc)
            if "too big" in msg.lower():
                raise errors.TooLarge(
                    key="too_big",
                    size=human.human_bytes(result.size),
                    max=human.human_bytes(BOT_API_LIMIT),
                ) from exc
            raise
        finally:
            try:
                fh.close()
            except OSError:
                pass
            if thumb_handle is not None:
                try:
                    thumb_handle.close()
                except OSError:
                    pass
