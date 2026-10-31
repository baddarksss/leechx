"""منوی کیفیت با تفکیک کدک و حجم فایل (Eporner: ۵ MP4 + ۵ AV1)."""
from __future__ import annotations

from app.services.downloader import (
    _variant_filename,
    fallback_title,
    is_eporner_extractor,
    with_av1_variants,
)
from app.services.formats import FormatOption, all_options, build_options, find_option


def eporner_formats() -> list[dict]:
    """همان ساختاری که yt-dlp برای Eporner برمی‌گرداند (بدون حجم و کدک)."""
    return [
        {
            "format_id": fid,
            "url": f"https://cdn.example/{height}-{fid}.mp4",
            "ext": "mp4",
            "vcodec": None,
            "acodec": None,
            "height": height,
            "width": height * 16 // 9,
            "fps": 30,
        }
        for fid, height in (
            ("240p", 240),
            ("360p", 360),
            ("480p", 480),
            ("720p_HD", 720),
            ("1080p_HD", 1080),
        )
    ]


def test_eporner_detection():
    assert is_eporner_extractor("Eporner")
    assert is_eporner_extractor("eporner")
    assert not is_eporner_extractor("Youtube")
    assert not is_eporner_extractor(None)


def test_fallback_title_uses_eporner_slug():
    url = "https://www.eporner.com/video-09fBSkYy45O/woman-anal-foot-fucking/"
    assert fallback_title(url, "Untitled") == "Woman anal foot fucking"
    assert fallback_title(url, "Real title") == "Real title"
    assert fallback_title("https://example.com/x", "") == "media"


def test_av1_variants_are_synthesized_for_every_height():
    formats = with_av1_variants(eporner_formats())
    av1 = [f for f in formats if f["format_id"].endswith("-av1")]
    assert [f["height"] for f in av1] == [240, 360, 480, 720, 1080]
    assert all(f["url"].endswith("-av1.mp4") for f in av1)
    assert all(f["vcodec"].startswith("av01") for f in av1)
    assert all(f.get("synthetic") for f in av1)
    assert len(formats) == 10


def test_av1_variants_skip_duplicates_and_non_mp4():
    formats = with_av1_variants([
        {"format_id": "720", "url": "https://x/a.mp4", "height": 720, "vcodec": "avc1"},
        {"format_id": "1080-av1", "url": "https://x/b-av1.mp4", "height": 1080,
         "vcodec": "av01.0.08M.08"},
        {"format_id": "hls", "url": "https://x/playlist.m3u8", "height": 480,
         "vcodec": None},
    ])
    heights = sorted(f["height"] for f in formats)
    assert heights == [480, 720, 720, 1080]  # فقط برای 720 نسخهٔ AV1 ساخته شد
    assert not any(f["format_id"] == "hls-av1" for f in formats)
    assert len([f for f in formats if f["format_id"] == "720-av1"]) == 1


def test_split_menu_shows_codec_size_and_exact_selector():
    formats = with_av1_variants(eporner_formats())
    for fmt in formats:
        fmt["filesize"] = fmt["height"] * 1000
    options = build_options(formats, split_codecs=True)
    assert len(options) == 10
    by_code = {o.code: o for o in options}
    assert by_code["1080"].label == "1080p MP4 · 1 MB"
    assert by_code["1080-av1"].label == "1080p AV1 · 1 MB"
    assert by_code["1080"].selector == "1080p_HD"
    assert by_code["1080-av1"].selector == "1080p_HD-av1"
    # فقط نسخهٔ ساخته‌شده آدرس مستقیم دارد؛ MP4 با استخراج دوبارهٔ yt-dlp می‌آید.
    assert by_code["1080-av1"].media_url.endswith("-av1.mp4")
    assert by_code["1080"].media_url == ""


def test_split_menu_order_and_audio():
    options = all_options(with_av1_variants(eporner_formats()), split_codecs=True)
    videos = [o for o in options if o.kind == "video"]
    assert [(o.height, o.codec) for o in videos[:4]] == [
        (240, "mp4"), (240, "av1"), (360, "mp4"), (360, "av1"),
    ]
    assert [o.kind for o in options[-2:]] == ["audio", "audio"]
    assert find_option(options, "video", "1080-av1").height == 1080


def test_size_label_only_when_known():
    options = build_options(eporner_formats())
    assert [o.label for o in options] == [
        "240p", "360p", "480p", "720p", "1080p",
    ]
    formats = eporner_formats()
    formats[0]["filesize"] = 4_887_771
    assert build_options(formats)[0].label == "240p · 4.7 MB"


def test_variant_filename_keeps_title_and_codec():
    option = FormatOption(
        kind="video", code="1080-av1", label="1080p AV1", selector="1080p_HD-av1",
        height=1080, ext="mp4", codec="av1",
    )
    name = _variant_filename("Some: Title/Here", option)
    assert name == "Some_ Title_Here [1080p AV1].mp4"
