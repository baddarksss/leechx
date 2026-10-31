"""تقسیم فایل‌های بزرگ‌تر از سقف آپلود تلگرام به پارت‌های قابل ارسال.

دو روش داریم:

* **ویدیو** (``mp4`` / ``mov`` / ``mkv`` …): اول با ``ffmpeg -c copy`` و اگر
  keyframeهای ویدیو اجازه نداد، با رمزگذاری مجدد H.264 به چند فایل MP4
  مستقل و قابل‌پخش تقسیم می‌شود.
* **بقیهٔ فایل‌ها**: تقسیم بایتی ساده (``.part1``، ``.part2`` …) که بعد از
  دانلود همهٔ پارت‌ها دوباره به‌هم چسبانده می‌شود.

هیچ پارتی از سقف تلگرام بزرگ‌تر نمی‌شود؛ اگر برش ویدیو به‌خاطر محل
keyframe کمی بزرگ‌تر شد، با پارت‌های بیشتر دوباره تلاش می‌کنیم.
"""
from __future__ import annotations

import asyncio
import math
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.core import errors, human

# برای ویدیو کمی حاشیه می‌گذاریم تا moov/سربار کانتینر از سقف رد نشود.
SAFETY = 0.90
# سقف تعداد پارت‌ها؛ بیشتر از این یعنی فایل برای تلگرام منطقی نیست.
MAX_PARTS = 10

PLAYABLE_EXT = {".mp4", ".m4v", ".mov"}
VIDEO_EXT = PLAYABLE_EXT | {".mkv", ".webm", ".avi", ".flv", ".ts", ".m2ts", ".wmv", ".3gp"}

_READ_CHUNK = 8 * 1024 * 1024


@dataclass
class SplitPlan:
    """نتیجهٔ تقسیم: فایل‌های آماده برای ارسال به ترتیب."""

    parts: list[Path] = field(default_factory=list)
    method: str = "none"  # none | video | bytes

    @property
    def count(self) -> int:
        return len(self.parts)


def usable_bytes(limit: int) -> int:
    """بزرگ‌ترین حجم هر پارت (با حاشیهٔ امن)."""
    return max(1, int(limit * SAFETY))


def planned_parts(size: int, limit: int) -> int:
    """تعداد پارتی که برای این حجم لازم است (حداقل ۱)."""
    if size <= 0 or limit <= 0:
        return 1
    return max(1, math.ceil(size / limit))


def part_name(stem: str, index: int, total: int, ext: str, *, bytes_mode: bool = False) -> str:
    """نام خوانا برای هر پارت؛ بدون کاراکتر غیرمجاز."""
    base = human.safe_filename(stem or "file", 110) or "file"
    if bytes_mode:
        return human.safe_filename(f"{base}.part{index}{ext}", 150)
    return human.safe_filename(f"{base} (part {index} of {total}){ext}", 150)


def _video_like(path: Path, mime: str = "") -> bool:
    suffix = path.suffix.lower()
    if suffix in VIDEO_EXT:
        return True
    return (mime or "").startswith("video/")


async def split_file(
    source: Path,
    limit: int,
    workdir: Path,
    *,
    mime: str = "",
    cancel: asyncio.Event | None = None,
) -> SplitPlan:
    """فایل را (در صورت نیاز) تقسیم می‌کند و پارت‌ها را برمی‌گرداند."""
    size = source.stat().st_size
    if limit <= 0 or size <= limit:
        return SplitPlan([source], "none")

    # هر پارت با حاشیهٔ امن ساخته می‌شود تا سربار کانتینر/فایل از سقف تلگرام رد نشود.
    cap = usable_bytes(limit)
    parts_needed = planned_parts(size, cap)
    if parts_needed > MAX_PARTS:
        raise errors.SplitTooMany(parts=parts_needed, max=MAX_PARTS)

    # فایل اصلی + پارت‌ها باید همزمان جا شوند.
    free = shutil.disk_usage(workdir).free
    if free < int(size * 1.25):
        raise errors.NotEnoughSpace(
            need=human.human_bytes(int(size * 1.25)),
            free=human.human_bytes(free),
        )

    if _video_like(source, mime):
        try:
            parts = await _split_video(source, cap, workdir, parts_needed, cancel)
        except errors.JobCancelled:
            raise
        except errors.LeechError:
            raise
        except Exception as exc:  # noqa: BLE001 — خطای غیرمنتظرهٔ ffmpeg
            raise errors.SplitFailed(str(exc)) from exc
        if parts:
            return SplitPlan(parts, "video")
        raise errors.SplitFailed("no output")

    parts = _split_bytes(source, cap, workdir, cancel)
    return SplitPlan(parts, "bytes")


async def _probe_duration(path: Path) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    try:
        return float((out or b"").decode("utf-8", "ignore").strip() or 0)
    except ValueError:
        return 0.0


async def _probe_vcodec(path: Path) -> str:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=nw=1:nk=1",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    return (out or b"").decode("utf-8", "ignore").strip().lower()


async def _split_video(
    source: Path,
    cap: int,
    workdir: Path,
    minimum_parts: int,
    cancel: asyncio.Event | None,
) -> list[Path]:
    """برش ویدیو؛ اول بدون رمزگذاری، در صورت نیاز با رمزگذاری مجدد."""
    duration = await _probe_duration(source)
    if duration <= 0:
        raise errors.SplitFailed("duration unknown")

    # فقط H.264 را می‌توان بدون رمزگذاری در MP4 برش داد و مطمئن بود تلگرام
    # آن را به‌صورت ویدیوی قابل‌پخش نشان می‌دهد؛ بقیهٔ کدک‌ها دوباره کد می‌شوند.
    if await _probe_vcodec(source) == "h264":
        try:
            return await _segment_copy(
                source, cap, workdir, minimum_parts, duration, ".mp4", cancel
            )
        except errors.JobCancelled:
            raise
        except errors.SplitFailed:
            pass

    # keyframeهای خیلی دور یا کدک ناسازگار: با رمزگذاری مجدد برش می‌زنیم.
    return await _segment_reencode(
        source, cap, workdir, minimum_parts, duration, cancel
    )


