"""پنل ادمین — شش دستهٔ روشن: آمار، کاربران، تنظیمات، گروه‌ها، دیپلوی، عیب‌یابی."""
from __future__ import annotations

import asyncio
import logging
import platform
import shutil
import time

from telegram import MessageOriginChannel, MessageOriginChat, MessageOriginUser, Update
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes

from app.bot import keyboards as kb
from app.bot.common import (
    edit,
    fmt_ts,
    lang_of,
    panel,
    reply,
    run_detached,
    safe_answer,
    send_home,
    services,
)
from app.bot.guards import in_preview, is_admin, is_staff, require_admin
from app.bot.states import (
    ST_ADD_ADMIN,
    ST_BAN,
    ST_BROADCAST,
    ST_COOKIE_ADD,
    ST_DEPLOY_ZIP,
    ST_GROUP_ID,
    ST_JOIN_CHAT,
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
from app.services.debug_access import SCOPES
from app.services.runtime_settings import RUNTIME_KEYS, SCHEMA
from app.version import CODENAME, RELEASE_DATE, __version__

log = logging.getLogger("leechx.admin")

STATUS_ICON = {
    "queued": "🕒",
    "running": "⚡️",
    "done": "✅",
    "failed": "❌",
    "canceled": "✖️",
}

# تغییر این مقادیر فقط بعد از ری‌استارت کامل اثر می‌گذارد.
# debug_enabled / debug_ip_allow عمداً اینجا نیستند: مسیرهای /debug/* همیشه ثبت
# می‌شوند و دسترسی در هر درخواست از تنظیمات زنده خوانده می‌شود.
RESTART_KEYS = {
    "telegram_api_url",
    "telegram_api_file_url",
    "telegram_api_id",
    "telegram_api_hash",
}


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "—"


def _ytdlp(svc) -> str:
    try:
        return svc.updater.ytdlp_version()
    except Exception:  # noqa: BLE001
        return "—"


# ── ورود به پنل ────────────────────────────────────────────
def _panel_body(lang: str) -> str:
    return text.t(lang, "admin_panel") + f"\n\n🤖 <b>LeechX v{__version__}</b> · {CODENAME}"


def _admin_kb(lang: str, update: Update):
    """کیبورد ثابت فقط در چت خصوصی معنی دارد؛ در گروه پیام بدون کیبورد می‌ماند."""
    if update.effective_chat is not None and update.effective_chat.type == "private":
        return kb.admin_persistent_menu(lang)
    return None


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_admin(update, context):
        return
    lang = lang_of(context)
    markup = _admin_kb(lang, update)
    if markup is None:
        await reply(update, _panel_body(lang))
        return
    await send_home(update, context, _panel_body(lang), markup)


async def show_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = lang_of(context)
    if update.callback_query is not None:
        # کیبورد ثابت با ویرایش پیام نمی‌آید؛ متن پنل در همان پیام می‌ماند.
        await panel(update, context, _panel_body(lang))
        return
    await cmd_admin(update, context)


async def show_section(update: Update, context: ContextTypes.DEFAULT_TYPE, section: str) -> None:
    """هر بخش در همان پیام پنل باز می‌شود (ویرایش، نه پیام تازه)."""
    lang = lang_of(context)
    svc = services(context)
    clear_state(context)

    if section == kb.SEC_STATS:
        body = await _render_stats(context)
        markup = kb.admin_section_menu(lang, kb.SEC_STATS)
    elif section == kb.SEC_USERS:
        body = text.t(lang, "admin_cat_users")
        markup = kb.admin_section_menu(lang, kb.SEC_USERS)
    elif section == kb.SEC_SETTINGS:
        body = _render_settings(context)
        markup = kb.settings_menu(lang, svc.settings.snapshot())
    elif section == kb.SEC_GROUPS:
        body = text.t(lang, "admin_cat_groups")
        markup = kb.admin_section_menu(lang, kb.SEC_GROUPS)
    elif section == kb.SEC_DEPLOY:
        await _render_deploy(update, context)
        return
    elif section == kb.SEC_DEBUG:
        await _render_debug(update, context)
        return
    elif section == kb.SEC_COOKIES:
        await _render_cookies(update, context)
        return
    elif section == kb.SEC_CANCEL:
        from app.bot.flows import start as start_flow

        await start_flow.cmd_cancel(update, context)
        return
    else:
        await show_panel(update, context)
        return

    await panel(update, context, body, markup)


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

    if action == "cat":
        # سازگاری با پیام‌های قدیمی: دسته → همان بخش.
        category = args[0] if args else ""
        await safe_answer(query)
        await show_section(update, context, category)
        return

    # ── آمار ──
    if action == "stats":
        await safe_answer(query)
        await panel(update, context, await _render_stats(context), reply_markup=kb.admin_section_menu(lang, kb.SEC_STATS))
        return

    if action == "jobs":
        await safe_answer(query)
        await panel(update, context, await _render_jobs(lang), reply_markup=kb.admin_section_menu(lang, kb.SEC_STATS))
        return

    if action == "traffic":
        await safe_answer(query)
        await panel(
            update,
            context,
            await _render_traffic(lang),
            reply_markup=kb.admin_section_menu(lang, kb.SEC_STATS),
        )
        return

    if action == "clean":
        await safe_answer(query)
        removed, freed = await svc.cleanup_once()
        await panel(
            update,
            context,
            text.t(lang, "admin_cleanup_done", files=removed, size=human.human_bytes(freed)),
            reply_markup=kb.admin_section_menu(lang, kb.SEC_STATS),
        )
        return

    # ── کاربران ──
    if action == "admins":
        await safe_answer(query)
        await _render_admins(update, context)
        return

    if action == "admadd":
        await safe_answer(query)
        set_state(context, ST_ADD_ADMIN)
        await panel(update, context, text.t(lang, "admin_add_prompt"))
        return

    if action == "admrm":
        uid = _int_arg(args)
        if uid is None:
            await safe_answer(query)
            return
        if uid in svc.cfg.owners:
            await safe_answer(query, text.t(lang, "admin_owner_immutable"), alert=True)
            return
        ok = await repo.remove_admin(uid)
        await svc.admin_group.audit("security", "admin_removed",
                                    update.effective_user.id, f"target={uid}, changed={ok}")
        if uid in svc.cfg.extra_admins:
            await safe_answer(query, text.t(lang, "admin_env_admin"), alert=True)
        else:
            await safe_answer(query, text.t(lang, "admin_remove_ok" if ok else "admin_remove_fail", uid=uid))
        await _render_admins(update, context)
        return

    if action == "bc":
        await safe_answer(query)
        set_state(context, ST_BROADCAST)
        await panel(update, context, text.t(lang, "admin_broadcast_prompt"))
        return

    if action == "user":
        await safe_answer(query)
        set_state(context, ST_LOOKUP_USER)
        await panel(update, context, text.t(lang, "admin_user_prompt"))
        return

    if action == "banmenu":
        await safe_answer(query)
        set_state(context, ST_BAN)
        await panel(
            update,
            context,
            text.t(lang, "admin_ban_prompt") + "\n\n" + text.t(lang, "admin_forward_hint"),
            reply_markup=kb.admin_section_menu(lang, kb.SEC_USERS),
        )
        return

    if action in ("ban", "unban") and _int_arg(args) is not None:
        uid = _int_arg(args)
        if action == "ban" and await is_staff(svc.cfg, uid):
            # ادمین/مالک نباید ناخواسته خودش یا همکارش را قفل کند.
            await safe_answer(query, text.t(lang, "admin_ban_staff"), alert=True)
            return
        await repo.set_banned(uid, action == "ban")
        await svc.admin_group.audit("security", f"user_{action}", update.effective_user.id, f"target={uid}")
        await safe_answer(query, "✅")
        await _show_user(update, context, uid)
        return

    # ── تنظیمات ──
    if action == "set":
        await safe_answer(query)
        await panel(
            update,
            context,
            _render_settings(context),
            reply_markup=kb.settings_menu(lang, svc.settings.snapshot()),
        )
        return

    if action == "toggle":
        if not args:
            await safe_answer(query)
            return
        key = args[0]
        if key in SCHEMA and SCHEMA[key][0] == "bool":
            value = await svc.settings.toggle(key)
            await svc.admin_group.audit("security", "setting_toggled",
                                        update.effective_user.id, f"{key}={value}")
            await safe_answer(query, f"{svc.settings.label(key, lang)}: {'ON' if value else 'OFF'}")
            await panel(
                update,
                context,
                _render_settings(context),
                reply_markup=kb.settings_menu(lang, svc.settings.snapshot()),
            )
        else:
            await safe_answer(query)
        return

    if action == "edit":
        if not args:
            await safe_answer(query)
            return
        key = args[0]
        if key not in SCHEMA:
            await safe_answer(query)
            return
        await safe_answer(query)
        set_state(context, ST_SET_VALUE, key=key)
        await panel(update, context, text.t(lang, "admin_set_value", label=svc.settings.label(key, lang)))
        return

    if action == "cookies":
        await safe_answer(query)
        await _render_cookies(update, context)
        return

    if action == "ckadd":
        await safe_answer(query)
        set_state(context, ST_COOKIE_ADD)
        await panel(update, context, text.t(lang, "cookie_add_prompt"))
        return

    if action == "cktest":
        await safe_answer(query)
        await _render_cookie_test(update, context)
        return

    if action == "ckdel":
        if args:
            name = args[0]
            ok = svc.cookies.delete(name)
            await svc.admin_group.audit("security", "cookie_deleted",
                                        update.effective_user.id, f"name={name}, changed={ok}")
            await safe_answer(
                query,
                # متن toast ساده است و HTML نمی‌پذیرد.
                text.t(lang, "cookie_deleted" if ok else "cookie_missing", name=name),
            )
            await _render_cookies(update, context)
        else:
            await safe_answer(query)
        return

    if action == "runtime":
        await safe_answer(query)
        await _render_runtime(update, context)
        return

    if action == "rtoggle":
        if not args or args[0] not in RUNTIME_KEYS or args[0] not in SCHEMA:
            await safe_answer(query)
            return
        key = args[0]
        value = await svc.settings.toggle(key)
        await safe_answer(
            query,
            text.t(lang, "admin_runtime_saved",
                   label=svc.settings.label(key, lang),
                   value=("🟢" if value else "🔴")),
        )
        await svc.admin_group.audit("security", "runtime_updated",
                                    update.effective_user.id, f"key={key}, value={value}")
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
        await panel(
            update,
            context,
            text.t(lang, "admin_runtime_prompt", label=svc.settings.label(key, lang)),
            reply_markup=kb.admin_section_menu(lang, kb.SEC_SETTINGS),
        )
        return

    # ── گروه‌ها و عضویت ──
    if action == "group":
        await safe_answer(query)
        await _render_group(update, context)
        return

    if action == "groupid":
        await safe_answer(query)
        set_state(context, ST_GROUP_ID)
        await panel(
            update,
            context,
            text.t(lang, "admin_group_prompt") + "\n\n" + text.t(lang, "admin_group_hint_setup"),
            reply_markup=kb.admin_section_menu(lang, kb.SEC_GROUPS),
        )
        return

    if action == "grouptest":
        ok = False
        if svc.admin_group.configured:
            ok = await svc.admin_group.send("logs", "🧪 <b>LeechX</b> — admin group test message.")
        await safe_answer(
            query,
            text.t(lang, "admin_group_test_ok" if ok else "admin_group_test_fail"),
            alert=True,
        )
        return

    if action == "groupoff":
        await svc.admin_group.audit("security", "group_disconnected", update.effective_user.id)
        await svc.admin_group.disable()
        await safe_answer(query, text.t(lang, "admin_group_off_done"))
        await _render_group(update, context)
        return

    if action == "join":
        await safe_answer(query)
        await _render_join(update, context)
        return

    if action == "jointoggle":
        await safe_answer(query)
        enabled = not svc.force_join.enabled
        await svc.force_join.set_enabled(enabled)
        await svc.admin_group.audit("security", "force_join_toggled",
                                    update.effective_user.id, f"enabled={enabled}")
        await _render_join(update, context)
        return

    if action == "joinadd":
        await safe_answer(query)
        set_state(context, ST_JOIN_CHAT)
        await panel(
            update,
            context,
            text.t(lang, "admin_join_prompt") + "\n\n" + text.t(lang, "admin_join_hint"),
            reply_markup=kb.admin_section_menu(lang, kb.SEC_GROUPS),
        )
        return

    if action == "joinrm":
        chat_id = _int_arg(args)
        if chat_id is None:
            await safe_answer(query)
            return
        removed = await svc.force_join.remove(chat_id)
        if removed is None:
            await safe_answer(query, text.t(lang, "admin_join_bad"), alert=True)
        else:
            await svc.admin_group.audit("security", "force_join_target_removed",
                                        update.effective_user.id, f"chat={chat_id}")
            await safe_answer(query, text.t(lang, "admin_join_removed", title=removed.title))
        await _render_join(update, context)
        return

    if action == "joincheck":
        await safe_answer(query)
        results = await svc.force_join.check_access(context.bot)
        if not results:
            body = text.t(lang, "admin_join_empty")
        elif all(ok for _, ok, _ in results):
            body = text.t(lang, "admin_join_check_ok")
        else:
            lines = [
                f"• {'✅' if ok else '❌'} <b>{human.esc(t.title)}</b> — {human.esc(detail or '—')}"
                for t, ok, detail in results
            ]
            body = text.t(lang, "admin_join_check_mixed", list="\n".join(lines))
        await panel(update, context, body, reply_markup=kb.force_join_menu(lang, svc.force_join.targets, svc.force_join.enabled))
        return

    # ── گزارش‌ها و لاگ‌ها ──
    if action == "reports":
        await safe_answer(query)
        await _render_reports(update, context)
        return

    if action == "rpclose":
        rid = _int_arg(args)
        if rid is not None:
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
        count = await repo.clear_logs()
        await safe_answer(query, text.t(lang, "admin_logs_cleared", count=count))
        await _render_logs(update, context)
        return

    # ── دیپلوی ──
    if action == "deploy":
        await safe_answer(query)
        await _render_deploy(update, context)
        return

    if action == "dpsrc":
        await safe_answer(query)
        await run_detached(context, _send_source_zip(update, context), update)
        return

    if action == "dpup":
        await safe_answer(query)
        set_state(context, ST_DEPLOY_ZIP)
        await panel(
            update,
            context,
            text.t(lang, "deploy_upload_prompt") + "\n\n" + text.t(lang, "deploy_update_note"),
            reply_markup=kb.admin_section_menu(lang, kb.SEC_DEPLOY),
        )
        return

    if action == "dpstaged":
        await safe_answer(query)
        await _render_staged(update, context)
        return

    if action == "dpapply":
        await safe_answer(query)
        await _apply_staged(update, context)
        return

    if action == "dpcancel":
        await safe_answer(query)
        context.user_data.pop("deploy_staged", None)
        await _render_deploy(update, context)
        return

    if action == "dpbackup":
        await safe_answer(query)
        await run_detached(context, _send_backup(update, context), update)
        return

    if action == "dprestart":
        await safe_answer(query)
        await panel(
            update,
            context,
            text.t(lang, "deploy_restart_confirm"),
            reply_markup=kb.deploy_restart_confirm(lang),
        )
        return

    if action == "dprestartyes":
        await safe_answer(query)
        await panel(update, context, text.t(lang, "deploy_restart_scheduled"))
        await svc.admin_group.audit("security", "manual_restart", update.effective_user.id)
        svc.request_restart()
        return

    if action in ("dpytdlp", "dpytdlpnight"):
        await safe_answer(query)
        await panel(update, context, text.t(lang, "deploy_ytdlp_working"))
        # نصب pip چند ده ثانیه طول می‌کشد؛ پنل در این مدت قفل نمی‌شود.
        await run_detached(
            context,
            _upgrade_ytdlp(update, context, msg, nightly=action.endswith("night")),
            update,
        )
        return

    if action == "dpver":
        await safe_answer(query)
        await panel(update, context, _version_text(svc, lang), reply_markup=kb.admin_section_menu(lang, kb.SEC_DEPLOY))
        return

    # ── عیب‌یابی ──
    if action == "debug":
        await safe_answer(query)
        await _render_debug(update, context)
        return

    if action == "dbtoggle":
        enabled = await svc.settings.toggle("debug_enabled")
        await safe_answer(
            query,
            text.t(lang, "debug_toggle_on" if enabled else "debug_toggle_off"),
        )
        await svc.admin_group.audit(
            "security", "debug_toggled", update.effective_user.id, f"enabled={enabled}"
        )
        await _render_debug(update, context)
        return

    if action == "dbttl":
        current = int(context.user_data.get("debug_ttl") or 6)
        hours = kb.next_debug_ttl(current, svc.debug.max_hours())
        context.user_data["debug_ttl"] = hours
        await safe_answer(query, text.t(lang, "btn_debug_ttl", hours=hours))
        await _render_debug(update, context)
        return

    if action == "dbmake":
        await safe_answer(query)
        if len(args) < 2:
            return
        scope, hours_raw = args[0], args[1]
        await _create_debug_token(update, context, scope, hours_raw)
        return

    if action == "dbinfo":
        token_id = _int_arg(args)
        row = next((t for t in await svc.debug.active() if t.id == token_id), None)
        if row is None:
            await safe_answer(query, text.t(lang, "debug_revoke_fail"), alert=True)
            await _render_debug(update, context)
            return
        await safe_answer(
            query,
            text.t(
                lang,
                "debug_token_info",
                id=row.id,
                scopes=text.t(lang, kb.debug_scope_key(row.scopes)),
                expires=time.strftime("%m-%d %H:%M", time.localtime(row.expires_at)),
                uses=row.uses,
            ),
            alert=True,
        )
        return

    if action == "dbrevoke":
        token_id = _int_arg(args)
        if token_id is None:
            await safe_answer(query)
            return
        ok = await svc.debug.revoke(token_id)
        if ok:
            await svc.admin_group.audit("security", "debug_token_revoked",
                                        update.effective_user.id, f"id={token_id}")
        await safe_answer(query, text.t(lang, "debug_revoke_ok" if ok else "debug_revoke_fail"))
        await _render_debug(update, context)
        return

    if action == "dbrevokeall":
        count = await svc.debug.revoke_all()
        await safe_answer(query, text.t(lang, "debug_revoke_ok"))
        await svc.admin_group.audit("security", "debug_tokens_revoked", update.effective_user.id,
                                    f"count={count}")
        await _render_debug(update, context)
        return

    if action == "dbhealth":
        await safe_answer(query)
        await _render_health(update, context)
        return

    if action in ("preview", "previewon"):
        await safe_answer(query)
        from app.bot.flows import start as start_flow

        # کیبورد ثابت کاربر جایگزین کیبورد ادمین می‌شود تا دقیقاً تجربهٔ یک ممبر عادی بماند.
        await start_flow.start_preview(update, context)
        return

    await safe_answer(query)


def _int_arg(args: list[str], index: int = 0) -> int | None:
    try:
        return int(args[index])
    except (IndexError, ValueError):
        return None


async def _upgrade_ytdlp(update: Update, context: ContextTypes.DEFAULT_TYPE, msg, *, nightly: bool) -> None:
    svc = services(context)
    lang = lang_of(context)
    try:
        result = await svc.updater.upgrade_ytdlp(nightly=nightly)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)[:200], "before": "?", "after": "?"}
    changed = bool(result.get("ok") and result.get("changed"))
    if changed:
        # ماژول yt_dlp قبلاً import شده است؛ بازسازی ایندکس فقط وقتی معنا دارد
        # که فرآیند دوباره بالا بیاید، ولی برای اطمینان از تازگی فهرست انجامش می‌دهیم.
        try:
            await asyncio.to_thread(svc.sites.build, True)
        except Exception:  # noqa: BLE001
            log.warning("site index rebuild failed", exc_info=True)
    if result.get("ok"):
        body = text.t(
            lang,
            "deploy_ytdlp_done",
            before=human.esc(str(result.get("before", "?"))),
            after=human.esc(str(result.get("after", "?"))),
        )
        if changed:
            body += "\n\n" + text.t(lang, "deploy_ytdlp_restart")
    else:
        body = text.t(lang, "deploy_ytdlp_fail", reason=human.esc(str(result.get("error") or "unknown")))
    await edit(msg, body, reply_markup=kb.admin_section_menu(lang, kb.SEC_DEPLOY))
    await svc.admin_group.audit(
        "system",
        "ytdlp_update",
        update.effective_user.id,
        f"ok={result.get('ok')}, changed={changed}, after={result.get('after')}, "
        f"dir={result.get('location', '')}",
    )
    if changed:
        # پیام اول برسد، بعد فرآیند نرم ری‌استارت شود تا اکسترکتورهای تازه بار شوند.
        await asyncio.sleep(1.5)
        svc.request_restart()


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
    used = await asyncio.to_thread(svc.store.total_size) + shared_size
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
        version=__version__,
    )


