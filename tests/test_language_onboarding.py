"""رگرسیون تنظیمات کاربر، انتخاب زبان و ترتیب قفل عضویت."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy import text as sql_text
from telegram import ReplyKeyboardMarkup
from telegram.ext import ApplicationHandlerStop

from app.bot import app as bot_app
from app.bot import keyboards as kb
from app.bot.flows import start as start_flow
from app.bot.flows import text_router
from app.core import text
from app.db import repo
from app.db.base import _migrate_user_language_selected
from app.services.force_join import JoinTarget
from app.version import __version__


class FakeMessage:
    def __init__(self, text_value: str = "") -> None:
        self.text = text_value
        self.chat_id = 10
        self.message_id = 1
        self.replies: list[tuple[str, dict]] = []
        self.edits: list[tuple[str, dict]] = []

    async def reply_text(self, body: str, **kwargs):
        self.replies.append((body, kwargs))
        return self

    async def edit_text(self, body: str, **kwargs):
        self.edits.append((body, kwargs))


class FakeQuery:
    def __init__(self, message: FakeMessage, data: str = "") -> None:
        self.message = message
        self.data = data
        self.answers: list[tuple[str | None, bool]] = []

    async def answer(self, body: str | None = None, show_alert: bool = False):
        self.answers.append((body, show_alert))


class FakeForceJoin:
    enabled = True

    def __init__(self, missing: list[JoinTarget] | None = None) -> None:
        self.missing_targets = missing or []
        self.calls = 0
        self.clears = 0

    def clear_cache(self, _user_id=None) -> None:
        self.clears += 1

    async def missing(self, _bot, _user_id: int, *, use_cache: bool = True):
        self.calls += 1
        return list(self.missing_targets), True


def _services(force_join: FakeForceJoin | None = None):
    return SimpleNamespace(
        cfg=SimpleNamespace(owners=[999], extra_admins=[], default_lang="fa"),
        settings=SimpleNamespace(maintenance=False, ttl_hours=6.0),
        force_join=force_join or FakeForceJoin(),
    )


def _update(message: FakeMessage, user_id: int = 10, *, query: FakeQuery | None = None):
    user = SimpleNamespace(
        id=user_id,
        username=f"user{user_id}",
        first_name="User",
        is_bot=False,
        language_code="en-US",
    )
    return SimpleNamespace(
        effective_user=user,
        effective_chat=SimpleNamespace(id=user_id, type="private"),
        effective_message=message,
        callback_query=query,
    )


def _context(services, *, lang: str | None = None):
    user_data = {}
    if lang:
        user_data["lang"] = lang
    return SimpleNamespace(user_data=user_data, bot_data={"services": services}, bot=object())


def _callback_data(markup) -> set[str]:
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


@pytest.mark.asyncio
async def test_start_prompts_language_before_forced_join_and_persists_choice(db):
    force_join = FakeForceJoin([JoinTarget(123, "Required channel", username="required")])
    services = _services(force_join)
    context = _context(services)
    message = FakeMessage("/start")
    update = _update(message)

    # /start reaches its handler before the channel gate so owner setup remains intact.
    await bot_app.gate(update, context)
    assert force_join.calls == 0
    await start_flow.cmd_start(update, context)
    prompt, kwargs = message.replies[-1]
    assert prompt == start_flow.LANGUAGE_PICKER_TEXT
    markup = kwargs["reply_markup"]
    assert _callback_data(markup) == {"l|fa", "l|en", "l|ru"}
    assert len(markup.inline_keyboard) == 3
    assert all(len(row) == 1 for row in markup.inline_keyboard)
    row = await repo.get_user(10)
    assert row is not None and row.language_selected is False

    # The initial language callback bypasses the gate, saves the selection, then
    # runs forced membership and replaces the picker with the channel list.
    prompt_message = message
    query = FakeQuery(prompt_message, "l|ru")
    callback_update = _update(prompt_message, query=query)
    await bot_app.gate(callback_update, context)
    assert force_join.calls == 0
    await start_flow.on_lang(callback_update, context, "ru")

    row = await repo.get_user(10)
    assert row is not None and row.lang == "ru" and row.language_selected is True
    assert force_join.calls == 1
    gate_text, gate_kwargs = message.edits[-1]
    assert gate_text
    assert "m|joincheck" in _callback_data(gate_kwargs["reply_markup"])


@pytest.mark.asyncio
async def test_first_time_admin_skips_language_picker_and_gets_persian_menu(db):
    services = _services()
    context = _context(services)
    message = FakeMessage("/start")
    update = _update(message, user_id=999)

    await bot_app.gate(update, context)
    assert context.user_data["lang"] == "fa"
    await start_flow.cmd_start(update, context)

    body, kwargs = message.replies[-1]
    assert body != start_flow.LANGUAGE_PICKER_TEXT
    assert "Welcome to LeechX" not in body
    assert context.user_data["lang"] == "fa"
    markup = kwargs["reply_markup"]
    assert isinstance(markup, ReplyKeyboardMarkup)
    labels = {button.text for row in markup.keyboard for button in row}
    assert "📊 آمار" in labels
    assert all(text.t(code, "btn_lang") not in labels for code in text.LANG_ORDER)
    row = await repo.get_user(999)
    assert row is not None and row.language_selected is False


@pytest.mark.asyncio
async def test_admin_overrides_legacy_locale_and_blocks_stale_language_callback(db):
    services = _services()
    await repo.upsert_user(999, "admin999", "Admin", lang="ru")
    await repo.set_lang(999, "ru", selected=True)
    context = _context(services, lang="ru")
    message = FakeMessage("/start")
    update = _update(message, user_id=999)

    await bot_app.gate(update, context)
    assert context.user_data["lang"] == "fa"
    await start_flow.cmd_start(update, context)
    body, kwargs = message.replies[-1]
    assert "Welcome to LeechX" not in body
    assert isinstance(kwargs["reply_markup"], ReplyKeyboardMarkup)
    assert text.t("ru", "btn_lang") not in {
        button.text for row in kwargs["reply_markup"].keyboard for button in row
    }

    query = FakeQuery(message, "l|en")
    callback_update = _update(message, user_id=999, query=query)
    await bot_app.gate(callback_update, context)
    await start_flow.on_lang(callback_update, context, "en")
    assert context.user_data["lang"] == "fa"
    assert query.answers[-1][1] is True
    assert text.t("fa", "admin_lang_fixed") in query.answers[-1][0]
    row = await repo.get_user(999)
    assert row is not None and row.lang == "ru" and row.language_selected is True
    latest_body, latest_kwargs = message.replies[-1]
    assert text.t("fa", "admin_lang_fixed") in latest_body
    labels = {button.text for row in latest_kwargs["reply_markup"].keyboard for button in row}
    assert "📊 آمار" in labels
    assert all(text.t(code, "btn_lang") not in labels for code in text.LANG_ORDER)


@pytest.mark.asyncio
async def test_language_choice_opens_bot_after_membership_passes(db):
    force_join = FakeForceJoin()
    services = _services(force_join)
    context = _context(services, lang="en")
    await repo.upsert_user(20, "user20", "User", lang="en")

    message = FakeMessage("Choose your language")
    query = FakeQuery(message, "l|en")
    update = _update(message, user_id=20, query=query)
    await bot_app.gate(update, context)
    await start_flow.on_lang(update, context, "en")

    assert force_join.calls == 1
    assert "Welcome to LeechX" in message.replies[-1][0]
    markup = message.replies[-1][1]["reply_markup"]
    assert isinstance(markup, ReplyKeyboardMarkup)
    labels = {button.text for row in markup.keyboard for button in row}
    assert text.t("en", "btn_settings") in labels
    assert text.t("en", "btn_lang") in labels
    assert markup.is_persistent is True
    row = await repo.get_user(20)
    assert row is not None and row.language_selected is True


@pytest.mark.asyncio
async def test_unselected_user_message_gets_picker_not_channel_gate(db):
    force_join = FakeForceJoin([JoinTarget(123, "Required channel", username="required")])
    services = _services(force_join)
    context = _context(services)
    message = FakeMessage("hello")
    update = _update(message, user_id=30)

    with pytest.raises(ApplicationHandlerStop):
        await bot_app.gate(update, context)
    assert force_join.calls == 0
    prompt, kwargs = message.replies[-1]
    assert prompt == start_flow.LANGUAGE_PICKER_TEXT
    assert _callback_data(kwargs["reply_markup"]) == {"l|fa", "l|en", "l|ru"}


@pytest.mark.asyncio
async def test_user_settings_button_renders_and_language_shortcut_is_visible(db):
    services = _services()
    context = _context(services, lang="en")
    message = FakeMessage("Welcome")
    query = FakeQuery(message, "m|settings")
    update = _update(message, user_id=40, query=query)

    await start_flow.on_menu(update, context, "settings")

    rendered, kwargs = message.edits[-1]
    assert "settings" in rendered.lower()
    assert "English" in rendered
    assert __version__ in rendered
    assert "m|lang" in _callback_data(kwargs["reply_markup"])

    menu = kb.main_menu("en", admin=False)
    assert "m|lang" in _callback_data(menu)


@pytest.mark.asyncio
async def test_settings_preference_toggles_persist_for_each_user(db):
    services = _services()
    context = _context(services, lang="en")
    await repo.upsert_user(45, "user45", "User", lang="en")
    message = FakeMessage("Your settings")
    query = FakeQuery(message, "m|prefmode")
    update = _update(message, user_id=45, query=query)

    await start_flow.on_menu(update, context, "prefmode")
    row = await repo.get_user(45)
    assert row.default_mode == "document"
    assert "Default format" in message.edits[-1][0]
    assert "m|prefdest" in _callback_data(message.edits[-1][1]["reply_markup"])

    await start_flow.on_menu(update, context, "prefdest")
    row = await repo.get_user(45)
    assert row.default_mode == "document"
    assert row.default_destination == "link"


@pytest.mark.asyncio
async def test_change_language_callback_renders_settings_without_keyword_collision(db):
    services = _services()
    context = _context(services, lang="en")
    await repo.upsert_user(50, "user50", "User", lang="en")
    await repo.set_lang(50, "en", selected=True)
    message = FakeMessage("Choose your language")
    query = FakeQuery(message, "l|ru")
    update = _update(message, user_id=50, query=query)

    await start_flow.on_lang(update, context, "ru")

    assert "настройки" in message.edits[-1][0].lower()
    assert "Русский" in message.edits[-1][0]
    keyboard_notice, keyboard_kwargs = message.replies[-1]
    assert text.t("ru", "menu_updated") in keyboard_notice
    assert isinstance(keyboard_kwargs["reply_markup"], ReplyKeyboardMarkup)
    labels = {button.text for row in keyboard_kwargs["reply_markup"].keyboard for button in row}
    assert text.t("ru", "btn_status") in labels
    assert text.t("fa", "btn_status") not in labels
    row = await repo.get_user(50)
    assert row is not None and row.lang == "ru" and row.language_selected is True


@pytest.mark.asyncio
async def test_preview_exit_restores_persian_admin_mode_and_stale_buttons_do_not_prompt(db):
    services = _services()
    await repo.upsert_user(999, "admin999", "Admin", lang="ru")
    await repo.set_lang(999, "ru", selected=True)
    context = _context(services, lang="ru")
    context.user_data["preview"] = True
    context.user_data["is_admin"] = False
    message = FakeMessage(text.t("ru", "btn_preview_exit"))

    await text_router.on_text(_update(message, user_id=999), context)

    assert context.user_data["preview"] is False
    assert context.user_data["is_admin"] is True
    assert context.user_data["lang"] == "fa"
    body, kwargs = message.replies[-1]
    assert text.t("fa", "preview_exit_done") in body
    assert text.t("fa", "send_link_or_file") not in body
    labels = {
        button.text
        for row in kwargs["reply_markup"].keyboard
        for button in row
    }
    assert "📊 آمار" in labels
    assert all(text.t(code, "btn_lang") not in labels for code in text.LANG_ORDER)


@pytest.mark.asyncio
async def test_unselected_admin_can_exit_preview_through_callback_in_persian(db):
    services = _services(FakeForceJoin([JoinTarget(123, "Required", username="required")]))
    await repo.upsert_user(999, "admin999", "Admin", lang="ru")
    context = _context(services, lang="ru")
    context.user_data.update(preview=True, is_admin=False)
    message = FakeMessage("Preview")
    query = FakeQuery(message, "m|exitpreview")
    update = _update(message, user_id=999, query=query)

    await bot_app.gate(update, context)
    await start_flow.on_menu(update, context, "exitpreview")

    assert context.user_data["preview"] is False
    assert context.user_data["lang"] == "fa"
    assert services.force_join.calls == 0
    body, kwargs = message.replies[-1]
    assert text.t("fa", "preview_exit_done") in body
    labels = {button.text for row in kwargs["reply_markup"].keyboard for button in row}
    assert "📊 آمار" in labels
    assert all(text.t(code, "btn_lang") not in labels for code in text.LANG_ORDER)


@pytest.mark.asyncio
async def test_admin_language_button_is_rejected_in_persian_without_link_prompt(db):
    services = _services()
    context = _context(services, lang="en")
    context.user_data["is_admin"] = True
    message = FakeMessage(text.t("en", "btn_lang"))

    await text_router.on_text(_update(message, user_id=999), context)

    body, kwargs = message.replies[-1]
    assert text.t("fa", "admin_lang_fixed") in body
    assert context.user_data["lang"] == "fa"
    assert text.t("en", "send_link_or_file") not in body
    labels = {button.text for row in kwargs["reply_markup"].keyboard for button in row}
    assert "📊 آمار" in labels
    assert all(text.t(code, "btn_lang") not in labels for code in text.LANG_ORDER)


@pytest.mark.parametrize("language", ("en", "ru"))
def test_legacy_localized_admin_section_buttons_still_route(language):
    assert text_router._admin_section_for_label(text.t(language, "sec_stats")) == kb.SEC_STATS


def test_existing_sqlite_users_receive_migration_default_false():
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            conn.execute(sql_text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            conn.execute(sql_text("INSERT INTO users (id) VALUES (1)"))
            _migrate_user_language_selected(conn)
            value = conn.execute(
                sql_text(
                    "SELECT language_selected, uploads, default_mode, default_destination "
                    "FROM users WHERE id = 1"
                )
            ).one()
            assert value[0] in (False, 0)
            assert value[1:] == (0, "video", "telegram")
    finally:
        engine.dispose()
