"""پنل ادمین: آمار، ادمین‌ها، تنظیمات، پیام همگانی، مدیریت کاربر."""
from __future__ import annotations

import asyncio
import logging
import time

from telegram import MessageOriginUser, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes

from app.bot import keyboards as kb
from app.bot.common import edit, fmt_ts, lang_of, reply, safe_answer, services
from app.bot.guards import is_admin, require_admin
from app.bot.states import (
    ST_ADD_ADMIN,
    ST_BAN,
    ST_BROADCAST,
    ST_COOKIE_ADD,
    ST_GROUP_ID,
    ST_LOOKUP_USER,
    ST_RUNTIME_VALUE,
    ST_SET_VALUE,
    clear_state,
    get_data,
    get_state,
    set_state,
)
from app.core import human, text
from app.db import repo
from app.services.cookies import CookieError
from app.services.runtime_settings import RUNTIME_KEYS, SCHEMA

log = logging.getLogger("leechx.admin")

STATUS_ICON = {
    "queued": "🕒",
    "running": "⚡️",
    "done": "✅",
    "failed": "❌",
    "canceled": "✖️",
}

# تغییر این مقادیر فقط بعد از ری‌استارت کامل اثر می‌گذارد.
RESTART_KEYS = {
    "telegram_api_url",
    "telegram_api_file_url",
    "telegram_api_id",
    "telegram_api_hash",
}


# ── ورود به پنل ────────────────────────────────────────────
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_admin(update, context):
        return
    lang = lang_of(context)
    await reply(update, text.t(lang, "admin_panel"), reply_markup=kb.admin_menu(lang))
    if update.effective_chat.type == "private":
        await reply(update, "📌 منوی ثابت مدیریت", reply_markup=kb.admin_persistent_menu(lang))


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
    clear_state(context)  # menu actions always supersede stale input forms
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
            await svc.admin_group.audit("security", "admin_removed",
                                        update.effective_user.id, f"target={uid}, changed={ok}")
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
        if key in SCHEMA and SCHEMA[key][0] == "bool":
            value = await svc.settings.toggle(key)
            await svc.admin_group.audit("security", "setting_toggled",
                                        update.effective_user.id, f"{key}={value}")
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

    if action == "cookies":
        await safe_answer(query)
        await _render_cookies(update, context)
        return

    if action == "ckadd":
        await safe_answer(query)
        set_state(context, ST_COOKIE_ADD)
        await edit(msg, text.t(lang, "cookie_add_prompt"))
        return

    if action == "cktest":
        await safe_answer(query)
        await _render_cookie_test(update, context)
        return

    if action == "ckdel":
        await safe_answer(query)
        if args:
            name = args[0]
            ok = svc.cookies.delete(name)
            await safe_answer(
                query,
                text.t(lang, "cookie_deleted" if ok else "cookie_missing", name=human.esc(name)),
            )
            await _render_cookies(update, context)
        return

    if action == "banmenu":
        await safe_answer(query)
        set_state(context, ST_BAN)
        await edit(
            msg,
            text.t(lang, "admin_ban_prompt") + "\n\n" + text.t(lang, "admin_forward_hint"),
            reply_markup=kb.back_home(lang),
        )
        return

    if action == "group":
        await safe_answer(query)
        await _render_group(update, context)
        return

    if action == "groupid":
        await safe_answer(query)
        set_state(context, ST_GROUP_ID)
        await edit(
            msg,
            text.t(lang, "admin_group_prompt")
            + "\n\n"
            + text.t(lang, "admin_group_hint_setup"),
            reply_markup=kb.back_home(lang),
        )
        return

    if action == "grouptest":
        await safe_answer(query)
        ok = False
        if svc.admin_group.configured:
            ok = await svc.admin_group.send(
                "logs",
                "🧪 <b>LeechX</b> — admin group test message.",
            )
        await safe_answer(
            query,
            text.t(lang, "admin_group_test_ok" if ok else "admin_group_test_fail"),
            alert=True,
        )
        return

    if action == "groupoff":
        await safe_answer(query)
        await svc.admin_group.audit("security", "group_disconnected", update.effective_user.id)
        await svc.admin_group.disable()
        await safe_answer(query, text.t(lang, "admin_group_off_done"))
        await _render_group(update, context)
        return

    if action == "reports":
        await safe_answer(query)
        await _render_reports(update, context)
        return

    if action == "rpclose":
        if args:
            rid = int(args[0])
            ok = await repo.set_report_status(rid)
            await safe_answer(
                query,
                text.t(lang, "admin_report_closed" if ok else "admin_report_missing", id=rid),
            )
            await _render_reports(update, context)
        else:
            await safe_answer(query)
        return

    if action == "logs":
        await safe_answer(query)
        await _render_logs(update, context)
        return

    if action == "logclear":
        await safe_answer(query)
        count = await repo.clear_logs()
        await safe_answer(query, text.t(lang, "admin_logs_cleared", count=count))
        await _render_logs(update, context)
        return

    if action == "runtime":
        await safe_answer(query)
        await _render_runtime(update, context)
        return

    if action == "redit":
        if not args:
            await safe_answer(query)
            return
        key = args[0]
        if key not in RUNTIME_KEYS or key not in SCHEMA:
            await safe_answer(query)
            return
        await safe_answer(query)
        set_state(context, ST_RUNTIME_VALUE, key=key)
        await edit(
            msg,
            text.t(lang, "admin_runtime_prompt", label=svc.settings.label(key)),
            reply_markup=kb.back_home(lang),
        )
        return

    if action in ("ban", "unban") and args:
        uid = int(args[0])
        await repo.set_banned(uid, action == "ban")
        await svc.admin_group.audit("security", f"user_{action}", update.effective_user.id,
                                    f"target={uid}")
        await safe_answer(query, "✅")
        await _show_user(update, context, uid)
        return