async def _render_traffic(lang: str = "fa") -> str:
    totals = await repo.traffic_totals()
    return text.t(
        lang,
        "admin_traffic",
        downloaded=human.human_bytes(totals["downloaded_bytes"]),
        source_downloaded=human.human_bytes(totals["source_download_bytes"]),
        telegram_received=human.human_bytes(totals["telegram_receive_bytes"]),
        uploaded=human.human_bytes(totals["uploaded_bytes"]),
        telegram_uploaded=human.human_bytes(totals["telegram_upload_bytes"]),
        link_served=human.human_bytes(totals["direct_link_serve_bytes"]),
        total=human.human_bytes(totals["total_bytes"]),
        note=text.t(lang, "traffic_note"),
    )


async def _render_jobs(lang: str = "fa") -> str:
    rows = await repo.recent_jobs(10)
    if not rows:
        return text.t(lang, "admin_jobs", list="—")
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
    return text.t(lang, "admin_jobs", list="\n".join(lines))


async def _render_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    rows = await repo.list_admins()
    owners = "، ".join(f"<code>{uid}</code>" for uid in svc.cfg.owners) or "—"
    if rows:
        lines = [f"• <code>{row.user_id}</code> — {fmt_ts(row.created_at)}" for row in rows]
        body = text.t(lang, "admin_admins", owners=owners, admins="\n".join(lines))
    else:
        body = text.t(lang, "admin_admins", owners=owners, admins="—")
    menu = kb.admins_menu(lang, [row.user_id for row in rows])
    await panel(update, context, body, menu)


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
        links=snap["max_links_per_user"],
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
    await panel(update, context, body, menu)


