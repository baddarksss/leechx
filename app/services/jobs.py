"""صف کار و اجرای دانلود→آپلود.

چرا صف؟ چون هر دانلود/آپلود سنگین است و کاربران زیادی همزمان درخواست
می‌دهند. با ``WORKERS`` می‌توانی همزمانی کل سرور و با
``PER_USER_CONCURRENCY`` همزمانی هر کاربر را کنترل کنی. هر کار پیام وضعیت
خودش را دارد که هر چند ثانیه یک‌بار ویرایش می‌شود.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field

from telegram.error import TelegramError

from app.config import Config
from app.core import errors, human, text
from app.db import repo
from app.services.downloader import Downloader, MediaInfo, Progress, fetch_thumbnail
from app.services.filestore import FileStore
from app.services.formats import FormatOption
from app.services.ratelimit import RateLimiter
from app.services.runtime_settings import RuntimeSettings
from app.services.uploader import Uploader

log = logging.getLogger("leechx.jobs")

EDIT_INTERVAL = 2.2


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
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    progress: Progress = field(default_factory=Progress)
    created_at: float = field(default_factory=time.time)
    last_text: str = ""
    last_edit: float = 0.0
    canceled_by_user: bool = False


class JobManager:
    def __init__(
        self,
        cfg: Config,
        settings: RuntimeSettings,
        store: FileStore,
        downloader: Downloader,
        uploader: Uploader,
        limiter: RateLimiter,
    ) -> None:
        self.cfg = cfg
        self.settings = settings
        self.store = store
        self.downloader = downloader
        self.uploader = uploader
        self.limiter = limiter

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
        self._tasks[task.id] = task
        self._queue.append(task)
        position = len(self._queue)
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
        self._wake.set()
        return position

    def get(self, job_id: str) -> JobTask | None:
        return self._tasks.get(job_id)

    def cancel(self, job_id: str, user_id: int) -> bool:
        task = self._tasks.get(job_id)
        if task is None or task.user_id != user_id:
            return False
        task.canceled_by_user = True
        task.cancel.set()
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
        try:
            await repo.update_job(task.id, status="running", started_at=started)
            task.progress.stage = "downloading"
            await self._edit_progress(task, force=True)

            result = await self.downloader.download(
                task.url,
                task.option,
                workdir,
                task.progress,
                task.cancel,
                task.info,
            )

            if task.cancel.is_set():
                raise errors.JobCancelled()

            if result.thumbnail is None:
                result.thumbnail = await fetch_thumbnail(
                    task.info.thumbnail if task.info else None,
                    workdir / "thumb.jpg",
                    self.cfg.proxy,
                )

            task.progress.stage = "uploading"
            task.progress.pct = 0.0
            await self._edit_progress(task, force=True)

            await self.uploader.send(self.bot, task.chat_id, result, task.progress, task.url)

            await repo.update_job(
                task.id,
                status="done",
                file_name=result.path.name,
                size=result.size,
                finished_at=int(time.time()),
            )
            await repo.bump_downloads(task.user_id)
            await repo.log_event(task.user_id, "download_done")
            await repo.log_event(task.user_id, "bytes", float(result.size))
            await self._edit_final(
                task,
                text.t(task.lang, "done") + f"\n<b>{human.esc(task.title)}</b>",
            )

        except errors.JobCancelled:
            await self._finish_canceled(task)
        except errors.LeechError as exc:
            log.info("job %s failed: %s (%s)", task.id, exc.key, exc.reason)
            await repo.update_job(
                task.id,
                status="failed",
                error=f"{exc.key}:{exc.reason}"[:400],
                finished_at=int(time.time()),
            )
            await repo.log_event(task.user_id, "download_failed")
            await self._edit_final(task, self._error_text(task.lang, exc))
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
        finally:
            self.store.drop_job_dir(task.id)
            self.limiter.release_slot(task.user_id)
            self._tasks.pop(task.id, None)
            self._wake.set()

    async def _finish_canceled(self, task: JobTask) -> None:
        await repo.update_job(task.id, status="canceled", finished_at=int(time.time()))
        await self._edit_final(task, text.t(task.lang, "canceled"))

    def _error_text(self, lang: str, exc: errors.LeechError) -> str:
        kwargs = dict(exc.extra)
        kwargs.setdefault("reason", human.esc(exc.reason or "?"))
        return text.t(lang, exc.key, **kwargs)

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
            return text.t(
                lang,
                "downloading",
                pct=int(prog.pct),
                bar=human.progress_bar(prog.pct),
                size=f"{human.human_bytes(prog.downloaded)} / {total}",
                speed=human.human_speed(prog.speed),
                eta=human.human_eta(prog.eta),
            )
        if prog.stage == "uploading":
            return text.t(
                lang,
                "uploading",
                pct=int(prog.pct),
                bar=human.progress_bar(prog.pct),
                size=f"{human.human_bytes(prog.uploaded)} / {human.human_bytes(prog.total)}",
            )
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
            )
        except TelegramError:
            pass

    async def _edit_final(self, task: JobTask, body: str) -> None:
        if not task.status_message_id or self.bot is None:
            return
        try:
            await self.bot.edit_message_text(
                chat_id=task.chat_id,
                message_id=task.status_message_id,
                text=body,
            )
        except TelegramError:
            pass

    async def _publisher_loop(self) -> None:
        while not self._stop.is_set():
            for task in list(self._tasks.values()):
                if task.progress.stage in ("downloading", "uploading", "postprocessing"):
                    await self._edit_progress(task)
            await asyncio.sleep(EDIT_INTERVAL)
