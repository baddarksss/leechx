"""Cancellable Telegram attachment -> direct-link transfers with measured progress.

Telegram's stock File.download_to_drive buffers the full file in memory on the
public Bot API. Stream the getFile URL instead, one chunk at a time.
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

from app.bot import keyboards as kb
from app.bot.common import edit
from app.core import human, text
from app.db import repo
from app.services.linktoken import make_token

log = logging.getLogger("leechx.telegram_transfers")
CHUNK = 256 * 1024

# پوشه‌های رسانه در ذخیره‌گاه Local Bot API؛ مسیر نسبی از یکی از این‌ها شروع می‌شود.
_API_MEDIA_FOLDERS = frozenset({
    "animations", "documents", "music", "passport", "photos", "profile_photos",
    "secret", "stickers", "temp", "thumbnails", "video_notes", "videos", "voice",
})


def _storage_relative(file_path: str) -> str:
    """``/var/lib/telegram-bot-api/<token>/documents/a.mkv`` ← ``documents/a.mkv``."""
    raw = (file_path or "").replace("\\", "/")
    if "://" in raw:
        raw = urlsplit(raw).path
    parts = [part for part in raw.split("/") if part]
    for index, part in enumerate(parts):
        if part in _API_MEDIA_FOLDERS:
            return "/".join(parts[index:])
    return parts[-1] if parts else ""


def _api_file_url(cfg, relative: str) -> str:
    """آدرس درست فایل روی Local Bot API؛ اگر تنظیم نشده باشد رشتهٔ خالی."""
    base = str(getattr(cfg, "telegram_api_file_url", "") or "").strip().rstrip("/")
    token = str(getattr(cfg, "bot_token", "") or "").strip()
    if not base or not relative or not token:
        return ""
    if token in base:
        return f"{base}/{relative}"
    if base.endswith("/bot"):
        return f"{base}{token}/{relative}"
    return f"{base}/bot{token}/{relative}"


BOT_API_CACHE_DIR = Path("/var/lib/telegram-bot-api")


def bot_api_cache_state(cfg) -> str:
    """وضعیت خواندن پوشهٔ کش Local Bot API: ok / missing / unreadable / off."""
    if not getattr(cfg, "uses_local_api", False):
        return "off"
    token = str(getattr(cfg, "bot_token", "") or "").strip()
    if not token:
        return "missing"
    root = BOT_API_CACHE_DIR / token
    try:
        if not root.is_dir():
            return "missing"
        with os.scandir(root) as entries:
            next(entries, None)
        return "ok"
    except OSError:
        return "unreadable"


def _readable_local_file(file_path: str) -> Path | None:
    """فایل محلی خواندنی؛ در غیر این صورت ``None`` (یعنی باید از HTTP خواند)."""
    if not file_path or file_path.startswith(("http://", "https://")):
        return None
    try:
        path = Path(file_path)
        if path.is_file() and os.access(path, os.R_OK):
            return path
    except OSError:
        return None
    return None


@dataclass
class FileLinkTask:
    id: str
    user_id: int
    chat_id: int
    name: str
    size: int
    mime: str
    lang: str
    attachment: object
    status: object
    username: str | None = None
    first_name: str | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    job: asyncio.Task | None = None
    finalizing: bool = False


class FileLinkTransfers:
    def __init__(self, svc) -> None:
        self.svc = svc
        self._tasks: dict[str, FileLinkTask] = {}

    def tasks_for_user(self, user_id: int) -> list[FileLinkTask]:
        return [t for t in self._tasks.values() if t.user_id == user_id]

    async def _record_received_file_bytes(self, path: Path, already_recorded: int = 0) -> int:
        try:
            size = path.stat().st_size
        except OSError:
            return already_recorded
        delta = max(0, size - already_recorded)
        if delta:
            try:
                await repo.record_traffic(telegram_receive_bytes=delta)
            except Exception:  # noqa: BLE001 — statistics must not break file delivery
                log.warning("Telegram receive traffic could not be recorded", exc_info=True)
        return max(already_recorded, size)

    async def start(self, update, lang: str, attachment, name: str, size: int) -> FileLinkTask | None:
        user = update.effective_user
        mime = getattr(attachment, "mime_type", None) or mimetypes.guess_type(name)[0] or "application/octet-stream"
        status = await update.effective_message.reply_text(
            text.t(lang, "file_received")
        )
        if status is None:
            return None
        task = FileLinkTask(
            id=secrets.token_hex(6), user_id=user.id,
            chat_id=update.effective_chat.id, name=name, size=size,
            mime=mime, lang=lang, attachment=attachment, status=status,
            username=user.username, first_name=user.first_name,
        )
        self._tasks[task.id] = task
        await edit(status, text.t(lang, "file_received"), reply_markup=kb.cancel_job(lang, task.id))
        task.job = asyncio.create_task(self._run(task), name=f"tgfile-{task.id}")
        return task

    def cancel(self, task_id: str, user_id: int) -> bool:
        task = self._tasks.get(task_id)
        if task is None or task.user_id != user_id or task.cancel_event.is_set() or task.finalizing:
            return False
        task.cancel_event.set()
        if task.job is not None and not task.job.done():
            task.job.cancel()
        return True

    async def stop(self) -> None:
        current = list(self._tasks.values())
        for task in current:
            task.cancel_event.set()
            if task.job is not None and not task.job.done():
                task.job.cancel()
        await asyncio.gather(*(t.job for t in current if t.job), return_exceptions=True)
        self._tasks.clear()

    async def _download(self, task: FileLinkTask, file_path: str, dest: Path) -> None:
        """Download and update the status message every ~2 seconds."""
        if task.cancel_event.is_set():
            raise asyncio.CancelledError()
        expected = task.size
        received = 0
        last_edit = 0.0
        begin = time.monotonic()
        async def progress(force: bool = False):
            nonlocal last_edit
            now = time.monotonic()
            if not force and now - last_edit < 2.0:
                return
            last_edit = now
            if expected:
                pct = min(99, int(received * 100 / expected))
                body = text.t(
                    task.lang, "file_link_progress",
                    bar=human.progress_bar(pct, show_pct=True),
                    size=f"{human.human_bytes(received)} / {human.human_bytes(expected)}",
                )
            else:
                body = text.t(task.lang, "file_link_wait", size=human.human_bytes(received))
            elapsed = max(.001, now - begin)
            speed = received / elapsed
            if expected and speed > 0:
                eta = int(max(0, expected - received) / speed)
                body += f"\n{human.human_speed(speed)} · {human.human_eta(eta)}"
            await edit(task.status, body, reply_markup=kb.cancel_job(task.lang, task.id))

        def count(size: int) -> None:
            nonlocal received
            received += size
            if received > self.svc.settings.max_link_bytes:
                raise RuntimeError("Maximum link file size exceeded")

        local = _readable_local_file(file_path)
        if local is not None:
            # Local Bot API با --local مسیر واقعی فایل را می‌دهد و همان پوشه در این
            # کانتینر هم سوار شده است؛ پس بدون HTTP مستقیم از دیسک می‌خوانیم.
            with local.open("rb") as fh, dest.open("wb") as output:
                while True:
                    if task.cancel_event.is_set():
                        raise asyncio.CancelledError()
                    chunk = await asyncio.to_thread(fh.read, CHUNK)
                    if not chunk:
                        break
                    await asyncio.to_thread(output.write, chunk)
                    count(len(chunk))
                    await progress()
        else:
            await self._download_http(task, file_path, dest, count, progress)
        if task.cancel_event.is_set():
            raise asyncio.CancelledError()
        if received <= 0 or (expected and received != expected):
            raise RuntimeError(f"Telegram transfer incomplete ({received}/{expected})")
        await progress(force=True)

    async def _download_http(self, task, file_path, dest, count, progress) -> None:
        """Stream the file through the Bot API file endpoint.

        PTB rewrites a ``getFile`` path into ``{base_file_url}/{path}`` when the
        path is not readable from this process. With ``--local`` the API reports
        an absolute path inside its own storage folder, so that rewrite becomes
        ``…/file/bot<token>/var/lib/telegram-bot-api/<token>/documents/…`` and the
        server answers **404**. Ask for the media-relative path instead, and keep
        the URL PTB produced only as a second candidate.
        """
        candidates: list[str] = []
        corrected = _api_file_url(self.svc.cfg, _storage_relative(file_path))
        if corrected:
            candidates.append(corrected)
        if file_path.startswith(("http://", "https://")) and file_path not in candidates:
            candidates.append(file_path)
        if not candidates:
            raise RuntimeError("Telegram file location is neither local nor a URL")
        failure = "Telegram file server unreachable"
        timeout = aiohttp.ClientTimeout(total=None, sock_read=120, connect=30)
        # Redirects stay disabled so the bot token cannot leak to another host.
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for url in candidates:
                async with session.get(url, allow_redirects=False) as response:
                    if response.status != 200:
                        failure = f"Telegram file server HTTP {response.status}"
                        continue
                    with dest.open("wb") as output:
                        async for chunk in response.content.iter_chunked(CHUNK):
                            if task.cancel_event.is_set():
                                raise asyncio.CancelledError()
                            output.write(chunk)
                            count(len(chunk))
                            await progress()
                    return
        raise RuntimeError(failure)

    async def _run(self, task: FileLinkTask) -> None:
        svc = self.svc
        dest = svc.store.link_path(task.id, task.name)
        registered = False
        received_traffic_recorded = 0
        try:
            tg_file = await task.attachment.get_file()
            await self._download(task, tg_file.file_path, dest)
            size = dest.stat().st_size
            received_traffic_recorded = await self._record_received_file_bytes(dest)
            if size > svc.settings.max_link_bytes:
                raise RuntimeError("File exceeds maximum link size")
            if task.cancel_event.is_set():
                raise asyncio.CancelledError()
            limit = svc.settings.max_links_per_user
            if limit > 0 and await repo.count_user_shared(task.user_id) >= limit:
                # سقف لینک همزمان بین شروع آپلود و پایانش پر شده است.
                await edit(task.status, text.t(task.lang, "link_quota_full", limit=limit))
                svc.store.drop_link_dir(task.id)
                return
            task.finalizing = True
            await edit(task.status, text.t(task.lang, "upload_wait"))
            ttl = svc.settings.ttl_seconds
            await repo.create_shared(task.id, task.user_id, str(dest), task.name, task.mime, size, ttl)
            registered = True
            if svc.admin_group is not None:
                await svc.admin_group.audit(
                    "file", "direct_link_created", task.user_id,
                    f"{task.id} | {size} bytes",
                )
            try:
                await repo.bump_uploads(task.user_id)
                await repo.log_event(task.user_id, "upload_done")
                await repo.log_event(task.user_id, "link_created", size)
            except Exception:
                log.warning("file link statistics could not be recorded", exc_info=True)
            token = make_token(task.id, svc.cfg.link_secret, ttl, user_id=task.user_id)
            url = f"{svc.cfg.public_base_url.rstrip('/')}/f/{token}"
            expires = datetime.fromtimestamp(int(time.time()) + ttl, tz=UTC).strftime("%H:%M UTC")
            await edit(task.status, text.t(
                task.lang, "link_ready",
                url=url, name=human.esc(task.name), size=human.human_bytes(size),
                ttl=f"{svc.settings.ttl_hours:g}", expires=expires,
            ), reply_markup=kb.link_actions(task.lang, url))
            if svc.admin_group is not None:
                try:
                    await svc.admin_group.notify_file_upload(
                        task.user_id, task.username, task.first_name, task.name, size,
                    )
                except Exception:
                    log.warning("admin upload notification failed", exc_info=True)
        except asyncio.CancelledError:
            received_traffic_recorded = await self._record_received_file_bytes(
                dest, received_traffic_recorded
            )
            if not registered:
                svc.store.drop_link_dir(task.id)
            if svc.admin_group is not None:
                await svc.admin_group.audit("file", "transfer_canceled",
                                            task.user_id, task.id)
            await edit(task.status, text.t(task.lang, "canceled"))
        except Exception as exc:
            log.warning("Telegram file-to-link transfer failed: %s", type(exc).__name__, exc_info=True)
            received_traffic_recorded = await self._record_received_file_bytes(
                dest, received_traffic_recorded
            )
            if svc.admin_group is not None:
                await svc.admin_group.audit("file", "transfer_failed", task.user_id,
                                            f"{task.id}, {type(exc).__name__}", severity="ERROR")
            if not registered:
                svc.store.drop_link_dir(task.id)
            await edit(task.status, text.t(task.lang, "failed", reason=human.esc(str(exc)[:120])))
        finally:
            self._tasks.pop(task.id, None)
