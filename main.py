"""LeechX — ربات لیچر تلگرام.

نقطهٔ ورود. اجرا:
    python main.py            # اجرای ربات
    python main.py --check    # فقط بررسی تنظیمات و اتصال دیتابیس
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import get_config, load_config  # noqa: E402
from app.logging_conf import setup_logging  # noqa: E402


def _ensure_token() -> bool:
    """اگر BOT_TOKEN نبود، همان اول اجرا از کاربر می‌گیرد و در .env ذخیره می‌کند."""
    if not sys.stdin or not sys.stdin.isatty():
        print("✗ BOT_TOKEN تنظیم نشده است. آن را در .env بگذار.", file=sys.stderr)
        return False
    print("🤖 برای راه‌اندازی فقط به توکن ربات نیاز است.")
    print("توکن را از @BotFather بگیر و اینجا وارد کن.")
    try:
        token = input("BOT_TOKEN: ").strip()
    except (EOFError, KeyboardInterrupt):
        return False
    if ":" not in token or len(token) < 20:
        print("✗ توکن نامعتبر است (باید شبیه 123456:ABC-DEF... باشد).", file=sys.stderr)
        return False

    env_path = Path(".env")
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.strip().startswith("BOT_TOKEN="):
            lines[index] = f"BOT_TOKEN={token}"
            replaced = True
            break
    if not replaced:
        lines.append(f"BOT_TOKEN={token}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass
    # اگر BOT_TOKEN در محیط (خالی) ست شده باشد، همان مقدار بر .env اولویت دارد.
    os.environ["BOT_TOKEN"] = token
    print(f"✓ توکن در {env_path.resolve()} ذخیره شد.")
    return True


async def _preload(cfg) -> None:
    """تنظیمات ذخیره‌شده در دیتابیس را قبل از ساخت اپلیکیشن اعمال می‌کند."""
    from app.db.base import dispose_db, init_db
    from app.services.runtime_settings import RuntimeSettings

    await init_db(cfg)
    try:
        settings = RuntimeSettings(cfg)
        await settings.load()
        settings.apply_to_config()
    finally:
        await dispose_db()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass

    cfg = get_config()
    if not cfg.bot_token.strip() and _ensure_token():
        cfg = load_config()
    setup_logging(cfg.log_level)

    problems = cfg.validate_runtime()
    if problems:
        for p in problems:
            print(f"✗ {p}", file=sys.stderr)
        print("\nفایل .env را کامل کن (نمونه: .env.example)", file=sys.stderr)
        return 2

    asyncio.run(_preload(cfg))

    if "--check" in sys.argv:
        return asyncio.run(_check(cfg))

    from app.bot.app import run_bot

    run_bot(cfg)
    return 0


async def _check(cfg) -> int:
    print(f"• دیتابیس: {cfg.sqlalchemy_url}")
    print(f"• پوشهٔ داده: {cfg.data_dir}")
    print(f"• سرور لینک: {cfg.public_base_url}")
    print(f"• Local Bot API: {'فعال' if cfg.uses_local_api else 'غیرفعال'}")
    print("✓ دیتابیس آماده است.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
