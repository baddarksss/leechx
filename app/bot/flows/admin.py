"""پنل ادمین: آمار، ادمین‌ها، تنظیمات، پیام همگانی، مدیریت کاربر."""
from __future__ import annotations

import asyncio
import logging
import time

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.bot import keyboards as kb
from app.bot.common import edit, fmt_ts, lang_of, reply, safe_answer, services
from app.bot.guards import is_admin, require_admin
from app.bot.states import (
    ST_ADD_ADMIN,
    ST_BROADCAST,
    ST_LOOKUP_USER,
    ST_SET_VALUE,
    clear_state,
    get_data,
    set_state,
)
from app.core import human, text
from app.db import repo
from app.services.runtime_settings import SCHEMA

log = logging.getLogger("leechx.admin")

STATUS_ICON = {
    "queued": "🕒",
    "running": "⚡️",
    "done": "✅",
    "failed": "❌",
    "canceled": "✖️",
}


# ── ورود به پنل ────────────────────────────────────────────
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_admin(update, context):
        return
    lang = lang_of(context)
    await reply(update, text.t(lang, "admin_panel"), reply_markup=kb.admin_menu(lang))


async def show_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context)
    query = update.callback_query
    if query is not None:
        await edit(query.message, text.t(lang, "admin_panel"), reply_markup=kb.admin_menu(lang))
    else:
        await reply(update, text.t(lang, "admin_panel"), reply_markup=kb.admin_menu(lang))


# ── هندلر callbackها ───────────────────────────────────────
async def on_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, args: list[str]) -> None:
    if not await require_admin(update, context):
        return
    svc = services(context)
    lang = lang_of(context)
    query = update.callback_query
    msg = query.message if query else None

    if action == "back":
        await safe_answer(query)
        await show_panel(update, context)
        return

    if action == "stats":
        await safe_answer(query)
        await edit(msg, await _render_stats(context), reply_markup=kb.admin_menu(lang))
        return

    if action == "jobs":
        await safe_answer(query)
        await edit(msg, await _render_jobs(), reply_markup=kb.admin_menu(lang))
        return

    if action == "admins":
        await safe_answer(query)
        await _render_admins(update, context)
        return

    if action == "admadd":
        await safe_answer(query)
        set_state(context, ST_ADD_ADMIN)
        await edit(msg, text.t(lang, "admin_add_prompt"))
        return

    if action == "admrm":
        await safe_answer(query)
        if args:
            uid = int(args[0])
            if uid in svc.cfg.owners:
                await safe_answer(query, text.t(lang, "admin_owner_immutable"), alert=True)
                return
            ok = await repo.remove_admin(uid)
            await safe_answer(query, text.t(lang, "admin_remove_ok" if ok else "admin_remove_fail", uid=uid))
            if uid in svc.cfg.extra_admins:
                await safe_answer(
                    query,
                    text.t(lang, "admin_env_admin"),
                    alert=True,
                )
            await _render_admins(update, context)
        return

    if action == "set":
        await safe_answer(query)
        await edit(
            msg,
            _render_settings(context),
            reply_markup=kb.settings_menu(lang, svc.settings.snapshot()),
        )
        return

    if action == "toggle":
        if not args:
            return
        key = args[0]
        if key in SCHEMA:
            value = await svc.settings.toggle(key)
            await safe_answer(query, f"{svc.settings.label(key)}: {'ON' if value else 'OFF'}")
            await edit(
                msg,
                _render_settings(context),
                reply_markup=kb.settings_menu(lang, svc.settings.snapshot()),
            )
        return

    if action == "edit":
        if not args:
            return
        key = args[0]
        if key not in SCHEMA:
            return
        await safe_answer(query)
        set_state(context, ST_SET_VALUE, key=key)
        await edit(msg, text.t(lang, "admin_set_value", label=svc.settings.label(key)))
        return

    if action == "bc":
        await safe_answer(query)
        set_state(context, ST_BROADCAST)
        await edit(msg, text.t(lang, "admin_broadcast_prompt"))
        return

    if action == "user":
        await safe_answer(query)
        set_state(context, ST_LOOKUP_USER)
        await edit(msg, text.t(lang, "admin_user_prompt"))
        return

    if action == "clean":
        await safe_answer(query)
        removed, freed = await svc.cleanup_once()
        await edit(
            msg,
            text.t(
                lang,
                "admin_cleanup_done",
                files=removed,
                size=human.human_bytes(freed),
            ),
            reply_markup=kb.admin_menu(lang),
        )
        return

    if action in ("ban", "unban") and args:
        uid = int(args[0])
        await repo.set_banned(uid, action == "ban")
        await safe_answer(query, "✅")
        await _show_user(update, context, uid)
        return


