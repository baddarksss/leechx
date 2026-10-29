"""دستورهای عمومی، منو و وضعیت کاربر."""
from __future__ import annotations

import logging

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from app.bot import keyboards as kb
from app.bot.common import edit, fmt_ts, lang_of, reply, safe_answer, services
from app.bot.guards import in_preview, is_admin
from app.bot.states import ST_CONTACT, clear_state, get_state, set_state
from app.core import human, text
from app.db import repo
from app.version import __version__, version_badge

log = logging.getLogger("leechx.start")


def _menu_markup(update: Update, lang: str, admin: bool, preview: bool):
    """ادمین (بدون پیش‌نمایش، در چت خصوصی) فقط کیبورد ثابت می‌بیند؛ بقیه منوی شیشه‌ای."""
    chat = update.effective_chat
    if admin and not preview and chat is not None and chat.type == "private":
        return kb.admin_persistent_menu(lang)
    return kb.main_menu(lang, admin and not preview, preview=preview)


# ── دستورها ────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = update.effective_user
    clear_state(context)  # /start must recover from unfinished forms

    # اولین کاربری که /start بزند مالک ربات می‌شود (مگر اینکه OWNER_IDS در env ست شده باشد).
    if not svc.cfg.owners:
        try:
            owner_id, claimed = await repo.claim_owner(user.id)
            if claimed:
                await svc.settings.set("owner_id", str(owner_id))
                svc.settings.apply_to_config()
                await reply(update, text.t(lang, "owner_claimed"))
        except Exception:  # noqa: BLE001 — دیتابیس نباید /start را بشکند
            log.exception("owner claim failed")

    admin = await is_admin(svc.cfg, user.id)
    preview = in_preview(context)
    body = text.t(lang, "start", ttl=_fmt_hours(svc.settings.ttl_hours))
    body += "\n\n" + version_badge()
    # یک پیام: متن + کیبورد درست (برای ادمین فقط کیبورد ثابت، بدون منوی شیشه‌ای تکراری)
    await reply(update, body, reply_markup=_menu_markup(update, lang, admin, preview))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    admin = await is_admin(svc.cfg, update.effective_user.id) and not in_preview(context)
    body = text.t(
        lang,
        "help",
        ttl=_fmt_hours(svc.settings.ttl_hours),
        max_mb=svc.settings.max_upload_bytes // (1024 * 1024),
    )
    await reply(update, body, reply_markup=_menu_markup(update, lang, admin, in_preview(context)))


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = update.effective_user
    row = await repo.get_user(user.id)
    admin = await is_admin(svc.cfg, user.id) and not in_preview(context)
    body = text.t(
        lang,
        "status",
        uid=user.id,
        downloads=row.downloads if row else 0,
        joined=fmt_ts(row.created_at if row else None),
        admin=text.t(lang, "yes" if admin else "no"),
        version=__version__,
    )
    await reply(update, body, reply_markup=_menu_markup(update, lang, admin, in_preview(context)))


