"""Telegram Bot API native inline-button styling support."""
from __future__ import annotations

import re
from importlib.metadata import version

from telegram import InlineKeyboardButton


def test_installed_telegram_library_serializes_native_button_style():
    installed = version("python-telegram-bot")
    match = re.match(r"^(\d+)\.(\d+)", installed)
    assert match is not None, f"could not parse python-telegram-bot version {installed}"
    assert tuple(map(int, match.groups())) >= (22, 7), (
        f"native button styles require python-telegram-bot >=22.7; found {installed}"
    )

    for style in ("primary", "success"):
        button = InlineKeyboardButton("Styled", callback_data="test", style=style)
        assert button.to_dict()["style"] == style
