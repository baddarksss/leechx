"""Site-specific regressions: VK, TNAFlix locales, missav manifests, sizes."""
from __future__ import annotations

from app.core import errors
from app.services.downloader import (
    _CAPTCHA_HOST,
    _hls_formats,
    _is_manifest,
    extractor_url,
    hls_manifest_variants,
    infer_heights,
    m3u8_candidates,
    vk_video_ref,
    vk_video_url,
    vk_wall_url,
)

# A tiny Dean-Edwards packed payload; base 10, four words.
PACKED_M3U8 = (
    "eval(function(p,a,c,k,e,d){e=function(c){return c};"
    "if(!''.replace(/^/,String)){while(c--){d[c]=k[c]||c}"
    "k=[function(e){return d[e]}];e=function(){return'\\\\w+'};c=1};"
    "while(c--){if(k[c]){p=p.replace(new RegExp('\\\\b'+e(c)+'\\\\b','g'),k[c])}}"
    "return p}('0://1.2/3/4/5.6',10,7,"
    "'https|surrit|com|playlist|apple|master|m3u8'.split('|'),0,{}))"
)


def test_extractor_url_normalizes_vk_and_tnaflix():
    assert extractor_url("https://vk.ru/wall-229729912_5412") == "https://vk.com/wall-229729912_5412"
    assert (
        extractor_url(
            "https://www.tnaflix.com/es/amateur-porn/Thief/video24309806"
        )
        == "https://www.tnaflix.com/amateur-porn/Thief/video24309806"
    )
    # Fragment is dropped for CF-solved pages.
    assert extractor_url("https://missav.ws/en/adn-812#c005a305") == "https://missav.ws/en/adn-812"


def test_vk_paths_and_og_reference():
    assert vk_wall_url("https://vk.ru/wall-229729912_5412") == "https://vk.com/wall-229729912_5412"
    assert vk_video_url("https://m.vk.com/video-1_2?list=abc") == "https://vk.com/video-1_2"
    html = (
        '<meta property="og:video" content="https://vk.ru/video_ext.php?'
        'oid=-229729912&amp;id=456240027&amp;hash=401927cd2b8357d5f4"/>'
    )
    assert vk_video_ref(html) == ("-229729912", "456240027")
    assert vk_video_ref('<div id="video-229729912_456240027"></div>') == (
        "-229729912",
        "456240027",
    )
    assert vk_video_ref("<html>nothing</html>") is None


def test_infer_heights_from_url_and_notes():
    formats = [
        {"url": "https://cdn.example/clip-1080p.mp4", "vcodec": "avc1"},
        {"url": "https://cdn.example/x.mp4", "format_note": "720p", "vcodec": "avc1"},
        {"url": "https://cdn.example/y.mp4", "vcodec": "none"},
        {"url": "https://cdn.example/already.mp4", "height": 480, "vcodec": "avc1"},
    ]
    infer_heights(formats)
    assert formats[0]["height"] == 1080
    assert formats[0]["width"] == 1920
    assert formats[1]["height"] == 720
    assert "height" not in formats[2]  # audio-only stays untouched
    assert formats[3]["height"] == 480


def test_m3u8_candidates_reads_packed_js_and_prefers_playlist():
    html = (
        '<script>var x = "https://cdn.example/a/master.m3u8";</script>'
        + PACKED_M3U8
        + "<script>var y = 'https://cdn.example/other.m3u8';</script>"
    )
    found = m3u8_candidates(html)
    assert "https://surrit.com/playlist/apple/master.m3u8" in found
    assert "https://cdn.example/a/master.m3u8" in found
    assert "https://cdn.example/other.m3u8" in found
    assert found[0] == "https://surrit.com/playlist/apple/master.m3u8"


def test_media_playlist_becomes_single_variant():
    media = "#EXTM3U\n#EXTINF:10.0,\nseg1.txt\n#EXTINF:5.5,\nseg2.txt\n"
    variants = hls_manifest_variants(media, "https://cdn.example/playlist.m3u8")
    assert len(variants) == 1
    assert variants[0]["url"] == "https://cdn.example/playlist.m3u8"
    assert hls_manifest_variants("#EXTM3U\n", "https://cdn.example/x") == []


def test_hls_formats_keep_approximate_size():
    formats = _hls_formats(
        [
            {
                "url": "https://cdn.example/720p.txt",
                "height": 720,
                "width": 1280,
                "fps": 30,
                "bandwidth": 2500000,
                "codecs": "avc1.4d401f,mp4a.40.2",
                "filesize_approx": 123456,
            }
        ]
    )
    assert formats[0]["filesize_approx"] == 123456


def test_is_manifest_detects_protocol_and_extension():
    assert _is_manifest({"url": "https://cdn.example/a.m3u8?token=1"})
    assert _is_manifest({"url": "https://cdn.example/a", "protocol": "m3u8_native"})
    assert _is_manifest({"url": "https://cdn.example/a.mpd"})
    assert not _is_manifest({"url": "https://cdn.example/a.mp4"})


def test_captcha_walled_player_is_detected():
    dood = '<div class="item" title="hosted on doodstream"><span>7.8 GB</span></div>'
    assert _CAPTCHA_HOST.search(dood)
    assert _CAPTCHA_HOST.search('<iframe src="https://playmogo.com/e/la16sn5bm9cv/">')
    assert _CAPTCHA_HOST.search('<a href="https://x.tld/pass_md5/abc/def">')
    assert not _CAPTCHA_HOST.search('<div title="hosted on rapidgator"></div>')
    assert errors.CaptchaWall().key == "captcha_wall"