def _cleanup(pattern: Path) -> None:
    for old in pattern.parent.glob(pattern.name.replace("%03d", "*")):
        old.unlink(missing_ok=True)


def _finalize(produced: list[Path], workdir: Path, stem: str, out_ext: str) -> list[Path]:
    total_parts = len(produced)
    parts: list[Path] = []
    for index, path in enumerate(produced, start=1):
        target = workdir / part_name(stem, index, total_parts, out_ext)
        path.replace(target)
        parts.append(target)
    return parts


async def _segment_copy(
    source: Path,
    cap: int,
    workdir: Path,
    minimum_parts: int,
    duration: float,
    out_ext: str,
    cancel: asyncio.Event | None,
) -> list[Path]:
    """برش بدون رمزگذاری مجدد؛ هر پارت یک ویدیوی مستقل است."""
    segment_format = out_ext.lstrip(".")
    stem = source.stem

    for attempt in range(3):
        if cancel is not None and cancel.is_set():
            raise errors.JobCancelled()
        total = minimum_parts + attempt
        # هر پارت کمی کوتاه‌تر از سهم دقیق تا keyframe بعدی از سقف رد نشود.
        per_part = max(1.0, duration / total * 0.97)
        pattern = workdir / f"split-{attempt}-%03d{out_ext}"
        _cleanup(pattern)

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_format",
            segment_format,
            "-segment_time",
            f"{per_part:.3f}",
            "-reset_timestamps",
            "1",
            str(pattern),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            await proc.wait()
        except FileNotFoundError as exc:
            raise errors.SplitFailed("ffmpeg missing") from exc

        produced = sorted(workdir.glob(pattern.name.replace("%03d", "*")))
        if proc.returncode == 0 and len(produced) >= 2 and all(
            p.stat().st_size <= cap for p in produced
        ):
            return _finalize(produced, workdir, stem, out_ext)

        # keyframe بعدی پارت را از سقف رد کرد؛ با پارت بیشتر دوباره تلاش کن.
        _cleanup(pattern)

    raise errors.SplitFailed("could not fit under the limit")


async def _segment_reencode(
    source: Path,
    cap: int,
    workdir: Path,
    minimum_parts: int,
    duration: float,
    cancel: asyncio.Event | None,
) -> list[Path]:
    """برش با رمزگذاری مجدد؛ برای ویدیوهایی که keyframe کافی برای copy ندارند.

    خروجی همیشه MP4 با کدک H.264/AAC است تا تلگرام آن را به‌عنوان ویدیوی
    قابل‌پخش بشناسد. بیت‌ریت از حجم مجاز هر پارت محاسبه می‌شود.
    """
    out_ext = ".mp4"
    stem = source.stem
    total = max(2, minimum_parts)

    for attempt in range(3):
        if cancel is not None and cancel.is_set():
            raise errors.JobCancelled()
        per_part = max(1.0, duration / total * 0.98)
        target_bps = int(cap * 8 * 0.82 / per_part)
        video_bps = target_bps - 96_000  # جای صدا
        if video_bps < 120_000:
            total += 1
            continue

        pattern = workdir / f"reenc-{attempt}-%03d{out_ext}"
        _cleanup(pattern)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-b:v",
            str(video_bps),
            "-maxrate",
            str(int(video_bps * 1.15)),
            "-bufsize",
            str(video_bps * 2),
            "-force_key_frames",
            f"expr:gte(t,n_forced*{per_part:.3f})",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-f",
            "segment",
            "-segment_format",
            "mp4",
            "-segment_time",
            f"{per_part:.3f}",
            "-reset_timestamps",
            "1",
            str(pattern),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            await proc.wait()
        except FileNotFoundError as exc:
            raise errors.SplitFailed("ffmpeg missing") from exc

        produced = sorted(workdir.glob(pattern.name.replace("%03d", "*")))
        if proc.returncode == 0 and len(produced) >= 2 and all(
            p.stat().st_size <= cap for p in produced
        ):
            return _finalize(produced, workdir, stem, out_ext)

        _cleanup(pattern)
        total += 1

    raise errors.SplitFailed("could not fit under the limit")


def _split_bytes(
    source: Path,
    cap: int,
    workdir: Path,
    cancel: asyncio.Event | None,
) -> list[Path]:
    """تقسیم خام بایتی؛ مناسب فایل‌های غیرویدیویی (zip، iso، …)."""
    size = source.stat().st_size
    chunk = max(1, cap)
    total = math.ceil(size / chunk)
    if total > MAX_PARTS:
        raise errors.SplitTooMany(parts=total, max=MAX_PARTS)

    stem, ext = source.stem, source.suffix
    parts: list[Path] = []
    with source.open("rb") as reader:
        for index in range(1, total + 1):
            if cancel is not None and cancel.is_set():
                raise errors.JobCancelled()
            target = workdir / part_name(stem, index, total, ext, bytes_mode=True)
            remaining = min(chunk, size - (index - 1) * chunk)
            with target.open("wb") as writer:
                while remaining > 0:
                    block = reader.read(min(_READ_CHUNK, remaining))
                    if not block:
                        break
                    writer.write(block)
                    remaining -= len(block)
            parts.append(target)
    return parts
