"""دستورهای عمومی، منو و وضعیت کاربر."""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards as kb
from app.bot.common import edit, fmt_ts, lang_of, reply, safe_answer, services
from app.bot.guards import is_admin
from app.bot.states import ST_CONTACT, clear_state, set_state
from app.core import human, text
from app.db import repo

log = logging.getLogger("leechx.start")


# ── دستورها ────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = update.effective_user

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
    body = text.t(lang, "start", ttl=_fmt_hours(svc.settings.ttl_hours))
    await reply(update, body, reply_markup=kb.main_menu(lang, admin))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    admin = await is_admin(svc.cfg, update.effective_user.id)
    body = text.t(
        lang,
        "help",
        ttl=_fmt_hours(svc.settings.ttl_hours),
        max_mb=svc.settings.max_upload_bytes // (1024 * 1024),
    )
    await reply(update, body, reply_markup=kb.main_menu(lang, admin))


async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = update.effective_user
    row = await repo.get_user(user.id)
    admin = await is_admin(svc.cfg, user.id)
    body = text.t(
        lang,
        "status",
        uid=user.id,
        downloads=row.downloads if row else 0,
        joined=fmt_ts(row.created_at if row else None),
        admin=text.t(lang, "yes" if admin else "no"),
    )
    await reply(update, body, reply_markup=kb.main_menu(lang, admin))


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
    admin = await is_admin(svc.cfg, update.effective_user.id)
    await reply(update, body, reply_markup=kb.main_menu(lang, admin))


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    clear_state(context)
    user = update.effective_user
    canceled = 0
    for task in svc.jobs.tasks_for_user(user.id):
        if svc.jobs.cancel(task.id, user.id):
            canceled += 1
    if canceled:
        await reply(update, text.t(lang, "canceled"))
    else:
        await reply(update, text.t(lang, "send_link_or_file"))


async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang_of(context)
    rows = [
        [kb.Btn(text.LANGS[code], callback_data=f"l|{code}")] for code in text.LANGS
    ]
    await reply(update, "🌍", reply_markup=kb.Kb(rows))


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
    admin = await is_admin(svc.cfg, update.effective_user.id)
    await safe_answer(query)

    if action == "close":
        await edit(query.message, "✖️")
        try:
            await query.message.delete()
        except Exception:  # noqa: BLE001
            pass
        return

    if action == "home":
        await edit(
            query.message,
            text.t(lang, "start", ttl=_fmt_hours(svc.settings.ttl_hours)),
            reply_markup=kb.main_menu(lang, admin),
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
            reply_markup=kb.main_menu(lang, admin),
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
            ),
            reply_markup=kb.main_menu(lang, admin),
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
            reply_markup=kb.main_menu(lang, admin),
        )
        return

    if action == "settings":
        rows = [[kb.Btn(text.LANGS[code], callback_data=f"l|{code}")] for code in text.LANGS]
        rows.append([kb.Btn(text.t(lang, "btn_back"), callback_data=kb.M_HOME)])
        await edit(
            query.message,
            f"<b>{text.t(lang, 'btn_settings')}</b>",
            reply_markup=kb.Kb(rows),
        )
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


async def on_lang(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str) -> None:
    if code not in text.LANGS:
        return
    query = update.callback_query
    svc = services(context)
    await repo.set_lang(update.effective_user.id, code)
    context.user_data["lang"] = code
    admin = await is_admin(svc.cfg, update.effective_user.id)
    await safe_answer(query, text.LANGS[code])
    await edit(
        query.message,
        text.t(code, "start", ttl=_fmt_hours(svc.settings.ttl_hours)),
        reply_markup=kb.main_menu(code, admin),
    )


def _fmt_hours(hours: float) -> str:
    return f"{hours:g}"
