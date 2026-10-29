"""تست دود: کل ربات بدون شبکه ساخته می‌شود و متن‌ها کامل‌اند."""
from __future__ import annotations

from app.core import text


def test_translations_are_complete():
    assert set(text.FA) == set(text.EN), "کلیدهای ترجمه بین زبان‌ها یکی نیست"
    for lang in text.LANGS:
        for key in text.FA:
            assert text.t(lang, key), f"متن خالی: {lang}.{key}"


def test_translation_formatting_is_safe():
    assert "{" not in text.t("fa", "send_link_or_file")
    # آرگومان جاافتاده نباید استثنا بدهد
    assert text.t("fa", "link_ready", url="x")
    assert text.t("xx", "done") == text.t("fa", "done")


def test_build_app_registers_handlers(cfg):
    from app.bot.app import build_app

    app = build_app(cfg)
    assert app.bot_data["cfg"] is cfg
    assert len(app.handlers) > 0
    commands = {
        c
        for group in app.handlers.values()
        for handler in group
        for c in getattr(handler, "commands", [])
    }
    assert {"start", "help", "sites", "me", "cancel", "admin"} <= commands


def test_config_validation(cfg):
    assert cfg.validate_runtime() == []
    assert cfg.files_dir.exists()
    assert cfg.tmp_dir.exists()
    assert cfg.link_secret


def test_site_index_builds():
    from app.services.sites import SiteIndex

    index = SiteIndex()
    index.build()
    assert index.count > 100
    assert index.match("https://www.youtube.com/watch?v=dQw4w9WgXcQ").name == "youtube"
    assert index.match("https://example.invalid/no-media") is None
    assert index.is_nsfw_url("https://www.pornhub.com/view_video.php?viewkey=1") is True
    assert index.search("instagram", 5)


def test_quality_menu_callback_data_is_valid():
    from app.bot import keyboards as kb
    from app.services.drafts import Draft
    from app.services.formats import all_options

    formats = [
        {"height": h, "ext": "mp4", "vcodec": "avc1", "tbr": 1000, "format_id": str(h)}
        for h in (360, 720, 1080)
    ]
    draft = Draft(
        id="abc123",
        user_id=1,
        chat_id=1,
        url="https://x.com/a",
        title="t",
        options=all_options(formats),
    )
    menu = kb.quality_menu("fa", draft)
    datas = [b.callback_data for row in menu.inline_keyboard for b in row if b.callback_data]
    assert datas
    for data in datas:
        assert len(data.encode()) <= 64, data
        assert data.count("|") <= 3
    assert any(d.startswith("q|abc123|1080|v") for d in datas)
    assert any(d.startswith("q|abc123|mp3|a") for d in datas)
    assert all(button.style is None for row in menu.inline_keyboard for button in row)


def test_config_rejects_bad_token_and_allows_missing_owner(tmp_path, monkeypatch):
    from app.config import get_config

    monkeypatch.setenv("BOT_TOKEN", "not-a-token")
    monkeypatch.setenv("OWNER_IDS", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "bad"))
    get_config.cache_clear()
    try:
        problems = get_config().validate_runtime()
        assert any("BOT_TOKEN" in p for p in problems)
        # مالک با اولین /start تعیین می‌شود؛ OWNER_IDS اجباری نیست.
        assert not any("OWNER_IDS" in p for p in problems)
    finally:
        get_config.cache_clear()


def test_bot_command_menu_exposes_only_start():
    from app.bot.app import COMMANDS

    assert [command for command, _description in COMMANDS] == ["start"]
