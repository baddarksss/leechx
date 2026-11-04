"""صف کار و اجرای دانلود→آپلود.

چرا صف؟ چون هر دانلود/آپلود سنگین است و کاربران زیادی همزمان درخواست
می‌دهند. با ``WORKERS`` می‌توانی همزمانی کل سرور و با
``PER_USER_CONCURRENCY`` همزمانی هر کاربر را کنترل کنی. هر کار پیام وضعیت
خودش را دارد که هر چند ثانیه یک‌بار ویرایش می‌شود.
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import shutil
import time
import zipfile
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Kb
from telegram import Message
from telegram.constants import ParseMode
from telegram.error import TelegramError

from app.bot import keyboards as kb
from app.config import Config
from app.core import errors, human, text
from app.db import repo
from app.services import nsfwguard, splitter, thumbs, torrent
from app.services.downloader import (
    Downloader,
    DownloadResult,
    MediaInfo,
    Progress,
    fetch_thumbnail,
)
from app.services.filestore import FileStore
from app.services.formats import FormatOption
from app.services.linktoken import make_token
from app.services.ratelimit import RateLimiter
from app.services.runtime_settings import RuntimeSettings
from app.services.source_policy import is_social_source, public_cache_eligible
from app.services.uploader import (
    PLAYABLE_VIDEO_EXT,
    Uploader,
    dc_speed,
    media_kind,
    upload_limit,
)

log = logging.getLogger("leechx.jobs")

EDIT_INTERVAL = 2.2

DELIVERY_MODES = ("video", "document", "link")


def apply_custom_name(result, custom: str):
    """نام دلخواه کاربر را روی فایل دانلودشده اعمال می‌کند."""
    parts = getattr(result, "parts", None) or []
    if len(parts) > 1:
        # آلبوم‌ها نام‌های اصلی خودشان را نگه می‌دارند؛ تغییر نام همهٔ فایل‌ها
        # به یک نام باعث از دست رفتن ترتیب/تشخیص می‌شود.
        return result
    name = human.safe_filename(custom, 150)
    if not name or name == "file":
        return result
    ext = result.path.suffix
    provided = Path(name).suffix
    if provided and ext and provided.lower() != ext.lower():
        name = name[: -len(provided)].rstrip(" .") or name
    if ext and not name.lower().endswith(ext.lower()):
        name = f"{name}{ext}"
    target = result.path.with_name(name)
    if target != result.path:
        try:
            result.path.rename(target)
            result.path = target
        except OSError:
            log.debug("could not rename %s -> %s", result.path, target, exc_info=True)
            return result
    result.title = human.safe_filename(Path(name).stem, 150)
    return result


@dataclass
class JobTask:
    id: str
    user_id: int
    chat_id: int
    url: str
    option: FormatOption
    title: str
    status_message_id: int | None = None
    info: MediaInfo | None = None
    lang: str = "fa"
    kind: str = "link"
    mode: str = "video"
    custom_name: str = ""
    custom_thumbnail: bytes | None = None
    # ترجیح کاربر: انتخاب کاور از فریم‌های ویدیو (پیش‌فرض خاموش)
    thumb_picker: bool = False
    # VIP از محدودیت‌های کاربر عادی، از جمله حذف خودکار NSFW، معاف است.
    vip: bool = False
    # فعال فقط برای URL عمومیِ مجاز، بدون کوکی و بدون علامت NSFW.
    public_cache: bool = False
    slot_acquired: bool = False
    # همهٔ پیام‌های رسانه‌ای که در این کار ارسال شدند (پارت‌ها/آلبوم)؛ برای
    # حذف زمان‌بندی‌شدهٔ محتوای بزرگسال لازم است.
    sent_messages: list[Message] = field(default_factory=list)
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    progress: Progress = field(default_factory=Progress)
    created_at: float = field(default_factory=time.time)
    last_text: str = ""
    last_edit: float = 0.0
    finalized: bool = False
    edit_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    canceled_by_user: bool = False
    upload_task: asyncio.Task | None = None
    upload_started: float = 0.0
    # در _run یک‌بار محاسبه می‌شود (چک NSFW برای هر پارت تکرار نمی‌شود).
    nsfw: bool = False
    # اسکرین‌شات‌های ویدیو برای انتخاب تامبنیل: (شناسهٔ پیام عکس، مسیر فایل)
    shots: list[tuple[int, Path]] = field(default_factory=list)
    thumb_picked: Path | None = None
    thumb_done: asyncio.Event = field(default_factory=asyncio.Event)


class JobManager:
    def __init__(
        self,
        cfg: Config,
        settings: RuntimeSettings,
        store: FileStore,
        downloader: Downloader,
        uploader: Uploader,
        limiter: RateLimiter,
        hub=None,
    ) -> None:
        self.cfg = cfg
        self.settings = settings
        self.store = store
        self.downloader = downloader
        self.uploader = uploader
        self.limiter = limiter
        self.hub = hub
        self.cache = None

        self.bot = None
        self._queue: deque[JobTask] = deque()
        self._tasks: dict[str, JobTask] = {}
        self._workers: list[asyncio.Task] = []
        self._publisher: asyncio.Task | None = None
        self._nsfw_tasks: set[asyncio.Task] = set()
        # (chat_id, message_id) → کار در حال «انتخاب تامبنیل»
        self._pickers: dict[tuple[int, int], JobTask] = {}
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        # تسک‌های کوتاه پس‌زمینه (مثل ثبت «لغو شد») با رفرنس قوی و لاگ خطا.
        self._bg: set[asyncio.Task] = set()

    # ── چرخهٔ عمر ───────────────────────────────────────────
    async def start(self, bot) -> None:
        self.bot = bot
        stale = await repo.fail_stale_jobs()
        if stale:
            log.info("marked %d stale jobs as failed", stale)
        self._stop.clear()
        for i in range(max(1, self.cfg.workers)):
            self._workers.append(asyncio.create_task(self._worker(i), name=f"worker-{i}"))
        self._publisher = asyncio.create_task(self._publisher_loop(), name="progress")
        log.info("job manager started with %d workers", len(self._workers))

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        for task in self._tasks.values():
            task.cancel.set()
        for worker in self._workers:
            worker.cancel()
        if self._publisher is not None:
            self._publisher.cancel()
        # تایمرهای حذف NSFW هم باید با خاموش‌شدن سرویس متوقف شوند.
        for sweep in list(self._nsfw_tasks):
            sweep.cancel()
        self._nsfw_tasks.clear()
        for job in list(self._bg):
            job.cancel()
        self._bg.clear()
        for job in (*self._workers, self._publisher):
            if job is not None:
                try:
                    await job
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        self._workers.clear()
        self._publisher = None
        for task in list(self._tasks.values()):
            self.store.drop_job_dir(task.id)
        self._tasks.clear()
        self._queue.clear()

    # ── API ─────────────────────────────────────────────────
    async def submit(self, task: JobTask) -> int:
        """کار را در صف می‌گذارد و موقعیت آن را برمی‌گرداند."""
        await repo.create_job(
            job_id=task.id,
            user_id=task.user_id,
            chat_id=task.chat_id,
            url=task.url,
            kind=task.kind,
            selector=task.option.selector,
            quality=task.option.label,
            title=task.title,
        )
        self._tasks[task.id] = task
        self._queue.append(task)
        position = len(self._queue)
        self._wake.set()
        return position

    def get(self, job_id: str) -> JobTask | None:
        return self._tasks.get(job_id)

    async def _record_traffic(self, **amounts: int) -> None:
        """Traffic statistics are best-effort and must never interrupt delivery."""
        try:
            await repo.record_traffic(**amounts)
        except Exception:  # noqa: BLE001
            log.warning("traffic counters could not be updated", exc_info=True)

    def cancel(self, job_id: str, user_id: int) -> bool:
        task = self._tasks.get(job_id)
        if task is None or task.user_id != user_id:
            return False
        task.canceled_by_user = True
        task.cancel.set()
        if task.upload_task is not None and not task.upload_task.done():
            task.upload_task.cancel()
        if task in self._queue:
            try:
                self._queue.remove(task)
            except ValueError:
                pass
            self._tasks.pop(task.id, None)
            self._spawn(self._finish_canceled(task), f"cancel-{task.id}")
        return True

    def _spawn(self, coro, name: str) -> None:
        """اجرای کوتاه پس‌زمینه با نگه‌داشتن رفرنس و لاگ خطا (بدون تسک یتیم)."""
        job = asyncio.create_task(coro, name=name)
        self._bg.add(job)

        def _done(finished: asyncio.Task) -> None:
            self._bg.discard(finished)
            if finished.cancelled():
                return
            exc = finished.exception()
            if exc is not None:
                log.warning("background task %s failed", finished.get_name(), exc_info=exc)

        job.add_done_callback(_done)

    def tasks_for_user(self, user_id: int) -> list[JobTask]:
        return [t for t in list(self._tasks.values()) if t.user_id == user_id]

    @property
    def active_count(self) -> int:
        return len(self._tasks)

    @property
    def uploading_users(self) -> int:
        """کاربرانی که همین حالا فایلی را در تلگرام آپلود می‌کنند."""
        return len(
            {
                task.user_id
                for task in self._tasks.values()
                if task.mode in ("video", "document") and task.progress.stage == "uploading"
            }
        )

    # ── صف ──────────────────────────────────────────────────
    def _take_next(self) -> JobTask | None:
        """اولین کاری که کاربرش ظرفیت دارد را برمی‌دارد.

        کارهای لغوشده از صف حذف و «لغو شد» ثبت می‌شوند (بدون گرفتن slot).
        کارهای کاربرِ پرمشغله در صف می‌مانند تا نوبت بقیه از دست نرود.
        """
        limit = self.cfg.per_user_concurrency
        canceled: list[JobTask] = []
        picked: JobTask | None = None

        for task in list(self._queue):
            if task.cancel.is_set():
                self._queue.remove(task)
                self._tasks.pop(task.id, None)
                canceled.append(task)
                continue
            if picked is None:
                task.slot_acquired = False
                if task.vip:
                    can_take = True
                else:
                    can_take = self.limiter.acquire_slot(task.user_id, limit)
                    task.slot_acquired = can_take
                if can_take:
                    self._queue.remove(task)
                    picked = task

        for task in canceled:
            self._spawn(self._finish_canceled(task), f"cancel-{task.id}")
        return picked

    async def _next_or_wait(self) -> JobTask | None:
        while not self._stop.is_set():
            task = self._take_next()
            if task is not None:
                return task
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=2.0)
            except TimeoutError:
                continue
        return None

    async def _worker(self, index: int) -> None:
        log.debug("worker %d up", index)
        while not self._stop.is_set():
            task = await self._next_or_wait()
            if task is None:
                break
            try:
                await self._run(task)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001 — هیچ خطایی نباید worker را بکشد
                log.exception("worker %d crashed on job %s", index, task.id)

    # ── اجرای کار ───────────────────────────────────────────
    async def _run(self, task: JobTask) -> None:
        started = int(time.time())
        workdir = self.store.job_dir(task.id)
        source_traffic_recorded = 0
        upload_traffic_recorded = 0
        # محتوای بزرگسال: مثل بقیهٔ فایل‌ها در آرشیو گروه ادمین ذخیره می‌شود،
        # ولی از کش بازپخش نمی‌شود تا هر درخواست تایمر حذف خودش را داشته باشد.
        # در صورت فعال‌بودن تنظیم، نسخهٔ چت بعد از چند ثانیه پاک می‌شود.
        nsfw = nsfwguard.is_nsfw(
            task.url, getattr(task.info, "extractor", "") if task.info is not None else ""
        )
        task.nsfw = nsfw
        # Cross-user reuse is opt-in by policy and fails closed if cookie status
        # cannot be determined. Private, signed, cookie-dependent, and NSFW URLs
        # remain scoped to the requesting user.
        cookie_for = getattr(self.downloader, "cookie_for", None)
        has_cookie = True
        if callable(cookie_for):
            try:
                has_cookie = cookie_for(task.url) is not None
            except Exception:  # noqa: BLE001 — uncertain auth state means do not share
                has_cookie = True
        extractor = getattr(task.info, "extractor", "") if task.info is not None else ""
        share = bool(getattr(self.settings, "cache_cross_user", False)) if self.settings is not None else False
        task.public_cache = (
            task.mode != "link"
            and not task.custom_thumbnail
            and public_cache_eligible(
                task.url, extractor, has_cookie=has_cookie, nsfw=nsfw,
                allow_any_host=share, allow_nsfw=share,
            )
        )
        nsfw_delete_seconds = 0
        try:
            await repo.update_job(task.id, status="running", started_at=started)
            task.progress.stage = "downloading"
            await self._edit_progress(task, force=True)
            if self.hub is not None:
                await self.hub.notify_job("download", task)

            if (
                task.mode != "link"
                and self.cache is not None
                and not task.custom_thumbnail
            ):
                try:
                    cached = await self.cache.cached_delivery(self.bot, task)
                except Exception:
                    cached = None
                    log.warning("media cache read failed; proceeding normally", exc_info=True)
                if cached is not None:
                    await repo.update_job(
                        task.id, status="done", size=int(cached),
                        finished_at=int(time.time()),
                    )
                    await repo.bump_downloads(task.user_id)
                    await repo.bump_uploads(task.user_id)
                    await repo.log_event(task.user_id, "download_done")
                    await repo.log_event(task.user_id, "upload_done")
                    await repo.log_event(task.user_id, "bytes", float(cached))
                    task.progress.stage = "done"
                    task.progress.pct = 100.0
                    body = text.t(task.lang, "done") + "\n" + text.t(
                        task.lang, "cache_fast_delivery"
                    )
                    # An adult delivery replayed from cache still needs its own
                    # delete timer (unless the user is VIP or the chat is a group).
                    if nsfw and self.settings.nsfw_autodelete and not task.vip:
                        seconds = self.settings.nsfw_autodelete_seconds
                        if self._schedule_nsfw_cleanup(task, seconds):
                            body += "\n" + text.t(
                                task.lang,
                                "nsfw_autodelete_job_line",
                                seconds=seconds,
                            )
                    await self._edit_final(task, body)
                    if self.hub is not None:
                        await self.hub.notify_job_result(task, "cache_hit")
                    return

            if task.cancel.is_set():
                raise errors.JobCancelled()

            # اگر حجم از قبل معلوم است و دیسک جا ندارد، دانلود شروع نشود
            # (پر شدن دیسک دیتابیس و همهٔ کارها را می‌شکند).
            expected = int(getattr(task.option, "filesize", 0) or 0)
            if expected and not self.store.has_room(expected):
                raise errors.DiskFull(
                    need=human.human_bytes(expected),
                    free=human.human_bytes(self.store.disk_free()),
                )

            if task.mode == "song":
                # تشخیص آهنگ کلیپ (Shazam) و آوردن نسخهٔ کامل از یوتیوب.
                result = await self.downloader.download_song(
                    task.url, workdir, task.progress, task.cancel, task.info
                )
            elif torrent.is_magnet(task.url):
                result = await self._download_torrent(task, workdir)
            else:
                result = await self.downloader.download(
                    task.url,
                    task.option,
                    workdir,
                    task.progress,
                    task.cancel,
                    task.info,
                )
            source_bytes = int(
                getattr(task.progress, "downloaded_bytes_total", 0) or result.size or 0
            )
            if source_bytes > 0:
                await self._record_traffic(source_download_bytes=source_bytes)
                source_traffic_recorded = source_bytes

            if task.cancel.is_set():
                raise errors.JobCancelled()

            if task.custom_name:
                result = apply_custom_name(result, task.custom_name)

            if task.mode == "link":
                if task.cancel.is_set():
                    raise errors.JobCancelled()
                await self._deliver_link(task, result)
            else:
                if result.thumbnail is None:
                    result.thumbnail = await fetch_thumbnail(
                        task.info.thumbnail if task.info else None,
                        workdir / "thumb.jpg",
                        self.cfg.proxy,
                    )
                    if result.thumbnail is not None:
                        try:
                            thumbnail_bytes = result.thumbnail.stat().st_size
                        except OSError:
                            thumbnail_bytes = 0
                        if thumbnail_bytes > 0:
                            await self._record_traffic(
                                source_download_bytes=thumbnail_bytes
                            )
                            source_traffic_recorded += thumbnail_bytes

                # مشخصات واقعیِ فایل را از خود فایل بگیریم:
                # * سایت‌هایی که از اکسترکتور عمومی می‌آیند مدت‌زمان ندارند و
                #   تلگرام ویدیو را «00:00» و بدون قاب نشان می‌دهد،
                # * بدون مدت، مرحلهٔ انتخاب تامبنیل هم اجرا نمی‌شد.
                kind = media_kind(result)
                if kind in ("video", "audio") and not getattr(result, "gallery", False):
                    try:
                        meta = await thumbs.probe_media(result.path)
                    except Exception:  # noqa: BLE001 — این متادیتا فقط تزئینی است
                        meta = None
                    if meta is not None:
                        if meta.width and meta.height:
                            result.width, result.height = meta.width, meta.height
                        if meta.duration:
                            result.duration = meta.duration
                # تامبنیل: قاب‌های ویدیو برای انتخاب کاربر + یک قاب پیشفرض معتبر
                try:
                    await self._maybe_pick_thumbnail(task, result, workdir)
                except errors.JobCancelled:
                    raise
                except Exception:  # noqa: BLE001 — انتخاب تامبنیل نباید کار را بکشد
                    log.exception("thumbnail picker failed; continuing with default")

                limit = upload_limit(self.cfg, self.settings)
                split_plan = None
                if not getattr(result, "gallery", False) and result.size > limit:
                    # فایل از سقف تلگرام بزرگ‌تر است: قبل از آپلود به پارت‌های
                    # مستقل تقسیم می‌شود (کاربر قبلاً تأیید کرده یا حجم نامشخص بود).
                    planned = splitter.planned_parts(
                        result.size, splitter.usable_bytes(limit)
                    )
                    task.progress.stage = "splitting"
                    task.progress.parts = planned
                    await self._edit_progress(task, force=True)
                    if self.hub is not None:
                        await self.hub.notify_job("upload", task, result)
                    split_plan = await splitter.split_file(
                        result.path,
                        limit,
                        workdir,
                        mime=result.mime,
                        cancel=task.cancel,
                    )
                    if split_plan.count > 1:
                        task.progress.parts = split_plan.count
                    else:
                        split_plan = None

                if task.cancel.is_set():
                    raise errors.JobCancelled()

                if split_plan is not None:
                    uploaded_message = await self._send_split(task, result, split_plan)
                    uploaded_bytes = int(
                        getattr(task.progress, "uploaded_bytes_total", 0) or 0
                    )
                    if uploaded_bytes > 0:
                        await self._record_traffic(telegram_upload_bytes=uploaded_bytes)
                        upload_traffic_recorded = uploaded_bytes
                else:
                    task.progress.stage = "uploading"
                    task.progress.pct = 0.0
                    task.upload_started = time.monotonic()
                    await self._edit_progress(task, force=True)
                    if self.hub is not None:
                        await self.hub.notify_job("upload", task, result)

                    if getattr(result, "gallery", False):
                        # گالری/آلبوم: عکس‌ها گروهی و بقیه تک‌تک می‌روند. حالت
                        # «ویدیو» برای گالری یعنی ارسال به‌صورت مدیا، «فایل» یعنی خام.
                        send_coro = self.uploader.send_gallery(
                            self.bot,
                            task.chat_id,
                            result,
                            task.progress,
                            task.url,
                            as_document=task.mode == "document",
                            caption_title=result.title,
                            custom_thumbnail=task.custom_thumbnail,
                            cancel=task.cancel,
                            sent=task.sent_messages,
                        )
                    else:
                        send_coro = self.uploader.send(
                            self.bot,
                            task.chat_id,
                            result,
                            task.progress,
                            task.url,
                            as_document=(
                                task.mode == "document"
                                or (
                                    task.mode == "video"
                                    and (
                                        media_kind(result) != "video"
                                        or result.suffix not in PLAYABLE_VIDEO_EXT
                                    )
                                )
                            ),
                            filename=result.path.name,
                            custom_thumbnail=task.custom_thumbnail,
                            cancel=task.cancel,
                            sent=task.sent_messages,
                        )
                    task.upload_task = asyncio.create_task(send_coro)
                    try:
                        uploaded_message = await task.upload_task
                        uploaded_bytes = int(
                            getattr(task.progress, "uploaded_bytes_total", 0)
                            or task.progress.uploaded
                            or result.size
                            or 0
                        )
                        if uploaded_bytes > 0:
                            await self._record_traffic(telegram_upload_bytes=uploaded_bytes)
                            upload_traffic_recorded = uploaded_bytes
                    except asyncio.CancelledError:
                        if task.cancel.is_set():
                            raise errors.JobCancelled() from None
                        raise
                    except errors.TooLarge:
                        # سقف واقعی سرور تلگرام کمی پایین‌تر از تنظیم ما بود؛ به‌جای
                        # شکست، همان فایل را تقسیم و پارت‌به‌پارت می‌فرستیم.
                        if task.cancel.is_set():
                            raise errors.JobCancelled() from None
                        plan = await splitter.split_file(
                            result.path,
                            splitter.retry_limit(result.path.stat().st_size, limit),
                            workdir,
                            mime=result.mime,
                            cancel=task.cancel,
                        )
                        if plan.count < 2:
                            raise
                        split_plan = plan
                        task.progress.parts = plan.count
                        uploaded_message = await self._send_split(task, result, plan)
                        uploaded_bytes = int(
                            getattr(task.progress, "uploaded_bytes_total", 0) or 0
                        )
                        if uploaded_bytes > 0:
                            await self._record_traffic(
                                telegram_upload_bytes=uploaded_bytes
                            )
                            upload_traffic_recorded = uploaded_bytes
                    finally:
                        task.upload_task = None
                    if task.cancel.is_set():
                        # Private-chat deliveries may be removed if cancellation
                        # raced with upload. Group topics remain immutable.
                        if task.chat_id > 0:
                            try:
                                await self.bot.delete_message(
                                    chat_id=task.chat_id,
                                    message_id=uploaded_message.message_id,
                                )
                            except TelegramError:
                                pass
                        raise errors.JobCancelled()
                    # آرشیو گروه ادمین برای محتوای بزرگسال هم مثل بقیه است؛
                    # فقط نسخهٔ چت کاربر بعد از تایمر پاک می‌شود.
                    if self.cache is not None:
                        await self.cache.record_delivery(self.bot, task, result, uploaded_message)

            await repo.update_job(
                task.id,
                status="done",
                file_name=result.path.name,
                size=result.size,
                finished_at=int(time.time()),
            )
            task.progress.stage = "done"
            task.progress.pct = 100.0
            await repo.bump_downloads(task.user_id)
            await repo.bump_uploads(task.user_id)
            await repo.log_event(task.user_id, "download_done")
            await repo.log_event(task.user_id, "upload_done")
            await repo.log_event(task.user_id, "bytes", float(result.size))
            if task.mode != "link" and nsfw and self.settings.nsfw_autodelete and not task.vip:
                seconds = self.settings.nsfw_autodelete_seconds
                if self._schedule_nsfw_cleanup(task, seconds):
                    nsfw_delete_seconds = seconds
            if task.mode != "link":
                body = text.t(task.lang, "done") + f"\n<b>{human.esc(result.title)}</b>"
                if split_plan is not None and split_plan.count > 1:
                    body += "\n" + text.t(
                        task.lang, "split_note", parts=split_plan.count
                    )
                if nsfw_delete_seconds:
                    body += "\n" + text.t(
                        task.lang,
                        "nsfw_autodelete_job_line",
                        seconds=nsfw_delete_seconds,
                    )
                await self._edit_final(task, body)
            if self.hub is not None:
                await self.hub.notify_job_result(task, "done", result.size)

        except errors.JobCancelled:
            await self._finish_canceled(task)
            if self.hub is not None:
                await self.hub.notify_job_result(task, "canceled")
        except asyncio.CancelledError:
            if task.cancel.is_set():
                await self._finish_canceled(task)
            else:
                raise
        except errors.LeechError as exc:
            log.info("job %s failed: %s (%s)", task.id, exc.key, exc.reason)
            await repo.update_job(
                task.id,
                status="failed",
                error=f"{exc.key}:{exc.reason}"[:400],
                finished_at=int(time.time()),
            )
            await repo.log_event(task.user_id, "download_failed")
            body = self._error_text(task.lang, exc)
            if exc.key in ("unsupported", "live_unsupported"):
                if await self._report_error(task, f"{exc.key}: {exc.reason}"):
                    body += "\n\n" + text.t(task.lang, "issue_reported")
            await self._edit_final(
                task, body, reply_markup=kb.retry_job(task.lang, task.id)
            )
            if self.hub is not None:
                await self.hub.notify_job_result(task, "failed", reason=f"{exc.key}: {exc.reason}")
        except Exception as exc:  # noqa: BLE001
            log.exception("job %s crashed", task.id)
            await repo.update_job(
                task.id,
                status="failed",
                error=str(exc)[:400],
                finished_at=int(time.time()),
            )
            await repo.log_event(task.user_id, "download_failed")
            await self._edit_final(
                task,
                text.t(task.lang, "failed", reason=human.esc(errors.public_reason(str(exc)))),
                reply_markup=kb.retry_job(task.lang, task.id),
            )
            await self._report_error(task, f"crash: {exc}")
            if self.hub is not None:
                await self.hub.notify_job_result(task, "crashed", reason=type(exc).__name__)
        finally:
            # Preserve measured partial bytes on failed/canceled network transfers.
            source_observed = max(
                0, int(getattr(task.progress, "downloaded_bytes_total", 0) or 0)
            )
            if source_observed > source_traffic_recorded:
                await self._record_traffic(
                    source_download_bytes=source_observed - source_traffic_recorded
                )
            upload_observed = max(
                0,
                int(
                    getattr(task.progress, "uploaded_bytes_total", 0)
                    or task.progress.uploaded
                    or 0
                ),
            )
            if upload_observed > upload_traffic_recorded:
                await self._record_traffic(
                    telegram_upload_bytes=upload_observed - upload_traffic_recorded
                )
            self.store.drop_job_dir(task.id)
            if task.slot_acquired:
                self.limiter.release_slot(task.user_id)
                task.slot_acquired = False
            self._tasks.pop(task.id, None)
            self._wake.set()

    def _schedule_nsfw_cleanup(self, task: JobTask, seconds: int) -> bool:
        """تایمر حذف را جدا از worker اجرا می‌کند تا صف معطل نماند.

        Group chats (including forum topics) are immutable archives.
        """
        if task.chat_id < 0:
            return False
        ids = [m.message_id for m in task.sent_messages if m is not None]
        if not ids or self.bot is None:
            return False
        job = asyncio.create_task(
            nsfwguard.cleanup_messages(
                self.bot,
                chat_id=task.chat_id,
                message_ids=ids,
                lang=task.lang,
                seconds=seconds,
            ),
            name=f"nsfw-{task.id}",
        )
        self._nsfw_tasks.add(job)
        job.add_done_callback(self._nsfw_done)
        return True

    def _nsfw_done(self, job: asyncio.Task) -> None:
        self._nsfw_tasks.discard(job)
        if job.cancelled():
            return
        exc = job.exception()
        if exc is not None:
            log.warning("nsfw cleanup failed", exc_info=exc)

    # ── مگنت/تورنت ────────────────────────────────────────────
    async def _download_torrent(self, task: JobTask, workdir: Path) -> DownloadResult:
        """مگنت را با aria2c می‌گیرد و بزرگ‌ترین فایلش را برمی‌گرداند."""
        got = await torrent.download(
            task.url,
            workdir,
            task.progress,
            task.cancel,
            connections=int(self.settings.aria2c_connections or 4),
        )
        mime = mimetypes.guess_type(got.path.name)[0] or "application/octet-stream"
        log.info("torrent delivered %s (%s files, %s bytes)", got.path.name, got.files, got.size)
        return DownloadResult(
            path=got.path,
            title=got.title or task.title,
            mime=mime,
            size=got.size,
        )

    # ── انتخاب تامبنیل از اسکرین‌شات‌های ویدیو ────────────────
    async def _maybe_pick_thumbnail(
        self, task: JobTask, result, workdir: Path
    ) -> None:
        """آلبوم قاب‌ها برای انتخاب کاربر؛ در نبود آن یک قاب پیشفرض می‌سازد."""
        if task.mode == "link" or task.custom_thumbnail:
            return
        if getattr(result, "gallery", False):
            return
        kind = media_kind(result)
        if kind not in ("video", "document"):
            return
        duration = float(
            result.duration or (task.info.duration if task.info is not None else 0) or 0
        )
        if duration < 3:
            return
        wait = int(self.settings.thumb_wait_seconds)
        # v5.13.0: آلبوم فریم‌ها پیش‌فرض خاموش است؛ فقط کاربری که از
        # «تنظیمات» روشنش کرده، آلبوم انتخاب کاور را می‌بیند.
        # Social platforms already ship a good cover; every other source may pick one.
        extractor = getattr(task.info, "extractor", "") if task.info is not None else ""
        if wait > 0 and task.thumb_picker and not is_social_source(task.url, extractor):
            await self._offer_thumb_shots(task, result, workdir, duration, wait)
        if task.custom_thumbnail is None and result.thumbnail is None:
            # کاور سایت نبود/خراب بود: یک قاب از خود ویدیو تا تلگرام سیاه نماند
            shots = await thumbs.extract_shots(
                result.path,
                thumbs.shot_times(duration, 1),
                workdir / "shots",
                cancel=task.cancel,
            )
            if shots and shots[-1].stat().st_size <= thumbs.SHOT_MAX_BYTES:
                task.custom_thumbnail = shots[-1].read_bytes()

    async def _offer_thumb_shots(
        self, task: JobTask, result, workdir: Path, duration: float, wait: int
    ) -> None:
        if self.bot is None or task.cancel.is_set() or task.chat_id < 0:
            # Interactive picker albums are temporary and cleaned up after use;
            # do not create them in group topics that must remain immutable.
            return
        count = int(getattr(self.settings, "thumb_shots", thumbs.SHOTS) or thumbs.SHOTS)
        shots = await thumbs.extract_shots(
            result.path, thumbs.shot_times(duration, count), workdir / "shots",
            cancel=task.cancel,
        )
        if not shots:
            return
        lang = task.lang
        try:
            ids = await thumbs.send_picker_album(
                self.bot, task.chat_id, shots,
                caption=text.t(lang, "thumb_album_caption"),
            )
        except TelegramError:
            log.info("thumb album could not be sent", exc_info=True)
            return
        if len(ids) != len(shots):
            shots = shots[: len(ids)]
        if task.cancel.is_set():
            await self._delete_messages(task.chat_id, ids)
            raise errors.JobCancelled()
        task.shots = list(zip(ids, shots, strict=False))
        panel = None
        try:
            panel = await self.bot.send_message(
                chat_id=task.chat_id,
                text=text.t(
                    lang, "thumb_picker_text", seconds=wait, count=len(shots)
                ),
                reply_markup=kb.thumb_picker_menu(lang, task.id),
            )
        except TelegramError:
            log.info("thumb picker panel failed", exc_info=True)
        for mid, _shot in task.shots:
            self._pickers[(task.chat_id, mid)] = task
        task.progress.stage = "thumb_wait"
        await self._edit_progress(task, force=True)
        try:
            await self._wait_thumb_decision(task, wait)
        finally:
            for mid, _shot in task.shots:
                self._pickers.pop((task.chat_id, mid), None)
                # عکس‌ها دیگر لازم نیست؛ چت تمیز بماند
                try:
                    await self.bot.delete_message(task.chat_id, mid)
                except (TelegramError, AttributeError):
                    pass
            if panel is not None:
                try:
                    await self.bot.delete_message(task.chat_id, panel.message_id)
                except TelegramError:
                    pass
        if task.cancel.is_set():
            raise errors.JobCancelled()
        chosen = task.thumb_picked
        if chosen is None or not chosen.is_file():
            return
        try:
            payload = chosen.read_bytes()
        except OSError:
            return
        if payload and len(payload) <= thumbs.SHOT_MAX_BYTES:
            task.custom_thumbnail = payload

    @staticmethod
    async def _wait_thumb_decision(task: JobTask, wait: int) -> None:
        remaining = max(1, int(wait))
        while remaining > 0 and not task.cancel.is_set():
            try:
                # انتظار کوتاه تا «لغو کار» هم بلافاصله دیده شود
                await asyncio.wait_for(task.thumb_done.wait(), timeout=1.0)
                return
            except TimeoutError:
                remaining -= 1

    def thumb_skip(self, job_id: str, user_id: int) -> bool:
        """دکمهٔ «اسکیپ»: آپلود با تامبنیل پیشفرض ادامه می‌یابد."""
        task = self._tasks.get(job_id)
        if task is None or task.user_id != user_id:
            return False
        task.thumb_picked = None
        task.thumb_done.set()
        return True

    def thumb_note_reply(
        self, chat_id: int, reply_to: int, user_id: int
    ) -> str | None:
        """ریپلای روی یکی از قاب‌های آلبوم = انتخاب همان قاب به‌عنوان کاور.

        ``None`` یعنی این پیام به قابِ هیچ کاری ربطی ندارد.
        """
        task = self._pickers.get((chat_id, reply_to))
        if task is None:
            return None
        if user_id != task.user_id:
            return "wrong_user"
        shot = dict(task.shots).get(reply_to)
        if shot is None or not shot.is_file():
            return "gone"
        task.thumb_picked = shot
        task.thumb_done.set()
        return "picked"

    async def _delete_messages(self, chat_id: int, message_ids: list[int]) -> None:
        """Clean up partial private-chat deliveries; never mutate group topics."""
        if chat_id < 0:
            return
        for message_id in message_ids:
            try:
                await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
            except TelegramError:
                pass

    async def _send_split(self, task: JobTask, result, plan) -> Message:
        """آپلود پارت‌های یک فایل تقسیم‌شده، هر پارت با پیشرفت مستقل."""
        total = plan.count
        first: Message | None = None
        sent: list[int] = []
        task.progress.parts = total
        try:
            for index, path in enumerate(plan.parts, start=1):
                if task.cancel.is_set():
                    raise errors.JobCancelled()
                part = self.uploader.part_result(result, path)
                # مدت هر پارت را از خودش بگیریم؛ وگرنه تلگرام «00:00» نشان می‌دهد.
                meta = await thumbs.probe_media(path)
                if meta is not None and meta.duration:
                    part.duration = meta.duration
                task.progress.stage = "uploading"
                task.progress.part = index
                task.progress.pct = 0.0
                task.progress.uploaded = 0
                task.progress.total = part.size
                task.upload_started = time.monotonic()
                await self._edit_progress(task, force=True)

                caption = text.t(
                    task.lang,
                    "split_caption",
                    title=result.title,
                    part=index,
                    parts=total,
                )
                send_coro = self.uploader.send(
                    self.bot,
                    task.chat_id,
                    part,
                    task.progress,
                    task.url,
                    as_document=(
                        task.mode == "document"
                        or (
                            task.mode == "video"
                            and (
                                media_kind(part) != "video"
                                or part.suffix not in PLAYABLE_VIDEO_EXT
                            )
                        )
                    ),
                    filename=path.name,
                    caption_title=caption,
                    custom_thumbnail=task.custom_thumbnail,
                    cancel=task.cancel,
                    reset_progress=False,
                    sent=task.sent_messages,
                )
                task.upload_task = asyncio.create_task(send_coro)
                try:
                    message = await task.upload_task
                except asyncio.CancelledError:
                    if task.cancel.is_set():
                        raise errors.JobCancelled() from None
                    raise
                finally:
                    task.upload_task = None
                sent.append(message.message_id)
                if first is None:
                    first = message
            task.progress.pct = 100.0
            if first is None:
                raise errors.UnsupportedUrl("Nothing uploaded")
            return first
        except BaseException:
            # اگر ارسال نیمه‌کاره ماند، پارت‌های قبلی هم پاک می‌شوند تا فایل
            # ناقص در چت کاربر نماند.
            await self._delete_messages(task.chat_id, sent)
            raise

    async def _report_error(self, task: JobTask, reason: str) -> bool:
        """خطای کار را در لاگ‌ها و تاپیک گزارش‌های گروه ادمین ثبت می‌کند."""
        if self.hub is None:
            return False
        try:
            user = await repo.get_user(task.user_id)
            report = await self.hub.report_issue(
                task.user_id,
                user.username if user else None,
                user.first_name if user else None,
                task.url,
                reason,
            )
            await self.hub.record_log(
                "ERROR",
                "job",
                f"کار {task.id} شکست خورد: {reason}",
                task.user_id,
            )
            return report is not None
        except Exception:  # noqa: BLE001
            log.exception("could not report job error")
            return False

    async def _finish_canceled(self, task: JobTask) -> None:
        await repo.update_job(task.id, status="canceled", finished_at=int(time.time()))
        await self._edit_final(task, text.t(task.lang, "canceled"))

    def _error_text(self, lang: str, exc: errors.LeechError) -> str:
        kwargs = dict(exc.extra)
        if exc.key in ("unsupported", "live_unsupported"):
            # پیام کاربر ساده می‌ماند؛ جزئیات خام فقط در لاگ و گزارش ادمین است.
            kwargs.pop("reason", None)
        else:
            kwargs.setdefault("reason", human.esc(errors.public_reason(exc.reason or "?")))
        return text.t(lang, exc.key, **kwargs)

    @staticmethod
    def _zip_parts(result):
        """آلبوم چندانتخابی را برای لینک مستقیم به یک ZIP تبدیل می‌کند."""
        parts = [p for p in (result.parts or []) if p.exists()]
        if len(parts) <= 1:
            return result
        base = human.safe_filename(result.title or "gallery", 80) or "gallery"
        archive = result.path.parent / f"{base}.zip"
        index = 2
        while archive.exists():
            archive = result.path.parent / f"{base} ({index}).zip"
            index += 1
        seen: set[str] = set()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED) as zf:
            for path in parts:
                arcname = human.safe_filename(path.name, 120) or "file"
                if arcname in seen:
                    stem, dot, ext = arcname.rpartition(".")
                    arcname = f"{stem} ({index}){dot}{ext}" if dot else f"{arcname} ({index})"
                    index += 1
                seen.add(arcname)
                zf.write(path, arcname=arcname)
        result.path = archive
        result.size = archive.stat().st_size
        result.mime = "application/zip"
        result.parts = [archive]
        return result

    async def _deliver_link(self, task: JobTask, result) -> None:
        """فایل دانلودشده را به پوشهٔ لینک مستقیم منتقل و لینک امضاشده می‌سازد."""
        limit = self.settings.max_links_per_user
        if not task.vip and limit > 0 and await repo.count_user_shared(task.user_id) >= limit:
            # سقف لینک همزمان پر شده است؛ فایل هنوز جابه‌جا نشده تا پوشهٔ کار
            # در finally پاک شود و فایل یتیم نماند.
            raise errors.LinkQuota(limit=limit)
        parts = getattr(result, "parts", None) or []
        if len(parts) > 1:
            # لینک مستقیم فقط یک فایل است؛ آلبوم را به ZIP تبدیل می‌کنیم.
            result = self._zip_parts(result)
        if result.size > self.settings.max_link_bytes:
            raise errors.FileTooLargeForLink(
                size=human.human_bytes(result.size),
                max=human.human_bytes(self.settings.max_link_bytes),
            )
        dest = self.store.link_path(task.id, result.path.name)
        try:
            shutil.move(str(result.path), str(dest))
        except OSError as exc:
            raise errors.UnsupportedUrl(f"Could not store link file: {exc}") from exc
        result.path = dest

        ttl = self.settings.ttl_seconds
        await repo.create_shared(
            task.id,
            task.user_id,
            str(dest),
            dest.name,
            result.mime or "application/octet-stream",
            result.size,
            ttl,
        )
        await repo.log_event(task.user_id, "link_created", float(result.size))

        token = make_token(task.id, self.cfg.link_secret, ttl, user_id=task.user_id)
        url = f"{self.cfg.public_base_url.rstrip('/')}/f/{token}"
        expires = time.strftime("%H:%M UTC", time.gmtime(int(time.time()) + ttl))
        body = text.t(
            task.lang,
            "link_ready",
            url=url,
            name=human.esc(dest.name),
            size=human.human_bytes(result.size),
            ttl=f"{self.settings.ttl_hours:g}",
            expires=expires,
        )
        markup = Kb([[Btn(text.t(task.lang, "open_link_btn"), url=url)]])
        await self._edit_final(task, body, reply_markup=markup)

    # ── پیام وضعیت ──────────────────────────────────────────
    def _progress_text(self, task: JobTask) -> str:
        prog = task.progress
        lang = task.lang
        if task.cancel.is_set():
            return text.t(lang, "canceled")
        if prog.stage in ("queued",):
            pos = 1
            try:
                pos = self._queue.index(task) + 1
            except ValueError:
                pass
            return text.t(lang, "queued", pos=pos)
        if prog.stage == "downloading":
            total = human.human_bytes(prog.total) if prog.total else "?"
            step = ("۱/۱" if task.mode == "link" else "۱/۲") if lang == "fa" else (
                "1/1" if task.mode == "link" else "1/2"
            )
            return text.t(lang, "progress_stage_download", step=step) + "\n" + text.t(
                lang,
                "downloading",
                bar=human.progress_bar(prog.pct, show_pct=True),
                size=f"{human.human_bytes(prog.downloaded)} / {total}",
                speed=human.human_speed(prog.speed),
                eta=human.human_eta(prog.eta),
            )
        if prog.stage == "splitting":
            step = "۲/۲" if lang == "fa" else "2/2"
            return text.t(lang, "progress_stage_upload", step=step) + "\n" + text.t(
                lang, "splitting", parts=max(2, prog.parts or 2)
            )
        if prog.stage == "thumb_wait":
            return text.t(lang, "thumb_wait_stage")
        if prog.stage == "recognizing":
            return text.t(lang, "progress_stage_recognize")
        if prog.stage == "uploading":
            elapsed = max(.001, time.monotonic() - task.upload_started)
            speed = prog.uploaded / elapsed
            eta = int(max(0, prog.total - prog.uploaded) / speed) if speed else None
            waiting = prog.total and prog.uploaded >= prog.total
            step = "۲/۲" if lang == "fa" else "2/2"
            stage = text.t(lang, "progress_stage_upload", step=step)
            part_line = ""
            if prog.parts > 1 and prog.part:
                part_line = text.t(
                    lang, "split_part_line", part=prog.part, parts=prog.parts
                ) + "\n"
            if waiting:
                # بایت‌ها به Local API رسیدند؛ از اینجا خودِ سرور فایل را به
                # تلگرام می‌فرستد و ما فقط پاسخ را می‌بینیم. درصد و زمان
                # باقی‌مانده را با سرعتِ آموخته‌شدهٔ همین سرور تخمین می‌زنیم تا
                # کاربر یک نوار ثابت روی ۹۹٪ نبیند.
                estimated = dc_speed()
                estimated_total = (prog.total / estimated) if prog.total else 0.0
                pct = min(99.0, elapsed / estimated_total * 100) if estimated_total else 0.0
                left = (
                    max(0.0, estimated_total - elapsed) if estimated_total else None
                )
                return stage + "\n" + part_line + text.t(
                    lang,
                    "uploading_dc",
                    bar=human.progress_bar(pct, show_pct=True),
                    size=human.human_bytes(prog.total or prog.uploaded),
                    speed=human.human_speed(estimated),
                    eta=human.human_eta(left),
                )
            return stage + "\n" + part_line + text.t(
                lang,
                "uploading",
                bar=human.progress_bar(prog.pct, show_pct=True),
                size=f"{human.human_bytes(prog.uploaded)} / {human.human_bytes(prog.total)}",
            ) + f"\n{human.human_speed(speed)} · {human.human_eta(eta)}"
        return text.t(lang, "processing")

    async def _edit_progress(self, task: JobTask, force: bool = False) -> None:
        # Serialize status edits. Without this lock the publisher can finish an
        # old 99% edit after _edit_final has already written the success message.
        async with task.edit_lock:
            if task.finalized or not task.status_message_id or self.bot is None:
                return
            now = time.monotonic()
            if not force and now - task.last_edit < EDIT_INTERVAL:
                return
            body = self._progress_text(task)
            if body == task.last_text and not force:
                return
            task.last_text = body
            task.last_edit = now
            try:
                await self.bot.edit_message_text(
                    chat_id=task.chat_id,
                    message_id=task.status_message_id,
                    text=body,
                    parse_mode=ParseMode.HTML,
                    reply_markup=Kb([[Btn(text.t(task.lang, "cancel_btn"),
                                          callback_data=f"x|{task.id}")]]),
                )
            except TelegramError:
                pass

    async def _edit_final(self, task: JobTask, body: str, reply_markup=None) -> None:
        async with task.edit_lock:
            # Set this even if there is no status message: the publisher must not
            # resurrect progress after a terminal result has been produced.
            task.finalized = True
            if not task.status_message_id or self.bot is None:
                return
            try:
                await self.bot.edit_message_text(
                    chat_id=task.chat_id,
                    message_id=task.status_message_id,
                    text=body,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            except TelegramError:
                pass

    async def _publisher_loop(self) -> None:
        while not self._stop.is_set():
            for task in list(self._tasks.values()):
                if (
                    not task.finalized
                    and task.progress.stage in ("downloading", "uploading", "postprocessing")
                ):
                    await self._edit_progress(task)
            await asyncio.sleep(EDIT_INTERVAL)
