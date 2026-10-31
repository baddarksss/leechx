"""دیپلوی از داخل ربات: خروجی ZIP سورس، اعتبارسنجی، بکاپ و اعمال سورس جدید.

فلسفه: ادمین نباید برای هر آپدیت به سرور یا GitHub برود. اما اعمال یک ZIP
دلخواه هم خطرناک است، پس این لایه:

* فقط فایل‌های «سورس» را خارج می‌کند (بدون ``.env``، ``data`` و دیتابیس).
* ZIP ورودی را سخت اعتبارسنجی می‌کند (path traversal، حجم، تعداد فایل، symlink).
* قبل از هر تغییر از سورس فعلی بکاپ ZIP می‌گیرد.
* وابستگی‌های جدید را **قبل از** دست‌زدن به سورس نصب می‌کند (اگر
  ``requirements.txt`` عوض شده باشد) تا آپدیتِ نیمه‌کاره رخ ندهد.
* فایل‌های سورسی که در ZIP جدید نیستند را پاک می‌کند (حذف‌شدن درست است).
* خروجی پایتون ZIP را قبل از اعمال بررسی می‌کند و در پایان ``__pycache__``
  کهنه را پاک می‌کند.
* یک اسنپ‌شات از سورسِ اعمال‌شده در ``data/updates`` می‌گذارد تا بعداً قابل
  دانلود/کامیت به GitHub باشد.
* فایل‌ها را جای‌گزین می‌کند و فقط در پایان، ری‌استارت را درخواست می‌دهد.

اعمال سورس داخل همان فرآیند انجام می‌شود؛ ری‌استارت واقعی در
``post_shutdown`` با ``os.execv`` یا دستور دلخواه اپراتور انجام می‌شود.
"""
from __future__ import annotations

import asyncio
import importlib.metadata
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from app.config import BASE_DIR, Config
from app.core import human
from app.version import __version__, parse_version

log = logging.getLogger("leechx.updater")

# همهٔ مسیرهایی که بخشی از سورس‌اند و باید در ZIP باشند.
INCLUDE_DIRS = ("app", "tests", "docs", ".github")
INCLUDE_ROOT_FILES = {
    "main.py",
    "requirements.txt",
    "pyproject.toml",
    "pytest.ini",
    "Dockerfile",
    "docker-compose.yml",
    ".dockerignore",
    ".gitignore",
    ".env.example",
    "LICENSE",
    "README.md",
    "README.fa.md",
    "CHANGELOG.md",
    "AGENTS.md",
    "LEECHX_FIXES.patch",
    "GROUP_SETUP_CACHE_LOGS_FA.md",
    "QA_FEATURES_V2_FA.md",
    "QA_FEATURES_V3_FA.md",
    "QA_FEATURES_V4_FA.md",
    "QA_FIX_REPORT_FA.md",
}

# هرگز نباید از ZIP وارد سورس شوند (حتی اگر داخل آرشیو باشند).
NEVER_WRITE = {
    ".env",
    ".git",
    "data",
    "__pycache__",
    ".venv",
    "venv",
    "keys_en.json",
}

MAX_FILES = 3000
MAX_UNCOMPRESSED = 300 * 1024 * 1024
VERSION_RE = re.compile(r'__version__\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"')

KEEP_BACKUPS = 5
KEEP_APPLIED = 3

# اگر ZIP جدید کمتر از این نسبت از فایل‌های فعلی را داشته باشد، ناقص تلقی می‌شود.
MIN_FILES_RATIO = 0.5
PIP_TIMEOUT = 900.0
COMPILE_TIMEOUT = 120.0


@dataclass
class ZipPreview:
    ok: bool
    reason: str = ""
    version: str = ""
    files: int = 0
    size: int = 0
    prefix: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def is_newer(self) -> bool:
        current = parse_version(__version__) or (0, 0, 0)
        incoming = parse_version(self.version) or (0, 0, 0)
        return incoming > current


@dataclass
class ApplyResult:
    ok: bool
    reason: str = ""
    version: str = ""
    files: int = 0
    removed: int = 0
    deps: bool = False
    backup: Path | None = None
    archive: Path | None = None


