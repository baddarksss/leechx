"""ظرف سرویس‌ها — یک‌جا ساخته و بین هندلرها به اشتراک گذاشته می‌شود.

اضافه‌کردن قابلیت جدید: سرویس را اینجا بساز، در ``setup`` راه بینداز و
در ``teardown`` ببند. هندلرها از ``context.bot_data["services"]`` می‌گیرند.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.config import Config
from app.db import repo
from app.services.admin_group import AdminGroup
from app.services.cache import CacheHub
from app.services.cookies import CookieStore
from app.services.debug_access import DebugAccess
from app.services.downloader import Downloader
from app.services.drafts import DraftStore
from app.services.filestore import FileStore
from app.services.force_join import ForceJoin
from app.services.jobs import JobManager
from app.services.link_server import LinkServer
from app.services.ratelimit import RateLimiter
from app.services.runtime_settings import RuntimeSettings
from app.services.sites import sites
from app.services.telegram_transfers import FileLinkTransfers
from app.services.updater import SourceUpdater
from app.services.uploader import Uploader
from app.version import __version__

log = logging.getLogger("leechx.container")


@dataclass
class Services:
    cfg: Config
    settings: RuntimeSettings
    store: FileStore
    downloader: Downloader
    uploader: Uploader
    limiter: RateLimiter
    jobs: JobManager
    server: LinkServer
    cookies: CookieStore
    admin_group: AdminGroup
    force_join: ForceJoin
    updater: SourceUpdater
    debug: DebugAccess
    drafts: DraftStore = field(default_factory=DraftStore)
    file_transfers: FileLinkTransfers | None = None
    cache: CacheHub | None = None
    sites: object = sites
    application: object | None = None
    started_at: float = field(default_factory=time.time)
    _cleanup: asyncio.Task | None = None

    @classmethod
    def create(cls, cfg: Config) -> Services:
        settings = RuntimeSettings(cfg)
        store = FileStore(cfg.files_dir, cfg.tmp_dir)
        cookies = CookieStore(cfg.cookies_dir)
        downloader = Downloader(cfg, cookies)
        uploader = Uploader(cfg, settings)
        limiter = RateLimiter(cfg.rate_limit_seconds)
        admin_group = AdminGroup(cfg, settings)
        force_join = ForceJoin(settings)
        updater = SourceUpdater(cfg)
        debug = DebugAccess(cfg, settings, updater)
        jobs = JobManager(
            cfg, settings, store, downloader, uploader, limiter, hub=admin_group
        )
        server = LinkServer(cfg, settings, store, hub=admin_group, debug=debug)
        instance = cls(
            cfg=cfg,
            settings=settings,
            store=store,
            downloader=downloader,
            uploader=uploader,
            limiter=limiter,
            jobs=jobs,
            server=server,
            cookies=cookies,
            admin_group=admin_group,
            force_join=force_join,
            updater=updater,
            debug=debug,
        )
        instance.file_transfers = FileLinkTransfers(instance)
        instance.cache = CacheHub(admin_group)
        instance.jobs.cache = instance.cache
        debug.attach(instance)
        return instance

    @property
    def uptime(self) -> int:
        return int(time.time() - self.started_at)

    async def setup(self, bot) -> None:
        await self.settings.load()
        self.settings.apply_to_config()
        self.admin_group.attach(bot)
        self.limiter.set_interval(self.settings.rate_limit_seconds)
        await asyncio.to_thread(self.sites.build)
        await self.server.start()
        await self.jobs.start(bot)
        self._cleanup = asyncio.create_task(self._cleanup_loop(), name="cleanup")
        log.info("services ready (LeechX v%s)", __version__)

    def attach_application(self, application) -> None:
        """اپلیکیشن تلگرام را نگه می‌دارد تا API عیب‌یابی بتواند نرم متوقفش کند."""
        self.application = application
        self.debug.set_application(application)

    def request_restart(self) -> None:
        """ری‌استارت نرم: بعد از خاموش‌شدن سرویس‌ها اجرا می‌شود."""
        self.updater.request_restart()
        if self.application is not None:
            asyncio.get_running_loop().call_later(1.0, self.application.stop_running)

    async def teardown(self) -> None:
        if self._cleanup is not None:
            self._cleanup.cancel()
            try:
                await self._cleanup
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await self.file_transfers.stop()
        await self.jobs.stop()
        await self.server.stop()
        log.info("services stopped")
        if self.updater.restart_requested:
            log.info("restart was requested; handing over to the new process")
            self.updater.perform_restart()

    # ── پاک‌سازی دوره‌ای ────────────────────────────────────
    async def _cleanup_loop(self) -> None:
        interval = max(30, int(self.cfg.cleanup_interval_seconds))
        while True:
            try:
                await asyncio.sleep(interval)
                await self.cleanup_once()
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: BLE001
                log.exception("cleanup failed")

    async def cleanup_once(self) -> tuple[int, int]:
        """(تعداد فایل حذف‌شده، بایت آزادشده)"""
        removed, freed = 0, 0
        for row in await repo.expired_shared():
            try:
                path = Path(row.path)
                size = path.stat().st_size if path.exists() else 0
                self.store.remove(path)
                self.store.drop_link_dir(row.id)
                await repo.delete_shared(row.id)
                removed += 1
                freed += size
            except Exception:  # noqa: BLE001
                log.exception("failed to delete shared %s", row.id)

        # پوشه‌های کارِ رهاشده (مثلاً اگر پروسه وسط کار کشته شد)
        extra_files, extra_bytes = self.store.purge_older_than(6 * 3600)
        removed += extra_files
        freed += extra_bytes

        self.drafts.prune()
        try:
            await repo.purge_debug_tokens()
        except Exception:  # noqa: BLE001
            log.debug("debug token purge failed", exc_info=True)
        if removed and self.admin_group is not None:
            await self.admin_group.audit("system", "cleanup", details=f"removed={removed}, bytes={freed}")
        if self.cache is not None:
            try:
                removed += await self.cache.clear_expired(self.jobs.bot)
            except Exception:
                log.exception("cache cleanup failed")
        log.debug("cleanup: %d files, %d bytes", removed, freed)
        return removed, freed
