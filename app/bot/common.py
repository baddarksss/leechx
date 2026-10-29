"""کمکی‌های مشترک هندلرها.

«پنل»: هر کاربر یک پیام منوی شیشه‌ای دارد که به‌جای ارسال پیام تازه ویرایش می‌شود.
دکمه‌های کیبورد ثابت و ورودی فرم‌ها بعد از پردازش از چت پاک می‌شوند تا چت خلوت بماند.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
from collections import OrderedDict
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from telegram import InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

from app.core import human, text

if TYPE_CHECKING:
    from app.container import Services

log = logging.getLogger("leechx.common")

PANEL_KEY = "panel"  # {"chat": id, "id": message_id, "tail": آخرین پیامِ متعلق به زنجیرهٔ پنل}
HOME_KEY = "home_msg"  # (chat_id, message_id) پیامی که کیبورد ثابت را نگه می‌دارد
DRAFT_SLOT = "draft_panel"  # پیام جریان لینک (تغییر نام/کاور)؛ جدا از منو تا منو آن را پاک نکند

# شناسهٔ callbackهای پاسخ‌داده‌شده؛ تلگرام فقط یک answer قبول می‌کند.
_ANSWERED: OrderedDict[str, None] = OrderedDict()
_ANSWER_LOCKS: OrderedDict[str, asyncio.Lock] = OrderedDict()
_ANSWERED_MAX = 4096
_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def services(context: ContextTypes.DEFAULT_TYPE) -> Services:
    return context.bot_data["services"]


def lang_of(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang") or text.DEFAULT_LANG


def fmt_ts(ts: int | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


def _is_inline(markup: Any) -> bool:
    return markup is None or isinstance(markup, InlineKeyboardMarkup)


def _not_modified(exc: Exception) -> bool:
    return "not modified" in str(exc).lower()


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


async def edit(message: Message | None, body: str, **kwargs) -> Message | None:
    """ویرایش امن؛ در صورت موفقیت (یا «تغییری نکرد») خود پیام را برمی‌گرداند، وگرنه None."""
    if message is None:
        return None
    if not _is_inline(kwargs.get("reply_markup")):
        # پیام ویرایشی فقط کیبورد شیشه‌ای می‌پذیرد؛ کیبورد ثابت باید با پیام تازه بیاید.
        kwargs.pop("reply_markup", None)
    kwargs.setdefault("parse_mode", ParseMode.HTML)
    kwargs.setdefault("disable_web_page_preview", True)
    try:
        await message.edit_text(body, **kwargs)
        return message
    except BadRequest as exc:
        if _not_modified(exc):
            return message
        if getattr(message, "caption", None) is None:
            return None
        # پیام رسانه‌ای (فایل/ویدیو) متن ندارد؛ کپشن را ویرایش می‌کنیم.
        try:
            await message.edit_caption(
                caption=body[:1024],
                parse_mode=kwargs.get("parse_mode"),
                reply_markup=kwargs.get("reply_markup"),
            )
            return message
        except BadRequest as caption_exc:
            return message if _not_modified(caption_exc) else None
        except TelegramError:
            return None
    except TelegramError:
        return None


async def safe_answer(query, body: str | None = None, alert: bool = False) -> bool:
    """پاسخ callback را فقط پس از موفقیت ثبت می‌کند و فراخوانی هم‌زمان را همگام می‌سازد."""
    if query is None:
        return False
    if body:
        # پاسخ callback متن ساده است؛ تگ‌های HTML متن‌های مشترک را حذف می‌کنیم. سقف ۲۰۰ نویسه.
        body = html.unescape(_TAG_RE.sub("", body))[:200]

    query_id = getattr(query, "id", None)
    if query_id is None:
        try:
            await query.answer(body, show_alert=alert)
            return True
        except TelegramError:
            return False

    key = str(query_id)
    if key in _ANSWERED:
        return False
    lock = _ANSWER_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _ANSWER_LOCKS[key] = lock
        # Keep the rare failed-answer locks bounded without evicting a lock in use.
        if len(_ANSWER_LOCKS) > _ANSWERED_MAX:
            for old_key, old_lock in tuple(_ANSWER_LOCKS.items()):
                if old_key != key and not old_lock.locked():
                    _ANSWER_LOCKS.pop(old_key, None)
                    if len(_ANSWER_LOCKS) <= _ANSWERED_MAX:
                        break
    else:
        _ANSWER_LOCKS.move_to_end(key)

    async with lock:
        if key in _ANSWERED:
            return False
        try:
            await query.answer(body, show_alert=alert)
        except TelegramError:
            # Do not memoize failures: the handler's finalizer/watchdog may retry.
            return False
        _ANSWERED[key] = None
        _ANSWERED.move_to_end(key)
        while len(_ANSWERED) > _ANSWERED_MAX:
            expired, _ = _ANSWERED.popitem(last=False)
            old_lock = _ANSWER_LOCKS.get(expired)
            if old_lock is not None and not old_lock.locked():
                _ANSWER_LOCKS.pop(expired, None)
        return True


# ── پنل تک‌پیامی ───────────────────────────────────────────
def _is_private(update: Update) -> bool:
    chat = getattr(update, "effective_chat", None)
    return chat is not None and getattr(chat, "type", None) == "private"


def _remember_panel(context, message: Message | None, slot: str = PANEL_KEY) -> None:
    if message is None or getattr(message, "message_id", None) is None:
        return
    chat_id = getattr(message, "chat_id", None)
    stored = context.user_data.get(slot) or {}
    same = stored.get("chat") == chat_id and stored.get("id") == message.message_id
    current_tail = stored.get("tail", message.message_id) if same else message.message_id
    context.user_data[slot] = {
        "chat": chat_id,
        "id": message.message_id,
        "tail": current_tail,
    }


async def _delete(context, chat_id: int | None, message_id: int | None) -> None:
    bot = getattr(context, "bot", None)
    if bot is None or chat_id is None or message_id is None:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramError:
        pass
    except Exception:  # noqa: BLE001 — حذف پیام هرگز نباید جریان را بشکند
        log.debug("delete_message failed", exc_info=True)


async def drop_user_input(update: Update) -> None:
    """پیام خود کاربر (ضربهٔ دکمهٔ ثابت، دستور، ورودی فرم) را در چت خصوصی پاک می‌کند."""
    if getattr(update, "callback_query", None) is not None or not _is_private(update):
        return
    message = getattr(update, "effective_message", None)
    if message is None:
        return
    try:
        await message.delete()
    except Exception:  # noqa: BLE001 — پیام قدیمی یا حذف‌شده
        pass


async def panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    body: str,
    reply_markup=None,
    *,
    slot: str = PANEL_KEY,
) -> Message | None:
    """نمایش یک صفحه در «پیام پنل» کاربر.

    * از دکمهٔ شیشه‌ای: همان پیام ویرایش می‌شود.
    * از کیبورد ثابت/فرم: اگر پنل قبلی آخرین پیام چت است ویرایش می‌شود؛ وگرنه
      پنل تازه پایین چت فرستاده و پنل قبلی پاک می‌شود (هیچ‌وقت منوی تکراری نمی‌ماند).
    * کیبورد ثابت (ReplyKeyboard) فقط با پیام تازه ممکن است.
    """
    query = getattr(update, "callback_query", None)
    chat = getattr(update, "effective_chat", None)
    chat_id = getattr(chat, "id", None)
    inline = _is_inline(reply_markup)
    stored = context.user_data.get(slot) or {}

    if inline:
        if query is not None and query.message is not None:
            done = await edit(query.message, body, reply_markup=reply_markup)
            if done is not None:
                _remember_panel(context, done, slot)
                return done
        else:
            incoming = getattr(getattr(update, "effective_message", None), "message_id", None)
            bot = getattr(context, "bot", None)
            fresh_bottom = (
                incoming is not None
                and stored.get("chat") == chat_id
                and stored.get("tail") == incoming - 1
            )
            if fresh_bottom and bot is not None:
                try:
                    result = await bot.edit_message_text(
                        body,
                        chat_id=chat_id,
                        message_id=stored["id"],
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                        reply_markup=reply_markup,
                    )
                    message = result if isinstance(result, Message) else None
                    stored["tail"] = incoming
                    context.user_data[slot] = stored
                    return message
                except BadRequest as exc:
                    if _not_modified(exc):
                        stored["tail"] = incoming
                        context.user_data[slot] = stored
                        return None
                except TelegramError:
                    pass

    sent = await reply(update, body, reply_markup=reply_markup)
    if sent is None:
        return None
    old_id = stored.get("id") if stored.get("chat") == chat_id else None
    if query is not None and query.message is not None and inline:
        # ویرایش پیام کلیک‌شده ممکن نبود (مثلاً پیام رسانه‌ای)؛ همان را جایگزین می‌کنیم.
        old_id = query.message.message_id if old_id is None else old_id
    if inline:
        _remember_panel(context, sent, slot)
    else:
        context.user_data.pop(slot, None)
    if old_id is not None and old_id != getattr(sent, "message_id", None) and _is_private(update):
        await _delete(context, chat_id, old_id)
    return sent


async def send_home(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    body: str,
    reply_markup,
) -> Message | None:
    """پیام خانه با کیبورد ثابت؛ پیام خانه و پنل قبلی پاک می‌شوند تا فقط یکی بماند."""
    sent = await reply(update, body, reply_markup=reply_markup)
    if sent is None or not _is_private(update):
        return sent
    chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
    old_home = context.user_data.get(HOME_KEY)
    stored = context.user_data.get(PANEL_KEY) or {}
    keep = {getattr(sent, "message_id", None)}
    query = getattr(update, "callback_query", None)
    if query is not None and query.message is not None:
        keep.add(query.message.message_id)  # پیام کلیک‌شده را خود هندلر مدیریت می‌کند
    if old_home and old_home[0] == chat_id and old_home[1] not in keep:
        await _delete(context, chat_id, old_home[1])
    if stored.get("chat") == chat_id and stored.get("id") not in keep:
        await _delete(context, chat_id, stored.get("id"))
        context.user_data.pop(PANEL_KEY, None)
    # اگر پنل همان پیام کلیک‌شده است، ردش را نگه می‌داریم تا پنل بعدی آن را جمع کند.
    context.user_data[HOME_KEY] = (chat_id, getattr(sent, "message_id", None))
    return sent


async def run_detached(
    context: ContextTypes.DEFAULT_TYPE,
    coro: Coroutine,
    update: Update | None = None,
) -> None:
    """کار طولانی را خارج از قفل هر کاربر اجرا می‌کند تا دکمه‌های بعدی منتظر نمانند.

    خطاها از طریق ``create_task(update=...)`` به هندلر خطای سراسری می‌رسند.
    بدون Application (تست‌ها) همان‌جا اجرا می‌شود.
    """
    application = getattr(context, "application", None)
    if application is None:
        await coro
        return
    application.create_task(coro, update=update)


def user_display(first: str | None, username: str | None, uid: int) -> str:
    name = human.esc(first or "")
    handle = f"@{human.esc(username)}" if username else "—"
    return f"{name} ({handle}, <code>{uid}</code>)"


def quality_line(draft_title: str) -> str:
    return human.esc(draft_title)
