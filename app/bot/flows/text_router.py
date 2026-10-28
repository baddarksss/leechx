"""روتر پیام‌های متنی: حالت ادمین → لینک → راهنما."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.common import lang_of, reply
from app.bot.flows import admin as admin_flow
from app.bot.flows import link as link_flow
from app.bot.states import get_state
from app.core import text, urlcheck

log = logging.getLogger("leechx.text")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not message.text:
        return

    state = get_state(context)
    if state:
        await admin_flow.handle_state(update, context, state)
        return

    urls = urlcheck.extract_urls(message.text)
    if not urls:
        lang = lang_of(context)
        await reply(update, text.t(lang, "send_link_or_file"))
        return

    if len(urls) > 1:
        lang = lang_of(context)
        await reply(update, text.t(lang, "playlist_detected"))

    await link_flow.handle_link(update, context, urls[0])
