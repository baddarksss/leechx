"""صف کار و اجرای دانلود→آپلود.

چرا صف؟ چون هر دانلود/آپلود سنگین است و کاربران زیادی همزمان درخواست
می‌دهند. با ``WORKERS`` می‌توانی همزمانی کل سرور و با
``PER_USER_CONCURRENCY`` همزمانی هر کاربر را کنترل کنی. هر کار پیام وضعیت
خودش را دارد که هر چند ثانیه یک‌بار ویرایش می‌شود.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Kb
from telegram.constants import ParseMode
from telegram.error import TelegramError

from app.config import Config
from app.core import errors, human, text
from app.db import repo
from app.services.downloader import Downloader, MediaInfo, Progress, fetch_thumbnail
from app.services.filestore import FileStore
from app.services.formats import FormatOption
from app.services.linktoken import make_token
from app.services.ratelimit import RateLimiter
from app.services.runtime_settings import RuntimeSettings
from app.services.uploader import PLAYABLE_VIDEO_EXT, Uploader, media_kind

log = logging.getLogger("leechx.jobs")

EDIT_INTERVAL = 2.2

DELIVERY_MODES = ("video", "document", "link")


def apply_custom_name(result, custom: str):
    """نام دلخواه کاربر را روی فایل دانلودشده اعمال می‌کند."""
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
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    progress: Progress = field(default_factory=Progress)
    created_at: float = field(default_factory=time.time)
    last_text: str = ""
    last_edit: float = 0.0
    canceled_by_user: bool = False
    upload_task: asyncio.Task | None = None
    upload_started: float = 0.0


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
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()

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
            asyncio.create_task(self._finish_canceled(task))
        return True

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
            if picked is None and self.limiter.acquire_slot(task.user_id, limit):
                self._queue.remove(task)
                picked = task

        for task in canceled:
            asyncio.create_task(self._finish_canceled(task))
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
        try:
            await repo.update_job(task.id, status="running", started_at=started)
            task.progress.stage = "downloading"
            await self._edit_progress(task, force=True)
            if self.hub is not None:
                await self.hub.notify_job("download", task)

            if task.mode != "link" and self.cache is not None and not task.custom_thumbnail:
                try:
                    cached = await self.cache.cached_delivery(self.bot, task)
                except Exception:
                    cached = False
                    log.warning("media cache read failed; proceeding normally", exc_info=True)
                if cached:
                    await repo.update_job(
                        task.id, status="done", size=int(cached),
                        finished_at=int(time.time()),
                    )
                    await repo.bump_downloads(task.user_id)
                    await repo.bump_uploads(task.user_id)
                    await repo.log_event(task.user_id, "download_done")
                    await repo.log_event(task.user_id, "upload_done")
                    await repo.log_event(task.user_id, "bytes", float(cached))
                    await self._edit_final(
                        task, text.t(task.lang, "done") +
                        ("\n♻️ دریافت سریع از کش" if task.lang == "fa" else
                         "\n♻️ Delivered from cache")
                    )
                    if self.hub is not None:
                        await self.hub.notify_job_result(task, "cache_hit")
                    return

            if task.cancel.is_set():
                raise errors.JobCancelled()

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

                task.progress.stage = "uploading"
                task.progress.pct = 0.0
                task.upload_started = time.monotonic()
                await self._edit_progress(task, force=True)
                if self.hub is not None:
                    await self.hub.notify_job("upload", task, result)

                if task.cancel.is_set():
                    raise errors.JobCancelled()
                task.upload_task = asyncio.create_task(
                    self.uploader.send(
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
                    )
                )
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
                finally:
                    task.upload_task = None
                if task.cancel.is_set():
                    # If the upload finished concurrently with cancellation,
                    # remove the message instead of claiming a successful cancel.
                    try:
                        await self.bot.delete_message(
                            chat_id=task.chat_id, message_id=uploaded_message.message_id
                        )
                    except TelegramError:
                        pass
                    raise errors.JobCancelled()
                if self.cache is not None:
                    await self.cache.record_delivery(self.bot, task, result, uploaded_message)

            await repo.update_job(
                task.id,
                status="done",
                file_name=result.path.name,
                size=result.size,
                finished_at=int(time.time()),
            )
            await repo.bump_downloads(task.user_id)
            await repo.bump_uploads(task.user_id)
            await repo.log_event(task.user_id, "download_done")
            await repo.log_event(task.user_id, "upload_done")
            await repo.log_event(task.user_id, "bytes", float(result.size))
            if task.mode != "link":
                await self._edit_final(
                    task,
                    text.t(task.lang, "done") + f"\n<b>{human.esc(result.title)}</b>",
                )
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
            await self._edit_final(task, body)
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
                text.t(task.lang, "failed", reason=human.esc(str(exc)[:150])),
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
            self.limiter.release_slot(task.user_id)
            self._tasks.pop(task.id, None)
            self._wake.set()

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
        kwargs.setdefault("reason", human.esc(exc.reason or "?"))
        return text.t(lang, exc.key, **kwargs)

    async def _deliver_link(self, task: JobTask, result) -> None:
        """فایل دانلودشده را به پوشهٔ لینک مستقیم منتقل و لینک امضاشده می‌سازد."""
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
            return f"📍 {step}\n" + text.t(
                lang,
                "downloading",
                pct=int(prog.pct),
                bar=human.progress_bar(prog.pct),
                size=f"{human.human_bytes(prog.downloaded)} / {total}",
                speed=human.human_speed(prog.speed),
                eta=human.human_eta(prog.eta),
            )
        if prog.stage == "uploading":
            elapsed = max(.001, time.monotonic() - task.upload_started)
            speed = prog.uploaded / elapsed
            eta = int(max(0, prog.total - prog.uploaded) / speed) if speed else None
            waiting = prog.total and prog.uploaded >= prog.total
            return ("📍 مرحله ۲/۲\n" if lang == "fa" else "📍 Stage 2/2\n") + text.t(
                lang,
                "uploading",
                pct=min(99, int(prog.pct)),
                bar=human.progress_bar(prog.pct),
                size=f"{human.human_bytes(prog.uploaded)} / {human.human_bytes(prog.total)}",
            ) + ("\n" + text.t(lang, "upload_wait") if waiting
                  else f"\n{human.human_speed(speed)} · {human.human_eta(eta)}")
        return text.t(lang, "processing")

    async def _edit_progress(self, task: JobTask, force: bool = False) -> None:
        if not task.status_message_id or self.bot is None:
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
                if task.progress.stage in ("downloading", "uploading", "postprocessing"):
                    await self._edit_progress(task)
            await asyncio.sleep(EDIT_INTERVAL)
