"""تست رفع سه ایراد v5.12.2: لینک فایل تلگرام، MKV و معافیت ادمین."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.flows import link as link_flow
from app.services.drafts import Draft
from app.services.formats import FormatOption
from app.services.telegram_transfers import (
    _api_file_url,
    _readable_local_file,
    _storage_relative,
)


# ── مسیر فایل Local Bot API ────────────────────────────────
def test_storage_relative_from_absolute_api_path():
    path = "/var/lib/telegram-bot-api/123:ABC/documents/file_1.mkv"
    assert _storage_relative(path) == "documents/file_1.mkv"


def test_storage_relative_keeps_media_relative_path():
    assert _storage_relative("documents/file_7.zip") == "documents/file_7.zip"


def test_storage_relative_from_broken_ptb_url():
    # همان آدرسی که PTB می‌ساخت و سرور با 404 جواب می‌داد.
    url = (
        "http://telegram-bot-api:8081/file/bot123:ABC"
        "/var/lib/telegram-bot-api/123:ABC/videos/a.mp4"
    )
    assert _storage_relative(url) == "videos/a.mp4"


def test_api_file_url_builds_local_endpoint():
    cfg = SimpleNamespace(
        telegram_api_file_url="http://telegram-bot-api:8081/file/bot",
        bot_token="123:ABC",
    )
    assert (
        _api_file_url(cfg, "documents/a.mkv")
        == "http://telegram-bot-api:8081/file/bot123:ABC/documents/a.mkv"
    )


def test_api_file_url_reuses_base_that_already_has_the_token():
    cfg = SimpleNamespace(
        telegram_api_file_url="http://telegram-bot-api:8081/file/bot123:ABC",
        bot_token="123:ABC",
    )
    assert (
        _api_file_url(cfg, "documents/a.mkv")
        == "http://telegram-bot-api:8081/file/bot123:ABC/documents/a.mkv"
    )


def test_api_file_url_is_empty_for_the_public_api():
    cfg = SimpleNamespace(telegram_api_file_url="", bot_token="123:ABC")
    assert _api_file_url(cfg, "documents/a.mkv") == ""


def test_readable_local_file_rejects_urls_and_missing_paths(tmp_path):
    assert _readable_local_file("https://api.telegram.org/file/bot1/a.mp4") is None
    assert _readable_local_file(str(tmp_path / "missing.mkv")) is None
    local = tmp_path / "clip.mkv"
    local.write_bytes(b"x")
    assert _readable_local_file(str(local)) == local


# ── MKV باید به‌صورت ویدیو انتخاب شود ──────────────────────
def test_mkv_can_be_delivered_as_video():
    draft = Draft(
        id="mkv1",
        user_id=1,
        chat_id=1,
        url="https://cdn.example.com/movie.mkv",
        title="movie.mkv",
        option=FormatOption(
            kind="direct", code="direct", label="direct", selector="", ext="mkv"
        ),
        send_as="video",
    )
    assert link_flow.can_send_as_video(draft)
    link_flow.normalize_delivery_mode(draft)
    assert draft.send_as == "video"


# ── محدودیت‌ها برای ادمین نباید اعمال شود ──────────────────
@pytest.mark.asyncio
async def test_admin_bypasses_daily_quota_and_link_cap():
    services = SimpleNamespace(settings=SimpleNamespace(daily_quota=1, max_links_per_user=1))
    context = SimpleNamespace(bot_data={"services": services}, user_data={"is_admin": True})
    assert await link_flow._quota_left(context, 7) is True
    assert await link_flow.link_quota_used(context, 7) == (0, 0)


@pytest.mark.asyncio
async def test_admin_in_preview_is_limited_like_a_user(monkeypatch):
    services = SimpleNamespace(settings=SimpleNamespace(daily_quota=1, max_links_per_user=1))
    context = SimpleNamespace(
        bot_data={"services": services},
        user_data={"is_admin": True, "preview": True},
    )

    async def used_up(user_id: int, kind: str, ts: int) -> float:
        return 1.0

    monkeypatch.setattr("app.bot.flows.link.repo.user_events_since", used_up)
    assert await link_flow._quota_left(context, 7) is False
