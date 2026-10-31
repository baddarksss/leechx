"""آپلود فایل در تلگرام با نمایش درصد آپلود.

``ProgressReader`` یک فایل را می‌پیچد و هر بار که PTB/httpx از آن می‌خواند
شمارنده را به‌روز می‌کند؛ به این ترتیب بدون تغییر در کتابخانه، درصد آپلود
واقعی داریم.

سه حالت تحویل پشتیبانی می‌شود (انتخاب با کاربر است):
* ``video``  → ``send_video`` / ``send_audio`` / ``send_photo``
* ``document`` → ``send_document`` (فایل خام، بدون پیش‌نمایش)
* ``link``   → در ``JobManager`` به لینک مستقیم تبدیل می‌شود (اینجا نیست)
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from telegram import InputFile, InputMediaPhoto, Message
from telegram.constants import ParseMode
from telegram.error import TelegramError

from app.config import Config
from app.core import caption as caption_mod
from app.core import errors, human
from app.services.downloader import DownloadResult, Progress
from app.services.runtime_settings import RuntimeSettings

log = logging.getLogger("leechx.uploader")

BOT_API_LIMIT = 50 * 1024 * 1024  # سقف آپلود Bot API بدون سرور محلی
PHOTO_LIMIT = 10 * 1024 * 1024   # سقف عکس تلگرام (sendPhoto)
ALBUM_CHUNK = 10                 # حداکثر آیتم در هر media group

# فرمت‌هایی که تلگرام به‌عنوان ویدیو قابل پخش می‌داند
PLAYABLE_VIDEO_EXT = {".mp4", ".m4v", ".mov"}


def upload_limit(cfg: Config, settings: RuntimeSettings) -> int:
    """بزرگ‌ترین فایلی که در این نصب می‌توان به تلگرام فرستاد.

    بدون سرور محلی، Bot API سخت‌گیرانه ۵۰ مگابایت است؛ با Local Bot API سقف
    قابل‌تنظیم ``max_upload_mb`` اعمال می‌شود.
    """
    limit = int(getattr(settings, "max_upload_bytes", BOT_API_LIMIT) or BOT_API_LIMIT)
    if getattr(cfg, "uses_local_api", False):
        return limit
    return min(limit, BOT_API_LIMIT)


class ProgressReader:
    """فایل را می‌خواند و تعداد بایت‌های خوانده‌شده را گزارش می‌کند."""

    def __init__(self, fh: BinaryIO, on_read: Callable[[int], None],
                 cancel: asyncio.Event | None = None) -> None:
        self._fh = fh
        self._on_read = on_read
        self._cancel = cancel

    def read(self, size: int = -1) -> bytes:
        if self._cancel is not None and self._cancel.is_set():
            raise errors.JobCancelled()
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


def media_kind(result: DownloadResult) -> str:
    if result.is_audio or result.mime.startswith("audio/"):
        return "audio"
    if result.mime.startswith("image/"):
        return "image"
    if result.mime.startswith("video/"):
        return "video"
    return "document"


class Uploader:
    def __init__(self, cfg: Config, settings: RuntimeSettings) -> None:
        self.cfg = cfg
        self.settings = settings

    def _check_size(self, size: int) -> None:
        limit = upload_limit(self.cfg, self.settings)
        if size > limit:
            raise errors.TooLarge(
                key="too_big",
                size=human.human_bytes(size),
                max=human.human_bytes(limit),
            )

    def limit(self) -> int:
        """سقف آپلود مؤثر (برای نمایش و تصمیم تقسیم)."""
        return upload_limit(self.cfg, self.settings)

    async def send(
        self,
        bot,
        chat_id: int,
        result: DownloadResult,
        progress: Progress,
        source_url: str = "",
        *,
        as_document: bool = False,
        filename: str | None = None,
        caption_title: str | None = None,
        custom_thumbnail: bytes | None = None,
        cancel: asyncio.Event | None = None,
        with_caption: bool = True,
        reset_progress: bool = True,
        progress_total: int | None = None,
    ) -> Message:
        self._check_size(result.size)
        if reset_progress:
            progress.stage = "uploading"
            progress.pct = 0.0
            progress.uploaded = 0
            progress.uploaded_bytes_total = 0
        progress.total = progress_total if progress_total is not None else result.size

        kind = media_kind(result)
        display_name = human.safe_filename(
            filename or result.path.name,
            150,
        )
        title = caption_title or result.title or Path(display_name).stem
        caption = caption_mod.build_caption(title, source_url, kind) if with_caption else ""
        common = {"caption": caption, "parse_mode": ParseMode.HTML}

        opened: list[BinaryIO] = []
        thumb_handle = None
        thumb_file = None

        def on_media_read(n: int) -> None:
            progress.uploaded += n
            progress.uploaded_bytes_total += n
            if progress.total:
                progress.pct = min(99.9, progress.uploaded * 100.0 / progress.total)

        def on_thumbnail_read(n: int) -> None:
            progress.uploaded_bytes_total += n

        def open_media() -> InputFile:
            fh = result.path.open("rb")
            opened.append(fh)
            return InputFile(
                ProgressReader(fh, on_media_read, cancel),
                filename=display_name,
                read_file_handle=False,
            )

        def make_thumbnail_input(handle, filename: str) -> InputFile:
            return InputFile(
                ProgressReader(handle, on_thumbnail_read, cancel),
                filename=filename,
                read_file_handle=False,
            )

        def reset() -> None:
            progress.pct = 0.0
            progress.uploaded = 0

        try:
            if custom_thumbnail:
                if len(custom_thumbnail) > 200 * 1024:
                    raise ValueError("custom thumbnail exceeds Telegram's 200 KB limit")
                thumb_handle = BytesIO(custom_thumbnail)
                thumb_file = make_thumbnail_input(thumb_handle, "thumbnail.jpg")
            elif result.thumbnail and result.thumbnail.exists():
                thumb_handle = result.thumbnail.open("rb")
                thumb_file = make_thumbnail_input(thumb_handle, "thumb.jpg")

            if not as_document and kind == "audio":
                return await bot.send_audio(
                    chat_id=chat_id,
                    audio=open_media(),
                    title=title[:64],
                    duration=result.duration or 0,
                    filename=display_name,
                    thumbnail=thumb_file,
                    **common,
                )

            if not as_document and kind == "image":
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=open_media(),
                    **common,
                )

            if not as_document and kind == "video" and result.suffix in PLAYABLE_VIDEO_EXT:
                extra = {}
                if result.width and result.height:
                    extra["width"] = result.width
                    extra["height"] = result.height
                try:
                    return await bot.send_video(
                        chat_id=chat_id,
                        video=open_media(),
                        duration=result.duration or 0,
                        supports_streaming=True,
                        thumbnail=thumb_file,
                        filename=display_name,
                        **extra,
                        **common,
                    )
                except TelegramError as exc:
                    # بعضی کدک‌ها را تلگرام به‌عنوان ویدیو قبول نمی‌کند؛
                    # همان فایل را به‌صورت document می‌فرستیم تا کار شکست نخورد.
                    if "too big" in str(exc).lower():
                        raise
                    log.info("video upload rejected (%s); retrying as document", exc)
                    reset()
                    if thumb_handle is not None and not thumb_handle.closed:
                        thumb_handle.seek(0)

            return await bot.send_document(
                chat_id=chat_id,
                document=open_media(),
                filename=display_name,
                thumbnail=thumb_file,
                **common,
            )
        except TelegramError as exc:
            msg = str(exc)
            if "too big" in msg.lower():
                limit = upload_limit(self.cfg, self.settings)
                raise errors.TooLarge(
                    key="too_big",
                    size=human.human_bytes(result.size),
                    max=human.human_bytes(limit),
                ) from exc
            raise
        finally:
            for handle in [*opened, thumb_handle]:
                if handle is None:
                    continue
                try:
                    handle.close()
                except OSError:
                    pass

    async def send_gallery(
        self,
        bot,
        chat_id: int,
        result: DownloadResult,
        progress: Progress,
        source_url: str = "",
        *,
        as_document: bool = False,
        filename: str | None = None,
        caption_title: str | None = None,
        custom_thumbnail: bytes | None = None,
        cancel: asyncio.Event | None = None,
    ) -> Message:
        """تحویل آلبوم/گالری: چندانتخابی عکس به‌صورت media group.

        عکس‌های سبک در گروه‌های ۱۰تایی (آلبوم تلگرام) و بقیهٔ فایل‌ها
        تک‌تک ارسال می‌شوند. در حالت ``document`` همه خام و جدا می‌روند.
        """
        parts = [p for p in (result.parts or [result.path]) if p and p.exists()]
        if not parts:
            raise errors.UnsupportedUrl("Nothing downloaded")

        title = caption_title or result.title
        if len(parts) == 1:
            single = self.part_result(result, parts[0])
            return await self.send(
                bot, chat_id, single, progress, source_url,
                as_document=as_document, filename=filename,
                caption_title=title, custom_thumbnail=custom_thumbnail,
                cancel=cancel,
            )

        for part in parts:
            self._check_size(part.stat().st_size)

        total = sum(part.stat().st_size for part in parts)
        progress.stage = "uploading"
        progress.pct = 0.0
        progress.uploaded = 0
        progress.uploaded_bytes_total = 0
        progress.total = total

        def on_read(n: int) -> None:
            progress.uploaded += n
            progress.uploaded_bytes_total += n
            if progress.total:
                progress.pct = min(99.9, progress.uploaded * 100.0 / progress.total)

        photo_parts = [
            part for part in parts
            if not as_document
            and self._is_photo(part)
            and part.stat().st_size <= PHOTO_LIMIT
        ]
        photo_set = set(photo_parts)
        others = [part for part in parts if part not in photo_set]

        first_message: Message | None = None
        caption_sent = False
        opened: list[BinaryIO] = []

        def markup(caption: str) -> InputMediaPhoto:
            return InputMediaPhoto(
                media=InputFile(
                    ProgressReader(fh, on_read, cancel),
                    filename=path.name,
                    read_file_handle=False,
                ),
                caption=caption or None,
                parse_mode=ParseMode.HTML if caption else None,
            )

        try:
            for start in range(0, len(photo_parts), ALBUM_CHUNK):
                chunk = photo_parts[start:start + ALBUM_CHUNK]
                media = []
                for path in chunk:
                    fh = path.open("rb")
                    opened.append(fh)
                    caption = ""
                    if not caption_sent and start == 0 and path is chunk[0]:
                        caption = caption_mod.build_caption(
                            title, source_url, "image"
                        )
                    media.append(markup(caption))
                try:
                    messages = await bot.send_media_group(
                        chat_id=chat_id, media=media
                    )
                    if not caption_sent and start == 0:
                        caption_sent = True
                    if first_message is None and messages:
                        first_message = messages[0]
                except TelegramError as exc:
                    log.info("media group rejected (%s); sending files one by one", exc)
                    for path in chunk:
                        if cancel is not None and cancel.is_set():
                            raise errors.JobCancelled() from None
                        single = self.part_result(result, path)
                        message = await self.send(
                            bot, chat_id, single, progress, source_url,
                            as_document=False,
                            caption_title=title,
                            with_caption=not caption_sent,
                            reset_progress=False,
                            progress_total=total,
                            cancel=cancel,
                        )
                        caption_sent = True
                        first_message = first_message or message

            for path in others:
                if cancel is not None and cancel.is_set():
                    raise errors.JobCancelled()
                single = self.part_result(result, path)
                message = await self.send(
                    bot, chat_id, single, progress, source_url,
                    as_document=(
                        as_document
                        or (self._is_photo(path) and path.stat().st_size > PHOTO_LIMIT)
                    ),
                    caption_title=title,
                    with_caption=not caption_sent,
                    reset_progress=False,
                    progress_total=total,
                    cancel=cancel,
                )
                caption_sent = True
                first_message = first_message or message

            progress.pct = 100.0
            if first_message is None:
                raise errors.UnsupportedUrl("Nothing uploaded")
            return first_message
        finally:
            for handle in opened:
                try:
                    handle.close()
                except OSError:
                    pass

    @staticmethod
    def _is_photo(path: Path) -> bool:
        mime, _ = mimetypes.guess_type(path.name)
        return bool(mime and mime.startswith("image/"))

    def part_result(self, parent: DownloadResult, path: Path) -> DownloadResult:
        """یک نتیجهٔ مستقل برای هر پارت (برای آپلود جداگانه)."""
        mime, _ = mimetypes.guess_type(path.name)
        mime = mime or parent.mime or "application/octet-stream"
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        return DownloadResult(
            path=path,
            title=parent.title,
            width=parent.width,
            height=parent.height,
            mime=mime,
            size=size,
            thumbnail=parent.thumbnail,
            is_audio=mime.startswith("audio/"),
            gallery=parent.gallery,
        )

