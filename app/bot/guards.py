"""کنترل دسترسی — با پشتیبانی از «حالت پیش‌نمایش کاربر»."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.core import text
from app.db import repo

if TYPE_CHECKING:
    from app.container import Services

log = logging.getLogger("leechx.guards")


def is_owner(cfg, user_id: int) -> bool:
    return user_id in cfg.owners


async def is_staff(cfg, user_id: int) -> bool:
    """ادمین واقعی (بدون توجه به حالت پیش‌نمایش)."""
    if user_id in cfg.owners or user_id in cfg.extra_admins:
        return True
    try:
        return await repo.is_db_admin(user_id)
    except Exception:  # noqa: BLE001
        log.debug("admin lookup failed", exc_info=True)
        return False


# نام قدیمی برای سازگاری با کد موجود.
async def is_admin(cfg, user_id: int) -> bool:
    return await is_staff(cfg, user_id)


def in_preview(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get("preview"))


def current_admin(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """ادمین مؤثر: در حالت پیش‌نمایش، دسترسی مدیریتی خاموش است."""
    return bool(context.user_data.get("is_admin")) and not in_preview(context)


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """اگر کاربر ادمین نباشد، پیام مناسب می‌فرستد و False برمی‌گرداند."""
    user = update.effective_user
    services: Services = context.bot_data["services"]
    lang = context.user_data.get("lang", text.DEFAULT_LANG)
    if user and await is_staff(services.cfg, user.id):
        if not in_preview(context):
            context.user_data["is_admin"] = True
            return True
        await _deny(update, text.t(lang, "preview_blocked"))
        return False

    await _deny(update, text.t(lang, "admin_only"))
    return False


async def _deny(update: Update, body: str) -> None:
    """برای دکمه‌ها هشدار کوچک (بدون پیام تازه)؛ برای پیام متنی پاسخ کوتاه."""
    query = getattr(update, "callback_query", None)
    if query is not None:
        from app.bot.common import safe_answer

        await safe_answer(query, body, alert=True)
        return
    message = update.effective_message
    if message is None:
        return
    try:
        await message.reply_text(body)
    except TelegramError:
        log.debug("could not send access-denied notice", exc_info=True)


def admin_ids_sync(cfg) -> set[int]:
    return set(cfg.owners) | set(cfg.extra_admins)
