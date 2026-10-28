"""کنترل دسترسی."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from app.core import text
from app.db import repo

if TYPE_CHECKING:
    from app.container import Services

log = logging.getLogger("leechx.guards")


def is_owner(cfg, user_id: int) -> bool:
    return user_id in cfg.owners


async def is_admin(cfg, user_id: int) -> bool:
    if user_id in cfg.owners or user_id in cfg.extra_admins:
        return True
    try:
        return await repo.is_db_admin(user_id)
    except Exception:  # noqa: BLE001
        log.debug("admin lookup failed", exc_info=True)
        return False


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """اگر کاربر ادمین نباشد، پیام مناسب می‌فرستد و False برمی‌گرداند."""
    user = update.effective_user
    services: Services = context.bot_data["services"]
    if user and await is_admin(services.cfg, user.id):
        return True
    lang = context.user_data.get("lang", text.DEFAULT_LANG)
    msg = update.effective_message
    if msg is not None:
        await msg.reply_text(text.t(lang, "admin_only"))
    return False


def admin_ids_sync(cfg) -> set[int]:
    return set(cfg.owners) | set(cfg.extra_admins)