# ── رندرها ─────────────────────────────────────────────────
async def _render_stats(context: ContextTypes.DEFAULT_TYPE) -> str:
    svc = services(context)
    lang = lang_of(context)
    users = await repo.count_users()
    admins = await repo.count_admins() + len(svc.cfg.owners)
    jobs, done, failed = await repo.jobs_count_today()
    shared = await repo.count_shared()
    shared_size = await repo.shared_total_size()
    used = svc.store.total_size() + shared_size
    return text.t(
        lang,
        "admin_stats",
        users=users,
        admins=admins,
        jobs=jobs,
        done=done,
        failed=failed,
        active=svc.jobs.active_count,
        shared=shared,
        shared_size=human.human_bytes(shared_size),
        disk=f"{human.human_bytes(used)} / {human.human_bytes(svc.store.disk_free())} free",
        uptime=human.human_duration(svc.uptime),
    )


async def _render_jobs() -> str:
    rows = await repo.recent_jobs(10)
    if not rows:
        return "—"
    lines = []
    for job in rows:
        when = time.strftime("%m-%d %H:%M", time.localtime(job.created_at))
        icon = STATUS_ICON.get(job.status, "•")
        size = human.human_bytes(job.size) if job.size else "—"
        title = human.truncate(job.title or job.url, 40)
        lines.append(
            f"{icon} <code>{job.id}</code> {when} · {job.quality or job.kind}\n"
            f"   {human.esc(title)} · {size} · <code>{job.user_id}</code>"
        )
    return "<b>🧾 کارهای اخیر</b>\n\n" + "\n".join(lines)


async def _render_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    rows = await repo.list_admins()
    owners = "، ".join(f"<code>{uid}</code>" for uid in svc.cfg.owners) or "—"
    if rows:
        lines = []
        for row in rows:
            lines.append(f"• <code>{row.user_id}</code> — {fmt_ts(row.created_at)}")
        body = text.t(lang, "admin_admins", owners=owners, admins="\n".join(lines))
    else:
        body = text.t(lang, "admin_admins", owners=owners, admins="—")
    menu = kb.admins_menu(lang, [row.user_id for row in rows])
    query = update.callback_query
    if query is not None:
        await edit(query.message, body, reply_markup=menu)
    else:
        await reply(update, body, reply_markup=menu)


def _render_settings(context: ContextTypes.DEFAULT_TYPE) -> str:
    svc = services(context)
    lang = lang_of(context)
    snap = svc.settings.snapshot()
    return text.t(
        lang,
        "admin_settings",
        ttl=f"{snap['link_ttl_hours']:g}",
        max_upload=snap["max_upload_mb"],
        max_link=snap["max_link_mb"],
        rate=f"{snap['rate_limit_seconds']:g}",
        maintenance=text.t(lang, "yes" if snap["maintenance"] else "no"),
        nsfw=text.t(lang, "yes" if snap["nsfw_enabled"] else "no"),
    )


