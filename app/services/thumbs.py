"""اسکرین‌شات‌های ویدیو برای انتخاب تامبنیل.

بعد از پایان دانلود، از ۱۰ زمانِ تصادفیِ فاصله‌دارِ ویدیو قاب گرفته می‌شود
و به‌صورت آلبوم برای انتخاب کاربر فرستاده می‌شود؛ کاربر روی هر قاب ریپلای
کند، همان قاب کاور آپلود می‌شود و اگر هیچ‌کاری نکند، آپلود با تامبنیل
پیشفرض (اولین قاب خوب یا کاور سایت) ادامه می‌یابد.

هیچ وابستگی به ربات نداریم؛ فقط ``ffmpeg`` و مسیر فایل. ``cancel`` قابل
تزریق است تا لغو کار وسط استخراج هم سریع تمام شود.
"""
from __future__ import annotations

import asyncio
import logging
import random
import shutil
import subprocess
from pathlib import Path

from telegram import InputMediaPhoto

log = logging.getLogger("leechx.thumbs")

SHOTS = 10          # تعداد قاب‌های پیشفرض برای انتخاب
SHOT_MAX_SIDE = 320
SHOT_MAX_BYTES = 200 * 1024  # سقف تلگرام برای تامبنیل
_SHOT_TIMEOUT = 25  # ثانیه به‌ازای هر قاب
_MIN_GAP = 1.0      # حداقل فاصلهٔ منطقی بین دو قاب (ثانیه)

# همهٔ پروتکل‌های استریمی به دانلودر داخلی سپرده می‌شوند؛ بقیه (مثل mp4
# پیشرونده) می‌توانند با aria2c چندکاناله شوند.
NATIVE_PROTOCOLS = {"m3u8", "m3u8_native", "mhtml", "ism", "dash", "http_dash_segments"}


def aria2c_opts() -> dict[str, object]:
    """گزینه‌های دانلود چندتکهٔ aria2c؛ اگر نصب نبود خالی."""
    if shutil.which("aria2c") is None:
        return {}
    return {
        "external_downloader": {p: "native" for p in NATIVE_PROTOCOLS}
        | {"default": "aria2c"},
        "external_downloader_args": {"aria2c": [
            "-x", "8", "-s", "8", "-k", "4M",
            "--max-connection-per-server=8",
            "--file-allocation=none",
            "--summary-interval=0",
            "--console-log-level=warn",
        ]},
    }


def shot_times(duration: float, count: int = SHOTS) -> list[float]:
    """تایم‌های تصادفی و بدون تداخل: هر تایم داخل یک بازهٔ مساوی میافتد.

    برای ویدیوهای خیلی کوتاه تعداد قاب‌ها کم می‌شود تا فاصله‌ها معنادار بماند.
    """
    duration = max(0.0, float(duration or 0))
    if duration <= 0:
        return []
    count = max(1, min(count, SHOTS))
    # هر قاب حداقل چند ثانیه از قبلی فاصله بگیرد.
    while count > 1 and duration / count < _MIN_GAP:
        count -= 1
    step = duration / count
    picks: list[float] = []
    for i in range(count):
        start = max(0.05, i * step + 0.05)
        end = min(duration - 0.05, (i + 1) * step - 0.05)
        if end <= start:
            end = start
        picks.append(random.uniform(start, end))
    return sorted(picks)


async def extract_shots(
    video: Path,
    times: list[float],
    workdir: Path,
    cancel: asyncio.Event | None = None,
) -> list[Path]:
    """از هر تایم یک قاب کوچک JPEG می‌گیرد؛ قاب‌های خراب حذف می‌شوند."""
    if not times:
        return []
    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return []
    shots: list[Path] = []
    for index, when in enumerate(times, start=1):
        if cancel is not None and cancel.is_set():
            break
        out = workdir / f"shot-{index:02d}.jpg"
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",
                "-nostdin",
                "-loglevel",
                "error",
                "-ss",
                f"{max(0.0, when):.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                f"scale={SHOT_MAX_SIDE}:{SHOT_MAX_SIDE}:"
                "force_original_aspect_ratio=decrease",
                "-q:v",
                "4",
                str(out),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=_SHOT_TIMEOUT)
        except (TimeoutError, FileNotFoundError, OSError):
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        if out.is_file() and out.stat().st_size <= SHOT_MAX_BYTES:
            shots.append(out)
    return shots


def chunk(items: list[Path], size: int = SHOTS) -> list[list[Path]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


async def send_picker_album(
    bot, chat_id: int, shots: list[Path], caption: str | None = None
) -> list[int]:
    """عکس‌ها را آلبومی برای انتخاب می‌فرستد و شناسهٔ پیام‌ها را برمی‌گرداند."""
    ids: list[int] = []
    groups = chunk(shots)
    for group_index, group in enumerate(groups):
        media = [
            InputMediaPhoto(
                media=shot.read_bytes(),
                caption=caption if group_index == 0 and index == 0 else None,
            )
            for index, shot in enumerate(group)
        ]
        messages = await bot.send_media_group(chat_id=chat_id, media=media)
        ids += [m.message_id for m in messages if m is not None]
    return ids
