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
from app.bot.common import lang_of, reply, safe_answer
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

COMMANDS = [
    ("start", "شروع"),
    ("help", "راهنما"),
    ("sites", "سایت‌های پشتیبانی"),
    ("me", "وضعیت من"),
    ("settings", "تنظیمات"),
    ("lang", "تغییر زبان"),
    ("cancel", "لغو کار جاری"),
    ("links", "لینک‌های مستقیم من"),
]


# ── چرخهٔ عمر ───────────────────────────────────────────────
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
                await repo.set_lang(user.id, detected)
                row.lang = detected
            except Exception:  # noqa: BLE001
                log.debug("could not store detected language", exc_info=True)

    context.user_data.setdefault("lang", row.lang or cfg.default_lang)
    preview = in_preview(context)
    staff = await is_staff(cfg, user.id)
    context.user_data["is_admin"] = staff and not preview

    # پنل مدیریت همیشه فارسی است؛ تغییر زبان مخصوص کاربران عادی (و حالت پیش‌نمایش) است.
    if staff and not preview:
        context.user_data["lang"] = text.DEFAULT_LANG

    if row.is_banned:
        await reply(update, text.t(lang_of(context), "banned"))
        raise ApplicationHandlerStop

    if services.settings.maintenance and not (staff and not preview):
        await reply(update, text.t(lang_of(context), "maintenance"))
        raise ApplicationHandlerStop

    # ── عضویت اجباری ──────────────────────────────────────
    # ادمین‌ها معاف‌اند، اما در «حالت پیش‌نمایش کاربر» دقیقاً مثل کاربر عادی.
    if staff and not preview:
        return
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
    await reply(update, body, reply_markup=kb.join_gate(lang, missing))
    raise ApplicationHandlerStop


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

    app.add_handler(CommandHandler("start", start_flow.cmd_start))
    app.add_handler(CommandHandler("help", start_flow.cmd_help))
    app.add_handler(CommandHandler("sites", start_flow.cmd_sites))
    app.add_handler(CommandHandler("me", start_flow.cmd_me))
    app.add_handler(CommandHandler("lang", start_flow.cmd_lang))
    app.add_handler(CommandHandler("settings", start_flow.cmd_settings))
    app.add_handler(CommandHandler("cancel", start_flow.cmd_cancel))
    app.add_handler(CommandHandler("links", links_flow.cmd_links))
    app.add_handler(CommandHandler("admin", admin_flow.cmd_admin))
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
