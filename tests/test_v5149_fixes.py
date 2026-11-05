"""Regressions for v5.14.9: private cache with covers, KVS qualities, HLS embeds."""
from __future__ import annotations

from app.services.downloader import (
    MediaInfo,
    hls_master_from_player,
    looks_like_kvs_formats,
    parse_kvs,
    prefer_kvs_info,
)

KVS_HTML = """
<html><head><title>Sample</title></head><body>
<video><source src="https://cdn.example/get_file/1/abc/100/100/100_720p.mp4/" type="video/mp4"></video>
<script>
var flashvars = {
    video_title: "Sample Video",
    license_code: "$123456789012345",
    video_url: "https://cdn.example/get_file/1/aaa/100/100/100.mp4/",
    video_url_text: "480p",
    video_alt_url: "https://cdn.example/get_file/1/bbb/100/100/100_720p.mp4/",
    video_alt_url_text: "720p",
    video_alt_url2: "https://cdn.example/get_file/1/ccc/100/100/100_1080p.mp4/",
    video_alt_url2_text: "1080p"
};
</script></body></html>
"""

PLAYER_HTML = (
    '<html><head><title>NowPlay</title></head><body><script>'
    'jwplayer("vplayer").setup({sources:[{file:'
    '"https://cdn.nowplay.example/hls/1/abc/master.m3u8?t=token&s=1&e=43200"}],'
    'image:"https://thumb.example/abc.jpg"});'
    "</script></body></html>"
)


def test_kvs_flashvars_expose_every_quality():
    info = parse_kvs(KVS_HTML, "https://site.example/video/1")
    assert info is not None
    assert [(f["height"], f["format_id"]) for f in info.formats] == [
        (480, "480p"),
        (720, "720p"),
        (1080, "1080p"),
    ]
    assert all(f.get("kvs") for f in info.formats)


def test_prefer_kvs_info_replaces_single_quality_result():
    ytdlp = MediaInfo(
        url="https://site.example/video/1",
        title="Sample Video",
        extractor="HTML5MediaEmbed",
        formats=[
            {
                "height": 720,
                "ext": "mp4",
                "url": "https://cdn.example/get_file/1/bbb/100/100/100_720p.mp4/",
            }
        ],
    )
    kvs = parse_kvs(KVS_HTML, "https://site.example/video/1")
    merged = prefer_kvs_info(ytdlp, kvs)
    assert merged.extractor == "KVS"
    assert merged.title == "Sample Video"
    assert {f["height"] for f in merged.formats} == {480, 720, 1080}


def test_prefer_kvs_info_keeps_the_richer_result():
    kvs = MediaInfo(
        url="https://site.example/video/1",
        title="t",
        extractor="KVS",
        formats=[{"height": 1080, "format_id": "1080p", "url": "https://x/get_file/a.mp4"}],
    )
    rich = MediaInfo(
        url="https://site.example/video/1",
        title="t",
        extractor="Generic",
        formats=[{"height": h, "url": f"https://x/{h}.mp4"} for h in (720, 1080, 2160)],
    )
    assert prefer_kvs_info(rich, kvs) is rich
    assert prefer_kvs_info(rich, None) is rich


def test_looks_like_kvs_formats():
    assert looks_like_kvs_formats([{"url": "https://x/get_file/1/a.mp4"}]) is True
    assert looks_like_kvs_formats([{"url": "https://x/a.mp4"}]) is False
    assert looks_like_kvs_formats([]) is False


def test_hls_master_is_read_from_the_player_script():
    master = hls_master_from_player(PLAYER_HTML, "https://nowplay.example/emb1")
    assert master == (
        "https://cdn.nowplay.example/hls/1/abc/master.m3u8?t=token&s=1&e=43200"
    )


def test_hls_master_returns_empty_without_a_manifest():
    assert hls_master_from_player("<html>no player</html>", "https://x.example/") == ""