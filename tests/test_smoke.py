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
