"""روتر callbackها — همهٔ دکمه‌های شیشه‌ای از اینجا رد می‌شوند."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards as kb
from app.bot.common import edit, lang_of, safe_answer, services
from app.bot.flows import admin as admin_flow
from app.bot.flows import link as link_flow
from app.bot.flows import start as start_flow
from app.core import text
from app.services.formats import find_option

log = logging.getLogger("leechx.callbacks")

MODE_BY_FLAG = {"v": "video", "d": "document", "l": "link"}


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    data = query.data
    parts = data.split("|")
    prefix, args = parts[0], parts[1:]

    try:
        if prefix == "m":
            await start_flow.on_menu(update, context, args[0] if args else "")
        elif prefix == "l":
            await start_flow.on_lang(update, context, args[0] if args else "")
        elif prefix == "a":
            await admin_flow.on_admin(update, context, args[0] if args else "", args[1:])
        elif prefix == "q":
            await _on_quality(update, context, args)
        elif prefix == "o":
            await _on_delivery(update, context, args)
        elif prefix == "x":
            await _on_cancel(update, context, args)
        elif prefix == "d":
            await _on_dismiss(update, context, args)
        else:
            await safe_answer(query)
    except Exception:  # noqa: BLE001
        log.exception("callback failed: %s", data)
        await safe_answer(query, "⚠️", alert=True)


async def _on_quality(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    """انتخاب کیفیت → نمایش صفحهٔ نحوهٔ تحویل (هنوز چیزی صف نمی‌شود)."""
    svc = services(context)
    lang = lang_of(context)
    query = update.callback_query
    if len(args) < 3:
        await safe_answer(query)
        return

    draft_id, code, kind_flag = args[0], args[1], args[2]
    draft = svc.drafts.get(draft_id, update.effective_user.id)
    if draft is None:
        await safe_answer(query, text.t(lang, "expired_draft"), alert=True)
        await edit(query.message, text.t(lang, "expired_draft"))
        return

    kind = "video" if kind_flag == "v" else "audio"
    option = find_option(draft.options, kind, code)
    if option is None:
        await safe_answer(query, text.t(lang, "invalid_url"), alert=True)
        return

    draft.option = option
    draft.lang = draft.lang or lang
    await safe_answer(query, option.label)
    await edit(
        query.message,
        link_flow.delivery_text(draft.lang, draft),
        reply_markup=kb.delivery_menu(draft.lang, draft),
    )


async def _on_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    """ویدیو / فایل / لینک مستقیم / تغییر نام / بازگشت به کیفیت."""
    svc = services(context)
    lang = lang_of(context)
    query = update.callback_query
    if len(args) < 2:
        await safe_answer(query)
        return

    draft_id, action = args[0], args[1]
    draft = svc.drafts.get(draft_id, update.effective_user.id)
    if draft is None:
        await safe_answer(query, text.t(lang, "expired_draft"), alert=True)
        await edit(query.message, text.t(lang, "expired_draft"))
        return
    user_lang = draft.lang or lang

    if action == "r":
        await safe_answer(query)
        await link_flow.start_rename(update, context, draft)
        return

    if action == "q":
        await safe_answer(query)
        if draft.kind == "direct":
            return
        draft.option = None
        await edit(query.message, link_flow.quality_text(user_lang, draft), reply_markup=kb.quality_menu(user_lang, draft))
        return

    mode = MODE_BY_FLAG.get(action)
    if mode is None or draft.option is None:
        await safe_answer(query)
        return

    if not svc.limiter.has_slot(draft.user_id, svc.cfg.per_user_concurrency):
        await safe_answer(query, text.t(user_lang, "too_many_active"), alert=True)
        return

    svc.drafts.pop(draft_id, draft.user_id)
    label = {
        "video": text.t(user_lang, "deliver_video_btn"),
        "document": text.t(user_lang, "deliver_doc_btn"),
        "link": text.t(user_lang, "deliver_link_btn"),
    }[mode]
    await safe_answer(query, label)
    await link_flow.enqueue(context, query.message, draft, mode, user_lang)


async def _on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    svc = services(context)
    lang = lang_of(context)
    if not args:
        await safe_answer(update.callback_query)
        return
    ok = svc.jobs.cancel(args[0], update.effective_user.id)
    if ok:
        await safe_answer(update.callback_query, text.t(lang, "canceled"))
    else:
        await safe_answer(update.callback_query, text.t(lang, "expired_draft"), alert=True)


async def _on_dismiss(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    svc = services(context)
    if args:
        svc.drafts.pop(args[0], update.effective_user.id)
    await safe_answer(update.callback_query)
    try:
        await update.callback_query.message.delete()
    except Exception:  # noqa: BLE001
        await edit(update.callback_query.message, "✖️")
