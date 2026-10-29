"""پیش‌نمایش کاربر و گیت عضویت اجباری در سطح هر آپدیت."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop

from app.bot import app as app_module
from app.bot import guards
from app.core import text
from app.db import repo
from app.services.force_join import ForceJoin, JoinTarget
from app.services.runtime_settings import RuntimeSettings


class Message:
    def __init__(self):
        self.texts: list[str] = []
        self.markups: list = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)
        self.markups.append(kwargs.get("reply_markup"))
        return self


class GateBot:
    def __init__(self, status: str = "left") -> None:
        self.status = status
        self.calls = 0

    async def get_chat_member(self, chat_id, user_id):
        self.calls += 1
        if self.status == "error":
            raise TelegramError("boom")
        return SimpleNamespace(status=self.status, is_member=False)


def make_update(user_id: int = 42, *, language_code: str = "ru", query=None):
    message = Message()
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=user_id, is_bot=False, username="u", first_name="U", language_code=language_code
        ),
        effective_chat=SimpleNamespace(id=user_id, type="private"),
        effective_message=message,
        callback_query=query,
    )


def make_context(services, bot, lang="fa", **user_data):
    data = {} if lang is None else {"lang": lang}
    data.update(user_data)
    return SimpleNamespace(
        bot_data={"services": services},
        user_data=data,
        bot=bot,
    )


# ── preview / admin guards ─────────────────────────────────
@pytest.mark.asyncio
async def test_preview_mode_disables_admin_power(db):
    context = make_context(SimpleNamespace(cfg=db), bot=None, preview=True, is_admin=False)
    update = make_update(1)

    assert await guards.require_admin(update, context) is False
    assert update.effective_message.texts == [text.t("fa", "preview_blocked")]
    assert guards.in_preview(context) is True
    assert guards.current_admin(context) is False


@pytest.mark.asyncio
async def test_staff_without_preview_is_admin(db):
    context = make_context(SimpleNamespace(cfg=db), bot=None)
    update = make_update(1)

    assert await guards.require_admin(update, context) is True
    assert context.user_data["is_admin"] is True
    assert guards.current_admin(context) is True


@pytest.mark.asyncio
async def test_non_admin_is_rejected(db):
    context = make_context(SimpleNamespace(cfg=db), bot=None)
    update = make_update(42)

    assert await guards.require_admin(update, context) is False
    assert update.effective_message.texts


# ── force-join gate ────────────────────────────────────────
async def make_gate(db, *, enabled: bool = True, status: str = "left"):
    settings = RuntimeSettings(db)
    await settings.load()
    await settings.set("force_join_enabled", enabled)
    await settings.set(
        "force_join_chats",
        json.dumps([JoinTarget(100, "Required channel", username="required").to_json()]),
    )
    services = SimpleNamespace(
        cfg=db,
        settings=settings,
        force_join=ForceJoin(settings),
    )
    return services, GateBot(status)


@pytest.mark.asyncio
async def test_gate_blocks_user_who_has_not_joined(db):
    services, bot = await make_gate(db)
    await repo.upsert_user(42, "u", "U", lang="en")
    await repo.set_lang(42, "en", selected=True)
    update = make_update(42)
    context = make_context(services, bot)

    with pytest.raises(ApplicationHandlerStop):
        await app_module.gate(update, context)

    assert bot.calls == 1
    assert update.effective_message.texts
    markup = update.effective_message.markups[-1]
    data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "m|joincheck" in data


@pytest.mark.asyncio
async def test_gate_allows_joined_user(db):
    services, bot = await make_gate(db, status="member")
    await repo.upsert_user(42, "u", "U", lang="en")
    await repo.set_lang(42, "en", selected=True)
    update = make_update(42)
    context = make_context(services, bot)

    await app_module.gate(update, context)  # بدون استثنا
    assert update.effective_message.texts == []


@pytest.mark.asyncio
async def test_gate_fails_open_when_telegram_errors(db):
    services, bot = await make_gate(db, status="error")
    await repo.upsert_user(42, "u", "U", lang="en")
    await repo.set_lang(42, "en", selected=True)
    update = make_update(42)
    context = make_context(services, bot)

    await app_module.gate(update, context)
    assert update.effective_message.texts == []


@pytest.mark.asyncio
async def test_gate_exempts_staff_but_not_staff_in_preview(db):
    services, bot = await make_gate(db)

    staff_update = make_update(1)
    staff_context = make_context(services, bot)
    await app_module.gate(staff_update, staff_context)
    assert staff_update.effective_message.texts == []
    assert bot.calls == 0
    await repo.set_lang(1, "en", selected=True)

    preview_update = make_update(1)
    preview_context = make_context(services, bot, preview=True)
    with pytest.raises(ApplicationHandlerStop):
        await app_module.gate(preview_update, preview_context)
    assert bot.calls == 1


@pytest.mark.asyncio
async def test_gate_lets_join_check_callback_through(db):
    services, bot = await make_gate(db)
    await repo.upsert_user(42, "u", "U", lang="en")
    await repo.set_lang(42, "en", selected=True)
    query = SimpleNamespace(data="m|joincheck")

    async def answer(*args, **kwargs):
        return None

    query.answer = answer
    update = make_update(42, query=query)
    update.callback_query = query
    context = make_context(services, bot)

    await app_module.gate(update, context)
    assert update.effective_message.texts == []


@pytest.mark.asyncio
async def test_gate_detects_language_on_first_message(db):
    settings = RuntimeSettings(db)
    await settings.load()
    await settings.set("force_join_enabled", False)
    services = SimpleNamespace(cfg=db, settings=settings, force_join=ForceJoin(settings))
    update = make_update(500, language_code="ru")
    context = make_context(services, GateBot(), lang=None)

    with pytest.raises(ApplicationHandlerStop):
        await app_module.gate(update, context)

    user = await repo.get_user(500)
    assert user is not None
    assert user.lang == "ru"
    assert user.language_selected is False
    assert context.user_data["lang"] == "ru"
    assert update.effective_message.texts
    assert "Выбери язык" in update.effective_message.texts[-1]


@pytest.mark.asyncio
async def test_banned_user_is_stopped(db):
    settings = RuntimeSettings(db)
    await settings.load()
    await settings.set("force_join_enabled", False)
    await repo.upsert_user(501, "banned", "B")
    await repo.set_banned(501, True)
    services = SimpleNamespace(cfg=db, settings=settings, force_join=ForceJoin(settings))
    update = make_update(501)
    context = make_context(services, GateBot())

    with pytest.raises(ApplicationHandlerStop):
        await app_module.gate(update, context)
    assert update.effective_message.texts


@pytest.mark.asyncio
async def test_maintenance_blocks_users_but_not_staff(db):
    settings = RuntimeSettings(db)
    await settings.load()
    await settings.set("force_join_enabled", False)
    await settings.set("maintenance", True)
    services = SimpleNamespace(cfg=db, settings=settings, force_join=ForceJoin(settings))

    user_update = make_update(502)
    with pytest.raises(ApplicationHandlerStop):
        await app_module.gate(user_update, make_context(services, GateBot()))

    staff_update = make_update(1)
    await app_module.gate(staff_update, make_context(services, GateBot()))
    assert staff_update.effective_message.texts == []


# ── زبان ادمین ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_admin_ui_is_always_persian(db):
    """ادمین همیشه فارسی می‌بیند، حتی اگر زبان دیگری ذخیره شده باشد."""
    services, bot = await make_gate(db, enabled=False)
    await repo.upsert_user(1, "owner", "O")
    await repo.set_lang(1, "en")

    update = make_update(1, language_code="en")
    context = make_context(services, bot, lang="en")
    await app_module.gate(update, context)
    assert context.user_data["lang"] == "fa"

    # در پیش‌نمایش کاربر، ادمین مثل یک کاربر عادی است و زبانش عوض نمی‌شود.
    preview_update = make_update(1, language_code="en")
    preview_context = make_context(services, bot, lang="en", preview=True)
    await app_module.gate(preview_update, preview_context)
    assert preview_context.user_data["lang"] == "en"


@pytest.mark.asyncio
async def test_admin_cannot_change_language(db):
    from app.bot.flows import start as start_flow

    services = SimpleNamespace(cfg=db)
    await repo.upsert_user(1, "owner", "O")
    await repo.set_lang(1, "fa")

    answered: list[str] = []

    async def answer(body=None, **kwargs):
        answered.append(body or "")

    query = SimpleNamespace(data="l|en", answer=answer)
    update = make_update(1, query=query)
    context = make_context(services, bot=None, lang="fa")
    await start_flow.on_lang(update, context, "en")

    assert context.user_data["lang"] == "fa"
    assert (await repo.get_user(1)).lang == "fa"
    assert answered == [text.t("fa", "admin_lang_fixed")]


@pytest.mark.asyncio
async def test_admin_lang_command_points_to_user_only(db):
    from app.bot.flows import start as start_flow

    services = SimpleNamespace(cfg=db)
    update = make_update(1)
    context = make_context(services, bot=None)
    await start_flow.cmd_lang(update, context)

    assert update.effective_message.texts == [text.t("fa", "admin_lang_fixed")]
    markup = update.effective_message.markups[-1]
    assert hasattr(markup, "keyboard")  # کیبورد ثابت ادمین

    # کاربر عادی همچنان منوی انتخاب زبان را می‌گیرد.
    user_update = make_update(42)
    await start_flow.cmd_lang(user_update, make_context(services, bot=None))
    assert hasattr(user_update.effective_message.markups[-1], "inline_keyboard")
