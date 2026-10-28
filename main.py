"""LeechX — ربات لیچر تلگرام.

نقطهٔ ورود. اجرا:
    python main.py            # اجرای ربات
    python main.py --check    # فقط بررسی تنظیمات و اتصال دیتابیس
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import get_config  # noqa: E402
from app.logging_conf import setup_logging  # noqa: E402


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass

    cfg = get_config()
    setup_logging(cfg.log_level)

    problems = cfg.validate_runtime()
    if problems:
        for p in problems:
            print(f"✗ {p}", file=sys.stderr)
        print("\nفایل .env را کامل کن (نمونه: .env.example)", file=sys.stderr)
        return 2

    if "--check" in sys.argv:
        return asyncio.run(_check(cfg))

    from app.bot.app import run_bot

    run_bot(cfg)
    return 0


async def _check(cfg) -> int:
    from app.db.base import init_db

    print(f"• دیتابیس: {cfg.sqlalchemy_url}")
    print(f"• پوشهٔ داده: {cfg.data_dir}")
    print(f"• سرور لینک: {cfg.public_base_url}")
    print(f"• Local Bot API: {'فعال' if cfg.uses_local_api else 'غیرفعال'}")
    await init_db(cfg)
    print("✓ دیتابیس آماده است.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
