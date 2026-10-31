"""قانون «رسانهٔ بزرگسال» — تشخیص، شمارش معکوس و حذف خودکار.

هدف: وقتی ربات فایلی از یک سایت بزرگسال تحویل می‌دهد، همان فایل مدت کوتاهی
بعد از چت پاک شود تا محتوای NSFW در گروه/کانال نماند. برای اینکه کاربر فایل
را از دست ندهد، پیش از حذف یک نسخهٔ خصوصی به چت خودش فرستاده می‌شود
(تلگرام اجازه نمی‌دهد ربات مستقیم در «Saved Messages» کاربر پیام بگذارد).

این ماژول هیچ وابستگی به دیتابیس یا شبکه ندارد؛ فقط ``sleep`` و ``bot`` را
می‌گیرد، بنابراین با یک bot جعلی هم کامل تست می‌شود.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from urllib.parse import urlsplit

from telegram.constants import ParseMode
from telegram.error import TelegramError

from app.core import text
from app.services.sites import NSFW_EXTRACTORS, NSFW_HOST_WORDS, sites

log = logging.getLogger("leechx.nsfw")

DEFAULT_SECONDS = 30
MIN_SECONDS = 5
MAX_SECONDS = 600
# سقف نسخه‌های خصوصی؛ گالری‌های بزرگ نباید باعث flood شوند.
MAX_DM_COPIES = 30


def clamp_seconds(value: int | None) -> int:
    """زمان حذف را در بازهٔ امن نگه می‌دارد (پیش‌فرض ۳۰ ثانیه)."""
    try:
        seconds = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_SECONDS
    return max(MIN_SECONDS, min(MAX_SECONDS, seconds))


def is_nsfw_extractor(extractor: str | None) -> bool:
    """آیا نام اکسترکتور/سایت در فهرست بزرگسال است؟"""
    key = (extractor or "").strip().casefold()
    if not key:
        return False
    base = key.split(":", 1)[0]
    return base in NSFW_EXTRACTORS or any(word in base for word in NSFW_HOST_WORDS)


def looks_like_nsfw_url(url: str) -> bool:
    """تشخیص سریع از خودِ لینک، حتی وقتی ایندکس سایت‌ها در دسترس نیست."""
    raw = (url or "").strip().casefold()
    if not raw:
        return False
    try:
        host = urlsplit(raw).hostname or ""
    except ValueError:
        host = ""
    haystack = host or raw
    if any(word in haystack for word in NSFW_HOST_WORDS):
        return True
    # دامنه‌هایی مثل xnxx.com / e621.net که هیچ‌کدام از واژه‌های بالا را ندارند.
    return any(label in NSFW_EXTRACTORS for label in haystack.split("."))


def is_nsfw(url: str, extractor: str | None = None) -> bool:
    """تشخیص محتوای بزرگسال از روی لینک یا اکسترکتور.

    شکستِ ایندکس سایت‌ها هرگز نباید تحویل فایل را متوقف کند؛ در آن حالت فقط
    الگوی میزبان بررسی می‌شود.
    """
    if is_nsfw_extractor(extractor):
        return True
    try:
        if sites.is_nsfw_url(url):
            return True
    except Exception:  # noqa: BLE001 — تشخیص نباید جریان را بشکند
        log.debug("nsfw url check failed", exc_info=True)
    return looks_like_nsfw_url(url)


async def cleanup_messages(
    bot,
    *,
    chat_id: int,
    user_id: int,
    message_ids: Sequence[int],
    lang: str,
    seconds: int,
    copy_dm: bool,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """اعلان زیر فایل، شمارش معکوس، و حذف فایل‌ها بعد از ``seconds`` ثانیه.

    ``sleep`` قابل تزریق است تا در تست‌ها بدون انتظار واقعی اجرا شود.
    """
    ids = [int(mid) for mid in message_ids if mid]
    if not ids or bot is None:
        return
    seconds = clamp_seconds(seconds)

    # ۱) نسخهٔ خصوصی، پیش از حذف — کاربر می‌تواند همان‌جا ذخیره/فوروارد کند.
    dm_sent = 0
    if copy_dm and chat_id != user_id:
        for mid in ids[:MAX_DM_COPIES]:
            try:
                await bot.copy_message(
                    chat_id=user_id, from_chat_id=chat_id, message_id=mid
                )
                dm_sent += 1
            except TelegramError as exc:
                # معمولاً یعنی کاربر ربات را بلاک کرده یا چت خصوصی ندارد.
                log.info("private nsfw copy stopped: %s", exc)
                break

    # ۲) اعلان زیر خود فایل.
    notice = None
    dm_line = text.t(lang, "nsfw_autodelete_dm_line") if dm_sent else ""
    try:
        notice = await bot.send_message(
            chat_id=chat_id,
            text=text.t(lang, "nsfw_autodelete_notice", seconds=seconds, dm_line=dm_line),
            parse_mode=ParseMode.HTML,
            reply_to_message_id=ids[0],
            allow_sending_without_reply=True,
        )
    except TelegramError:
        log.info("nsfw notice could not be sent", exc_info=True)

    # ۳) شمارش معکوس (حداکثر هر ۱۰ ثانیه یک ویرایش تا به flood نخوریم).
    step = max(1, min(10, seconds // 5 or 1))
    remaining = seconds
    while remaining > 0:
        chunk = min(step, remaining)
        await sleep(chunk)
        remaining -= chunk
        if remaining <= 0 or notice is None:
            continue
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=notice.message_id,
                text=text.t(lang, "nsfw_autodelete_countdown", seconds=remaining),
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            notice = None  # پیام پاک شده؛ فقط حذف فایل را ادامه بده

    # ۴) حذف واقعی. پارت‌های آلبوم با حذف اولین پیام هم پاک می‌شوند؛ خطای
    # «پیام پیدا نشد» بی‌خطر است.
    for mid in ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except TelegramError:
            pass

    if notice is not None:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=notice.message_id,
                text=text.t(lang, "nsfw_autodelete_done"),
                parse_mode=ParseMode.HTML,
            )
        except TelegramError:
            pass
