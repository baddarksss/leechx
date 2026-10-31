"""تامبنیل تحویل: دانلود کامل، رد فایل ناقص و تبدیل به JPEG سالم.

سرور محلی aiohttp است؛ هیچ درخواست بیرونی انجام نمی‌شود. اگر ffmpeg روی
ماشین تست باشد، دادهٔ ساختگی زیر رد می‌شود و مسیر fallback آزموده می‌شود.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web

from app.services import downloader
from app.services.downloader import fetch_thumbnail

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 800 + b"\xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 800 + b"IEND"
WEBP = b"RIFF" + (800).to_bytes(4, "little") + b"WEBPVP8 " + b"\x00" * 800


@pytest.fixture
async def thumb_server():
    async def handler(request: web.Request) -> web.StreamResponse:
        kind = request.match_info["kind"]
        if kind == "jpeg":
            return web.Response(body=JPEG, content_type="image/jpeg")
        if kind == "png":
            return web.Response(body=PNG, content_type="image/png")
        if kind == "webp":
            return web.Response(body=WEBP, content_type="image/webp")
        if kind == "short-jpeg":
            # بدنهٔ کامل نیست: EOI ندارد
            return web.Response(body=JPEG[:-2], content_type="image/jpeg")
        if kind == "html":
            return web.Response(body=b"<html>" + b"x" * 800, content_type="text/html")
        if kind == "truncated":
            # Content-Length بزرگ‌تر از بدنهٔ واقعی: همان تامبنیل «نصفه»
            resp = web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "image/jpeg",
                    "Content-Length": str(len(JPEG) + 1000),
                },
            )
            await resp.prepare(request)
            await resp.write(JPEG)
            await resp.write_eof()
            return resp
        return web.Response(status=404)

    app = web.Application()
    app.router.add_get("/{kind}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
    yield f"http://127.0.0.1:{port}"
    await runner.cleanup()


@pytest.mark.asyncio
async def test_complete_cover_is_accepted(thumb_server, tmp_path: Path):
    dest = tmp_path / "thumb.jpg"
    path = await fetch_thumbnail(f"{thumb_server}/jpeg", dest)
    assert path == dest
    assert dest.read_bytes() == JPEG
    # فایل موقت خام نباید باقی بماند
    assert not (tmp_path / "thumb-raw.jpg").exists()


@pytest.mark.asyncio
async def test_complete_png_cover_is_accepted(thumb_server, tmp_path: Path):
    path = await fetch_thumbnail(f"{thumb_server}/png", tmp_path / "thumb.jpg")
    assert path is not None and path.read_bytes() == PNG


@pytest.mark.asyncio
async def test_truncated_download_is_rejected(monkeypatch, thumb_server, tmp_path: Path):
    # Content-Length با بدنه نمی‌خوانَد؛ تلگرام همین را نصفه نشان می‌داد.
    original = downloader.aiohttp.ClientTimeout
    monkeypatch.setattr(
        downloader.aiohttp, "ClientTimeout", lambda **_: original(total=0.5)
    )
    assert await fetch_thumbnail(f"{thumb_server}/truncated", tmp_path / "thumb.jpg") is None
    assert not (tmp_path / "thumb.jpg").exists()


@pytest.mark.asyncio
async def test_broken_jpeg_is_rejected(thumb_server, tmp_path: Path):
    assert await fetch_thumbnail(f"{thumb_server}/short-jpeg", tmp_path / "thumb.jpg") is None


@pytest.mark.asyncio
async def test_non_image_is_rejected(thumb_server, tmp_path: Path):
    assert await fetch_thumbnail(f"{thumb_server}/html", tmp_path / "thumb.jpg") is None


@pytest.mark.asyncio
async def test_webp_cover_is_converted_to_jpeg(monkeypatch, thumb_server, tmp_path: Path):
    async def fake_convert(source: Path, dest: Path) -> bool:
        dest.write_bytes(JPEG)
        return True

    monkeypatch.setattr(downloader, "_thumbnail_to_jpeg", fake_convert)
    dest = tmp_path / "thumb.jpg"
    path = await fetch_thumbnail(f"{thumb_server}/webp", dest)
    assert path == dest
    assert dest.read_bytes() == JPEG


@pytest.mark.asyncio
async def test_webp_cover_is_dropped_without_conversion(monkeypatch, thumb_server, tmp_path: Path):
    async def no_ffmpeg(source: Path, dest: Path) -> bool:
        return False

    monkeypatch.setattr(downloader, "_thumbnail_to_jpeg", no_ffmpeg)
    assert await fetch_thumbnail(f"{thumb_server}/webp", tmp_path / "thumb.jpg") is None