async def _show_user(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = await repo.get_user(uid)
    msg = update.callback_query.message if update.callback_query else update.effective_message
    if user is None:
        await edit(msg, text.t(lang, "admin_add_fail"))
        return
    body = text.t(
        lang,
        "admin_user_info",
        uid=user.id,
        name=human.esc(user.first_name or "—"),
        username=human.esc(user.username or "—"),
        downloads=user.downloads,
        banned=text.t(lang, "yes" if user.is_banned else "no"),
        admin=text.t(lang, "yes" if await is_admin(svc.cfg, uid) else "no"),
        joined=fmt_ts(user.created_at),
    )
    action = "unban" if user.is_banned else "ban"
    label = text.t(lang, "btn_unban" if user.is_banned else "btn_ban")
    await edit(
        msg,
        body,
        reply_markup=kb.back_home(lang, [[kb.Btn(label, callback_data=f"a|{action}|{uid}")]]),
    )


# ── ورودی متنی حالت‌ها ─────────────────────────────────────
async def handle_state(update: Update, context: ContextTypes.DEFAULT_TYPE, state: str) -> None:
    if not await require_admin(update, context):
        clear_state(context)
        return

    svc = services(context)
    lang = lang_of(context)
    message = update.effective_message
    raw = (message.text or "").strip() if message else ""
    if not raw:
        await reply(update, text.t(lang, "admin_bad_value"))
        return

    if state == ST_BROADCAST:
        clear_state(context)
        ids = await repo.all_user_ids()
        await reply(update, text.t(lang, "admin_broadcast_started", count=len(ids)))
        ok, fail = await broadcast(context, ids, message.text_html or human.esc(raw), lang)
        await reply(update, text.t(lang, "admin_broadcast_done", ok=ok, fail=fail))
        return

    if state == ST_ADD_ADMIN:
        user = await _resolve_user(raw)
        clear_state(context)
        if user is None:
            await reply(update, text.t(lang, "admin_add_fail"))
            return
        if await repo.count_admins() >= svc.cfg.max_admins > 0:
            await reply(update, text.t(lang, "admin_limit_reached", max=svc.cfg.max_admins))
            return
        await repo.add_admin(user.id, update.effective_user.id)
        await reply(update, text.t(lang, "admin_add_ok", uid=user.id))
        return

    if state == ST_SET_VALUE:
        key = get_data(context).get("key", "")
        clear_state(context)
        if key not in SCHEMA:
            await reply(update, text.t(lang, "admin_bad_value"))
            return
        kind = SCHEMA[key][0]
        try:
            if kind == "bool":
                value = raw.lower() in ("1", "on", "true", "yes", "بله", "روشن")
            elif kind == "int":
                value = int(raw)
            else:
                value = float(raw)
        except ValueError:
            await reply(update, text.t(lang, "admin_bad_value"))
            return
        await svc.settings.set(key, value)
        svc.limiter.set_interval(svc.settings.rate_limit_seconds)
        await reply(
            update,
            text.t(lang, "admin_set_ok", label=svc.settings.label(key), value=value),
            reply_markup=kb.settings_menu(lang, svc.settings.snapshot()),
        )
        return

    if state == ST_LOOKUP_USER:
        clear_state(context)
        user = await _resolve_user(raw)
        if user is None:
            await reply(update, text.t(lang, "admin_add_fail"))
            return
        await _show_user(update, context, user.id)
        return

    clear_state(context)


async def _resolve_user(raw: str):
    token = raw.strip().lstrip("@")
    if token.lstrip("-").isdigit():
        return await repo.get_user(int(token))
    return await repo.find_user_by_username(token)


# ── پیام همگانی ────────────────────────────────────────────
async def broadcast(
    context: ContextTypes.DEFAULT_TYPE,
    ids: list[int],
    body: str,
    lang: str,
) -> tuple[int, int]:
    bot = context.bot
    sem = asyncio.Semaphore(15)
    ok = fail = 0

    async def send(uid: int) -> None:
        nonlocal ok, fail
        async with sem:
            try:
                await bot.send_message(uid, body, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                ok += 1
            except Exception:  # noqa: BLE001 — کاربر بلاک کرده / حذف شده
                fail += 1
            await asyncio.sleep(0.03)

    await asyncio.gather(*(send(uid) for uid in ids))
    log.info("broadcast finished: ok=%d fail=%d", ok, fail)
    return ok, fail
