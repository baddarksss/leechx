"""گروه‌بندی فرمت‌های yt-dlp به گزینه‌های قابل‌نمایش برای کاربر.

ورودی: لیست خام ``info["formats"]`` از yt-dlp.
خروجی: چند ``FormatOption`` مرتب‌شده (ویدیو از کم به زیاد، بعد صدا).
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_VIDEO_OPTIONS = 7


@dataclass(frozen=True)
class FormatOption:
    kind: str          # video | audio
    code: str          # "1080" | "mp3" | "m4a"
    label: str         # "1080p" | "MP3 192k"
    selector: str      # انتخاب‌گر yt-dlp
    height: int = 0
    ext: str = ""
    filesize: int | None = None
    fps: int = 0


AUDIO_MP3 = FormatOption(
    kind="audio",
    code="mp3",
    label="MP3 192k",
    selector="ba[ext=m4a]/ba/b",
    ext="mp3",
)

AUDIO_M4A = FormatOption(
    kind="audio",
    code="m4a",
    label="M4A",
    selector="ba[ext=m4a]/ba/b",
    ext="m4a",
)


def video_selector(height: int) -> str:
    """انتخاب‌گر پایدار: اول mp4/h264 (سازگارترین)، بعد هر چیز دیگری."""
    return (
        f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
        f"bv*[height<={height}]+ba/"
        f"b[height<={height}]/"
        f"bv*[height<={height}]"
    )


def _size_of(fmt: dict) -> int | None:
    size = fmt.get("filesize") or fmt.get("filesize_approx")
    return int(size) if size else None


def _fps_of(fmt: dict) -> int:
    try:
        return int(fmt.get("fps") or 0)
    except (TypeError, ValueError):
        return 0


def build_options(formats: list[dict] | None, max_height: int = 0) -> list[FormatOption]:
    """بهترین فرمت هر ارتفاع را انتخاب و به گزینه تبدیل می‌کند."""
    formats = formats or []
    best: dict[int, dict] = {}

    for fmt in formats:
        if not isinstance(fmt, dict):
            continue
        if (fmt.get("vcodec") or "none") == "none":
            continue
        if fmt.get("ext") in ("mhtml", "none"):
            continue
        try:
            height = int(fmt.get("height") or 0)
        except (TypeError, ValueError):
            height = 0
        if height <= 0:
            continue
        if max_height and height > max_height:
            continue
        current = best.get(height)
        if current is None or _rank(fmt) > _rank(current):
            best[height] = fmt

    if not best:
        # بعضی سایت‌ها ارتفاع نمی‌دهند → یک گزینهٔ «بهترین کیفیت»
        return [
            FormatOption(
                kind="video",
                code="best",
                label="Best",
                selector="bv*+ba/b",
                height=0,
                ext="mp4",
            )
        ]

    heights = sorted(best)[-MAX_VIDEO_OPTIONS:]
    options: list[FormatOption] = []
    for height in heights:
        fmt = best[height]
        fps = _fps_of(fmt)
        label = f"{height}p" + (f"{fps}" if fps >= 50 else "")
        options.append(
            FormatOption(
                kind="video",
                code=str(height),
                label=label,
                selector=video_selector(height),
                height=height,
                ext="mp4",
                filesize=_size_of(fmt),
                fps=fps,
            )
        )
    return options


def _rank(fmt: dict) -> tuple:
    """mp4 و h264 بالاتر = سازگاری بیشتر با پخش تلگرام."""
    ext = (fmt.get("ext") or "").lower()
    vcodec = (fmt.get("vcodec") or "").lower()
    tbr = float(fmt.get("tbr") or 0)
    return (
        1 if ext == "mp4" else 0,
        1 if vcodec.startswith(("avc", "h264")) else 0,
        tbr,
    )


def all_options(formats: list[dict] | None, max_height: int = 0) -> list[FormatOption]:
    return [*build_options(formats, max_height), AUDIO_MP3, AUDIO_M4A]


def find_option(options: list[FormatOption], kind: str, code: str) -> FormatOption | None:
    for opt in options:
        if opt.kind == kind and opt.code == code:
            return opt
    # سازگاری: اگر ارتفاع درخواستی موجود نبود، نزدیک‌ترین پایین‌تر را بده
    if kind == "video" and code.isdigit():
        target = int(code)
        videos = sorted(
            (o for o in options if o.kind == "video" and o.height > 0),
            key=lambda o: o.height,
            reverse=True,
        )
        for opt in videos:
            if opt.height <= target:
                return opt
    return None