async def _render_cookie_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    files = svc.cookies.list_files()
    lines: list[str] = []
    for cookie in files:
        problems = svc.cookies.problems(cookie)
        if problems:
            status = text.t(lang, "cookie_problem", reason=human.esc("; ".join(problems)))
        else:
            status = text.t(lang, "cookie_ok")
        lines.append(f"• <b>{cookie.name}</b> — {status}")
    if not lines:
        lines = [text.t(lang, "cookie_empty")]
    body = text.t(lang, "cookie_test_result", list="\n".join(lines))
    menu = kb.cookies_menu(lang, [cookie.name for cookie in files])
    await panel(update, context, body, menu)


async def _render_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    group = svc.admin_group
    status = text.t(lang, "admin_group_configured" if group.configured else "admin_group_not_configured")
    hint = text.t(lang, "admin_group_hint_ok" if group.configured else "admin_group_hint_setup")
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
        f"\n\n📦 {group.topic_id('cache') or '—'}"
        f"\n🧾 {group.topic_id('audit') or '—'}"
        f"\n🔐 {group.topic_id('security') or '—'}"
    )
    menu = kb.group_menu(lang, group.configured)
    await panel(update, context, body, menu)


async def _render_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    targets = svc.force_join.targets
    if targets:
        lines = [
            f"• {'🟢' if svc.force_join.enabled else '⚪️'} <b>{human.esc(t.title)}</b>"
            f"\n  <code>{t.chat_id}</code>"
            for t in targets
        ]
        listing = "\n".join(lines)
    else:
        listing = text.t(lang, "admin_join_empty")
    body = text.t(
        lang,
        "admin_join_panel",
        status="🟢 ON" if svc.force_join.enabled else "🔴 OFF",
        count=len(targets),
        list=listing,
    )
    menu = kb.force_join_menu(lang, targets, svc.force_join.enabled)
    await panel(update, context, body, menu)


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
                "admin_report_kind_contact" if row.kind == "contact" else "admin_report_kind_unsupported",
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
    await panel(update, context, body, menu)


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
    await panel(update, context, body, menu)


