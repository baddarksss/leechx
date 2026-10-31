"""تست‌های HLS/Cloudflare: باز کردن پک JS، پلی‌لیست‌ها و منوی کیفیت."""
from __future__ import annotations

from app.core import errors
from app.services.downloader import (
    _hls_formats,
    hls_links,
    hls_master_variants,
    hls_segments,
    iframe_sources,
    looks_like_cf_block,
    pick_hls_variant,
    unpack_packed_js,
)
from app.services.formats import all_options

# نمونهٔ کوچک Dean-Edwards packer: base=10 و چهار کلمه.
PACKED = (
    "eval(function(p,a,c,k,e,d){e=function(c){return c};"
    "if(!''.replace(/^/,String)){while(c--){d[c]=k[c]||c}"
    "k=[function(e){return d[e]}];e=function(){return'\\\\w+'};c=1};"
    "while(c--){if(k[c]){p=p.replace(new RegExp('\\\\b'+e(c)+'\\\\b','g'),k[c])}}"
    "return p}('0 1 = \"2://3.com/a.mp4\";',10,4,'var|x|https|example'.split('|'),0,{}))"
)

MASTER = """#EXTM3U
#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=856964,RESOLUTION=852x480,FRAME-RATE=29.97,CODECS="avc1.4d401f,mp4a.40.2"
index-f1-v1-a1.txt
#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=5113000,RESOLUTION=3840x2160,CODECS="avc1.640033,mp4a.40.2"
/sub/index-f4-v1-a1.txt
"""

VARIANT = """#EXTM3U
#EXT-X-TARGETDURATION:10
#EXTINF:10.0,
seg-1.woff2
#EXTINF:10.0,
/sub/seg-2.woff2
#EXT-X-ENDLIST
"""


def test_unpack_packed_js_decodes_payload():
    decoded = unpack_packed_js(PACKED)
    assert decoded == 'var x = "https://example.com/a.mp4";'


def test_unpack_returns_none_for_regular_html():
    assert unpack_packed_js("<html>hello</html>") is None


def test_hls_links_plain_and_relative():
    html = '<script>var cfg = {"hls3": "https://cdn.example/master.txt"};</script>'
    assert hls_links(html) == {"hls3": "https://cdn.example/master.txt"}
    assert hls_links('var cfg = {"hls3": "/hls/master.txt"};', "https://a.example/x/") == {
        "hls3": "https://a.example/hls/master.txt"
    }


def test_iframe_sources_filters_ads_and_data_uris():
    html = (
        '<iframe src="javascript:false"></iframe>'
        '<iframe src="data:text/html;base64,AAAA"></iframe>'
        '<iframe src="https://www.google.com/recaptcha/api2/anchor?k=1"></iframe>'
        '<iframe src="//embed.example/v/1"></iframe>'
        '<iframe src="https://embed.example/v/1"></iframe>'
    )
    assert iframe_sources(html) == ["//embed.example/v/1", "https://embed.example/v/1"]


def test_master_variants_parse_heights_and_urls():
    variants = hls_master_variants(MASTER, "https://cdn.example/path/master.txt")
    assert [v["height"] for v in variants] == [480, 2160]
    assert variants[0]["url"] == "https://cdn.example/path/index-f1-v1-a1.txt"
    assert variants[1]["url"] == "https://cdn.example/sub/index-f4-v1-a1.txt"
    assert variants[0]["fps"] == 29
    assert variants[1]["width"] == 3840
    assert variants[1]["codecs"] == "avc1.640033,mp4a.40.2"


def test_segments_skip_comments_and_resolve():
    segments = hls_segments(VARIANT, "https://cdn.example/path/index-f4.txt")
    assert segments == [
        "https://cdn.example/path/seg-1.woff2",
        "https://cdn.example/sub/seg-2.woff2",
    ]


def test_pick_variant_exact_lower_and_best():
    variants = hls_master_variants(MASTER, "https://cdn.example/master.txt")
    assert pick_hls_variant(variants, 2160)["height"] == 2160
    assert pick_hls_variant(variants, 1080)["height"] == 480
    assert pick_hls_variant(variants, 0)["height"] == 2160


def test_cf_detection():
    assert looks_like_cf_block(errors.AccessDenied("403"))
    assert looks_like_cf_block(errors.UnsupportedUrl("HTTP Error 403: Forbidden"))
    assert looks_like_cf_block(errors.UnsupportedUrl("Just a moment..."))
    assert not looks_like_cf_block(errors.ResourceNotFound("404"))


def test_hls_formats_and_quality_menu():
    variants = hls_master_variants(MASTER, "https://cdn.example/master.txt")
    formats = _hls_formats(variants)
    assert all(fmt["hls"] is True for fmt in formats)
    assert formats[0]["vcodec"] == "avc1.4d401f"
    assert formats[1]["acodec"] == "mp4a.40.2"

    options = all_options(formats)
    video = [opt for opt in options if opt.kind == "video"]
    assert [opt.code for opt in video] == ["480", "2160"]
    assert video[1].label == "2160p MP4"
    assert video[1].hls is True
    assert video[1].selector == "hls-2160"
    # صدا هم باید برای HLS در دسترس باشد (از بهترین واریانت استخراج می‌شود)
    assert [opt.code for opt in options if opt.kind == "audio"] == ["mp3", "m4a"]
