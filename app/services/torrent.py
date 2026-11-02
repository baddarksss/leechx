"""دانلود مگنت/تورنت با ``aria2c`` — بدون وابستگی یا سرویس جانبی.

``aria2c`` از v5.11.0 در ایمیج هست (برای دانلود پیشرونده) و پروتکل BitTorrent
را هم بومی پشتیبانی می‌کند؛ پس همان باینری را صدا می‌زنیم تا نه کتابخانهٔ
سنگین لازم باشد و نه qBittorrent/Transmission روی سرور.

جریان کار: مگنت → aria2c در پوشهٔ کارِ همان کار → بزرگ‌ترین فایل دانلودشده.
اگر تورنت چند فایل داشته باشد، بزرگ‌ترین فایل (که معمولاً ویدیوی اصلی است)
تحویل داده می‌شود و بقیه با پوشهٔ کار پاک می‌شوند.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.core import errors

log = logging.getLogger("leechx.torrent")

MAGNET_PREFIX = "magnet:?"
_SKIP_SUFFIXES = {".aria2", ".torrent", ".tmp", ".part"}
_POLL_SECONDS = 2.0


def is_magnet(url: str) -> bool:
    return (url or "").strip().lower().startswith(MAGNET_PREFIX)


def display_name(magnet: str) -> str:
    """نام نمایشی از پارامتر ``dn`` مگنت (یا خالی)."""
    try:
        params = parse_qs(urlparse(magnet).query)
    except ValueError:
        return ""
    for key in ("dn", "xl"):
        values = params.get(key) or []
        for value in values:
            name = (value or "").strip()
            if name:
                return name
    return ""


@dataclass
class TorrentResult:
    path: Path
    title: str
    size: int
    files: int = 1


def _counted(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() in _SKIP_SUFFIXES:
            continue
        files.append(path)
    return files


def bytes_on_disk(root: Path) -> int:
    total = 0
    for path in _counted(root):
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def largest_file(root: Path) -> Path | None:
    best: Path | None = None
    best_size = 0
    for path in _counted(root):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > best_size:
            best, best_size = path, size
    return best


async def download(
    magnet: str,
    workdir: Path,
    progress,
    cancel: asyncio.Event,
    *,
    connections: int = 4,
    timeout: float = 7200.0,
) -> TorrentResult:
    """مگنت را دانلود می‌کند و بزرگ‌ترین فایل را برمی‌گرداند."""
    exe = shutil.which("aria2c")
    if exe is None:
        raise errors.TorrentFailed("aria2c is not installed", key="torrent_unavailable")
    workdir.mkdir(parents=True, exist_ok=True)
    args = [
        exe,
        f"--dir={workdir}",
        "--seed-time=0",
        "--bt-stop-timeout=90",
        "--console-log-level=warn",
        "--summary-interval=0",
        "--file-allocation=none",
        "--auto-file-renaming=false",
        "--allow-overwrite=true",
        f"--max-connection-per-server={max(1, int(connections))}",
        "--bt-max-peers=60",
        "--enable-dht=true",
        "--follow-torrent=mem",
        magnet,
    ]
    log.info("torrent download started")
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    code: int | None = None
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(60.0, float(timeout))
    try:
        while True:
            try:
                code = await asyncio.wait_for(proc.wait(), timeout=_POLL_SECONDS)
                break
            except TimeoutError:
                pass
            if cancel.is_set():
                proc.kill()
                await proc.wait()
                raise errors.JobCancelled()
            total = await asyncio.to_thread(bytes_on_disk, workdir)
            progress.downloaded = total
            progress.downloaded_bytes_total = max(progress.downloaded_bytes_total, total)
            if loop.time() > deadline:
                proc.kill()
                await proc.wait()
                raise errors.TorrentFailed("torrent download timed out")
    finally:
        if proc.returncode is None:  # pragma: no cover — فقط مسیر خطای غیرمنتظره
            proc.kill()
            try:
                await proc.wait()
            except ProcessLookupError:
                pass

    if code:
        raise errors.TorrentFailed(f"aria2c exited with {code}")
    path = await asyncio.to_thread(largest_file, workdir)
    if path is None:
        raise errors.TorrentFailed("torrent finished without a file")
    files = len(await asyncio.to_thread(_counted, workdir))
    size = await asyncio.to_thread(lambda: path.stat().st_size)
    title = display_name(magnet) or path.stem
    return TorrentResult(path=path, title=title, size=int(size), files=files)