class SourceUpdater:
    def __init__(self, cfg: Config, root: Path | None = None) -> None:
        self.cfg = cfg
        self.root = (root or BASE_DIR).resolve()
        self.workdir = cfg.data_dir / "updates"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.restart_requested = False

    # ── خروجی/بکاپ ──────────────────────────────────────────
    def source_files(self) -> list[Path]:
        files: list[Path] = []
        for name in INCLUDE_DIRS:
            base = self.root / name
            if not base.is_dir():
                continue
            for path in base.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(self.root)
                if any(part in NEVER_WRITE for part in rel.parts):
                    continue
                if path.suffix in (".pyc", ".pyo") or "__pycache__" in rel.parts:
                    continue
                files.append(path)
        for name in INCLUDE_ROOT_FILES:
            path = self.root / name
            if path.is_file():
                files.append(path)
        return files

    def source_size(self) -> int:
        total = 0
        for path in self.source_files():
            try:
                total += path.stat().st_size
            except OSError:
                continue
        return total

    def export_zip(self, kind: str = "source", version: str | None = None) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        label = version or __version__
        target = self.workdir / f"leechx-{kind}-v{label}-{stamp}.zip"
        files = self.source_files()
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in files:
                zf.write(path, path.relative_to(self.root).as_posix())
            zf.comment = f"LeechX v{__version__} {kind}".encode()
        log.info("exported %s (%d files, %s)", target.name, len(files), human.human_bytes(target.stat().st_size))
        return target

    def backup(self, reason: str = "update") -> Path:
        path = self.export_zip(kind=f"backup-{reason}", version=__version__)
        self._prune_backups()
        return path

    def backups(self) -> list[Path]:
        return sorted(self.workdir.glob("leechx-backup-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)

    def latest_backup(self) -> Path | None:
        items = self.backups()
        return items[0] if items else None

    def _prune_backups(self) -> None:
        for old in self.backups()[KEEP_BACKUPS:]:
            try:
                old.unlink()
            except OSError:
                continue

    # ── اعتبارسنجی ZIP ──────────────────────────────────────
    @staticmethod
    def _safe_name(name: str) -> bool:
        if not name or name.startswith("/") or name.startswith("\\"):
            return False
        parts = Path(name).parts
        return not any(part in ("..", "") for part in parts)

    def inspect_zip(self, path: Path) -> ZipPreview:
        try:
            if not path.is_file() or path.stat().st_size == 0:
                return ZipPreview(False, "empty file")
            if not zipfile.is_zipfile(path):
                return ZipPreview(False, "not a ZIP archive")
            with zipfile.ZipFile(path) as zf:
                infos = [i for i in zf.infolist() if not i.is_dir()]
                if not infos:
                    return ZipPreview(False, "archive has no files")
                if len(infos) > MAX_FILES:
                    return ZipPreview(False, f"too many files ({len(infos)} > {MAX_FILES})")
                total = 0
                names: list[str] = []
                for info in infos:
                    if not self._safe_name(info.filename):
                        return ZipPreview(False, f"unsafe path: {info.filename[:80]}")
                    mode = (info.external_attr >> 16) & 0o170000
                    if mode == 0o120000:
                        return ZipPreview(False, f"symlink not allowed: {info.filename[:80]}")
                    total += info.file_size
                    if total > MAX_UNCOMPRESSED:
                        return ZipPreview(False, "archive expands beyond the limit")
                    names.append(info.filename.replace("\\", "/"))

                prefix = self._common_prefix(names)
                relative = [n[len(prefix):] for n in names] if prefix else names
                if "main.py" not in relative or "app/version.py" not in relative:
                    return ZipPreview(False, "main.py and app/version.py are required")

                version_raw = zf.read(self._with_prefix(prefix, "app/version.py")).decode("utf-8", "replace")
                match = VERSION_RE.search(version_raw)
                version = match.group(1) if match else ""
                notes: list[str] = []
                if not version:
                    notes.append("version not detected in app/version.py")
                if any(n.startswith((".env", "data/")) for n in relative):
                    notes.append("private paths were ignored")
                return ZipPreview(
                    ok=True,
                    version=version or "?",
                    files=len(relative),
                    size=path.stat().st_size,
                    prefix=prefix,
                    notes=notes,
                )
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            return ZipPreview(False, str(exc)[:160])

    @staticmethod
    def _common_prefix(names: list[str]) -> str:
        """اگر همهٔ فایل‌ها زیر یک پوشهٔ واحد هستند، آن را برمی‌گرداند."""
        first = names[0]
        if "/" not in first:
            return ""
        root = first.split("/", 1)[0] + "/"
        if all(name.startswith(root) for name in names):
            return root
        return ""

    @staticmethod
    def _with_prefix(prefix: str, name: str) -> str:
        return f"{prefix}{name}" if prefix else name

    # ── اعمال سورس ─────────────────────────────────────────
    def apply_zip(self, path: Path) -> ApplyResult:
        preview = self.inspect_zip(path)
        if not preview.ok:
            return ApplyResult(False, preview.reason)

        stamp = time.strftime("%Y%m%d-%H%M%S")
        staging = self.workdir / f"staging-{stamp}"
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename.replace("\\", "/")
                    if preview.prefix:
                        if not name.startswith(preview.prefix):
                            continue
                        name = name[len(preview.prefix):]
                    if not name or not self._safe_name(name):
                        continue
                    parts = Path(name).parts
                    if parts and parts[0] in NEVER_WRITE:
                        continue
                    if ".env" in parts or "__pycache__" in parts:
                        continue
                    dest = staging / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, dest.open("wb") as out:
                        shutil.copyfileobj(src, out)

            if not (staging / "main.py").is_file() or not (staging / "app" / "version.py").is_file():
                return ApplyResult(False, "staged archive is incomplete")

            staged = self._staged_files(staging)
            current = len(self.source_files())
            if current and len(staged) < max(3, int(current * MIN_FILES_RATIO)):
                return ApplyResult(
                    False,
                    f"archive looks incomplete ({len(staged)} files vs {current} in the running source)",
                )

            # ۱) سلامت نحوی کد جدید — قبل از هر تغییری
            ok, reason = self._compile_check(staging)
            if not ok:
                return ApplyResult(False, f"python syntax error: {reason}")

            # ۲) وابستگی‌ها — قبل از جای‌گزینی سورس، تا خرابی نیمه‌کاره نداشته باشیم
            deps = False
            if self.requirements_changed(staging):
                ok, reason = self._install_requirements(staging / "requirements.txt")
                if not ok:
                    return ApplyResult(False, f"dependency install failed: {reason}")
                deps = True

            # ۳) بکاپ، حذف فایل‌های منسوخ، نوشتن فایل‌های جدید
            backup = self.backup(reason="pre-update")
            removed = self._remove_stale(staged)
            copied = 0
            for src in staging.rglob("*"):
                if not src.is_file():
                    continue
                if "__pycache__" in src.parts or src.suffix in (".pyc", ".pyo"):
                    continue
                rel = src.relative_to(staging)
                target = self.root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
                copied += 1

            self._purge_pycache()

            # ۴) اسنپ‌شات سورس اعمال‌شده (برای دانلود/کامیت به GitHub)
            archive: Path | None = None
            try:
                archive = self.export_zip(kind="applied", version=preview.version)
                self._prune_applied()
            except OSError:
                log.warning("could not export applied source snapshot", exc_info=True)

            self._write_last_update(
                preview.version, copied, backup, removed=removed, deps=deps, archive=archive
            )
        except (OSError, zipfile.BadZipFile) as exc:
            log.exception("source update failed")
            return ApplyResult(False, str(exc)[:160])
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        return ApplyResult(
            True,
            version=preview.version,
            files=copied,
            removed=removed,
            deps=deps,
            backup=backup,
            archive=archive,
        )

    @staticmethod
    def _staged_files(staging: Path) -> set[str]:
        return {
            path.relative_to(staging).as_posix()
            for path in staging.rglob("*")
            if path.is_file()
        }

    def _compile_check(self, staging: Path) -> tuple[bool, str]:
        """کامپایل همهٔ فایل‌های پایتون ZIP؛ خطای نحوی = عدم اعمال."""
        result: tuple[bool, str] = (True, "")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "compileall", "-q", str(staging)],
                capture_output=True,
                text=True,
                timeout=COMPILE_TIMEOUT,
            )
            if proc.returncode != 0:
                tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
                result = (False, (" | ".join(tail) or "compileall failed")[:300])
        except (OSError, subprocess.TimeoutExpired) as exc:
            log.warning("compile check skipped: %s", exc)
        finally:
            # compileall داخل staging پوشهٔ __pycache__ می‌سازد؛ نباید به سورس راه یابد.
            for cache in staging.rglob("__pycache__"):
                shutil.rmtree(cache, ignore_errors=True)
        return result

    def requirements_changed(self, staging: Path) -> bool:
        """آیا ``requirements.txt`` نسبت به سورس فعلی عوض شده است؟"""
        new_path = staging / "requirements.txt"
        old_path = self.root / "requirements.txt"
        if not new_path.is_file():
            return False
        try:
            return self._parse_requirements(new_path) != self._parse_requirements(old_path)
        except OSError:
            return True

    @staticmethod
    def _parse_requirements(path: Path) -> set[str]:
        if not path.is_file():
            return set()
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return set()
        lines = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            lines.append(line)
        return set(lines)

    def _install_requirements(self, requirements: Path) -> tuple[bool, str]:
        args = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "-r",
            str(requirements),
        ]
        if not self._site_packages_writable():
            args.append("--user")
        env = dict(os.environ)
        env.setdefault("PIP_USER", "1")
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=PIP_TIMEOUT,
                cwd=str(self.root),
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)[:200]
        if proc.returncode == 0:
            log.info("dependencies installed from %s", requirements)
            return True, ""
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-4:]
        return False, (" | ".join(tail) or f"pip exited with {proc.returncode}")[:300]

    def _remove_stale(self, staged: set[str]) -> int:
        """فایل‌هایی که در سورس فعلی هستند ولی در ZIP جدید نیستند را حذف می‌کند."""
        removed = 0
        for old in self.source_files():
            rel = old.relative_to(self.root).as_posix()
            if rel in staged:
                continue
            try:
                old.unlink()
                removed += 1
            except OSError:
                log.warning("could not remove stale file %s", rel)
        if removed:
            log.info("removed %d stale source files", removed)
        return removed

    def _purge_pycache(self) -> None:
        for path in self.root.rglob("__pycache__"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

    def applied_archives(self) -> list[Path]:
        return sorted(
            self.workdir.glob("leechx-applied-*.zip"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    def _prune_applied(self) -> None:
        for old in self.applied_archives()[KEEP_APPLIED:]:
            try:
                old.unlink()
            except OSError:
                continue

    def _write_last_update(
        self,
        version: str,
        files: int,
        backup: Path | None,
        *,
        removed: int = 0,
        deps: bool = False,
        archive: Path | None = None,
    ) -> None:
        payload = {
            "version": version,
            "at": int(time.time()),
            "files": files,
            "removed": removed,
            "deps": deps,
            "backup": backup.name if backup else "",
            "archive": archive.name if archive else "",
        }
        try:
            (self.workdir / "last_update.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            log.warning("could not write last_update.json", exc_info=True)

    def last_update(self) -> dict:
        try:
            raw = (self.workdir / "last_update.json").read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    # ── ری‌استارت ───────────────────────────────────────────
    def request_restart(self) -> None:
        self.restart_requested = True

    def perform_restart(self) -> None:
        """در پایان خاموش‌شدن نرم اجرا می‌شود. برنمی‌گردد اگر execv موفق باشد."""
        command = self.cfg.update_restart_command.strip()
        if command:
            log.info("restarting with operator command: %s", command)
            try:
                subprocess.Popen(command, shell=True, cwd=str(self.root))
                return
            except OSError:
                log.exception("restart command failed; falling back to execv")
        log.info("restarting in place with execv")
        try:
            os.execv(sys.executable, [sys.executable, *sys.argv])
        except OSError:
            log.exception("execv failed; exiting so the supervisor can restart")
            os._exit(0)

    # ── بروزرسانی yt-dlp ────────────────────────────────────
    @staticmethod
    def ytdlp_version() -> str:
        try:
            return importlib.metadata.version("yt-dlp")
        except importlib.metadata.PackageNotFoundError:
            return "not installed"

    @staticmethod
    def ytdlp_location() -> str:
        """مسیری که yt-dlp نصب شده؛ برای اطمینان از پایدار بودنش (volume)."""
        try:
            dist = importlib.metadata.distribution("yt-dlp")
            return str(Path(dist.locate_file("")).resolve())
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def user_base() -> str:
        override = os.environ.get("PYTHONUSERBASE", "").strip()
        return override or str(Path.home() / ".local")

    async def upgrade_ytdlp(self, nightly: bool = False, timeout: float = 300.0) -> dict:
        before = self.ytdlp_version()
        args = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "yt-dlp",
        ]
        if nightly:
            args.append("--pre")
        if not self._site_packages_writable():
            args.append("--user")
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            code = proc.returncode
        except (OSError, TimeoutError) as exc:
            return {"ok": False, "error": str(exc)[:160], "before": before, "after": before}

        after = self.ytdlp_version()
        tail = (output or b"").decode("utf-8", "replace").strip().splitlines()[-6:]
        return {
            "ok": code == 0,
            "error": "" if code == 0 else "\n".join(tail)[:400],
            "before": before,
            "after": after,
            "changed": after != before,
            "location": self.ytdlp_location(),
            "user_base": self.user_base(),
        }

    @staticmethod
    def _site_packages_writable() -> bool:
        try:
            import yt_dlp

            target = Path(yt_dlp.__file__).resolve().parent
            return os.access(target, os.W_OK)
        except Exception:  # noqa: BLE001
            return False

    # ── اطلاعات نمایشی ─────────────────────────────────────
    def stats(self) -> dict:
        last = self.last_update()
        backup = self.latest_backup()
        return {
            "version": __version__,
            "size": human.human_bytes(self.source_size()),
            "files": len(self.source_files()),
            "backup": human.human_duration(int(time.time() - backup.stat().st_mtime)) + " ago" if backup else "—",
            "last_update": (
                time.strftime("%Y-%m-%d %H:%M", time.localtime(int(last.get("at", 0))))
                + f" (v{last.get('version', '?')})"
                if last
                else "—"
            ),
        }
