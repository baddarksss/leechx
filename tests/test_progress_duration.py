"""پیشرفت دانلود با دانلودر بیرونی (aria2c) و تحویل AV1 به‌صورت ویدیو.

این تست‌ها شبکه را لمس نمی‌کنند: فقط حساب‌وکتاب فایل روی دیسک و قواعد
انتخاب حالت تحویل بررسی می‌شود.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.bot.flows import link as link_flow
from app.services import downloader, thumbs
from app.services.downloader import Progress
from app.services.drafts import Draft
from app.services.formats import FormatOption
from app.services.runtime_settings import RuntimeSettings


# ── مدت واقعی فایل (ffprobe) ────────────────────────────────
def test_media_meta_reads_duration_and_video_stream():
    data = {
        "streams": [
            {"codec_type": "audio"},
            {"codec_type": "video", "width": 1920, "height": 1080},
        ],
        "format": {"duration": "2510.373800"},
    }
    meta = thumbs.media_meta(data)
    assert meta is not None
    assert (meta.width, meta.height) == (1920, 1080)
    assert meta.duration == 2510


def test_media_meta_without_duration_or_video():
    assert thumbs.media_meta({}) is None
    assert thumbs.media_meta({"streams": [], "format": {}}) is None
    assert thumbs.media_meta({"format": {"duration": "N/A"}}) is None
    audio_only = thumbs.media_meta(
        {"streams": [{"codec_type": "audio"}], "format": {"duration": "42.6"}}
    )
    assert audio_only is not None
    assert audio_only.duration == 43
    assert audio_only.width is None


def test_media_meta_uses_rotated_display_size():
    data = {
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "side_data_list": [{"rotation": -90}],
            }
        ],
        "format": {"duration": "10"},
    }
    meta = thumbs.media_meta(data)
    assert meta is not None and (meta.width, meta.height) == (1080, 1920)


# ── پیشرفت از روی دیسک (aria2c هیچ hook ای صدا نمی‌زند) ─────
def test_disk_progress_counts_written_blocks_not_sparse_length(tmp_path: Path):
    target = tmp_path / "clip.mp4.part"
    with target.open("wb") as handle:
        handle.truncate(8 * 1024 * 1024)  # طول کامل فایل، بدون داده
        handle.seek(0)
        handle.write(b"x" * (256 * 1024))
    (tmp_path / "clip.mp4.part.aria2").write_bytes(b"\0" * 4096)

    written, span = downloader.disk_progress(tmp_path)
    assert span == 8 * 1024 * 1024
    assert 0 < written < span  # فقط بلوک‌های واقعی شمرده می‌شوند
    assert written < 1024 * 1024  # فایل کنترل آریا هم حساب نشده است


def test_advance_progress_fills_speed_and_eta():
    progress = Progress()
    progress.reset_download()
    progress.total = 10 * 1024 * 1024
    downloader.advance_progress(progress, 1024 * 1024, time.monotonic() - 2)
    assert progress.downloaded == 1024 * 1024
    assert progress.speed > 0
    assert progress.pct > 0
    assert progress.eta and progress.eta > 0


@pytest.mark.asyncio
async def test_watcher_publishes_disk_progress(tmp_path: Path):
    cancel = asyncio.Event()
    progress = Progress()
    watcher = asyncio.create_task(
        downloader.watch_disk_progress(
            tmp_path, progress, cancel, 4 * 1024 * 1024, interval=0.05, grace=0
        )
    )
    (tmp_path / "clip.mp4.part").write_bytes(b"x" * (1024 * 1024))
    await asyncio.sleep(0.3)
    cancel.set()
    await asyncio.wait_for(watcher, timeout=2)

    assert progress.downloaded >= 1024 * 1024
    assert progress.total == 4 * 1024 * 1024
    assert 20 <= progress.pct <= 99.9
    assert progress.speed > 0


@pytest.mark.asyncio
async def test_watcher_stays_out_of_the_way_when_hooks_report(tmp_path: Path):
    progress = Progress(downloaded=1234, total=4321, pct=28.0)
    await asyncio.wait_for(
        downloader.watch_disk_progress(
            tmp_path, progress, asyncio.Event(), 999, interval=0.05, grace=0
        ),
        timeout=2,
    )
    # خود yt-dlp گزارش می‌دهد؛ مقادیر نباید دستکاری شوند.
    assert (progress.downloaded, progress.total, progress.pct) == (1234, 4321, 28.0)


def test_generic_untitled_output_is_renamed(tmp_path: Path):
    source = tmp_path / "Untitled [abc123].mp4"
    source.write_bytes(b"x")
    renamed = downloader._rename_generic_output(source, "Real title", "abc123")
    assert renamed.name == "Real title [abc123].mp4"
    assert renamed.exists() and not source.exists()
    # نامی که واقعاً از سایت آمده نباید عوض شود.
    assert downloader._rename_generic_output(renamed, "Other", "abc123") == renamed


# ── تعداد اتصال aria2c (تنظیم ادمین) ────────────────
def test_aria2c_opts_uses_configured_connections(monkeypatch):
    monkeypatch.setattr(thumbs.shutil, "which", lambda name: "/usr/bin/aria2c")
    args = thumbs.aria2c_opts(16)["external_downloader_args"]["aria2c"]
    assert args[:6] == ["-x", "16", "-s", "16", "-k", "4M"]
    assert "--max-connection-per-server=16" in args


def test_aria2c_connection_count_is_clamped(monkeypatch):
    monkeypatch.setattr(thumbs.shutil, "which", lambda name: "/usr/bin/aria2c")
    for raw, expected in (
        (None, thumbs.ARIA2C_DEFAULT),
        (0, thumbs.ARIA2C_DEFAULT),
        (500, thumbs.ARIA2C_MAX),
        (1, thumbs.ARIA2C_MIN),
    ):
        args = thumbs.aria2c_opts(raw)["external_downloader_args"]["aria2c"]
        assert args[1] == str(expected)


def test_runtime_setting_clamps_connection_count(cfg):
    settings = RuntimeSettings(cfg)
    assert settings.aria2c_connections == thumbs.ARIA2C_DEFAULT
    settings._cache = {"aria2c_connections": "20"}
    assert settings.aria2c_connections == 20
    settings._cache = {"aria2c_connections": "999"}
    assert settings.aria2c_connections == thumbs.ARIA2C_MAX
    assert settings.snapshot()["aria2c_connections"] == thumbs.ARIA2C_MAX


def test_downloader_passes_connection_count(cfg, monkeypatch):
    monkeypatch.setattr(thumbs.shutil, "which", lambda name: "/usr/bin/aria2c")
    settings = SimpleNamespace(aria2c_connections=12)
    downloader_with_settings = downloader.Downloader(cfg, None, settings)
    assert downloader_with_settings.connections == 12
    opts = downloader._base_opts(cfg, "https://example.com/a.mp4", None, 12)
    assert "--max-connection-per-server=12" in opts["external_downloader_args"]["aria2c"]
    # بدون تنظیمات، پیش‌فرض قبلی (۸) حفظ می‌شود.
    assert downloader.Downloader(cfg).connections is None


def test_external_downloader_detected(monkeypatch):
    monkeypatch.setattr(thumbs, "aria2c_opts", lambda: {})
    assert downloader.uses_external_downloader() is False
    monkeypatch.setattr(
        thumbs, "aria2c_opts", lambda: {"external_downloader": {"default": "aria2c"}}
    )
    assert downloader.uses_external_downloader() is True


# ── AV1 باید ویدیو تحویل داده شود، نه فایل ──────────────────
def test_av1_quality_is_offered_as_video():
    option = FormatOption(
        kind="video",
        code="1080-av1",
        label="1080p AV1 · 785.8 MB",
        selector="1080p_HD-av1",
        height=1080,
        ext="mp4",
        codec="av1",
    )
    draft = Draft(
        id="d1",
        user_id=1,
        chat_id=1,
        url="https://www.eporner.com/video-VbkRXCqmRR6/title/",
        title="title",
        option=option,
        send_as="video",
    )
    assert link_flow.can_send_as_video(draft)
    # خروجی‌های غیرقابل‌پخش همچنان به حالت فایل می‌روند.
    draft.option = FormatOption(
        kind="video", code="x", label="x", selector="x", ext="webm", codec="vp9"
    )
    assert not link_flow.can_send_as_video(draft)
