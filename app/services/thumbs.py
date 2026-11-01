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
import json
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
# کیفیت‌های JPEG از بهترین به ضعیف‌ترین؛ تا وقتی حجم زیر سقف تلگرام بیاید
# از q:v 2 شروع می‌کنیم تا تامبنیل روی تلگرام دسکتاپ (که آن را بزرگ‌نمایی
# می‌کند) تار و کش‌دار دیده نشود.
_SHOT_QUALITIES = (2, 4, 6, 8)
_PROBE_TIMEOUT = 15
# مقیاس با lanczos + حذف SAR غیرمربعی: نسبت تصویر قاب دقیقاً همان چیزی
# می‌ماند که تلگرام برای ویدیو اعلام می‌کند، پس دسکتاپ آن را نمی‌کشد.
_SHOT_FILTER = (
    f"scale={SHOT_MAX_SIDE}:{SHOT_MAX_SIDE}:"
    "force_original_aspect_ratio=decrease:force_divisible_by=2:"
    "flags=lanczos,setsar=1,unsharp=5:5:0.4"
)

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
        if await _grab_frame(video, when, out):
            shots.append(out)
    return shots


async def _grab_frame(video: Path, when: float, out: Path) -> bool:
    """یک قاب در ``when`` می‌گیرد؛ اگر از سقف حجم رد شد کیفیت را کم می‌کند."""
    for quality in _SHOT_QUALITIES:
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
                _SHOT_FILTER,
                "-q:v",
                str(quality),
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
            out.unlink(missing_ok=True)
            return False
        if proc.returncode != 0:
            out.unlink(missing_ok=True)
            return False
        try:
            size = out.stat().st_size
        except OSError:
            return False
        if 0 < size <= SHOT_MAX_BYTES:
            return True
        out.unlink(missing_ok=True)
    return False


def chunk(items: list[Path], size: int = SHOTS) -> list[list[Path]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _ratio(text: str | None) -> tuple[int, int] | None:
    """«16:9» یا «1:1» را به جفت صحیح تبدیل می‌کند؛ «0:1»/«N/A» یعنی نامعلوم."""
    if not text or not isinstance(text, str):
        return None
    left, _, right = text.partition(":")
    try:
        num, den = int(left), int(right)
    except (TypeError, ValueError):
        return None
    if num <= 0 or den <= 0:
        return None
    return num, den


def _rotation(stream: dict) -> int:
    """زاویهٔ چرخش متادیتا (۰..۳۵۹)؛ ffmpeg آن را منفی هم می‌نویسد."""
    raw = None
    side_data = stream.get("side_data_list") or stream.get("stream_side_data")
    if isinstance(side_data, list):
        for item in side_data:
            if isinstance(item, dict) and item.get("rotation") is not None:
                raw = item["rotation"]
                break
    if raw is None:
        tags = stream.get("tags")
        if isinstance(tags, dict):
            raw = tags.get("rotate")
    try:
        return int(round(float(raw))) % 360
    except (TypeError, ValueError):
        return 0


def display_size(stream: dict) -> tuple[int, int] | None:
    """ابعاد نمایشیِ یک استریم ویدیو: چرخش و SAR را هم حساب می‌کند.

    تلگرام دسکتاپ تامبنیل را به نسبت ابعادِ اعلام‌شدهٔ ویدیو می‌کشد؛ پس اگر
    عرض/ارتفاع را از خود فایل (و نه متادیتای yt-dlp) بگیریم، تصویر کش نمی‌آید.
    """
    try:
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    sar = _ratio(stream.get("sample_aspect_ratio"))
    dar = _ratio(stream.get("display_aspect_ratio"))
    if sar is not None:
        shown_w = width * sar[0] / sar[1]
    elif dar is not None:
        shown_w = height * dar[0] / dar[1]
    else:
        shown_w = float(width)
    shown_h = float(height)
    if _rotation(stream) % 180 == 90:
        shown_w, shown_h = shown_h, shown_w
    return max(1, round(shown_w)), max(1, round(shown_h))


async def probe_display_size(video: Path) -> tuple[int, int] | None:
    """ابعاد واقعیِ نمایش ویدیو با ffprobe؛ در نبود ffprobe/خطا ``None``."""
    if shutil.which("ffprobe") is None:
        return None
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,sample_aspect_ratio,display_aspect_ratio"
            ":stream_tags=rotate:stream_side_data=rotation",
            "-of",
            "json",
            str(video),
            stdout=asyncio.subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_PROBE_TIMEOUT)
    except (TimeoutError, FileNotFoundError, OSError):
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        return None
    if proc.returncode != 0 or not stdout:
        return None
    try:
        data = json.loads(stdout.decode("utf-8", "replace"))
    except ValueError:
        return None
    streams = data.get("streams") if isinstance(data, dict) else None
    if not isinstance(streams, list) or not streams:
        return None
    stream = streams[0]
    if not isinstance(stream, dict):
        return None
    size = display_size(stream)
    if size is None:
        log.debug("could not derive display size for %s", video)
    return size


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
