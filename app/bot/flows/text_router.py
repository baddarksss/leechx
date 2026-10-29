"""روتر پیام‌های متنی: حالت ادمین/تغییر نام → لینک → راهنما."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.common import lang_of, reply, services
from app.bot import keyboards as kb
from app.bot.flows import user_links as links_flow
from app.bot.flows import admin as admin_flow
from app.bot.flows import link as link_flow
from app.bot.flows import start as start_flow
from app.bot.states import ADMIN_STATES, ST_CONTACT, ST_RENAME, clear_state, get_state
from app.core import text, urlcheck

log = logging.getLogger("leechx.text")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return

    labels = kb.persistent_admin_labels(lang_of(context))
    if context.user_data.get("is_admin") and message.text in labels.values():
        clear_state(context)
        key = next(k for k, v in labels.items() if v == message.text)
        if key == "panel":
            await admin_flow.show_panel(update, context)
        elif key == "stats":
            await reply(update, await admin_flow._render_stats(context),
                        reply_markup=kb.admin_menu(lang_of(context)))
        elif key == "jobs":
            await reply(update, await admin_flow._render_jobs(),
                        reply_markup=kb.admin_menu(lang_of(context)))
        elif key == "settings":
            svc = services(context)
            await reply(update, admin_flow._render_settings(context),
                        reply_markup=kb.settings_menu(lang_of(context), svc.settings.snapshot()))
        elif key == "reports":
            await admin_flow._render_reports(update, context)
        elif key == "links":
            await links_flow.cmd_links(update, context)
        elif key == "cancel":
            await start_flow.cmd_cancel(update, context)
        elif key == "home":
            await start_flow.cmd_start(update, context)
        return

    state = get_state(context)
    if state == ST_RENAME:
        await link_flow.handle_rename(update, context)
        return
    if state == ST_CONTACT:
        await start_flow.handle_contact(update, context)
        return
    if state in ADMIN_STATES:
        await admin_flow.handle_state(update, context, state)
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

    await link_flow.handle_link(update, context, urls[0])
