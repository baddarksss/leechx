"""هندلر خطای سراسری — هیچ خطایی نباید سکوت کند."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest, Forbidden, NetworkError
from telegram.ext import ContextTypes

from app.bot.common import lang_of, reply, safe_answer
from app.core import human, text

log = logging.getLogger("leechx.errors")


def _is_benign(error: BaseException | None) -> bool:
    """خطاهای گذرای تلگرام که نباید پیام خطا جلوی کاربر بگذارند."""
    if isinstance(error, (NetworkError, Forbidden)):  # TimedOut زیرکلاس NetworkError است
        return True
    if isinstance(error, BadRequest):
        message = str(error).lower()
        return any(part in message for part in (
            "message is not modified",
            "query is too old",
            "query id is invalid",
            "message to delete not found",
            "message to edit not found",
            "message can't be deleted",
        ))
    return False


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _is_benign(context.error):
        log.warning("telegram transient error: %s", context.error)
        return
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
    # متن خام استثنا ممکن است مسیر فایل یا آدرس داخلی را لو بدهد؛ فقط نوع خطا نمایش داده می‌شود.
    reason = human.esc(type(context.error).__name__) if context.error else "unknown"
    if update.callback_query is not None:
        await safe_answer(update.callback_query, text.t(lang, "failed", reason=reason), alert=True)
        return
    await reply(update, text.t(lang, "failed", reason=reason))
