"""مدیریت فایل‌های موقت روی دیسک.

قاعدهٔ طلایی: هر کاری که شروع می‌شود یک پوشهٔ اختصاصی می‌گیرد و در
``finally`` پاک می‌شود. هیچ فایلی از «حالت لینک» باقی نمی‌ماند.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            continue
    return total


class FileStore:
    def __init__(self, root: Path, tmp: Path) -> None:
        self.root = Path(root)
        self.tmp = Path(tmp)
        self.jobs = self.root / "jobs"
        self.links = self.root / "links"
        for p in (self.root, self.tmp, self.jobs, self.links):
            p.mkdir(parents=True, exist_ok=True)

    # ── پوشهٔ کار ───────────────────────────────────────────
    def job_dir(self, job_id: str) -> Path:
        path = self.jobs / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def drop_job_dir(self, job_id: str) -> None:
        self.remove(self.jobs / job_id)

    # ── فایل‌های لینک مستقیم ────────────────────────────────
    def link_path(self, file_id: str, filename: str) -> Path:
        folder = self.links / file_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder / filename

    def drop_link_dir(self, file_id: str) -> None:
        self.remove(self.links / file_id)

    # ── عمومی ───────────────────────────────────────────────
    def remove(self, path: Path) -> None:
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink(missing_ok=True)
        except OSError:
            pass

    def purge_older_than(self, seconds: int, base: Path | None = None) -> tuple[int, int]:
        """پوشه‌های قدیمی‌تر از N ثانیه را پاک می‌کند → (تعداد، بایت آزادشده)"""
        base = base or self.jobs
        if not base.exists():
            return 0, 0
        cutoff = time.time() - seconds
        removed, freed = 0, 0
        for child in base.iterdir():
            try:
                mtime = child.stat().st_mtime
            except OSError:
                continue
            if mtime >= cutoff:
                continue
            size = dir_size(child) if child.is_dir() else child.stat().st_size
            self.remove(child)
            removed += 1
            freed += size
        return removed, freed

    def disk_free(self) -> int:
        try:
            return shutil.disk_usage(self.root).free
        except OSError:
            return 0

    def total_size(self) -> int:
        return dir_size(self.jobs) + dir_size(self.links)