# ── رندرها ─────────────────────────────────────────────────
async def _render_stats(context: ContextTypes.DEFAULT_TYPE) -> str:
    svc = services(context)
    lang = lang_of(context)
    users = await repo.count_users()
    active_users = await repo.count_active_users(7)
    banned = await repo.count_banned_users()
    admins = await repo.count_admins() + len(svc.cfg.owners)
    jobs, done, failed = await repo.jobs_count_today()
    active_links = await repo.count_active_shared()
    reports = await repo.count_open_reports()
    shared_size = await repo.shared_total_size()
    used = svc.store.total_size() + shared_size
    return text.t(
        lang,
        "admin_stats",
        users=users,
        active_users=active_users,
        banned=banned,
        uploading=svc.jobs.uploading_users,
        active_links=active_links,
        reports=reports,
        admins=admins,
        jobs=jobs,
        done=done,
        failed=failed,
        active=svc.jobs.active_count,
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


async def _render_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    files = svc.cookies.list_files()
    lines = [svc.cookies.describe(cookie) for cookie in files]
    if not lines:
        lines = [text.t(lang, "cookie_empty")]
    body = text.t(lang, "admin_cookies", count=len(files), list="\n".join(lines))
    menu = kb.cookies_menu(lang, [cookie.name for cookie in files])
    query = update.callback_query
    if query is not None:
        await edit(query.message, body, reply_markup=menu)
    else:
        await reply(update, body, reply_markup=menu)


async def _render_cookie_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    files = svc.cookies.list_files()
    lines: list[str] = []
    for cookie in files:
        problems = svc.cookies.problems(cookie)
        if problems:
            status = text.t(
                lang,
                "cookie_problem",
                reason=human.esc("; ".join(problems)),
            )
        else:
            status = text.t(lang, "cookie_ok")
        lines.append(f"• <b>{cookie.name}</b> — {status}")
    if not lines:
        lines = [text.t(lang, "cookie_empty")]
    body = text.t(lang, "cookie_test_result", list="\n".join(lines))
    menu = kb.cookies_menu(lang, [cookie.name for cookie in files])
    query = update.callback_query
    if query is not None:
        await edit(query.message, body, reply_markup=menu)
    else:
        await reply(update, body, reply_markup=menu)


async def _render_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    group = svc.admin_group
    status = text.t(
        lang,
        "admin_group_configured" if group.configured else "admin_group_not_configured",
    )
    hint = text.t(
        lang,
        "admin_group_hint_ok" if group.configured else "admin_group_hint_setup",
    )
    body = text.t(
        lang,
        "admin_group_panel",
        status=status,
        title=human.esc(group.title or "—"),
        chat=group.chat_id or "—",
        downloads=svc.settings.get_str("topic_downloads") or "—",
        uploads=svc.settings.get_str("topic_uploads") or "—",
        reports=svc.settings.get_str("topic_reports") or "—",
        logs=svc.settings.get_str("topic_logs") or "—",
        hint=hint,
    )
    body += (
        f"\n\n📦 کش رسانه‌ها: {group.topic_id('cache') or '—'}"
        f"\n🧾 ممیزی عملیات: {group.topic_id('audit') or '—'}"
        f"\n🔐 امنیت و تنظیمات: {group.topic_id('security') or '—'}"
    )
    menu = kb.group_menu(lang, group.configured)
    query = update.callback_query
    if query is not None:
        await edit(query.message, body, reply_markup=menu)
    else:
        await reply(update, body, reply_markup=menu)


async def _render_reports(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context)
    rows = await repo.recent_reports(limit=10, status="open")
    if not rows:
        body = text.t(lang, "admin_reports", count=0, list=text.t(lang, "admin_reports_empty"))
    else:
        items = []
        for row in rows:
            kind = text.t(
                lang,
                "admin_report_kind_contact"
                if row.kind == "contact"
                else "admin_report_kind_unsupported",
            )
            icon = "✉️" if row.kind == "contact" else "🌐"
            parts = []
            if row.url:
                parts.append(f"🔗 <code>{human.esc(human.truncate(row.url, 300))}</code>")
            if row.text:
                parts.append(f"💬 {human.esc(human.truncate(row.text, 500))}")
            items.append(
                text.t(
                    lang,
                    "admin_report_item",
                    icon=icon,
                    id=row.id,
                    kind=kind,
                    when=time.strftime("%m-%d %H:%M", time.localtime(row.created_at)),
                    name=human.esc(row.first_name or "—"),
                    username=human.esc(row.username or "—"),
                    uid=row.user_id,
                    body="\n".join(parts) or "—",
                )
            )
        body = text.t(lang, "admin_reports", count=len(rows), list="\n\n".join(items))
    menu = kb.reports_menu(lang, [row.id for row in rows])
    query = update.callback_query
    if query is not None:
        await edit(query.message, body, reply_markup=menu)
    else:
        await reply(update, body, reply_markup=menu)


async def _render_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context)
    rows = await repo.recent_logs(15)
    if not rows:
        body = text.t(lang, "admin_logs", count=0, list=text.t(lang, "admin_logs_empty"))
    else:
        icons = {"ERROR": "❌", "WARNING": "⚠️", "INFO": "ℹ️"}
        lines = []
        for row in rows:
            when = time.strftime("%m-%d %H:%M", time.localtime(row.created_at))
            line = (
                f"{icons.get(row.level, '•')} <b>{human.esc(row.level)}</b> · "
                f"<code>{human.esc(row.source)}</code> · {when}\n"
                f"{human.esc(human.truncate(row.message, 400))}"
            )
            if row.user_id:
                line += f"\n👤 <code>{row.user_id}</code> · #{row.id}"
            lines.append(line)
        body = text.t(lang, "admin_logs", count=len(rows), list="\n\n".join(lines))
    menu = kb.logs_menu(lang)
    query = update.callback_query
    if query is not None:
        await edit(query.message, body, reply_markup=menu)
    else:
        await reply(update, body, reply_markup=menu)


