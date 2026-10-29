"""روتر پیام‌های متنی: حالت ادمین/تغییر نام → لینک → راهنما."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards as kb
from app.bot.common import DRAFT_SLOT, drop_user_input, lang_of, panel, reply, run_detached
from app.bot.flows import admin as admin_flow
from app.bot.flows import link as link_flow
from app.bot.flows import start as start_flow
from app.bot.states import (
    ADMIN_STATES,
    ST_CONTACT,
    ST_DEPLOY_ZIP,
    ST_RENAME,
    ST_THUMBNAIL,
    clear_state,
    get_state,
)
from app.core import text, urlcheck

log = logging.getLogger("leechx.text")

_LEGACY_USER_KEYBOARD_ACTIONS = {
    "fa": {
        "🌐 سایت‌های پشتیبانی": "sites",
        "📖 راهنما": "help",
        "📊 وضعیت من": "status",
        "🌍 تغییر زبان": "lang",
        "✉️ ارتباط با ادمین": "contact",
        "⌨️ بستن کیبورد": "kbclose",
    },
    "en": {
        "🌐 Supported sites": "sites",
        "📖 Help": "help",
        "📊 My status": "status",
        "🌍 Change language": "lang",
        "✉️ Contact admin": "contact",
        "⌨️ Close keyboard": "kbclose",
    },
    "ru": {
        "🌐 Поддерживаемые сайты": "sites",
        "📖 Помощь": "help",
        "📊 Мой статус": "status",
        "🌍 Сменить язык": "lang",
        "✉️ Связаться с админом": "contact",
        "⌨️ Закрыть клавиатуру": "kbclose",
    },
}


def _admin_section_for_label(label: str) -> str | None:
    """Resolve current admin buttons and the removed cancel shortcut in old keyboards."""
    for language in text.LANG_ORDER:
        for section, translated in kb.persistent_admin_labels(language).items():
            if label == translated:
                return section
        if label == text.t(language, "sec_cancel"):
            # Legacy keyboards kept after an update remain harmless: this only cancels
            # the admin's own jobs/forms, never tasks belonging to other users.
            return kb.SEC_CANCEL
    return None


def _user_action_for_label(label: str, *, preview: bool) -> str | None:
    """Resolve current and stale reply-keyboard text in any supported language."""
    for language in text.LANG_ORDER:
        for action, translated in kb.user_persistent_labels(language, preview=preview).items():
            if label == translated:
                return action
    for legacy in _LEGACY_USER_KEYBOARD_ACTIONS.values():
        if label in legacy:
            return legacy[label]
    # Old preview keyboards can remain visible in Telegram after the admin has
    # already exited; recognize that button too, so it never falls through as text.
    if any(label == text.t(language, "btn_preview_exit") for language in text.LANG_ORDER):
        return "exitpreview"
    return None


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return

    if context.user_data.get("is_admin"):
        section = _admin_section_for_label(message.text)
        if section is not None:
            clear_state(context)
            try:
                await admin_flow.show_section(update, context, section)
            finally:
                await drop_user_input(update)
            return

    # A persistent user keyboard may still be visible on a client after role or
    # language changes (notably when leaving preview). Resolve its labels for staff
    # as well, so stale buttons never fall through to the generic link prompt.
    action = _user_action_for_label(
        message.text,
        preview=bool(context.user_data.get("preview")),
    )
    if action is not None:
        clear_state(context)
        try:
            await start_flow.on_user_menu(update, context, action)
        finally:
            await drop_user_input(update)
        return

    state = get_state(context)
    if state == ST_RENAME:
        await link_flow.handle_rename(update, context)
        await drop_user_input(update)
        return
    if state == ST_THUMBNAIL:
        await panel(update, context, text.t(lang_of(context), "thumbnail_prompt"), slot=DRAFT_SLOT)
        await drop_user_input(update)
        return
    if state == ST_CONTACT:
        await start_flow.handle_contact(update, context)
        return
    if state == ST_DEPLOY_ZIP:
        await panel(update, context, text.t(lang_of(context), "deploy_upload_prompt"))
        await drop_user_input(update)
        return
    if state in ADMIN_STATES:
        try:
            await admin_flow.handle_state(update, context, state)
        finally:
            # ورودی فرم (مثلاً کوکی یا مقدار تنظیمات) نباید در چت بماند.
            await drop_user_input(update)
        return
    if state:
        clear_state(context)

    urls = urlcheck.extract_urls(message.text)
    if not urls:
        lang = lang_of(context)
        await reply(update, text.t(lang, "send_link_or_file"))
        return

    if len(urls) > 1:
        lang = lang_of(context)
        await reply(update, text.t(lang, "playlist_detected"))

    # بررسی لینک (yt-dlp) ممکن است چند ثانیه طول بکشد؛ خارج از قفل کاربر اجرا
    # می‌شود تا دکمه‌های همین کاربر در این مدت فوراً جواب بدهند.
    await run_detached(context, link_flow.handle_link(update, context, urls[0]), update)