async def _render_runtime(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    items = [(key, svc.settings.label(key, lang), svc.settings.masked(key)) for key in RUNTIME_KEYS]
    body = text.t(lang, "admin_runtime")
    body += (
        "\n\n🩺 <b>Local Bot API</b>\n"
        + text.t(lang, "local_api_help").split("\n\n", 1)[0]
    )
    menu = kb.runtime_menu(lang, items)
    await panel(update, context, body, menu)


# ── دیپلوی ─────────────────────────────────────────────────
def _version_text(svc, lang: str = "fa") -> str:
    return text.t(
        lang,
        "version_info",
        version=__version__,
        codename=CODENAME,
        date=RELEASE_DATE,
        python=platform.python_version(),
        ytdlp=human.esc(_ytdlp(svc)),
        ffmpeg=human.esc(_ffmpeg()),
        uptime=human.human_duration(svc.uptime),
    )


async def show_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ورود از کیبورد ثابت به بخش دیپلوی (بدون callback)."""
    if not await require_admin(update, context):
        return
    clear_state(context)
    await _render_deploy(update, context)


async def _render_deploy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    stats = await asyncio.to_thread(svc.updater.stats)
    staged = context.user_data.get("deploy_staged")
    if staged:
        await _render_staged(update, context)
        return
    body = text.t(
        lang,
        "deploy_panel",
        version=__version__,
        codename=CODENAME,
        ytdlp=human.esc(_ytdlp(svc)),
        python=platform.python_version(),
        size=stats["size"],
        backup=stats["backup"],
        last_update=stats["last_update"],
    )
    menu = kb.deploy_menu(lang, staged=False, has_backup=bool(svc.updater.latest_backup()))
    await panel(update, context, body, menu)


async def _render_staged(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    staged = context.user_data.get("deploy_staged")
    if not staged:
        await _render_deploy(update, context)
        return
    preview = await asyncio.to_thread(svc.updater.inspect_zip, staged)
    if not preview.ok:
        context.user_data.pop("deploy_staged", None)
        await panel(
            update,
            context,
            text.t(lang, "deploy_zip_bad", reason=human.esc(preview.reason)),
            reply_markup=kb.admin_section_menu(lang, kb.SEC_DEPLOY),
        )
        return
    notes = "\n".join(f"• {human.esc(note)}" for note in preview.notes)
    body = text.t(
        lang,
        "deploy_staged",
        current=__version__,
        new=preview.version,
        files=preview.files,
        size=human.human_bytes(preview.size),
        notes=notes,
    )
    body += "\n\n" + text.t(lang, "deploy_update_note")
    menu = kb.deploy_menu(lang, staged=True)
    await panel(update, context, body, menu)


async def _send_source_zip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    chat_id = update.effective_chat.id
    path = await asyncio.to_thread(svc.updater.export_zip, "source")
    caption = text.t(
        lang,
        "deploy_source_caption",
        version=__version__,
        files=len(svc.updater.source_files()),
        size=human.human_bytes(path.stat().st_size),
    )
    try:
        with path.open("rb") as handle:
            await context.bot.send_document(
                chat_id=chat_id,
                document=handle,
                filename=path.name,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
    except TelegramError:
        log.exception("could not send source zip")
        await reply(update, text.t(lang, "deploy_failed", reason="Telegram upload failed"))


async def _send_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    path = svc.updater.latest_backup()
    if path is None:
        await reply(update, text.t(lang, "deploy_no_backup"))
        return
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
    try:
        with path.open("rb") as handle:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=handle,
                filename=path.name,
                caption=text.t(lang, "deploy_backup_caption", when=when),
                parse_mode=ParseMode.HTML,
            )
    except TelegramError:
        log.exception("could not send backup zip")
        await reply(update, text.t(lang, "deploy_no_backup"))


async def _apply_staged(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    staged = context.user_data.pop("deploy_staged", None)
    if not staged:
        await _render_deploy(update, context)
        return
    result = await asyncio.to_thread(svc.updater.apply_zip, staged)
    try:
        staged.unlink(missing_ok=True)
    except OSError:
        pass
    if not result.ok:
        await panel(
            update,
            context,
            text.t(lang, "deploy_failed", reason=human.esc(result.reason)),
            reply_markup=kb.admin_section_menu(lang, kb.SEC_DEPLOY),
        )
        return
    await svc.admin_group.audit("system", "source_deployed", update.effective_user.id,
                                f"version={result.version}, files={result.files}, "
                                f"removed={result.removed}, deps={result.deps}")
    body = text.t(lang, "deploy_applied", version=human.esc(result.version))
    details: list[str] = []
    if result.removed:
        details.append(text.t(lang, "deploy_removed", count=result.removed))
    if result.deps:
        details.append(text.t(lang, "deploy_deps"))
    if details:
        body += "\n" + "\n".join(details)
    await panel(update, context, body)
    svc.request_restart()


# ── عیب‌یابی ───────────────────────────────────────────────
async def _render_debug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    tokens = await svc.debug.active()
    body = text.t(
        lang,
        "debug_panel",
        state="🟢 ON" if svc.settings.debug_enabled else "🔴 OFF",
        active=len(tokens),
    )
    if not tokens:
        body += "\n\n" + text.t(lang, "debug_none")
    if not svc.settings.debug_enabled:
        body += "\n\n" + text.t(lang, "debug_disabled")
    # فهرست توکن‌ها فقط به‌صورت دکمه (هر کدام با 🗑 کنارش) نمایش داده می‌شود.
    menu = kb.debug_menu(
        lang,
        tokens,
        svc.settings.debug_enabled,
        svc.debug.max_hours(),
        ttl=int(context.user_data.get("debug_ttl") or 6),
    )
    await panel(update, context, body, menu)


async def _create_debug_token(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    scope: str,
    hours_raw: str,
) -> None:
    svc = services(context)
    lang = lang_of(context)
    if not svc.settings.debug_enabled:
        await _render_debug(update, context)
        return
    if scope not in SCOPES:
        scope = "read"
    try:
        hours = int(hours_raw)
    except ValueError:
        hours = 6
    raw, row = await svc.debug.create(
        update.effective_user.id,
        hours=hours,
        scopes=svc.debug.normalize_scopes(scope),
        label=f"ui:{scope}",
    )
    base = svc.settings.get_str("public_base_url") or svc.cfg.public_base_url
    url = svc.debug.access_url(base, raw)
    body = text.t(
        lang,
        "debug_token_created",
        url=human.esc(url),
        scopes=text.t(lang, kb.debug_scope_key(row.scopes)),
        expires=time.strftime("%m-%d %H:%M", time.localtime(row.expires_at)),
    )
    if "127.0.0.1" in base or "localhost" in base:
        body += "\n\n" + text.t(lang, "debug_no_public_url", base=human.esc(base))
    await svc.admin_group.audit("security", "debug_token_created", update.effective_user.id,
                                f"scope={row.scopes}, id={row.id}, hours={hours}")
    # همان پیام پنل ویرایش می‌شود؛ پیام تازه‌ای در چت نمی‌آید.
    await panel(update, context, body, kb.debug_token_menu(lang, url, row.id))


async def _render_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    health = await svc.debug._health_payload()
    problems = health.get("problems") or []
    if problems:
        block = text.t(lang, "debug_health_problem", list="\n".join(f"• {human.esc(p)}" for p in problems))
    else:
        block = text.t(lang, "debug_health_ok")
    body = text.t(
        lang,
        "debug_health",
        version=health["version"],
        python=health["python"],
        ytdlp=human.esc(health["ytdlp"]),
        ffmpeg=human.esc(health["ffmpeg"]),
        db=health["database"],
        disk=health["disk_free"],
        web=health["web"],
        jobs=health["active_jobs"],
        users=health["users"],
        problems=block,
    )
    await panel(update, context, body, kb.debug_back_menu(lang))


async def _show_user(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = await repo.get_user(uid)
    if user is None:
        await panel(update, context, text.t(lang, "admin_add_fail"),
                    kb.admin_section_menu(lang, kb.SEC_USERS))
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
    markup = kb.Kb([
        [kb.Btn(label, callback_data=f"a|{action}|{uid}")],
        *(kb.admin_section_menu(lang, kb.SEC_USERS).inline_keyboard),
    ])
    await panel(update, context, body, markup)


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
        await panel(update, context, text.t(lang, "admin_bad_value"))
        return

    if state == ST_BROADCAST:
        clear_state(context)
        ids = await repo.all_user_ids()
        status = await panel(update, context, text.t(lang, "admin_broadcast_started", count=len(ids)))
        body = message.text_html or human.esc(raw)
        # ارسال به همه چند دقیقه طول می‌کشد؛ خارج از قفل ادمین اجرا می‌شود.
        await run_detached(context, _run_broadcast(update, context, ids, body, status), update)
        return

    if state == ST_ADD_ADMIN:
        user = await _resolve_user(raw, context=context)
        clear_state(context)
        if user is None:
            await panel(update, context, text.t(lang, "admin_add_fail"))
            return
        if await repo.count_admins() >= svc.cfg.max_admins > 0:
            await panel(update, context, text.t(lang, "admin_limit_reached", max=svc.cfg.max_admins))
            return
        await repo.add_admin(user.id, update.effective_user.id)
        await svc.admin_group.audit("security", "admin_added",
                                    update.effective_user.id, f"new_admin={user.id}")
        await panel(update, context, text.t(lang, "admin_add_ok", uid=user.id))
        return

    if state == ST_SET_VALUE:
        key = get_data(context).get("key", "")
        clear_state(context)
        if key not in SCHEMA:
            await panel(update, context, text.t(lang, "admin_bad_value"))
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
            await panel(update, context, text.t(lang, "admin_bad_value"))
            return
        if kind != "bool" and value < 0:
            await panel(update, context, text.t(lang, "admin_bad_value"))
            return
        await svc.settings.set(key, value)
        await svc.admin_group.audit("security", "setting_updated",
                                    update.effective_user.id, f"key={key} (value hidden)")
        svc.limiter.set_interval(svc.settings.rate_limit_seconds)
        await panel(
            update,
            context,
            text.t(lang, "admin_set_ok", label=svc.settings.label(key, lang), value=value),
            reply_markup=kb.settings_menu(lang, svc.settings.snapshot()),
        )
        return

    if state == ST_LOOKUP_USER:
        clear_state(context)
        user = await _resolve_user(raw, context=context)
        if user is None:
            await panel(update, context, text.t(lang, "admin_add_fail"))
            return
        await _show_user(update, context, user.id)
        return

    if state == ST_BAN:
        clear_state(context)
        user = await _resolve_user(raw, context=context, create=True)
        if user is None:
            await panel(update, context, text.t(lang, "admin_add_fail"))
            return
        await _show_user(update, context, user.id)
        return

    if state == ST_GROUP_ID:
        clear_state(context)
        token = raw.strip()
        if not token.lstrip("-").isdigit() or int(token) >= 0:
            await panel(update, context, text.t(lang, "admin_group_bad_id"))
            return
        chat_id = int(token)
        title = ""
        try:
            chat = await context.bot.get_chat(chat_id)
            if (chat.type != "supergroup" or not getattr(chat, "is_forum", False)
                    or getattr(chat, "username", None)):
                await panel(update, context, "⚠️ یک سوپرگروه خصوصی با Topics فعال وارد کن.")
                return
            title = getattr(chat, "title", "") or ""
        except TelegramError:
            await panel(update, context, text.t(lang, "admin_group_test_fail"))
            return
        created = await svc.admin_group.configure(chat_id, title)
        ok = sum(1 for value in created.values() if value)
        failed = len(created) - ok
        await panel(
            update,
            context,
            text.t(lang, "admin_group_saved", created=ok, failed=failed),
            reply_markup=kb.group_menu(lang, True),
        )
        return

    if state == ST_JOIN_CHAT:
        clear_state(context)
        await _add_join_target(update, context, raw)
        return

    if state == ST_RUNTIME_VALUE:
        key = get_data(context).get("key", "")
        clear_state(context)
        if key not in RUNTIME_KEYS or key not in SCHEMA:
            await panel(update, context, text.t(lang, "admin_bad_value"))
            return
        value = "" if raw.strip() == "-" else raw.strip()
        if key == "public_base_url" and value and not value.startswith(("http://", "https://")):
            await panel(update, context, text.t(lang, "admin_bad_value"))
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
            label=svc.settings.label(key, lang),
            value=human.esc(svc.settings.masked(key)),
        )
        if key in RESTART_KEYS:
            body += "\n\n" + text.t(lang, "admin_runtime_restart")
        items = [(item, svc.settings.label(item, lang), svc.settings.masked(item)) for item in RUNTIME_KEYS]
        await panel(update, context, body, reply_markup=kb.runtime_menu(lang, items))
        return

    if state == ST_COOKIE_ADD:
        clear_state(context)
        try:
            cookie = svc.cookies.save_text(raw)
        except CookieError as exc:
            await panel(update, context, text.t(lang, "cookie_bad", reason=human.esc(str(exc)[:150])))
            return
        await panel(
            update,
            context,
            text.t(
                lang,
                "cookie_saved",
                name=human.esc(cookie.name),
                domains=human.esc(", ".join(cookie.domains[:5]) or "—"),
            ),
        )
        return

    clear_state(context)


async def _add_join_target(update: Update, context: ContextTypes.DEFAULT_TYPE, raw: str) -> None:
    svc = services(context)
    lang = lang_of(context)
    try:
        target = await svc.force_join.resolve(context.bot, raw)
    except (ValueError, TelegramError):
        await panel(update, context, text.t(lang, "admin_join_bad"))
        return
    results = await svc.force_join.check_access(context.bot)
    for item, ok, _detail in results:
        if item.chat_id == target.chat_id and not ok:
            await panel(update, context, text.t(lang, "admin_join_admin_needed", title=human.esc(target.title)))
            return
    await svc.force_join.add(target)
    await svc.admin_group.audit("security", "force_join_target_added", update.effective_user.id,
                                f"chat={target.chat_id}")
    await panel(
        update,
        context,
        text.t(lang, "admin_join_added", title=human.esc(target.title), chat=target.chat_id),
        reply_markup=kb.force_join_menu(lang, svc.force_join.targets, svc.force_join.enabled),
    )


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

    allowed = await is_staff(svc.cfg, user.id) and not in_preview(context)
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
    """در حالت «بن کردن» یا «عضویت اجباری»، پیام فورواردشده را تبدیل می‌کند."""
    state = get_state(context)
    if state not in (ST_BAN, ST_JOIN_CHAT):
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

    if state == ST_JOIN_CHAT:
        chat_id = None
        if isinstance(origin, (MessageOriginChat, MessageOriginChannel)):
            chat_id = getattr(getattr(origin, "sender_chat", None), "id", None) or getattr(
                getattr(origin, "chat", None), "id", None
            )
        clear_state(context)
        if chat_id is None:
            await panel(update, context, text.t(lang, "admin_join_bad"))
        else:
            await _add_join_target(update, context, str(chat_id))
        raise ApplicationHandlerStop

    if not isinstance(origin, MessageOriginUser):
        await panel(
            update,
            context,
            text.t(lang, "admin_forward_hint") + "\n\n" + text.t(lang, "admin_ban_prompt"),
        )
        raise ApplicationHandlerStop

    clear_state(context)
    await _show_user(update, context, origin.sender_user.id)
    raise ApplicationHandlerStop


# ── پیام همگانی ────────────────────────────────────────────
async def _run_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, ids, body, status) -> None:
    svc = services(context)
    lang = lang_of(context)
    ok, fail = await broadcast(context, ids, body, lang)
    done = text.t(lang, "admin_broadcast_done", ok=ok, fail=fail)
    if await edit(status, done) is None:
        await reply(update, done)
    await svc.admin_group.audit("security", "broadcast_completed",
                                update.effective_user.id, f"sent={ok}, failed={fail}")


# سقف تلگرام حدود ۳۰ پیام در ثانیه است؛ کمی پایین‌تر می‌مانیم.
BROADCAST_PER_SECOND = 25
BROADCAST_WORKERS = 8


async def broadcast(
    context: ContextTypes.DEFAULT_TYPE,
    ids: list[int],
    body: str,
    lang: str,
) -> tuple[int, int]:
    """ارسال همگانی با چند worker و سقف نرخ؛ RetryAfter رعایت و یک‌بار تکرار می‌شود."""
    bot = context.bot
    queue: asyncio.Queue[int] = asyncio.Queue()
    for uid in ids:
        queue.put_nowait(uid)
    interval = BROADCAST_WORKERS / BROADCAST_PER_SECOND
    ok = fail = 0

    async def send(uid: int) -> bool:
        for _attempt in range(2):
            try:
                await bot.send_message(uid, body, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                return True
            except RetryAfter as exc:
                delay = exc.retry_after
                await asyncio.sleep(delay.total_seconds() if hasattr(delay, "total_seconds") else float(delay))
            except Exception:  # noqa: BLE001 — کاربر بلاک کرده / حذف شده
                return False
        return False

    async def worker() -> None:
        nonlocal ok, fail
        while True:
            try:
                uid = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if await send(uid):
                ok += 1
            else:
                fail += 1
            await asyncio.sleep(interval)

    await asyncio.gather(*(worker() for _ in range(min(BROADCAST_WORKERS, max(1, len(ids))))))
    log.info("broadcast finished: ok=%d fail=%d", ok, fail)
    _ = lang
    return ok, fail
