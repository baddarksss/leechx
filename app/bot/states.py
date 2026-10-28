"""وضعیت‌های گفت‌وگو (به‌جای ConversationHandler، ساده و قابل‌توسعه)."""
from __future__ import annotations

from telegram.ext import ContextTypes

ST_BROADCAST = "broadcast"
ST_ADD_ADMIN = "add_admin"
ST_SET_VALUE = "set_value"
ST_LOOKUP_USER = "lookup_user"


def set_state(context: ContextTypes.DEFAULT_TYPE, state: str, **data) -> None:
    context.user_data["state"] = state
    context.user_data["state_data"] = data


def get_state(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    return context.user_data.get("state")


def get_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.get("state_data") or {}


def clear_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("state", None)
    context.user_data.pop("state_data", None)
