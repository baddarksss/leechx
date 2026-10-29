"""کیبورد ثابت کاربر: چیدمان، تنظیمات پیش‌فرض و مسیر دکمه‌ها."""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

from app.bot import keyboards as kb
from app.bot.flows import text_router
from app.core import text


class FakeMessage:
    def __init__(self, body: str) -> None:
        self.text = body
        self.replies: list[tuple[str, dict]] = []

    async def reply_text(self, body: str, **kwargs):
        self.replies.append((body, kwargs))
        return self


def _update(message: FakeMessage, user_id: int = 42):
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=user_id,
            username=f"user{user_id}",
            first_name="User",
            is_bot=False,
        ),
        effective_chat=SimpleNamespace(id=user_id, type="private"),
        effective_message=message,
        callback_query=None,
    )


def _context(cfg=None, *, lang: str = "fa"):
    services = SimpleNamespace(cfg=cfg) if cfg is not None else None
    return SimpleNamespace(
        user_data={"lang": lang, "is_admin": False},
        bot_data={"services": services} if services is not None else {},
        bot=None,
    )


@pytest.mark.parametrize("code", text.LANG_ORDER)
def test_user_keyboard_is_persistent_and_grouped(code):
    markup = kb.user_persistent_menu(code)
    assert isinstance(markup, ReplyKeyboardMarkup)
    assert markup.resize_keyboard is True
    assert markup.is_persistent is True
    rows = [[button.text for button in row] for row in markup.keyboard]
    assert rows == [
        [text.t(code, "my_links_btn"), text.t(code, "btn_status")],
        [text.t(code, "btn_settings"), text.t(code, "btn_lang")],
        [text.t(code, "btn_help")],
        [text.t(code, "btn_contact")],
    ]
    labels = {label for row in rows for label in row}
    assert text.t(code, "btn_sites") not in labels
    assert text.t(code, "btn_kb_close") not in labels
    assert rows[-1] == [text.t(code, "btn_contact")]


@pytest.mark.parametrize("code", ("en", "ru"))
def test_regular_user_persistent_and_inline_submenus_follow_selected_language(code):
    markups = [
        kb.user_persistent_menu(code),
        kb.main_menu(code, admin=False),
        kb.user_settings_menu(code),
    ]
    labels = []
    for markup in markups:
        rows = markup.keyboard if isinstance(markup, ReplyKeyboardMarkup) else markup.inline_keyboard
        labels.extend(button.text for row in rows for button in row)
    assert all(re.search(r"[\u0600-\u06ff]", label) is None for label in labels)


def test_admin_menus_are_persian_and_have_no_language_switch():
    admin_menu = kb.admin_persistent_menu("ru")
    inline_menu = kb.main_menu("en", admin=True)
    for markup in (admin_menu, inline_menu):
        rows = markup.keyboard if isinstance(markup, ReplyKeyboardMarkup) else markup.inline_keyboard
        buttons = [button for row in rows for button in row]
        assert any(re.search(r"[\u0600-\u06ff]", button.text) for button in buttons)
        assert all(getattr(button, "callback_data", None) != kb.M_LANG for button in buttons)
        labels = {button.text for button in buttons}
        assert all(text.t(code, "btn_lang") not in labels for code in text.LANG_ORDER)

    # Preview behaves as the user's selected locale, including the language control.
    preview_menu = kb.main_menu("en", admin=True, preview=True)
    preview_buttons = [button for row in preview_menu.inline_keyboard for button in row]
    assert any(button.callback_data == kb.M_LANG for button in preview_buttons)
    assert any(button.text == text.t("en", "btn_lang") for button in preview_buttons)


def test_preview_keyboard_includes_exit_button():
    markup = kb.user_persistent_menu("fa", preview=True)
    rows = [[button.text for button in row] for row in markup.keyboard]
    assert [text.t("fa", "btn_preview_exit")] in rows
    assert rows[-1] == [text.t("fa", "btn_contact")]


@pytest.mark.asyncio
async def test_settings_button_text_opens_settings_with_persistent_keyboard(db):
    message = FakeMessage(kb.user_persistent_labels("fa")["settings"])
    update = _update(message)
    context = _context(db)

    await text_router.on_text(update, context)

    body, kwargs = message.replies[-1]
    assert "تنظیمات" in body
    assert "پیش‌فرض" in body
    markup = kwargs["reply_markup"]
    assert isinstance(markup, InlineKeyboardMarkup)
    callbacks = {
        button.callback_data
        for row in markup.inline_keyboard for button in row
    }
    assert {"m|prefmode", "m|prefdest", "m|lang"} <= callbacks


def test_user_persistent_labels_no_longer_expose_sites_or_keyboard_hide():
    labels = kb.user_persistent_labels("en")
    assert "sites" not in labels
    assert "kbclose" not in labels


@pytest.mark.asyncio
async def test_legacy_keyboard_tap_refreshes_removed_buttons(db):
    from types import SimpleNamespace

    from app.db import repo

    await repo.upsert_user(42, "user42", "User", lang="en")
    await repo.set_lang(42, "en", selected=True)
    # The old Persian reply keyboard can remain visible after a language switch.
    message = FakeMessage("📊 وضعیت من")
    context = _context(db, lang="en")
    context.bot_data["services"].settings = SimpleNamespace(ttl_hours=6)

    await text_router.on_text(_update(message), context)

    body = message.replies[-1][0]
    assert "Your status" in body
    assert "Send a link or a file" not in body
    markup = message.replies[-1][1]["reply_markup"]
    assert isinstance(markup, ReplyKeyboardMarkup)
    labels = {button.text for row in markup.keyboard for button in row}
    assert text.t("en", "btn_contact") in labels
    assert text.t("en", "btn_sites") not in labels
    assert text.t("en", "btn_kb_close") not in labels
