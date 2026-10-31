"""Cancellable Telegram attachment -> direct-link transfers with measured progress.

Telegram's stock File.download_to_drive buffers the full file in memory on the
public Bot API. Stream the getFile URL instead, one chunk at a time.
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import aiohttp

from app.bot import keyboards as kb
from app.bot.common import edit
from app.core import human, text
from app.db import repo
from app.services.linktoken import make_token

log = logging.getLogger("leechx.telegram_transfers")
CHUNK = 256 * 1024


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

        # Local Telegram Bot API provides a path on a shared filesystem.
        if not file_path.startswith(("http://", "https://")):
            source = Path(file_path)
            with source.open("rb") as fh, dest.open("wb") as output:
                while True:
                    if task.cancel_event.is_set():
                        raise asyncio.CancelledError()
                    chunk = await asyncio.to_thread(fh.read, CHUNK)
                    if not chunk:
                        break
                    await asyncio.to_thread(output.write, chunk)
                    received += len(chunk)
                    if received > self.svc.settings.max_link_bytes:
                        raise RuntimeError("Maximum link file size exceeded")
                    await progress()
        else:
            # Only consume the trusted URL returned by Bot.get_file.
            # Redirects are explicitly disabled to avoid leaking its bot token.
            timeout = aiohttp.ClientTimeout(total=None, sock_read=120, connect=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(file_path, allow_redirects=False) as response:
                    if response.status != 200:
                        raise RuntimeError(f"Telegram file server HTTP {response.status}")
                    with dest.open("wb") as output:
                        async for chunk in response.content.iter_chunked(CHUNK):
                            if task.cancel_event.is_set():
                                raise asyncio.CancelledError()
                            output.write(chunk)
                            received += len(chunk)
                            if received > self.svc.settings.max_link_bytes:
                                raise RuntimeError("Maximum link file size exceeded")
                            await progress()
        if task.cancel_event.is_set():
            raise asyncio.CancelledError()
        if received <= 0 or (expected and received != expected):
            raise RuntimeError(f"Telegram transfer incomplete ({received}/{expected})")
        await progress(force=True)

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
