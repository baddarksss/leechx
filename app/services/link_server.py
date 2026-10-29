"""وب‌سرور کوچک: پخش/دانلود فایل‌های لینک مستقیم + healthcheck.

* لینک‌ها امضاشده و منقضی‌شدنی‌اند (HMAC) — کسی نمی‌تواند فایل دیگران را حدس بزند.
* دانلود بازه‌ای (Range) پشتیبانی می‌شود تا پلیرها/مرورگرها بتوانند seek کنند.
* مسیر فایل همیشه داخل ``storage/links`` اعتبارسنجی می‌شود (ضد path traversal).
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import re
import time
from pathlib import Path
from urllib.parse import quote

from aiohttp import web

from app.config import Config
from app.db import healthcheck, repo
from app.services.filestore import FileStore
from app.services.linktoken import read_token
from app.services.runtime_settings import RuntimeSettings

log = logging.getLogger("leechx.web")

CHUNK = 64 * 1024
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


def _content_disposition(name: str, inline: bool) -> str:
    kind = "inline" if inline else "attachment"
    ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "file"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    if not header:
        return None
    match = RANGE_RE.match(header.strip())
    if not match:
        return None
    start_raw, end_raw = match.groups()
    if start_raw == "" and end_raw == "":
        return None
    if start_raw == "":
        suffix = int(end_raw)
        if suffix <= 0:
            return None
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
    if start >= size or start > end:
        return None
    return start, min(end, size - 1)


class LinkServer:
    def __init__(self, cfg: Config, settings: RuntimeSettings, store: FileStore, hub=None) -> None:
        self.cfg = cfg
        self.settings = settings
        self.store = store
        self.hub = hub
        self._access_logged: dict[str, float] = {}
        self._runner: web.AppRunner | None = None

    # ── ساخت اپلیکیشن ──────────────────────────────────────
    def build_app(self) -> web.Application:
        app = web.Application(client_max_size=1024 * 1024)  # این سرور آپلود نمی‌گیرد
        app.router.add_get("/", self._index)
        app.router.add_get("/health", self._health)
        app.router.add_get("/f/{token}", self._serve)
        return app

    async def start(self) -> None:
        app = self.build_app()
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.cfg.host, self.cfg.port)
        await site.start()
        log.info("link server on http://%s:%s", self.cfg.host, self.cfg.port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    # ── هندلرها ────────────────────────────────────────────
    async def _index(self, request: web.Request) -> web.Response:
        return web.Response(
            text="LeechX is running.\n",
            content_type="text/plain",
            headers={"Cache-Control": "no-store"},
        )

    async def _health(self, request: web.Request) -> web.Response:
        db_ok = await healthcheck()
        payload = {
            "status": "ok" if db_ok else "degraded",
            "db": db_ok,
            "time": int(time.time()),
            "shared_files": await repo.count_shared(),
            "disk_free": self.store.disk_free(),
        }
        return web.json_response(payload, status=200 if db_ok else 503)

    async def _serve(self, request: web.Request) -> web.StreamResponse:
        token = request.match_info.get("token", "")
        payload = read_token(token, self.cfg.link_secret)
        if payload is None:
            return web.Response(status=410, text="Link expired or invalid.\n")

        file_id = str(payload.get("f", ""))
        row = await repo.get_shared(file_id)
        if row is None:
            return web.Response(status=404, text="File not found.\n")

        if row.expires_at <= int(time.time()):
            await self._drop(row.id, row.path)
            return web.Response(status=410, text="Link expired.\n")

        path = Path(row.path)
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(self.store.links.resolve()):
                log.warning("path traversal attempt: %s", row.path)
                return web.Response(status=403, text="Forbidden.\n")
        except OSError:
            return web.Response(status=404, text="File not found.\n")

        if not resolved.is_file():
            await self._drop(row.id, row.path)
            return web.Response(status=404, text="File not found.\n")

        size = resolved.stat().st_size
        if size <= 0 or size != row.size:
            log.warning("link file size mismatch %s: expected %s, got %s", row.id, row.size, size)
            return web.Response(status=503, text="File unavailable or incomplete.\n")
        ctype = row.mime or mimetypes.guess_type(row.name)[0] or "application/octet-stream"
        inline = ctype.startswith(("video/", "audio/", "image/"))
        rng = _parse_range(request.headers.get("Range"), size)

        headers = {
            "Content-Type": ctype,
            "Content-Disposition": _content_disposition(row.name, inline),
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, no-store",
            "X-Expires-At": str(row.expires_at),
        }

        if request.headers.get("Range") and rng is None:
            return web.Response(status=416, headers={
                "Content-Range": f"bytes */{size}",
                "Accept-Ranges": "bytes",
                "Cache-Control": "private, no-store",
            })
        if rng is None:
            start, end = 0, size - 1
            status = 200
        else:
            start, end = rng
            status = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"

        length = max(0, end - start + 1)
        headers["Content-Length"] = str(length)

        response = web.StreamResponse(status=status, headers=headers)
        if request.method == "HEAD":
            await response.prepare(request)
            await response.write_eof()
            return response

        await response.prepare(request)
        remaining = length
        try:
            with resolved.open("rb") as fh:
                fh.seek(start)
                while remaining > 0:
                    chunk = fh.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    await response.write(chunk)
                    remaining -= len(chunk)
            await response.write_eof()
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        except OSError:
            log.exception("failed streaming %s", resolved)
            return response

        try:
            await repo.touch_shared(row.id)
        except Exception:  # noqa: BLE001 — آمار نباید دانلود را خراب کند
            log.debug("touch_shared failed", exc_info=True)
        if self.hub is not None:
            now = time.monotonic()
            if now - self._access_logged.get(row.id, 0) >= 300:
                self._access_logged[row.id] = now
                try:
                    await self.hub.audit(
                        "link_http", "direct_link_access", row.user_id,
                        f"file={row.id}, HTTP {status}, bytes={length}",
                    )
                except Exception:
                    log.debug("HTTP access audit failed", exc_info=True)
            if len(self._access_logged) > 20000:
                cutoff = now - 600
                self._access_logged = {k: v for k, v in self._access_logged.items() if v > cutoff}
        return response

    async def _drop(self, file_id: str, path: str) -> None:
        self.store.remove(Path(path))
        self.store.drop_link_dir(file_id)
        await repo.delete_shared(file_id)