async def _render_runtime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    items = [
        (key, svc.settings.label(key), svc.settings.masked(key))
        for key in RUNTIME_KEYS
    ]
    body = text.t(lang, "admin_runtime")
    menu = kb.runtime_menu(lang, items)
    query = update.callback_query
    if query is not None:
        await edit(query.message, body, reply_markup=menu)
    else:
        await reply(update, body, reply_markup=menu)


async def _show_user(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = await repo.get_user(uid)
    msg = update.callback_query.message if update.callback_query else update.effective_message
    if user is None:
        if update.callback_query is not None:
            await edit(msg, text.t(lang, "admin_add_fail"))
        else:
            await reply(update, text.t(lang, "admin_add_fail"))
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
    markup = kb.back_home(lang, [[kb.Btn(label, callback_data=f"a|{action}|{uid}")]])
    if update.callback_query is not None:
        await edit(msg, body, reply_markup=markup)
    else:
        await reply(update, body, reply_markup=markup)


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
        await svc.admin_group.audit("security", "broadcast_completed",
                                    update.effective_user.id, f"sent={ok}, failed={fail}")
        return

    if state == ST_ADD_ADMIN:
        user = await _resolve_user(raw, context=context)
        clear_state(context)
        if user is None:
            await reply(update, text.t(lang, "admin_add_fail"))
            return
        if await repo.count_admins() >= svc.cfg.max_admins > 0:
            await reply(update, text.t(lang, "admin_limit_reached", max=svc.cfg.max_admins))
            return
        await repo.add_admin(user.id, update.effective_user.id)
        await svc.admin_group.audit("security", "admin_added",
                                    update.effective_user.id, f"new_admin={user.id}")
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
        await svc.admin_group.audit("security", "setting_updated",
                                    update.effective_user.id, f"key={key} (value hidden)")
        svc.limiter.set_interval(svc.settings.rate_limit_seconds)
        await reply(
            update,
            text.t(lang, "admin_set_ok", label=svc.settings.label(key), value=value),
            reply_markup=kb.settings_menu(lang, svc.settings.snapshot()),
        )
        return

    if state == ST_LOOKUP_USER:
        clear_state(context)
        user = await _resolve_user(raw, context=context)
        if user is None:
            await reply(update, text.t(lang, "admin_add_fail"))
            return
        await _show_user(update, context, user.id)
        return

    if state == ST_BAN:
        clear_state(context)
        user = await _resolve_user(raw, context=context, create=True)
        if user is None:
            await reply(update, text.t(lang, "admin_add_fail"))
            return
        await _show_user(update, context, user.id)
        return

    if state == ST_GROUP_ID:
        clear_state(context)
        token = raw.strip()
        if not token.lstrip("-").isdigit() or int(token) >= 0:
            await reply(update, text.t(lang, "admin_group_bad_id"))
            return
        chat_id = int(token)
        title = ""
        try:
            chat = await context.bot.get_chat(chat_id)
            if (chat.type != "supergroup" or not getattr(chat, "is_forum", False)
                    or getattr(chat, "username", None)):
                await reply(update, "⚠️ یک سوپرگروه خصوصی با Topics فعال وارد کن.")
                return
            title = getattr(chat, "title", "") or ""
        except TelegramError:
            await reply(update, text.t(lang, "admin_group_test_fail"))
            return
        created = await svc.admin_group.configure(chat_id, title)
        ok = sum(1 for value in created.values() if value)
        failed = len(created) - ok
        await reply(
            update,
            text.t(lang, "admin_group_saved", created=ok, failed=failed),
            reply_markup=kb.group_menu(lang, True),
        )
        return

    if state == ST_RUNTIME_VALUE:
        key = get_data(context).get("key", "")
        clear_state(context)
        if key not in RUNTIME_KEYS or key not in SCHEMA:
            await reply(update, text.t(lang, "admin_bad_value"))
            return
        value = "" if raw.strip() == "-" else raw.strip()
        if key == "public_base_url" and value and not value.startswith(
            ("http://", "https://")
        ):
            await reply(update, text.t(lang, "admin_bad_value"))
            return
        await svc.settings.set(key, value)
        await svc.admin_group.audit("security", "runtime_updated",
                                    update.effective_user.id, f"key={key} (value hidden)")
        svc.settings.apply_to_config()
        if key == "rate_limit_seconds":
            svc.limiter.set_interval(svc.settings.rate_limit_seconds)
        body = text.t(
            lang,
            "admin_runtime_saved",
            label=svc.settings.label(key),
            value=human.esc(svc.settings.masked(key)),
        )
        if key in RESTART_KEYS:
            body += "\n\n" + text.t(lang, "admin_runtime_restart")
        items = [
            (item, svc.settings.label(item), svc.settings.masked(item))
            for item in RUNTIME_KEYS
        ]
        await reply(update, body, reply_markup=kb.runtime_menu(lang, items))
        return

    if state == ST_COOKIE_ADD:
        clear_state(context)
        try:
            cookie = svc.cookies.save_text(raw)
        except CookieError as exc:
            await reply(update, text.t(lang, "cookie_bad", reason=human.esc(str(exc)[:150])))
            return
        await reply(
            update,
            text.t(
                lang,
                "cookie_saved",
                name=human.esc(cookie.name),
                domains=human.esc(", ".join(cookie.domains[:5]) or "—"),
            ),
        )
        return

    clear_state(context)


async def _resolve_user(raw: str, context: ContextTypes.DEFAULT_TYPE | None = None, create: bool = False):
    """کاربر را با آیدی عددی یا @یوزرنیم پیدا می‌کند.

    برای بن کردن، اگر کاربر هنوز /start نزده باشد یک رکورد خالی ساخته می‌شود.
    """
    token = raw.strip()
    if token.lstrip("-").isdigit():
        uid = int(token)
        user = await repo.get_user(uid)
        if user is None and create:
            user = await repo.upsert_user(uid)
        return user

    handle = token.lstrip("@").strip()
    if not handle:
        return None
    user = await repo.find_user_by_username(handle)
    if user is not None or context is None:
        return user
    try:
        chat = await context.bot.get_chat(f"@{handle}")
    except Exception:  # noqa: BLE001 — یوزرنیم نامعتبر/خصوصی
        return None
    return await repo.upsert_user(
        chat.id,
        getattr(chat, "username", None),
        getattr(chat, "first_name", None),
    )


# ── راه‌اندازی گروه با /setup ────────────────────────────────
async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """گروه ادمین را از داخل خود گروه تنظیم می‌کند (قابل‌اعتمادترین راه)."""
    svc = services(context)
    lang = lang_of(context)
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or chat.type not in ("group", "supergroup"):
        await reply(update, text.t(lang, "setup_not_group"))
        return
    if user is None:
        return

    allowed = await is_admin(svc.cfg, user.id)
    if not allowed:
        await reply(update, text.t(lang, "setup_need_admin"))
        return

    # All operational messages and archived media belong in one private forum.
    if (chat.type != "supergroup" or not getattr(chat, "is_forum", False)
            or getattr(chat, "username", None)):
        await reply(update, "⚠️ گروه باید سوپرگروه خصوصی با قابلیت Topics فعال باشد.")
        return
    created = await svc.admin_group.configure(chat.id, chat.title or "")
    body = text.t(
        lang,
        "setup_done",
        downloads=created.get("downloads") or "—",
        uploads=created.get("uploads") or "—",
        reports=created.get("reports") or "—",
        logs=created.get("logs") or "—",
    )
    body += (
        f"\n📦 کش: <code>{created.get('cache') or '—'}</code>"
        f"\n🧾 ممیزی: <code>{created.get('audit') or '—'}</code>"
        f"\n🔐 امنیت: <code>{created.get('security') or '—'}</code>"
    )
    await reply(update, body)
    await svc.admin_group.audit("security", "group_setup", user.id,
                                f"group {chat.id}; topics {sum(bool(x) for x in created.values())}/7")


async def handle_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """در حالت «بن کردن»، پیام فورواردشده را به کاربر اصلی تبدیل می‌کند."""
    if get_state(context) != ST_BAN:
        message = update.effective_message
        if message is None:
            return
        if message.effective_attachment is not None:
            from app.bot.flows import files as files_flow
            await files_flow.handle_file(update, context)
        elif message.text:
            from app.bot.flows import text_router
            await text_router.on_text(update, context)
        return
    lang = lang_of(context)
    if not await require_admin(update, context):
        clear_state(context)
        raise ApplicationHandlerStop

    message = update.effective_message
    origin = getattr(message, "forward_origin", None)
    if not isinstance(origin, MessageOriginUser):
        await reply(
            update,
            text.t(lang, "admin_forward_hint")
            + "\n\n"
            + text.t(lang, "admin_ban_prompt"),
        )
        raise ApplicationHandlerStop

    clear_state(context)
    await _show_user(update, context, origin.sender_user.id)
    raise ApplicationHandlerStop


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
