"""سه‌زبانه بودن رابط: کلیدها، پرچم‌ها، تشخیص زبان و زنجیرهٔ جایگزینی."""
from __future__ import annotations

import re

import pytest

from app.core import text
from app.version import __version__

PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def test_three_languages_with_flags_in_order():
    assert tuple(text.LANGS) == ("fa", "en", "ru")
    assert text.LANG_ORDER == ("fa", "en", "ru")
    assert "🇮🇷" in text.LANGS["fa"]
    assert "🇬🇧" in text.LANGS["en"]
    assert "🇷🇺" in text.LANGS["ru"]


def test_every_language_has_every_key_and_no_empty_values():
    assert set(text.FA) == set(text.EN) == set(text.RU)
    for code in text.LANG_ORDER:
        table = text.MESSAGES[code]
        assert table
        for key, value in table.items():
            assert value.strip(), f"empty translation: {code}.{key}"


def test_placeholders_are_consistent_between_languages():
    for key, raw in text.FA.items():
        expected = set(PLACEHOLDER.findall(raw))
        for code in ("en", "ru"):
            found = set(PLACEHOLDER.findall(text.MESSAGES[code][key]))
            assert found == expected, f"placeholder mismatch: {code}.{key}"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("fa", "fa"),
        ("fa-IR", "fa"),
        ("per", "fa"),
        ("en-US", "en"),
        ("ru-RU", "ru"),
        ("de", "fa"),
        ("", "fa"),
        (None, "fa"),
    ],
)
def test_normalize_lang(raw, expected):
    assert text.normalize_lang(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("fa", "fa"), ("ru", "ru"), ("en-GB", "en"), ("de", "en"), (None, "en")],
)
def test_lang_from_telegram(raw, expected):
    assert text.lang_from_telegram(raw) == expected


def test_russian_falls_back_to_english_then_persian(monkeypatch):
    key = "done"
    assert text.t("ru", key) == text.RU[key]

    # اگر ترجمهٔ روسی نبود، انگلیسی؛ و اگر انگلیسی هم نبود، فارسی.
    monkeypatch.delitem(text.RU, key)
    assert text.t("ru", key) == text.EN[key]

    monkeypatch.delitem(text.EN, key)
    assert text.t("ru", key) == text.FA[key]


def test_unknown_language_uses_default_language():
    assert text.t("xx", "done") == text.FA["done"]
    assert text.t("", "done") == text.FA["done"]


def test_missing_key_returns_key_not_exception():
    assert text.t("fa", "definitely_missing_key") == "definitely_missing_key"


@pytest.mark.parametrize("code", text.LANG_ORDER)
def test_settings_panel_and_language_confirmation_format(code):
    panel = text.t(
        code,
        "settings_panel",
        language=text.LANGS[code],
        version=__version__,
        send_as=text.t(code, "delivery_mode_video"),
        destination=text.t(code, "delivery_destination_telegram"),
    )
    saved = text.t(code, "lang_saved", language=text.LANGS[code])
    assert text.LANGS[code] in panel
    assert __version__ in panel
    assert text.t(code, "delivery_mode_video") in panel
    assert text.t(code, "delivery_destination_telegram") in panel
    assert text.LANGS[code] in saved
    assert text.t(code, "lang_start_prompt")


@pytest.mark.parametrize("code", text.LANG_ORDER)
def test_delivery_panel_and_status_are_localized_and_non_admin(code):
    delivery = text.t(
        code,
        "delivery_panel",
        title="clip",
        quality="1080p",
        size="10 MB",
        send_as=text.t(code, "delivery_mode_video"),
        destination=text.t(code, "delivery_destination_telegram"),
        ttl_line="\n" + text.t(code, "delivery_ttl_short", ttl="6"),
    )
    status = text.t(
        code,
        "status",
        uid=7,
        downloads=3,
        uploads=2,
        joined="2026-01-01",
        version=__version__,
    )
    assert "clip" in delivery
    assert "6" in delivery
    assert __version__ in status
    assert "3" in status and "2" in status
    assert "admin" not in status.lower()
