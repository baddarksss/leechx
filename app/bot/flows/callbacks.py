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
from app.bot.flows import user_links as links_flow
from app.core import human, text
from app.services.formats import find_option

log = logging.getLogger("leechx.callbacks")

MODE_BY_FLAG = {"v": "video", "d": "document", "l": "link"}


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    try:
        await _dispatch(update, context, query)
    finally:
        # The processor watchdog also covers user-lock and pre-handler gate delays.
        await safe_answer(query)


async def _dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE, query) -> None:
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
        elif prefix == "u":
            await links_flow.on_callback(update, context, args)
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
    link_flow.normalize_delivery_mode(draft)
    switched = link_flow.apply_apk_limits(svc, draft)
    if switched:
        await safe_answer(query, text.t(draft.lang, "apk_switched_link"))
    else:
        await safe_answer(query, option.label)
    await edit(
        query.message,
        link_flow.delivery_text(draft.lang, draft, svc.settings.ttl_hours),
        reply_markup=kb.delivery_menu(draft.lang, draft),
    )


async def _on_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    """Per-link selections, rename/thumbnail, then queue the chosen delivery."""
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

    if action == "tab":
        section = args[2] if len(args) > 2 else ""
        if section in {"format", "destination", "edits"}:
            await safe_answer(query, text.t(user_lang, "delivery_section_hint"))
        else:
            await safe_answer(query)
        return

    if action == "r":
        await safe_answer(query)
        await link_flow.start_rename(update, context, draft)
        return

    if action in {"thumbnail", "thumb"}:
        await safe_answer(query)
        await link_flow.start_thumbnail(update, context, draft)
        return

    if action == "q":
        await safe_answer(query)
        if draft.kind == "direct" or draft.auto_quality:
            return
        draft.option = None
        body = (
            link_flow.apk_draft_text(user_lang, draft)
            if draft.kind == "apk"
            else link_flow.quality_text(user_lang, draft)
        )
        await edit(query.message, body,
                   reply_markup=kb.quality_menu(user_lang, draft))
        return

    if action == "format":
        if len(args) < 3 or args[2] not in {"video", "document"}:
            await safe_answer(query)
            return
        requested = args[2]
        if (
            requested == "video"
            and draft.kind != "gallery"
            and not link_flow.can_send_as_video(draft)
        ):
            draft.send_as = "document"
            await safe_answer(
                query, text.t(user_lang, "video_mode_unavailable"), alert=True
            )
        else:
            draft.send_as = requested
            await safe_answer(query, text.t(user_lang, "delivery_choice_saved"))
        await edit(
            query.message,
            link_flow.delivery_text(user_lang, draft, svc.settings.ttl_hours),
            reply_markup=kb.delivery_menu(user_lang, draft),
        )
        return

    if action == "destination":
        if len(args) < 3 or args[2] not in {"telegram", "link"}:
            await safe_answer(query)
            return
        draft.destination = args[2]
        await safe_answer(query, text.t(user_lang, "delivery_choice_saved"))
        await edit(
            query.message,
            link_flow.delivery_text(user_lang, draft, svc.settings.ttl_hours),
            reply_markup=kb.delivery_menu(user_lang, draft),
        )
        return

    new_panel = action == "start"
    if new_panel:
        if draft.option is None:
            await safe_answer(query)
            return
        link_flow.normalize_delivery_mode(draft)
        mode = "link" if draft.destination == "link" else draft.send_as
    else:
        # Keep callbacks already present on older Telegram messages working.
        mode = MODE_BY_FLAG.get(action)
        if mode is None or draft.option is None:
            await safe_answer(query)
            return
        if mode == "video" and draft.kind != "gallery" and not link_flow.can_send_as_video(draft):
            mode = "document"

    if not svc.limiter.has_slot(draft.user_id, svc.cfg.per_user_concurrency):
        await safe_answer(query, text.t(user_lang, "too_many_active"), alert=True)
        return

    # سقف لینک مستقیم همزمان: Draft دست‌نخورده می‌ماند تا کاربر یکی را حذف
    # کند و همان دکمه را دوباره بزند (بدون نیاز به فرستادن دوبارهٔ لینک).
    if mode == "link":
        limit, used = await link_flow.link_quota_used(context, draft.user_id)
        if limit and used >= limit:
            await safe_answer(
                query, text.t(user_lang, "link_quota_full", limit=limit), alert=True
            )
            return

    if (
        mode != "link"
        and draft.option is not None
        and (draft.option.filesize or 0) > link_flow.telegram_limit(svc)
    ):
        # فایل بزرگ‌تر از سقف Bot API فقط با لینک مستقیم تحویل می‌شود؛
        # جلوی دانلود بی‌فایده گرفته می‌شود.
        await safe_answer(
            query,
            text.t(
                user_lang,
                "too_big",
                size=human.human_bytes(draft.option.filesize or 0),
                max=human.human_bytes(link_flow.telegram_limit(svc)),
            ),
            alert=True,
        )
        return

    svc.drafts.pop(draft_id, draft.user_id)
    if mode == "link":
        label = text.t(user_lang, "deliver_link_btn")
    elif mode == "document":
        label = text.t(user_lang, "deliver_doc_btn")
    else:
        label = text.t(user_lang, "deliver_video_btn")
    await safe_answer(
        query,
        label if not new_panel else text.t(user_lang, kb.delivery_start_key(draft)),
    )
    await link_flow.enqueue(context, query.message, draft, mode, user_lang)


async def _on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    svc = services(context)
    lang = lang_of(context)
    if not args:
        await safe_answer(update.callback_query)
        return
    ok = svc.jobs.cancel(args[0], update.effective_user.id)
    if not ok and getattr(svc, "file_transfers", None) is not None:
        ok = svc.file_transfers.cancel(args[0], update.effective_user.id)
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
