"""دسترسی موقت عیب‌یابی برای هوش مصنوعی — توکن زمان‌دار + HTTP API.

چرا این‌طوری؟
* هوش مصنوعی نباید رمز سرور یا پنل ادمین را بگیرد.
* توکن فقط یک بازهٔ کوتاه (حداکثر ۲۴ ساعت) زنده است و هر لحظه باطل می‌شود.
* در دیتابیس فقط ``sha256`` توکن ذخیره می‌شود؛ خود توکن یک‌بار نمایش داده می‌شود.
* هر توکن سه سطح دارد: ``read`` (خواندن سورس/وضعیت)، ``write`` (اصلاح فایل‌ها)
  و ``restart`` (ری‌استارت/بروزرسانی yt-dlp/اجرای تست‌ها).

مسیرها روی همان وب‌سرور لینک مستقیم سوار می‌شوند (``app/services/link_server.py``).
مسیرها همیشه ثبت می‌شوند و دسترسی واقعی در هر درخواست با ``debug_enabled``
(به‌طور پیش‌فرض روشن) بررسی می‌شود؛ پس روشن/خاموش‌کردن از پنل ری‌استارت نمی‌خواهد.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import secrets
import shutil
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web

from app.config import Config
from app.core import human
from app.db import healthcheck, repo
from app.services.runtime_settings import RuntimeSettings
from app.services.updater import SourceUpdater
from app.version import __version__, version_line

if TYPE_CHECKING:  # pragma: no cover
    from app.container import Services

MAX_HOURS = 24
TOKEN_PREFIX = "lxdbg_"
SCOPES: tuple[str, ...] = ("read", "write", "restart")
MAX_READ_BYTES = 256 * 1024
MAX_WRITE_BYTES = 512 * 1024

# فقط همین بخش‌ها از طریق API قابل نوشتن‌اند. هیچ‌وقت ``.env``/``data``/``.git``.
WRITABLE_PREFIXES = ("app/", "tests/", "docs/", ".github/")
WRITABLE_FILES = {
    "main.py",
    "pyproject.toml",
    "requirements.txt",
    "pytest.ini",
    "Dockerfile",
    "docker-compose.yml",
    ".dockerignore",
    ".gitignore",
    ".env.example",
    "README.md",
    "README.fa.md",
    "CHANGELOG.md",
    "AGENTS.md",
}
NEVER_WRITE = {".env", ".git", "data", "__pycache__", ".venv", "venv"}


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> int:
    return int(time.time())


class DebugAccess:
    """مدیریت توکن‌ها + منطق مسیرهای ``/debug``."""

    def __init__(self, cfg: Config, settings: RuntimeSettings, updater: SourceUpdater) -> None:
        self.cfg = cfg
        self.settings = settings
        self.updater = updater
        self.services: Services | None = None
        self.application = None

    def attach(self, services: Services) -> None:
        self.services = services

    def set_application(self, application) -> None:
        self.application = application

    # ── توکن‌ها ────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        return self.settings.debug_enabled

    @staticmethod
    def normalize_scopes(scopes: str | None) -> str:
        wanted = {part.strip() for part in (scopes or "read").split(",")}
        ordered = [scope for scope in SCOPES if scope in wanted]
        return ",".join(ordered or ["read"])

    @staticmethod
    def scope_label(scopes: str) -> str:
        parts = [p for p in (scopes or "").split(",") if p]
        if "restart" in parts:
            return "restart"
        if "write" in parts:
            return "write"
        return "read"

    def max_hours(self) -> int:
        configured = int(getattr(self.cfg, "debug_token_max_hours", MAX_HOURS) or MAX_HOURS)
        return max(1, min(configured, MAX_HOURS))

    async def create(
        self,
        created_by: int,
        *,
        hours: int = 6,
        scopes: str = "read",
        label: str = "",
    ) -> tuple[str, Any]:
        """توکن خام + رکورد دیتابیس را برمی‌گرداند (توکن خام فقط همین‌جا)."""
        await repo.purge_debug_tokens()
        ttl_hours = max(1, min(int(hours or 1), self.max_hours()))
        raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
        row = await repo.create_debug_token(
            _sha256(raw),
            label=label or "ai",
            scopes=self.normalize_scopes(scopes),
            created_by=created_by,
            expires_at=_now() + ttl_hours * 3600,
        )
        return raw, row

    async def active(self) -> list:
        return list(await repo.active_debug_tokens())

    async def revoke(self, token_id: int) -> bool:
        return await repo.revoke_debug_token(token_id)

    async def revoke_all(self) -> int:
        return await repo.revoke_all_debug_tokens()

    # ── احراز هویت ─────────────────────────────────────────
    @staticmethod
    def _bearer(request: web.Request) -> str:
        header = request.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            return header[7:].strip()
        return request.headers.get("X-Debug-Token", "").strip()

    @staticmethod
    def _error(status: int, message: str) -> web.Response:
        return web.json_response({"ok": False, "error": message}, status=status)

    async def _auth(self, request: web.Request, scope: str) -> tuple[Any | None, web.Response | None]:
        if not self.enabled:
            return None, self._error(403, "debug access is disabled")
        allowed = self.settings.debug_ip_allow
        remote = (request.remote or "").strip()
        if allowed and remote not in allowed:
            return None, self._error(403, f"ip {remote or '?'} is not allow-listed")
        raw = self._bearer(request)
        if not raw:
            return None, self._error(401, "missing bearer token")
        row = await repo.get_debug_token_by_hash(_sha256(raw))
        if row is None or row.revoked:
            return None, self._error(401, "invalid or revoked token")
        if row.expires_at <= _now():
            return None, self._error(401, "token expired")
        if scope not in (row.scopes or "").split(","):
            return None, self._error(403, f"token lacks '{scope}' scope")
        try:
            await repo.touch_debug_token(row.id)
        except Exception:  # noqa: BLE001 — آمار نباید درخواست را بشکند
            pass
        return row, None

    # ── مسیرهای خواندن ─────────────────────────────────────
    def _known_files(self) -> list[str]:
        return sorted(
            path.relative_to(self.updater.root).as_posix()
            for path in self.updater.source_files()
        )

    def _resolve_read(self, raw_path: str) -> tuple[Path | None, str]:
        rel = (raw_path or "").strip().replace("\\", "/").lstrip("/")
        if not rel:
            return None, "empty path"
        parts = Path(rel).parts
        if any(part in ("..", "") for part in parts):
            return None, "unsafe path"
        if parts and parts[0] in NEVER_WRITE:
            return None, "private path"
        target = (self.updater.root / rel).resolve()
        if not target.is_relative_to(self.updater.root):
            return None, "path escapes the project"
        if not target.is_file():
            return None, "file not found"
        if target.stat().st_size > MAX_READ_BYTES:
            return None, "file is too large to read"
        return target, ""

    @staticmethod
    def _writable(rel: str) -> bool:
        rel = rel.replace("\\", "/").lstrip("/")
        parts = Path(rel).parts
        if not parts or any(part in ("..", "") for part in parts):
            return False
        if parts[0] in NEVER_WRITE or ".env" in parts or "__pycache__" in parts:
            return False
        if rel in WRITABLE_FILES:
            return True
        return any(rel.startswith(prefix) for prefix in WRITABLE_PREFIXES)

    async def _health_payload(self) -> dict:
        svc = self.services
        problems: list[str] = []
        db_ok = await healthcheck()
        if not db_ok:
            problems.append("database is unreachable")

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            problems.append("ffmpeg was not found in PATH")

        ytdlp = self.updater.ytdlp_version()
        if ytdlp == "not installed":
            problems.append("yt-dlp is not installed")

        try:
            disk = human.human_bytes(svc.store.disk_free()) if svc else "?"
        except Exception:  # noqa: BLE001
            disk = "?"
        try:
            jobs = svc.jobs.active_count if svc else 0
        except Exception:  # noqa: BLE001
            jobs = 0
        try:
            users = await repo.count_users()
        except Exception:  # noqa: BLE001
            users = 0
        server = getattr(svc, "server", None) if svc else None
        if getattr(server, "_runner", None):
            web_state = "running"
        else:
            web_state = "stopped" if svc else "?"

        return {
            "ok": not problems,
            "version": __version__,
            "version_line": version_line(),
            "python": platform.python_version(),
            "ytdlp": ytdlp,
            "ffmpeg": ffmpeg or "missing",
            "database": "ok" if db_ok else "down",
            "disk_free": disk,
            "web": web_state,
            "active_jobs": jobs,
            "users": users,
            "debug_enabled": self.enabled,
            "max_token_hours": self.max_hours(),
            "problems": problems,
            "time": _now(),
        }

    async def _state_payload(self) -> dict:
        svc = self.services
        settings = self.settings
        return {
            "ok": True,
            "version": __version__,
            "uptime_seconds": svc.uptime if svc else 0,
            "public_base_url": settings.get_str("public_base_url"),
            "maintenance": settings.maintenance,
            "nsfw_enabled": settings.nsfw_enabled,
            "force_join": {
                "enabled": settings.force_join_enabled,
                "targets": [t.to_json() for t in (svc.force_join.targets if svc else [])],
            },
            "debug": {"enabled": settings.debug_enabled, "ip_allow": settings.debug_ip_allow},
            "limits": {
                "link_ttl_hours": settings.ttl_hours,
                "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
                "max_link_mb": settings.max_link_bytes // (1024 * 1024),
                "rate_limit_seconds": settings.rate_limit_seconds,
                "daily_quota": settings.daily_quota,
            },
            "last_update": self.updater.last_update(),
            "source": self.updater.stats(),
        }

    # ── هندلرهای HTTP ──────────────────────────────────────
    async def _h_health(self, request: web.Request) -> web.Response:
        _, error = await self._auth(request, "read")
        if error:
            return error
        return web.json_response(await self._health_payload())

    async def _h_state(self, request: web.Request) -> web.Response:
        _, error = await self._auth(request, "read")
        if error:
            return error
        return web.json_response(await self._state_payload())

    async def _h_logs(self, request: web.Request) -> web.Response:
        _, error = await self._auth(request, "read")
        if error:
            return error
        try:
            limit = max(1, min(int(request.query.get("limit", "50")), 200))
        except ValueError:
            limit = 50
        level = (request.query.get("level") or "").upper()
        rows = list(await repo.recent_logs(limit))
        if level:
            rows = [row for row in rows if row.level == level]
        return web.json_response(
            {
                "ok": True,
                "count": len(rows),
                "logs": [
                    {
                        "id": row.id,
                        "level": row.level,
                        "source": row.source,
                        "message": row.message,
                        "user_id": row.user_id,
                        "at": row.created_at,
                    }
                    for row in rows
                ],
            }
        )

    async def _h_source_get(self, request: web.Request) -> web.Response:
        _, error = await self._auth(request, "read")
        if error:
            return error
        raw_path = request.query.get("path", "")
        if not raw_path:
            files = self._known_files()
            return web.json_response({"ok": True, "count": len(files), "files": files})
        target, reason = self._resolve_read(raw_path)
        if target is None:
            return self._error(400, reason)
        content = target.read_text(encoding="utf-8", errors="replace")
        return web.json_response(
            {
                "ok": True,
                "path": target.relative_to(self.updater.root).as_posix(),
                "size": target.stat().st_size,
                "sha256": _sha256(content),
                "content": content,
            }
        )

    async def _h_source_post(self, request: web.Request) -> web.Response:
        _, error = await self._auth(request, "write")
        if error:
            return error
        try:
            payload = await request.json()
        except (json.JSONDecodeError, ValueError):
            return self._error(400, "body must be JSON")

        if not isinstance(payload, dict):
            return self._error(400, "body must be a JSON object")
        files: dict[str, str] = {}
        if isinstance(payload.get("files"), dict):
            files = {str(k): str(v) for k, v in payload["files"].items()}
        elif "path" in payload and "content" in payload:
            files = {str(payload["path"]): str(payload["content"])}
        if not files:
            return self._error(400, "send {\"files\": {path: content}} or {path, content}")

        for name, body in files.items():
            if not self._writable(name):
                return self._error(400, f"path is not writable: {name[:120]}")
            if len(body.encode("utf-8")) > MAX_WRITE_BYTES:
                return self._error(400, f"file is too large: {name[:120]}")

        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup_root = self.cfg.data_dir / "debug-backups" / stamp
        written: list[str] = []
        for name, body in files.items():
            rel = name.replace("\\", "/").lstrip("/")
            target = self.updater.root / rel
            if target.exists():
                keep = backup_root / rel
                keep.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, keep)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            written.append(rel)

        return web.json_response(
            {
                "ok": True,
                "written": written,
                "backup": str(backup_root) if written else "",
                "restart_required": True,
                "hint": "POST /debug/restart to load the changes.",
            }
        )

    async def _h_restart(self, request: web.Request) -> web.Response:
        _, error = await self._auth(request, "restart")
        if error:
            return error
        self.updater.request_restart()
        loop = asyncio.get_running_loop()
        if self.application is not None:
            # پاسخ HTTP اول ارسال شود، بعد فرآیند نرم متوقف شود.
            loop.call_later(1.5, self.application.stop_running)
        return web.json_response(
            {"ok": True, "restarting": True, "current_version": __version__}
        )

    async def _h_ytdlp(self, request: web.Request) -> web.Response:
        _, error = await self._auth(request, "restart")
        if error:
            return error
        nightly = (request.query.get("nightly") or "").lower() in ("1", "true", "yes")
        result = await self.updater.upgrade_ytdlp(nightly=nightly)
        if self.services is not None:
            try:
                await asyncio.to_thread(self.services.sites.build)
            except Exception:  # noqa: BLE001
                result.setdefault("warnings", []).append("site index rebuild failed")
        return web.json_response({"ok": bool(result.get("ok")), **result})

    async def _h_pytest(self, request: web.Request) -> web.Response:
        _, error = await self._auth(request, "write")
        if error:
            return error
        args = [sys.executable, "-m", "pytest", "-q", "--no-header"]
        target = request.query.get("path")
        if target:
            rel = target.replace("\\", "/").lstrip("/")
            if rel.startswith("tests/") and self._writable(rel):
                args.append(rel)
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(self.updater.root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            code = proc.returncode
        except (OSError, TimeoutError) as exc:
            return self._error(500, f"could not run tests: {exc}")
        text = (output or b"").decode("utf-8", "replace")
        tail = "\n".join(text.strip().splitlines()[-80:])
        return web.json_response({"ok": code == 0, "code": code, "output": tail})

    def register(self, app: web.Application) -> None:
        routes = [
            ("GET", "/debug/health", self._h_health),
            ("GET", "/debug/state", self._h_state),
            ("GET", "/debug/logs", self._h_logs),
            ("GET", "/debug/source", self._h_source_get),
            ("POST", "/debug/source", self._h_source_post),
            ("POST", "/debug/restart", self._h_restart),
            ("POST", "/debug/ytdlp-update", self._h_ytdlp),
            ("POST", "/debug/pytest", self._h_pytest),
        ]
        for method, path, handler in routes:
            app.router.add_route(method, path, handler)


def hash_token(raw: str) -> str:
    """برای تست‌ها/ابزارهای بیرونی."""
    return _sha256(raw)
