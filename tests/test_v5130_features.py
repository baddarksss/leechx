"""v5.13.0: magnet/torrent helpers, cover picker prefs, history reset, user list."""
from __future__ import annotations

import pytest

from app.core import errors, text, urlcheck
from app.db import repo
from app.db.base import session
from app.db.models import User
from app.services import thumbs, torrent


def test_is_magnet_and_display_name():
    magnet = "magnet:?xt=urn:btih:abc&dn=My%20Movie%202024&tr=udp://x"
    assert torrent.is_magnet(magnet)
    assert torrent.is_magnet("  MAGNET:?xt=urn:btih:abc")
    assert not torrent.is_magnet("https://example.com/a.mp4")
    assert torrent.display_name(magnet) == "My Movie 2024"
    assert torrent.display_name("magnet:?xt=urn:btih:abc") == ""


def test_largest_file_ignores_partials(tmp_path):
    (tmp_path / "small.mp4").write_bytes(b"a" * 10)
    (tmp_path / "big.mkv").write_bytes(b"b" * 100)
    (tmp_path / "big.mkv.aria2").write_bytes(b"c" * 500)
    (tmp_path / "meta.torrent").write_bytes(b"d" * 900)
    assert torrent.largest_file(tmp_path) == tmp_path / "big.mkv"
    assert torrent.bytes_on_disk(tmp_path) == 110


def test_extract_magnet_from_text():
    blob = "ببین magnet:?xt=urn:btih:deadbeef&dn=Show luego"
    assert urlcheck.extract_magnet(blob) == "magnet:?xt=urn:btih:deadbeef&dn=Show"
    assert urlcheck.extract_magnet("https://example.com") is None
    assert urlcheck.extract_magnet(None) is None


def test_torrent_error_is_translated_everywhere():
    exc = errors.TorrentFailed("boom")
    assert exc.key == "torrent_failed"
    for lang in text.LANG_ORDER:
        assert "boom" in text.t(lang, exc.key, reason="boom")


def test_shot_times_count_bounds():
    assert len(thumbs.shot_times(120.0, 4)) == 4
    assert len(thumbs.shot_times(120.0, 10)) == 10


def test_thumb_shots_setting_defaults_and_clamps(cfg):
    from app.services.runtime_settings import RuntimeSettings

    settings = RuntimeSettings(cfg)
    assert 4 <= settings.thumb_shots <= 10
    settings._cache["thumb_shots"] = "2"
    assert settings.thumb_shots == 4
    settings._cache["thumb_shots"] = "50"
    assert settings.thumb_shots == 10


@pytest.mark.asyncio
async def test_reset_history_clears_events_and_traffic(db):
    await repo.log_event(5, "download_done")
    await repo.record_traffic(source_download_bytes=1234)
    cleared = await repo.reset_history()
    assert cleared["events"] >= 1
    assert await repo.user_events_since(5, "download_done", 0) == 0
    assert (await repo.traffic_totals())["source_download_bytes"] == 0


@pytest.mark.asyncio
async def test_user_thumb_picker_preference_roundtrip(db):
    await repo.set_user_preferences(
        55, default_mode="video", default_destination="telegram", thumb_picker=True
    )
    row = await repo.get_user(55)
    assert row is not None and row.thumb_picker is True
    # بدون پاس دادن thumb_picker مقدار قبلی حفظ می‌شود
    await repo.set_user_preferences(55, default_mode="document", default_destination="link")
    row = await repo.get_user(55)
    assert row is not None and row.thumb_picker is True


@pytest.mark.asyncio
async def test_list_users_search_and_paging(db):
    async with session() as s:
        s.add(User(id=101, username="alice_x", first_name="Alice", last_seen=1000))
        s.add(User(id=102, username="bob_y", first_name="Bob", last_seen=2000))
        await s.commit()
    assert [row.id for row in await repo.list_users(10, 0, "alice")] == [101]
    assert await repo.count_users_filtered("bob") == 1
    assert await repo.count_users_filtered("102") == 1
    # مرتب‌سازی بر اساس آخرین بازدید (نزولی)
    assert [row.id for row in await repo.list_users(1, 0)] == [102]
    assert [row.id for row in await repo.list_users(1, 1)] == [101]
