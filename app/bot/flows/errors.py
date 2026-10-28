"""هندلر خطای سراسری — هیچ خطایی نباید سکوت کند."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.common import lang_of, reply
from app.core import human, text

log = logging.getLogger("leechx.errors")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("unhandled error", exc_info=context.error)
    if not isinstance(update, Update) or update.effective_message is None:
        return
    try:
        lang = lang_of(context) if context.user_data is not None else text.DEFAULT_LANG
    except Exception:  # noqa: BLE001
        lang = text.DEFAULT_LANG
    reason = human.esc(str(context.error)[:120]) if context.error else "unknown"
    await reply(update, text.t(lang, "failed", reason=reason))
