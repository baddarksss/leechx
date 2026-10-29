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
    user_id = None
    if isinstance(update, Update) and update.effective_user is not None:
        user_id = update.effective_user.id

    services = context.bot_data.get("services")
    hub = getattr(services, "admin_group", None) if services is not None else None
    if hub is not None:
        try:
            await hub.record_log(
                "ERROR",
                "handler",
                f"{type(context.error).__name__} (details retained in server logs)",
                user_id,
            )
        except Exception:  # noqa: BLE001 — ثبت خطا نباید خطای دیگری بسازد
            log.debug("could not record handler error", exc_info=True)

    if not isinstance(update, Update) or update.effective_message is None:
        return
    try:
        lang = lang_of(context) if context.user_data is not None else text.DEFAULT_LANG
    except Exception:  # noqa: BLE001
        lang = text.DEFAULT_LANG
    reason = human.esc(str(context.error)[:120]) if context.error else "unknown"
    await reply(update, text.t(lang, "failed", reason=reason))
