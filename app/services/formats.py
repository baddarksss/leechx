"""گروه‌بندی فرمت‌های yt-dlp به گزینه‌های قابل‌نمایش برای کاربر.

ورودی: لیست خام ``info["formats"]`` از yt-dlp.
خروجی: چند ``FormatOption`` مرتب‌شده (ویدیو از کم به زیاد، بعد صدا).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core import human

MAX_VIDEO_OPTIONS = 7
# وقتی منو بر اساس کدک جدا می‌شود (مثل Eporner با ۵ نسخهٔ MP4 و ۵ نسخهٔ AV1)
# باید جای بیشتری برای گزینه‌های ویدیویی باشد.
MAX_SPLIT_VIDEO_OPTIONS = 12


@dataclass(frozen=True)
class FormatOption:
    kind: str          # video | audio
    code: str          # "1080" | "1080-av1" | "mp3" | "m4a"
    label: str         # "1080p MP4 · 78.5 MB" | "MP3 192k"
    selector: str      # انتخاب‌گر yt-dlp
    height: int = 0
    ext: str = ""
    filesize: int | None = None
    fps: int = 0
    codec: str = ""    # "mp4" | "av1" | ... (برای تفکیک کدک‌ها)
    # اگر پر باشد، دانلود مستقیم از همین آدرس انجام می‌شود (نسخه‌هایی که
    # اکسترکتور yt-dlp دوباره پیدا نمی‌کند، مثل AV1 اپورنر).
    media_url: str = ""
    # KVS: آدرس امضاشده کوتاه‌عمر است؛ هنگام دانلود دوباره ساخته می‌شود.
    kvs: bool = False


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


def _codec_name(fmt: dict) -> str:
    """نام کوتاه کدک برای برچسب دکمه (MP4 / AV1 / WEBM…)."""
    vcodec = (fmt.get("vcodec") or "").lower()
    if vcodec.startswith(("av01", "av1")):
        return "AV1"
    if vcodec.startswith(("avc", "h264")):
        return "MP4"
    ext = (fmt.get("ext") or "").lower()
    if ext == "mp4":
        return "MP4"
    return ext.upper()


def _label_of(height: int, fps: int, filesize: int | None, codec: str = "") -> str:
    """مثلاً ``1080p`` یا ``1080p MP4 · 78.5 MB``."""
    label = f"{height}p" + (f"{fps}" if fps >= 50 else "")
    if codec:
        label = f"{label} {codec}"
    if filesize:
        label = f"{label} · {human.human_bytes(filesize)}"
    return label


def _fps_of(fmt: dict) -> int:
    try:
        return int(fmt.get("fps") or 0)
    except (TypeError, ValueError):
        return 0


# شناسه‌هایی که خود اسم فایل/کیفیت نیستند و برچسب «Best» برایشان بهتر است
_GENERIC_IDS = re.compile(r"(?:video_url|alt_url\d*|http[_-]?\d+|hls[_-]?\d*|dash)", re.I)


def _is_video_fmt(fmt: dict) -> bool:
    """آیا این یک فرمت ویدیویی قابل نمایش است؟ (صدا/مانیفست نه)"""
    if not isinstance(fmt, dict):
        return False
    if str(fmt.get("vcodec") or "").lower() == "none":
        return False
    return fmt.get("ext") not in (None, "none", "mhtml")


def _height_of(fmt: dict) -> int:
    try:
        return int(fmt.get("height") or 0)
    except (TypeError, ValueError):
        return 0


def _alt_option(fmt: dict, used: set[str]) -> FormatOption | None:
    """گزینه برای فرمتی که ارتفاع ندارد ولی کیفیتش نام‌دار است (مثل LQ/HQ)."""
    raw = str(fmt.get("format_note") or fmt.get("format_id") or "").strip()
    if not raw:
        return None
    name = "Best" if _GENERIC_IDS.fullmatch(raw) else raw
    codec = _codec_name(fmt)
    filesize = _size_of(fmt)
    label = name + (f" {codec}" if codec else "")
    if filesize:
        label += f" · {human.human_bytes(filesize)}"
    code = re.sub(r"[^a-z0-9]+", "", name.lower()) or "alt"
    while code in used:
        code += "x"
    used.add(code)
    return FormatOption(
        kind="video",
        code=code,
        label=label,
        selector=str(fmt.get("format_id") or "bv*+ba/b"),
        height=_height_of(fmt),
        ext=(fmt.get("ext") or "mp4").lower(),
        filesize=filesize,
        fps=_fps_of(fmt),
        codec=codec.lower(),
        kvs=bool(fmt.get("kvs")),
        media_url=(fmt.get("url") or "") if (fmt.get("synthetic") or fmt.get("kvs")) else "",
    )


def build_options(
    formats: list[dict] | None,
    max_height: int = 0,
    split_codecs: bool = False,
) -> list[FormatOption]:
    """بهترین فرمت هر ارتفاع را انتخاب و به گزینه تبدیل می‌کند.

    با ``split_codecs=True`` هر کدک (مثلاً MP4 و AV1) جداگانه نمایش داده می‌شود
    تا کاربر بداند دقیقاً چه چیزی دانلود می‌کند.
    """
    formats = formats or []
    if split_codecs:
        return _build_split_options(formats, max_height)

    best: dict[int, dict] = {}

    for fmt in formats:
        if not _is_video_fmt(fmt):
            continue
        height = _height_of(fmt)
        if height <= 0:
            continue
        if max_height and height > max_height:
            continue
        current = best.get(height)
        if current is None or _rank(fmt) > _rank(current):
            best[height] = fmt

    used: set[str] = set()
    options: list[FormatOption] = []

    if not best:
        # هیچ ارتفاعی نداریم: هر کیفیت نام‌دار (LQ/HQ/Best…) یک دکمه جدا شود.
        for fmt in formats:
            if not _is_video_fmt(fmt):
                continue
            option = _alt_option(fmt, used)
            if option is not None:
                options.append(option)
        if options:
            options.sort(key=lambda o: (o.height, o.filesize or 0))
            return options[-MAX_VIDEO_OPTIONS:]
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
    for height in heights:
        fmt = best[height]
        fps = _fps_of(fmt)
        filesize = _size_of(fmt)
        kvs = bool(fmt.get("kvs"))
        label = _label_of(height, fps, filesize, _codec_name(fmt))
        # اگر سایت خودش نسخه را نام‌گذاری کرده (HQ/LQ...) همان نام هم بیاید.
        tag = str(fmt.get("format_id") or "").strip().upper()
        if tag in {"LQ", "HQ", "SD", "HD", "FHD", "UHD"} and tag.lower() not in label.lower():
            label = f"{tag} {label}"
        options.append(
            FormatOption(
                kind="video",
                code=str(height),
                label=label,
                # KVS باید با همان کلید فرمت و مسیر مستقیم دانلود شود.
                selector=str(fmt.get("format_id")) if kvs else video_selector(height),
                height=height,
                ext="mp4",
                filesize=filesize,
                fps=fps,
                codec=_codec_name(fmt).lower() or "mp4",
                kvs=kvs,
                media_url=(fmt.get("url") or "") if (fmt.get("synthetic") or kvs) else "",
            )
        )

    # کیفیت‌های بی‌ارتفاع (مثل LQ سایت‌های KVS) نباید گم شوند.
    used = {o.code for o in options}
    known_urls = {str(fmt.get("url")) for fmt in best.values() if fmt.get("url")}
    extras: list[FormatOption] = []
    for fmt in formats:
        if not _is_video_fmt(fmt) or _height_of(fmt) > 0:
            continue
        if str(fmt.get("url") or "") in known_urls:
            continue
        option = _alt_option(fmt, used)
        if option is not None:
            extras.append(option)
    if extras:
        extras.sort(key=lambda o: (o.height, o.filesize or 0))
        options = extras + options
    return options[-MAX_VIDEO_OPTIONS:]


def _build_split_options(formats: list[dict], max_height: int) -> list[FormatOption]:
    """یک گزینه برای هر ترکیب ارتفاع+کدک؛ با انتخاب‌گر دقیق ``format_id``."""
    best: dict[tuple[int, str], dict] = {}
    for fmt in formats:
        if not isinstance(fmt, dict):
            continue
        if str(fmt.get("vcodec") or "").lower() == "none":
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
        codec = _codec_name(fmt) or "VIDEO"
        current = best.get((height, codec))
        if current is None or _rank(fmt) > _rank(current):
            best[(height, codec)] = fmt

    if not best:
        return build_options(formats, max_height)

    priority = {"MP4": 0, "AV1": 1}
    keys = sorted(best, key=lambda key: (key[0], priority.get(key[1], 2), key[1]))
    while len(keys) > MAX_SPLIT_VIDEO_OPTIONS:
        keys.pop(0)

    options: list[FormatOption] = []
    for height, codec in keys:
        fmt = best[(height, codec)]
        fps = _fps_of(fmt)
        filesize = _size_of(fmt)
        code = str(height) if codec == "MP4" else f"{height}-{codec.lower()}"
        options.append(
            FormatOption(
                kind="video",
                code=code,
                label=_label_of(height, fps, filesize, codec),
                # format_id دقیق، چون منوی جداگانه باید همان نسخهٔ کدک را بدهد.
                selector=str(fmt.get("format_id") or "") or video_selector(height),
                height=height,
                ext=(fmt.get("ext") or "mp4").lower(),
                filesize=filesize,
                fps=fps,
                codec=codec.lower(),
                # نسخه‌های ساخته‌شده (AV1) در استخراج دوم yt-dlp وجود ندارند.
                media_url=(fmt.get("url") or "")
                if (fmt.get("synthetic") or fmt.get("kvs")) else "",
                kvs=bool(fmt.get("kvs")),
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


def all_options(
    formats: list[dict] | None,
    max_height: int = 0,
    split_codecs: bool = False,
) -> list[FormatOption]:
    return [
        *build_options(formats, max_height, split_codecs=split_codecs),
        AUDIO_MP3,
        AUDIO_M4A,
    ]


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
