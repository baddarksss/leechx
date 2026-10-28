"""روتر callbackها — همهٔ دکمه‌های شیشه‌ای از اینجا رد می‌شوند."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.common import edit, lang_of, safe_answer, services
from app.bot.flows import admin as admin_flow
from app.bot.flows import start as start_flow
from app.core import text
from app.services.formats import find_option

log = logging.getLogger("leechx.callbacks")


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

    if not svc.limiter.has_slot(draft.user_id, svc.cfg.per_user_concurrency):
        await safe_answer(query, text.t(lang, "too_many_active"), alert=True)
        return

    svc.drafts.pop(draft_id, draft.user_id)
    await safe_answer(query, option.label)

    from app.bot.flows.link import _enqueue
    from app.services.downloader import MediaInfo

    info = MediaInfo(
        url=draft.url,
        title=draft.title,
        duration=draft.duration,
        uploader=draft.uploader,
        thumbnail=draft.thumbnail,
        extractor=draft.extractor,
    )
    await _enqueue(context, query.message, draft.url, info, option, draft.lang or lang, draft.user_id)


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
