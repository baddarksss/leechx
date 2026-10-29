"""دستورهای عمومی، منو و وضعیت کاربر.

هر صفحه در «پیام پنل» کاربر نمایش داده می‌شود (ویرایش به‌جای پیام تازه)؛
فقط پیام خوش‌آمد که کیبورد ثابت را می‌آورد پیام جدید است.
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from app.bot import keyboards as kb
from app.bot.common import edit, fmt_ts, lang_of, panel, reply, safe_answer, send_home, services
from app.bot.guards import in_preview, is_admin
from app.bot.states import ST_CONTACT, clear_state, get_state, set_state
from app.core import human, text
from app.db import repo
from app.version import __version__, version_badge

log = logging.getLogger("leechx.start")

# Telegram requires message text with an inline keyboard; this invisible separator
# keeps first-run language choice visually caption-free.
LANGUAGE_PICKER_TEXT = "\u2063"


def _is_private(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.type == "private"


def _menu_markup(update: Update, lang: str, admin: bool, preview: bool):
    """ادمین (بدون پیش‌نمایش، در چت خصوصی) فقط کیبورد ثابت می‌بیند؛ بقیه منوی شیشه‌ای."""
    if admin and not preview and _is_private(update):
        return kb.admin_persistent_menu(lang)
    return kb.main_menu(lang, admin and not preview, preview=preview)


def _inline_menu(update: Update, lang: str, admin: bool, preview: bool):
    """منوی شیشه‌ای برای صفحه‌های پنل؛ در چت خصوصی کیبورد ثابت کافی است."""
    if _is_private(update):
        return None
    return kb.main_menu(lang, admin and not preview, preview=preview)


def _reply_menu_markup(update: Update, lang: str, admin: bool, preview: bool):
    """Persistent reply keyboard for private chats; inline menus remain in groups."""
    if admin and not preview:
        lang = text.DEFAULT_LANG
        if _is_private(update):
            return kb.admin_persistent_menu(lang)
        return kb.main_menu(lang, True)
    if not _is_private(update):
        return kb.main_menu(lang, False, preview=preview)
    return kb.user_persistent_menu(lang, preview=preview)


def _stale_keyboard_tap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """ضربه روی کیبوردِ زبانِ قبلی؛ باید کیبورد ثابت تازه فرستاده شود."""
    if update.callback_query is not None or not _is_private(update):
        return False
    message = update.effective_message
    label = getattr(message, "text", None) or ""
    if not label or label.startswith("/"):
        return False
    lang = lang_of(context)
    if context.user_data.get("is_admin") and not in_preview(context):
        lang = text.DEFAULT_LANG
        context.user_data["lang"] = lang
        current = set(kb.persistent_admin_labels(lang).values())
    else:
        current = set(
            kb.user_persistent_labels(lang, preview=in_preview(context)).values()
        )
    return label not in current


async def _show(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    body: str,
    *,
    admin: bool,
    markup=None,
) -> None:
    """صفحهٔ کاربر را در پنل نشان می‌دهد؛ برای کیبورد کهنه، کیبورد تازه هم می‌فرستد."""
    lang = lang_of(context)
    preview = in_preview(context)
    if markup is None and _stale_keyboard_tap(update, context):
        await send_home(update, context, body, _reply_menu_markup(update, lang, admin, preview))
        return
    if markup is None:
        markup = _inline_menu(update, lang, admin, preview)
    await panel(update, context, body, reply_markup=markup)


def _user_defaults(row) -> tuple[str, str]:
    mode = getattr(row, "default_mode", "video") if row is not None else "video"
    destination = getattr(row, "default_destination", "telegram") if row is not None else "telegram"
    if mode not in {"video", "document"}:
        mode = "video"
    if destination not in {"telegram", "link"}:
        destination = "telegram"
    return mode, destination


def _user_settings_body(lang: str, row) -> tuple[str, str, str]:
    mode, destination = _user_defaults(row)
    mode_key = "delivery_mode_video" if mode == "video" else "delivery_mode_file"
    destination_key = (
        "delivery_destination_telegram" if destination == "telegram"
        else "delivery_destination_link"
    )
    body = text.t(
        lang,
        "settings_panel",
        language=text.LANGS.get(lang, text.LANGS[text.DEFAULT_LANG]),
        send_as=text.t(lang, mode_key),
        destination=text.t(lang, destination_key),
        version=__version__,
    )
    return body, mode, destination


def _welcome(lang: str, ttl_hours: float) -> str:
    return text.t(lang, "start", ttl=_fmt_hours(ttl_hours)) + "\n\n" + version_badge()


def _help_body(svc, lang: str) -> str:
    return text.t(
        lang,
        "help",
        ttl=_fmt_hours(svc.settings.ttl_hours),
        max_mb=svc.settings.max_upload_bytes // (1024 * 1024),
    )


def _status_body(lang: str, user, row) -> str:
    return text.t(
        lang,
        "status",
        uid=user.id,
        downloads=row.downloads if row else 0,
        uploads=row.uploads if row else 0,
        joined=fmt_ts(row.created_at if row else None),
        version=__version__,
    )


def _sites_body(svc, lang: str, query: str = "") -> str:
    include_nsfw = svc.settings.nsfw_enabled
    if not query:
        return text.t(
            lang,
            "sites_title",
            count=svc.sites.count,
            popular=svc.sites.popular(include_nsfw) or "—",
        )
    results = svc.sites.search(query, limit=30, include_nsfw=include_nsfw)
    lines = []
    for entry in results:
        desc = f" — {human.esc(entry.description)}" if entry.description else ""
        icon = "🔞 " if entry.nsfw else ""
        lines.append(f"{icon}<code>{human.esc(entry.name)}</code>{desc}")
    return text.t(
        lang,
        "sites_search",
        q=human.esc(query),
        count=len(results),
        list="\n".join(lines) or text.t(lang, "sites_none"),
    )


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
                lang = text.DEFAULT_LANG
                context.user_data["lang"] = lang
                await reply(update, text.t(lang, "owner_claimed"))
        except Exception:  # noqa: BLE001 — دیتابیس نباید /start را بشکند
            log.exception("owner claim failed")

    admin = await is_admin(svc.cfg, user.id)
    preview = in_preview(context)
    if admin and not preview:
        lang = text.DEFAULT_LANG
        context.user_data["lang"] = lang
    row = await repo.get_user(user.id)
    if not (admin and not preview) and (row is None or not row.language_selected):
        await panel(
            update,
            context,
            LANGUAGE_PICKER_TEXT,
            reply_markup=kb.language_menu(lang, onboarding=True),
        )
        return
    # یک پیام: متن + کیبورد درست؛ پیام خانه و پنل قبلی پاک می‌شوند.
    await send_home(
        update,
        context,
        _welcome(lang, svc.settings.ttl_hours),
        _reply_menu_markup(update, lang, admin, preview),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    admin = await is_admin(svc.cfg, update.effective_user.id) and not in_preview(context)
    await _show(update, context, _help_body(svc, lang), admin=admin)


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = update.effective_user
    row = await repo.get_user(user.id)
    admin = await is_admin(svc.cfg, user.id) and not in_preview(context)
    await _show(update, context, _status_body(lang, user, row), admin=admin)


async def cmd_sites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    query = " ".join(getattr(context, "args", None) or []).strip()
    admin = await is_admin(svc.cfg, update.effective_user.id) and not in_preview(context)
    await _show(update, context, _sites_body(svc, lang, query), admin=admin)


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
    key = "canceled" if (canceled or previous_state or discarded) else "cancel_nothing"
    await panel(update, context, text.t(lang, key))


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    admin = await is_admin(svc.cfg, update.effective_user.id)
    preview = in_preview(context)
    if admin and not preview:
        from app.bot.flows import admin as admin_flow

        await admin_flow.show_section(update, context, kb.SEC_SETTINGS)
        return
    row = await repo.get_user(update.effective_user.id)
    body, mode, destination = _user_settings_body(lang, row)
    await _show(
        update,
        context,
        body,
        admin=False,
        markup=kb.user_settings_menu(lang, mode, destination),
    )


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    admin = await is_admin(svc.cfg, update.effective_user.id) and not in_preview(context)
    if admin:
        lang = text.DEFAULT_LANG
        context.user_data["lang"] = lang
        await _show(update, context, text.t(lang, "admin_lang_fixed"), admin=True)
        return
    lang = lang_of(context)
    await _show(
        update,
        context,
        text.t(lang, "lang_title", current=text.LANGS[lang]),
        admin=admin,
        markup=kb.language_menu(lang),
    )


async def on_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    """Dispatch text taps from the persistent user keyboard."""
    clear_state(context)
    handlers = {
        "help": cmd_help,
        "status": cmd_me,
        "sites": cmd_sites,
        "settings": cmd_settings,
        "lang": cmd_lang,
    }
    if action in handlers:
        await handlers[action](update, context)
        return
    if action == "links":
        from app.bot.flows import user_links as links_flow

        await links_flow.cmd_links(update, context)
        return
    if action == "contact":
        svc = services(context)
        admin = await is_admin(svc.cfg, update.effective_user.id) and not in_preview(context)
        set_state(context, ST_CONTACT)
        await _show(update, context, text.t(lang_of(context), "contact_prompt"), admin=admin)
        return
    if action == "kbclose":
        await reply(
            update,
            text.t(lang_of(context), "kb_closed"),
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    if action == "exitpreview":
        await handle_preview_exit_text(update, context)


async def handle_preview_exit_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Restore the admin keyboard after exiting preview from a text-button tap."""
    svc = services(context)
    user = update.effective_user
    if not await is_admin(svc.cfg, user.id):
        await panel(update, context, text.t(lang_of(context), "admin_only"))
        return
    _leave_preview(context)
    lang = lang_of(context)
    await send_home(
        update,
        context,
        text.t(lang, "preview_exit_done") + "\n\n" + version_badge(),
        kb.admin_persistent_menu(lang),
    )


