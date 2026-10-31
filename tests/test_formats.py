from app.services.formats import (
    AUDIO_M4A,
    AUDIO_MP3,
    all_options,
    build_options,
    find_option,
    video_selector,
)


def fmt(height, ext="mp4", vcodec="avc1.4d401f", tbr=1000, fps=30, **kw):
    data = {
        "height": height,
        "ext": ext,
        "vcodec": vcodec,
        "acodec": "none",
        "tbr": tbr,
        "fps": fps,
        "format_id": f"v{height}",
    }
    data.update(kw)
    return data


def test_build_options_picks_best_per_height():
    formats = [
        fmt(1080, tbr=2000),
        fmt(1080, tbr=5000),           # بهتر
        fmt(720, tbr=1500),
        fmt(360, tbr=500),
        {"height": None, "vcodec": "avc1", "ext": "mp4"},  # بی‌ارتفاع → نادیده
        {"height": 480, "vcodec": "none", "ext": "m4a"},   # فقط صدا → نادیده
    ]
    options = build_options(formats)
    assert [o.height for o in options] == [360, 720, 1080]
    assert options[-1].label == "1080p MP4"
    assert "height<=1080" in options[-1].selector


def test_build_options_prefers_mp4_over_webm():
    formats = [fmt(720, ext="webm", vcodec="vp9", tbr=9000), fmt(720, ext="mp4", tbr=1000)]
    options = build_options(formats)
    assert options[0].selector == video_selector(720)
    assert options[0].ext == "mp4"


def test_build_options_caps_count():
    formats = [fmt(h) for h in (144, 240, 360, 480, 720, 1080, 1440, 2160)]
    options = build_options(formats)
    assert len(options) <= 7
    assert options[-1].height == 2160


def test_build_options_max_height():
    formats = [fmt(480), fmt(1080), fmt(2160)]
    options = build_options(formats, max_height=1080)
    assert [o.height for o in options] == [480, 1080]


def test_build_options_fallback_when_no_heights():
    options = build_options([])
    assert len(options) == 1
    assert options[0].code == "best"


def test_fps_suffix():
    options = build_options([fmt(1080, fps=60)])
    assert options[0].label == "1080p60 MP4"


def test_all_options_includes_audio():
    options = all_options([fmt(720)])
    codes = {(o.kind, o.code) for o in options}
    assert ("video", "720") in codes
    assert ("audio", "mp3") in codes
    assert ("audio", "m4a") in codes


def test_find_option_exact_and_fallback():
    options = all_options([fmt(480), fmt(720)])
    assert find_option(options, "video", "720").height == 720
    assert find_option(options, "video", "1080").height == 720  # نزدیک‌ترین پایین‌تر
    assert find_option(options, "audio", "mp3") is AUDIO_MP3
    assert find_option(options, "audio", "m4a") is AUDIO_M4A
    assert find_option(options, "video", "nope") is None
