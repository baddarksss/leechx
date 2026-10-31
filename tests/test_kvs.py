"""تست‌های KVS: پیدا کردن آبجکت فلش‌وارس با نام تصادفی و ساخت فرمت‌ها."""
from __future__ import annotations

from app.services.downloader import is_kvs_error, parse_kvs
from app.services.formats import all_options, build_options

HTML = """<!doctype html><html><head>
<title>Fallback Title</title>
<meta property="og:image" content="https://kvs.example/contents/42/preview.jpg"/>
<script type="text/javascript">
var t9a8b7c6d5 = {
    video_id: '42',
    video_title: 'My Test Video',
    license_code: '$452444814926944',
    rnd: '1793442477',
    video_url: 'function/0/https://kvs.example/get_file/53/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/1000/42/42.mp4/',
    video_url_text: '720p',
    preview_url: 'https://kvs.example/contents/42/preview.jpg',
    postfix: '.mp4'
};
</script></head>
<body><span>Duration: <em>01:02</em></span></body></html>"""

URL = "https://kvs.example/video/42/my-test-video/"


def test_kvs_error_detection():
    assert is_kvs_error("ERROR: [generic] Unable to extract flashvars")
    assert is_kvs_error("Unable to extract KVS player")
    assert not is_kvs_error("HTTP Error 404")


def test_parse_kvs_builds_real_format_from_random_var():
    info = parse_kvs(HTML, URL)
    assert info is not None
    assert info.title == "My Test Video"
    assert info.duration == 62
    assert info.extractor == "KVS"
    assert info.thumbnail == "https://kvs.example/contents/42/preview.jpg"
    assert len(info.formats) == 1
    fmt = info.formats[0]
    assert fmt["url"].startswith("https://kvs.example/get_file/53/")
    assert fmt["url"].endswith(".mp4/")
    assert fmt["height"] == 720
    assert fmt["ext"] == "mp4"
    assert fmt["kvs"] is True
    assert fmt["http_headers"]["Referer"] == URL


def test_parse_kvs_returns_none_for_regular_pages():
    assert parse_kvs("<html><body>hello</body></html>", URL) is None


def test_kvs_menu_marks_direct_download_with_size():
    info = parse_kvs(HTML, URL)
    info.formats[0]["filesize"] = 10 * 1024 * 1024
    options = all_options(info.formats)
    video = [o for o in options if o.kind == "video"][0]
    assert video.code == "720"
    assert video.label == "720p MP4 · 10 MB"
    assert video.kvs is True
    assert video.media_url.startswith("https://kvs.example/get_file/")
    assert video.selector == "720p"


def test_kvs_without_height_gets_best_label():
    info = parse_kvs(HTML.replace("video_url_text: '720p',", ""), URL)
    options = build_options(info.formats)
    assert options[0].code == "best"
    assert options[0].label == "Best MP4"
    assert options[0].kvs is True
    assert options[0].selector == "video_url"


def test_unknown_height_quality_is_not_dropped():
    """سایتی مثل fpo.xxx کیفیت LQ را بدون ارتفاع می‌دهد؛ نباید حذف شود."""
    formats = [
        {"format_id": "HQ", "height": 720, "ext": "mp4", "vcodec": None, "url": "https://x/720.mp4"},
        {"format_id": "LQ", "height": None, "ext": "mp4", "vcodec": None, "url": "https://x/lq.mp4"},
    ]
    options = build_options(formats)
    assert [o.code for o in options] == ["lq", "720"]
    assert options[0].label == "LQ MP4"
    assert options[0].selector == "LQ"
    assert options[1].label == "HQ 720p MP4"


def test_two_named_formats_without_heights_get_two_buttons():
    formats = [
        {"format_id": "HQ", "ext": "mp4", "vcodec": None, "url": "https://x/hq.mp4", "filesize": 20_000_000},
        {"format_id": "LQ", "ext": "mp4", "vcodec": None, "url": "https://x/lq.mp4", "filesize": 8_000_000},
    ]
    options = build_options(formats)
    assert [o.label for o in options] == ["LQ MP4 · 7.6 MB", "HQ MP4 · 19.1 MB"]