def _leave_preview(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["preview"] = False
    context.user_data["is_admin"] = True
    context.user_data["lang"] = text.DEFAULT_LANG


def _enter_preview(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["preview"] = True
    context.user_data["is_admin"] = False


async def start_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ورود ادمین به حالت کاربر: پنل فعلی بنر می‌شود و کیبورد کاربر جایگزین کیبورد ادمین."""
    svc = services(context)
    lang = lang_of(context)
    _enter_preview(context)
    query = update.callback_query
    if query is not None:
        await edit(query.message, text.t(lang, "preview_banner"), reply_markup=InlineKeyboardMarkup([]))
    await send_home(
        update,
        context,
        _welcome(lang, svc.settings.ttl_hours),
        kb.user_persistent_menu(lang, preview=True),
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
        await panel(update, context, text.t(lang, "contact_prompt"))
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
        await panel(update, context, text.t(lang, "contact_failed"))
        return

    hub = getattr(svc, "admin_group", None)
    if hub is not None:
        try:
            await hub.notify_report(report)
        except Exception:  # noqa: BLE001
            log.exception("could not forward contact message")
    await panel(update, context, text.t(lang, "contact_sent"))


# ── callbackهای منو ────────────────────────────────────────
async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    query = update.callback_query
    svc = services(context)
    lang = lang_of(context)
    preview = in_preview(context)
    admin = await is_admin(svc.cfg, update.effective_user.id) and not preview
    if admin:
        lang = text.DEFAULT_LANG
        context.user_data["lang"] = lang
    clear_state(context)
    # ویرایش پیام فقط کیبورد شیشه‌ای می‌پذیرد؛ کیبورد ثابت ادمین اینجا کاربرد ندارد.
    inline_menu = kb.main_menu(lang, admin, preview=preview)

    if action == "close":
        await safe_answer(query)
        try:
            await query.message.delete()
        except Exception:  # noqa: BLE001
            await edit(query.message, "✖️")
        return

    if action == "home":
        await safe_answer(query)
        await panel(update, context, _welcome(lang, svc.settings.ttl_hours), inline_menu)
        return

    if action == "help":
        await safe_answer(query)
        await panel(update, context, _help_body(svc, lang), inline_menu)
        return

    if action == "status":
        await safe_answer(query)
        user = update.effective_user
        row = await repo.get_user(user.id)
        await panel(update, context, _status_body(lang, user, row), inline_menu)
        return

    if action == "sites":
        await safe_answer(query)
        await panel(update, context, _sites_body(svc, lang), inline_menu)
        return

    if action == "settings":
        if admin:
            from app.bot.flows import admin as admin_flow

            await safe_answer(query)
            await admin_flow.show_section(update, context, kb.SEC_SETTINGS)
            return
        await safe_answer(query)
        row = await repo.get_user(update.effective_user.id)
        body, mode, destination = _user_settings_body(lang, row)
        await panel(update, context, body, kb.user_settings_menu(lang, mode, destination))
        return

    if action in {"prefmode", "prefdest"}:
        if admin:
            await safe_answer(query, text.t(lang, "admin_only"), alert=True)
            return
        user_id = update.effective_user.id
        row = await repo.get_user(user_id)
        mode, destination = _user_defaults(row)
        if action == "prefmode":
            mode = "document" if mode == "video" else "video"
        else:
            destination = "link" if destination == "telegram" else "telegram"
        await repo.set_user_preferences(
            user_id,
            default_mode=mode,
            default_destination=destination,
        )
        await safe_answer(query, text.t(lang, "delivery_choice_saved"))
        row = await repo.get_user(user_id)
        body, mode, destination = _user_settings_body(lang, row)
        await panel(update, context, body, kb.user_settings_menu(lang, mode, destination))
        return

    if action == "lang":
        if admin:
            await safe_answer(query, text.t(lang, "admin_lang_fixed"), alert=True)
            await panel(update, context, text.t(lang, "admin_lang_fixed"), inline_menu)
            return
        await safe_answer(query)
        await panel(
            update,
            context,
            text.t(lang, "lang_title", current=text.LANGS[lang]),
            kb.language_menu(lang),
        )
        return

    if action == "kbclose":
        await safe_answer(query)
        # ReplyKeyboardRemove فقط روی یک پیام تازه اثر می‌گذارد، نه پیام ویرایشی.
        await edit(query.message, "⌨️", reply_markup=InlineKeyboardMarkup([]))
        await reply(update, text.t(lang, "kb_closed"), reply_markup=ReplyKeyboardRemove())
        return

    if action == "contact":
        await safe_answer(query)
        set_state(context, ST_CONTACT)
        await panel(update, context, text.t(lang, "contact_prompt"), kb.back_home(lang))
        return

    if action == "admin":
        if not admin:
            await safe_answer(query, text.t(lang, "admin_only"), alert=True)
            return
        from app.bot.flows import admin as admin_flow

        await safe_answer(query)
        await admin_flow.show_panel(update, context)
        return

    if action == "preview":
        if not await is_admin(svc.cfg, update.effective_user.id):
            await safe_answer(query, text.t(lang, "admin_only"), alert=True)
            return
        await safe_answer(query)
        await start_preview(update, context)
        return

    if action == "exitpreview":
        if not await is_admin(svc.cfg, update.effective_user.id):
            await safe_answer(query, text.t(lang, "admin_only"), alert=True)
            return
        await safe_answer(query)
        _leave_preview(context)
        lang = lang_of(context)
        await edit(query.message, text.t(lang, "preview_exit_done"), reply_markup=InlineKeyboardMarkup([]))
        await send_home(
            update,
            context,
            text.t(lang, "preview_exit_done") + "\n\n" + version_badge(),
            kb.admin_persistent_menu(lang),
        )
        return

    if action == "joincheck":
        await _verify_join(update, context, edit_message=True)
        return

    await safe_answer(query)


async def _verify_join(update: Update, context: ContextTypes.DEFAULT_TYPE, *, edit_message: bool) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = update.effective_user
    svc.force_join.clear_cache(user.id)
    missing, complete = await svc.force_join.missing(context.bot, user.id, use_cache=False)
    query = update.callback_query
    if not missing:
        await safe_answer(query, text.t(lang, "join_gate_ok"))
        if edit_message and query is not None:
            await edit(query.message, text.t(lang, "join_gate_ok"), reply_markup=InlineKeyboardMarkup([]))
        admin = await is_admin(svc.cfg, user.id)
        preview = in_preview(context)
        await send_home(
            update,
            context,
            _welcome(lang, svc.settings.ttl_hours),
            _reply_menu_markup(update, lang, admin, preview),
        )
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
        await panel(update, context, body, markup)


def _join_list(targets) -> str:
    return "\n".join(
        f"• <b>{human.esc(t.title)}</b> — <a href=\"{human.esc(t.url())}\">link</a>"
        for t in targets
    )


async def on_lang(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str) -> None:
    svc = services(context)
    user = update.effective_user
    query = update.callback_query
    preview = in_preview(context)
    admin = await is_admin(svc.cfg, user.id)
    if admin and not preview:
        lang = text.DEFAULT_LANG
        context.user_data["lang"] = lang
        await safe_answer(query, text.t(lang, "admin_lang_fixed"), alert=True)
        await send_home(
            update,
            context,
            text.t(lang, "admin_lang_fixed"),
            _reply_menu_markup(update, lang, admin=True, preview=False),
        )
        return
    if code not in text.LANGS:
        await safe_answer(query)
        return

    row = await repo.get_user(user.id)
    onboarding = row is None or not row.language_selected
    clear_state(context)
    await repo.set_lang(user.id, code, selected=True)
    context.user_data["lang"] = code
    await safe_answer(query, text.t(code, "lang_saved", language=text.LANGS[code]))

    if onboarding:
        # انتخاب زبان کامل شد؛ کاربران عادی وارد قفل عضویت می‌شوند، اما ادمین
        # مانند قبل از عضویت اجباری معاف است (مگر اینکه در پیش‌نمایش باشد).
        if admin and not preview:
            missing = []
        else:
            svc.force_join.clear_cache(user.id)
            missing, _complete = await svc.force_join.missing(
                context.bot, user.id, use_cache=False
            )
        if missing:
            body = text.t(code, "join_gate_title", list=_join_list(missing))
            await edit(query.message, body, reply_markup=kb.join_gate(code, missing))
            return
        await edit(
            query.message,
            text.t(code, "lang_saved", language=text.LANGS[code]),
            reply_markup=InlineKeyboardMarkup([]),
        )
        await send_home(
            update,
            context,
            _welcome(code, svc.settings.ttl_hours),
            _reply_menu_markup(update, code, admin, preview),
        )
        return

    row = await repo.get_user(user.id)
    body, mode, destination = _user_settings_body(code, row)
    await panel(update, context, body, kb.user_settings_menu(code, mode, destination))
    # Telegram keeps the old persistent reply keyboard until a new message sends
    # the localized one; the settings message itself uses an inline keyboard.
    await send_home(
        update,
        context,
        text.t(code, "menu_updated"),
        _reply_menu_markup(update, code, admin, preview),
    )


def _fmt_hours(hours: float) -> str:
    return f"{hours:g}"
