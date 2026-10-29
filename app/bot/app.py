"""ساخت و اجرای اپلیکیشن تلگرام."""
from __future__ import annotations

import logging
from datetime import UTC

from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    TypeHandler,
    filters,
)

from app.bot import keyboards as kb
from app.bot.common import drop_user_input, lang_of, panel, reply, safe_answer
from app.bot.flows import admin as admin_flow
from app.bot.flows import callbacks as callbacks_flow
from app.bot.flows import errors as errors_flow
from app.bot.flows import files as files_flow
from app.bot.flows import start as start_flow
from app.bot.flows import text_router
from app.bot.flows import user_links as links_flow
from app.bot.guards import in_preview, is_staff
from app.bot.update_processor import UserOrderedUpdateProcessor
from app.config import Config
from app.container import Services
from app.core import human, text
from app.db import dispose_db, init_db, repo
from app.version import __version__

log = logging.getLogger("leechx.bot")

# Keep the Telegram command menu focused on onboarding; other actions live on buttons.
COMMANDS = [("start", "شروع")]


def _is_start_command(update: Update) -> bool:
    message = update.effective_message
    raw = (getattr(message, "text", None) or "").split(maxsplit=1)
    if not raw:
        return False
    return raw[0].split("@", 1)[0].lower() == "/start"


# ── چرخهٔ عمر ───────────────────────────────────────────────
async def _notify_startup_owners(bot, owner_ids: list[int]) -> None:
    """Tell configured/dynamic owners that the bot is ready after startup or restart."""
    recipients = sorted({int(owner_id) for owner_id in owner_ids if int(owner_id) > 0})
    if not recipients:
        log.info("startup notification skipped: no owner chat is configured")
        return
    sent = 0
    for owner_id in recipients:
        try:
            owner = await repo.get_user(owner_id)
            lang = text.normalize_lang(owner.lang if owner is not None else None)
        except Exception:  # noqa: BLE001 — startup notice must not depend on user lookup
            lang = text.DEFAULT_LANG
            log.debug("could not load startup notification language for owner_id=%s", owner_id, exc_info=True)
        body = text.t(lang, "startup_ready", version=__version__)
        try:
            await bot.send_message(chat_id=owner_id, text=body)
            sent += 1
        except Exception:  # noqa: BLE001 — one blocked owner must not prevent bot startup
            log.warning("startup notification failed for owner_id=%s", owner_id, exc_info=True)
    log.info("startup notification sent to %s/%s owner chat(s)", sent, len(recipients))


async def post_init(application: Application) -> None:
    cfg: Config = application.bot_data["cfg"]
    await init_db(cfg)
    services = Services.create(cfg)
    application.bot_data["services"] = services
    services.attach_application(application)
    await services.setup(application.bot)
    try:
        await application.bot.set_my_commands([BotCommand(cmd, desc) for cmd, desc in COMMANDS])
    except Exception:  # noqa: BLE001
        log.warning("could not set commands", exc_info=True)
    await _notify_startup_owners(application.bot, cfg.owners)
    log.info("bot @%s ready (LeechX v%s)", getattr(application.bot, "username", "?"), __version__)


async def post_shutdown(application: Application) -> None:
    services: Services | None = application.bot_data.get("services")
    if services is not None:
        await services.teardown()
    await dispose_db()


