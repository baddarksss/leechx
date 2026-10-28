"""راه‌اندازی لاگ‌ها — خروجی ساختاریافته و کوتاه برای خواندن در Railway/Docker."""
from __future__ import annotations

import logging
import sys


class _ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)-18s %(message)s", "%H:%M:%S")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        if not self.use_color:
            return text
        color = self.COLORS.get(record.levelname, "")
        return f"{color}{text}{self.RESET}" if color else text


def setup_logging(level: str = "INFO") -> None:
    use_color = sys.stderr.isatty()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_ColorFormatter(use_color))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, str(level or "INFO").upper(), logging.INFO))

    for noisy in ("telegram", "telegram.ext", "httpx", "aiohttp.access", "yt_dlp", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