async def cmd_sites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    query = " ".join(context.args or []).strip()
    include_nsfw = svc.settings.nsfw_enabled

    if not query:
        body = text.t(
            lang,
            "sites_title",
            count=svc.sites.count,
            popular=svc.sites.popular(include_nsfw) or "—",
        )
    else:
        results = svc.sites.search(query, limit=30, include_nsfw=include_nsfw)
        lines = []
        for entry in results:
            desc = f" — {human.esc(entry.description)}" if entry.description else ""
            icon = "🔞 " if entry.nsfw else ""
            lines.append(f"{icon}<code>{entry.name}</code>{desc}")
        body = text.t(
            lang,
            "sites_search",
            q=human.esc(query),
            count=len(results),
            list="\n".join(lines) or text.t(lang, "sites_none"),
        )
    admin = await is_admin(svc.cfg, update.effective_user.id) and not in_preview(context)
    await reply(update, body, reply_markup=_menu_markup(update, lang, admin, in_preview(context)))


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    previous_state = get_state(context)
    clear_state(context)
    user = update.effective_user
    discarded = svc.drafts.clear_user(user.id)
    canceled = 0
    for task in svc.jobs.tasks_for_user(user.id):
        if svc.jobs.cancel(task.id, user.id):
            canceled += 1
    transfers = getattr(svc, "file_transfers", None)
    if transfers is not None:
        for transfer in transfers.tasks_for_user(user.id):
            if transfers.cancel(transfer.id, user.id):
                canceled += 1
    if canceled or previous_state or discarded:
        await reply(update, text.t(lang, "canceled"))
    else:
        await reply(update, text.t(lang, "cancel_nothing"))


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    if await is_admin(svc.cfg, update.effective_user.id) and not in_preview(context):
        from app.bot.flows import admin as admin_flow

        await admin_flow.show_section(update, context, kb.SEC_SETTINGS)
        return
    body = text.t(lang, "settings_panel", lang=text.LANGS[lang], version=__version__)
    await reply(update, body, reply_markup=kb.user_settings_menu(lang))


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context)
    await reply(
        update,
        text.t(lang, "lang_title", current=text.LANGS[lang]),
        reply_markup=kb.language_menu(lang),
    )


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پیام کاربر در حالت «ارتباط با ادمین» را ذخیره و به گروه ادمین می‌فرستد."""
    svc = services(context)
    lang = lang_of(context)
    user = update.effective_user
    message = update.effective_message
    raw = (message.text or "").strip() if message else ""
    clear_state(context)
    if not raw:
        await reply(update, text.t(lang, "contact_prompt"))
        return

    try:
        report = await repo.add_report(
            "contact",
            user.id,
            username=user.username,
            first_name=user.first_name,
            text=raw[:4000],
        )
    except Exception:  # noqa: BLE001
        log.exception("could not store contact message")
        await reply(update, text.t(lang, "contact_failed"))
        return

    hub = getattr(svc, "admin_group", None)
    if hub is not None:
        try:
            await hub.notify_report(report)
        except Exception:  # noqa: BLE001
            log.exception("could not forward contact message")
    await reply(update, text.t(lang, "contact_sent"))


# ── callbackهای منو ────────────────────────────────────────
async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    query = update.callback_query
    svc = services(context)
    lang = lang_of(context)
    preview = in_preview(context)
    admin = await is_admin(svc.cfg, update.effective_user.id) and not preview
    clear_state(context)
    await safe_answer(query)

    if action == "close":
        try:
            await query.message.delete()
        except Exception:  # noqa: BLE001
            await edit(query.message, "✖️")
        return

    if action == "home":
        await edit(
            query.message,
            text.t(lang, "start", ttl=_fmt_hours(svc.settings.ttl_hours)) + "\n\n" + version_badge(),
            reply_markup=_menu_markup(update, lang, admin, preview),
        )
        return

    if action == "help":
        await edit(
            query.message,
            text.t(
                lang,
                "help",
                ttl=_fmt_hours(svc.settings.ttl_hours),
                max_mb=svc.settings.max_upload_bytes // (1024 * 1024),
            ),
            reply_markup=_menu_markup(update, lang, admin, preview),
        )
        return

    if action == "status":
        user = update.effective_user
        row = await repo.get_user(user.id)
        await edit(
            query.message,
            text.t(
                lang,
                "status",
                uid=user.id,
                downloads=row.downloads if row else 0,
                joined=fmt_ts(row.created_at if row else None),
                admin=text.t(lang, "yes" if admin else "no"),
                version=__version__,
            ),
            reply_markup=_menu_markup(update, lang, admin, preview),
        )
        return

    if action == "sites":
        include_nsfw = svc.settings.nsfw_enabled
        await edit(
            query.message,
            text.t(
                lang,
                "sites_title",
                count=svc.sites.count,
                popular=svc.sites.popular(include_nsfw) or "—",
            ),
            reply_markup=kb.main_menu(lang, admin, preview=preview),
        )
        return

    if action == "settings":
        if admin:
            from app.bot.flows import admin as admin_flow

            await admin_flow.show_section(update, context, kb.SEC_SETTINGS)
            return
        await edit(
            query.message,
            text.t(lang, "settings_panel", lang=text.LANGS[lang], version=__version__),
            reply_markup=kb.user_settings_menu(lang),
        )
        return

    if action == "lang":
        await edit(
            query.message,
            text.t(lang, "lang_title", current=text.LANGS[lang]),
            reply_markup=kb.language_menu(lang),
        )
        return

    if action == "kbclose":
        # مثل تلگرام بومی: ReplyKeyboardRemove روی همان پیام اعمال می‌شود.
        await edit(query.message, text.t(lang, "kb_closed"), reply_markup=ReplyKeyboardRemove())
        return

    if action == "contact":
        set_state(context, ST_CONTACT)
        await edit(
            query.message,
            text.t(lang, "contact_prompt"),
            reply_markup=kb.back_home(lang),
        )
        return

    if action == "admin":
        if not admin:
            await safe_answer(query, text.t(lang, "admin_only"), alert=True)
            return
        from app.bot.flows import admin as admin_flow

        await admin_flow.show_panel(update, context)
        return

    if action == "preview":
        if not await is_admin(svc.cfg, update.effective_user.id):
            await safe_answer(query, text.t(lang, "admin_only"), alert=True)
            return
        context.user_data["preview"] = True
        context.user_data["is_admin"] = False
        # اول کیبورد ثابت برداشته می‌شود، بعد دقیقاً منوی یک کاربر عادی می‌آید.
        await edit(query.message, text.t(lang, "preview_banner"), reply_markup=ReplyKeyboardRemove())
        await reply(
            update,
            text.t(lang, "start", ttl=_fmt_hours(svc.settings.ttl_hours)) + "\n\n" + version_badge(),
            reply_markup=kb.main_menu(lang, False, preview=True),
        )
        return

    if action == "exitpreview":
        if not await is_admin(svc.cfg, update.effective_user.id):
            await safe_answer(query, text.t(lang, "admin_only"), alert=True)
            return
        context.user_data["preview"] = False
        context.user_data["is_admin"] = True
        await reply(
            update,
            text.t(lang, "preview_exit_done") + "\n\n" + version_badge(),
            reply_markup=kb.admin_persistent_menu(lang),
        )
        return

    if action == "joincheck":
        await _verify_join(update, context, edit_message=True)
        return


async def _verify_join(update: Update, context: ContextTypes.DEFAULT_TYPE, *, edit_message: bool) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = update.effective_user
    svc.force_join.clear_cache(user.id)
    missing, complete = await svc.force_join.missing(context.bot, user.id, use_cache=False)
    query = update.callback_query
    if not missing:
        await safe_answer(query, text.t(lang, "join_gate_ok"))
        body = text.t(lang, "start", ttl=_fmt_hours(svc.settings.ttl_hours)) + "\n\n" + version_badge()
        if edit_message and query is not None:
            await edit(query.message, body, reply_markup=kb.main_menu(lang, False))
        else:
            await reply(update, body, reply_markup=kb.main_menu(lang, False))
        return
    if not complete:
        await safe_answer(query, text.t(lang, "join_gate_error"), alert=True)
    else:
        await safe_answer(query, text.t(lang, "join_gate_still"), alert=True)
    body = text.t(lang, "join_gate_title", list=_join_list(missing))
    markup = kb.join_gate(lang, missing)
    if edit_message and query is not None:
        await edit(query.message, body, reply_markup=markup)
    else:
        await reply(update, body, reply_markup=markup)


def _join_list(targets) -> str:
    return "\n".join(
        f"• <b>{human.esc(t.title)}</b> — <a href=\"{human.esc(t.url())}\">link</a>"
        for t in targets
    )


async def on_lang(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str) -> None:
    if code not in text.LANGS:
        return
    query = update.callback_query
    clear_state(context)
    await repo.set_lang(update.effective_user.id, code)
    context.user_data["lang"] = code
    await safe_answer(query, text.t(code, "lang_saved", lang=text.LANGS[code]))
    await edit(
        query.message,
        text.t(code, "settings_panel", lang=text.LANGS[code], version=__version__),
        reply_markup=kb.user_settings_menu(code),
    )


def _fmt_hours(hours: float) -> str:
    return f"{hours:g}"
