"""کمکی‌های مشترک هندلرها."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.core import human, text

if TYPE_CHECKING:
    from app.container import Services


def services(context: ContextTypes.DEFAULT_TYPE) -> Services:
    return context.bot_data["services"]


def lang_of(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang") or text.DEFAULT_LANG


def fmt_ts(ts: int | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


async def reply(update: Update, body: str, **kwargs) -> Message | None:
    msg = update.effective_message
    if msg is None:
        return None
    kwargs.setdefault("parse_mode", ParseMode.HTML)
    kwargs.setdefault("disable_web_page_preview", True)
    try:
        return await msg.reply_text(body, **kwargs)
    except TelegramError:
        return None


async def edit(message: Message | None, body: str, **kwargs) -> None:
    if message is None:
        return
    kwargs.setdefault("parse_mode", ParseMode.HTML)
    kwargs.setdefault("disable_web_page_preview", True)
    try:
        await message.edit_text(body, **kwargs)
    except TelegramError:
        pass


async def safe_answer(query, body: str | None = None, alert: bool = False) -> None:
    try:
        await query.answer(body, show_alert=alert)
    except TelegramError:
        pass


def user_display(first: str | None, username: str | None, uid: int) -> str:
    name = human.esc(first or "")
    handle = f"@{human.esc(username)}" if username else "—"
    return f"{name} ({handle}, <code>{uid}</code>)"


def quality_line(draft_title: str) -> str:
    return human.esc(draft_title)
