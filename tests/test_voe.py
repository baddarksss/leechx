"""تستهای رزولور VOE: دیکود payload بدون اجرای JS و تشخیص صفحهٔ پلیر.

تستها هیچ شبکهای لمس نمیکنند؛ payload با معکوس الگوریتم ساخته میشود.
"""
from __future__ import annotations

import base64
import json

from app.services.downloader import (
    _VOE_MARKERS,
    _voe_rot13,
    decode_voe_config,
    hls_master_variants,
    looks_like_voe,
    voe_payload,
    voe_redirect_target,
)

MASTER = """#EXTM3U
#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=1491162,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"
index-v1-a1.m3u8?t=abc
#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=5113000,RESOLUTION=1920x1080,CODECS="avc1.640033,mp4a.40.2"
index-v2-a1.m3u8?t=abc
"""


def _encode_payload(config: dict) -> str:
    """معکوس دقیق الگوریتم دیکود (برای تست)."""
    encoded = base64.b64encode(json.dumps(config, ensure_ascii=False).encode()).decode()
    raw = bytes((ord(char) + 3) & 0xFF for char in encoded[::-1])
    return _voe_rot13(base64.b64encode(raw).decode())


def test_decode_voe_config_roundtrip():
    config = {
        "source": "https://ugc-cdn.example/engine/hls2-c/x_,n,.urlset/master.m3u8?t=abc",
        "title": "SWALLOWED Some Title 1080p.mp4",
        "thumbnail": "https://ugc-cdn.example/cache/abc_storyboard_L2.jpg",
        "file_code": "mqryvmojppml",
    }
    payload = _encode_payload(config)
    assert payload  # نانخالی و بدون نشانهٔ خام
    assert decode_voe_config(payload) == config


def test_decode_voe_config_rejects_garbage():
    assert decode_voe_config("") is None
    assert decode_voe_config("not a payload") is None


def test_markers_are_stripped():
    # نشانهها به «_» تبدیل و سپس حذف میشوند؛ payload با نشانهٔ تزریقشده
    # باید دقیقاً همان کانفیگ را بدهد.
    config = {"source": "https://cdn.example/master.m3u8"}
    plain = _encode_payload(config)
    assert decode_voe_config(plain) == config
    assert all(marker not in plain for marker in _VOE_MARKERS)


def test_voe_payload_extracts_first_array_item():
    html = '<html><script type="application/json">["ABC123"]</script></html>'
    assert voe_payload(html) == "ABC123"
    assert voe_payload("<html>no payload</html>") is None
    assert voe_payload('<script type="application/json">{"a": 1}</script>') is None


def test_voe_redirect_target():
    html = (
        "<script>window.location.href = "
        "'https://shannoncoldalready.com/e/mqryvmojppml';</script>"
    )
    assert (
        voe_redirect_target(html, "https://voe.sx/e/mqryvmojppml")
        == "https://shannoncoldalready.com/e/mqryvmojppml"
    )
    assert voe_redirect_target("<html>nothing</html>", "https://voe.sx/e/x") is None


def test_looks_like_voe():
    assert looks_like_voe("https://voe.sx/e/mqryvmojppml")
    assert looks_like_voe("https://www.voe.sx/e/mqryvmojppml")
    assert not looks_like_voe("https://girlswallowed.com/swallowed-x/")
    assert not looks_like_voe("https://shannoncoldalready.com/e/mqryvmojppml")


def test_decoded_source_builds_hls_menu():
    variants = hls_master_variants(MASTER, "https://ugc-cdn.example/x/master.m3u8")
    assert [v["height"] for v in variants] == [720, 1080]
    assert variants[0]["url"].startswith("https://ugc-cdn.example/x/index-v1-a1.m3u8")