# ── گیتِ هر آپدیت ───────────────────────────────────────────
async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or user.is_bot:
        return
    services: Services = context.bot_data["services"]
    cfg = services.cfg

    try:
        row = await repo.upsert_user(user.id, user.username, user.first_name)
    except Exception:  # noqa: BLE001 — دیتابیس نباید ربات را قفل کند
        log.exception("user upsert failed")
        return

    # زبان اولین پیام را از کلاینت تلگرام حدس می‌زنیم (فارسی/انگلیسی/روسی).
    if row.lang == text.DEFAULT_LANG and row.last_seen == row.created_at:
        detected = text.lang_from_telegram(getattr(user, "language_code", None))
        if detected != row.lang:
            try:
                await repo.set_lang(user.id, detected, selected=False)
                row.lang = detected
            except Exception:  # noqa: BLE001
                log.debug("could not store detected language", exc_info=True)

    # The persisted choice is authoritative on every update, avoiding stale
    # per-process language state after a switch or restart.
    context.user_data["lang"] = text.normalize_lang(row.lang or cfg.default_lang)
    preview = in_preview(context)
    staff = await is_staff(cfg, user.id)
    context.user_data["is_admin"] = staff and not preview

    if row.is_banned:
        await _block(update, text.t(lang_of(context), "banned"))
        raise ApplicationHandlerStop

    if services.settings.maintenance and not (staff and not preview):
        await _block(update, text.t(lang_of(context), "maintenance"))
        raise ApplicationHandlerStop

    # ── زبان اولیه پیش از قفل عضویت ───────────────────────
    # هر کاربر، از جمله ادمین، زبان را یک‌بار انتخاب می‌کند؛ /start باید به هندلر
    # برسد تا منطق مالک اولیه حفظ شود، و callback انتخاب زبان نیز از گیت بگذرد.
    language_callback = update.callback_query
    choosing_initial_language = bool(
        language_callback is not None
        and language_callback.data in {f"l|{code}" for code in text.LANGS}
    )
    if not row.language_selected:
        if _is_start_command(update) or choosing_initial_language:
            return
        lang = lang_of(context)
        await safe_answer(update.callback_query)
        await panel(
            update,
            context,
            start_flow.LANGUAGE_PICKER_TEXT,
            reply_markup=kb.language_menu(lang, onboarding=True),
        )
        raise ApplicationHandlerStop

    # پس از انتخاب زبان، ادمین‌ها از عضویت اجباری معاف‌اند؛ در حالت پیش‌نمایش
    # همچنان دقیقاً مانند کاربر عادی بررسی می‌شوند.
    if staff and not preview:
        return

    # ── عضویت اجباری ──────────────────────────────────────
    if not services.force_join.enabled:
        return

    lang = lang_of(context)
    missing, complete = await services.force_join.missing(context.bot, user.id)
    if not missing:
        return

    query = update.callback_query
    if query is not None:
        if query.data == "m|joincheck":
            return  # اجازه بده همین هندلر بررسی مجدد را انجام دهد
        await safe_answer(query, text.t(lang, "join_gate_still"), alert=True)
        raise ApplicationHandlerStop

    body = text.t(lang, "join_gate_title", list=_join_targets(missing))
    await panel(update, context, body, reply_markup=kb.join_gate(lang, missing))
    raise ApplicationHandlerStop


async def _block(update: Update, body: str) -> None:
    """برای دکمه‌ها هشدار کوچک کافی است؛ پیام تازه فقط برای پیام متنی."""
    if update.callback_query is not None:
        await safe_answer(update.callback_query, body, alert=True)
        return
    await reply(update, body)


def _private_command(handler):
    """دستور تایپ‌شده (مثل /help) بعد از اجرا از چت خصوصی پاک می‌شود."""

    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            await handler(update, context)
        finally:
            await drop_user_input(update)

    wrapper.__name__ = getattr(handler, "__name__", "command")
    wrapper.__wrapped__ = handler  # type: ignore[attr-defined]
    return wrapper


def _join_targets(targets) -> str:
    return "\n".join(
        f"• <b>{human.esc(t.title)}</b> — <a href=\"{human.esc(t.url())}\">link</a>"
        for t in targets
    )


# ── ساخت اپلیکیشن ───────────────────────────────────────────
def build_app(cfg: Config) -> Application:
    builder = (
        Application.builder()
        .token(cfg.bot_token)
        .defaults(Defaults(parse_mode=ParseMode.HTML, tzinfo=UTC))
        .concurrent_updates(UserOrderedUpdateProcessor(48))
        .post_init(post_init)
        .post_shutdown(post_shutdown)
    )
    if cfg.uses_local_api:
        builder = builder.base_url(cfg.telegram_api_url.strip())
        if cfg.telegram_api_file_url.strip():
            builder = builder.base_file_url(cfg.telegram_api_file_url.strip())

    app = builder.build()
    app.bot_data["cfg"] = cfg

    app.add_handler(TypeHandler(Update, gate), group=-1)

    commands = {
        "start": start_flow.cmd_start,
        "help": start_flow.cmd_help,
        "sites": start_flow.cmd_sites,
        "me": start_flow.cmd_me,
        "lang": start_flow.cmd_lang,
        "settings": start_flow.cmd_settings,
        "cancel": start_flow.cmd_cancel,
        "links": links_flow.cmd_links,
        "admin": admin_flow.cmd_admin,
    }
    for name, handler in commands.items():
        app.add_handler(CommandHandler(name, _private_command(handler)))
    app.add_handler(CommandHandler("setup", admin_flow.cmd_setup))

    app.add_handler(CallbackQueryHandler(callbacks_flow.on_callback))
    app.add_handler(
        MessageHandler(filters.FORWARDED & ~filters.COMMAND, admin_flow.handle_forwarded)
    )
    app.add_handler(MessageHandler(filters.ATTACHMENT, files_flow.handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router.on_text))

    app.add_error_handler(errors_flow.on_error)
    return app


def run_bot(cfg: Config) -> None:
    app = build_app(cfg)
    log.info("starting polling…")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
        close_loop=True,
    )
