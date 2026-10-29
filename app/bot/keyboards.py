"""کیبوردهای تلگرام — همهٔ callback dataها کوتاه و بدون فاصله هستند.

منوی کاربر روی کارهای اصلی تمرکز دارد؛ جمع‌کردن کیبورد با کنترل بومی تلگرام
انجام می‌شود. تنظیمات پیش‌فرض و انتخاب هر لینک در دکمه‌های inline مدیریت می‌شوند.
"""
from __future__ import annotations

import time

from telegram import CopyTextButton, ReplyKeyboardMarkup
from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Kb

from app.core import text
from app.core.human import parse_bool
from app.services.drafts import Draft
from app.services.runtime_settings import SCHEMA as RUNTIME_SCHEMA

# ── پیشوندها ────────────────────────────────────────────────
M_HELP = "m|help"
M_STATUS = "m|status"
M_SITES = "m|sites"
M_SETTINGS = "m|settings"
M_ADMIN = "m|admin"
M_CONTACT = "m|contact"
M_CLOSE = "m|close"
M_HOME = "m|home"
M_LANG = "m|lang"
M_KB_CLOSE = "m|kbclose"  # callback قدیمی؛ در منوهای جدید نمایش داده نمی‌شود
M_PREF_MODE = "m|prefmode"
M_PREF_DEST = "m|prefdest"
M_PREVIEW = "m|preview"
M_EXIT_PREVIEW = "m|exitpreview"

A_STATS = "a|stats"
A_JOBS = "a|jobs"
A_TRAFFIC = "a|traffic"
A_ADMINS = "a|admins"
A_SET = "a|set"
A_BC = "a|bc"
A_USER = "a|user"
A_BAN = "a|banmenu"
A_CLEAN = "a|clean"
A_COOKIES = "a|cookies"
A_GROUP = "a|group"
A_REPORTS = "a|reports"
A_LOGS = "a|logs"
A_RUNTIME = "a|runtime"
A_BACK = "a|back"

# بخش‌های پنل ادمین — هر بخش فقط یک‌جا (کیبورد ثابت) باز می‌شود.
SEC_STATS = "stats"
SEC_USERS = "users"
SEC_SETTINGS = "settings"
SEC_GROUPS = "groups"
SEC_DEPLOY = "deploy"
SEC_DEBUG = "debug"
SEC_COOKIES = "cookies"
SEC_CANCEL = "cancel"
SECTIONS = (
    SEC_STATS,
    SEC_USERS,
    SEC_SETTINGS,
    SEC_GROUPS,
    SEC_DEPLOY,
    SEC_DEBUG,
    SEC_COOKIES,
    SEC_CANCEL,
)

LANG_PREFIX = "l|"


def _btn(lang: str, key: str, data: str, **kwargs) -> Btn:
    return Btn(text.t(lang, key, **kwargs), callback_data=data)


def _delivery_btn(label: str, data: str, *, style: str | None = None) -> Btn:
    """Apply native color only when a section header or final action requests it."""
    if style is None:
        return Btn(label, callback_data=data)
    return Btn(label, callback_data=data, style=style)


def main_menu(lang: str, admin: bool, preview: bool = False) -> Kb:
    """Inline equivalent of the concise persistent user menu."""
    rows = [
        [_btn(lang, "btn_sites", M_SITES), _btn(lang, "my_links_btn", "u|ls|0")],
        [_btn(lang, "btn_status", M_STATUS), _btn(lang, "btn_settings", M_SETTINGS)],
        [_btn(lang, "btn_lang", M_LANG)],
    ]
    if preview:
        rows.append([_btn(lang, "btn_preview_exit", M_EXIT_PREVIEW)])
    elif admin:
        rows.append([_btn(lang, "btn_admin", M_ADMIN), _btn(lang, "btn_preview", M_PREVIEW)])
    rows.extend([
        [_btn(lang, "btn_help", M_HELP)],
        [_btn(lang, "btn_contact", M_CONTACT)],
    ])
    return Kb(rows)


def user_persistent_labels(lang: str, *, preview: bool = False) -> dict[str, str]:
    """Text labels and actions for the persistent user reply keyboard."""
    labels = {
        "links": text.t(lang, "my_links_btn"),
        "status": text.t(lang, "btn_status"),
        "settings": text.t(lang, "btn_settings"),
        "lang": text.t(lang, "btn_lang"),
        "help": text.t(lang, "btn_help"),
        "contact": text.t(lang, "btn_contact"),
    }
    if preview:
        labels["exitpreview"] = text.t(lang, "btn_preview_exit")
    return labels


def user_persistent_menu(lang: str, *, preview: bool = False) -> ReplyKeyboardMarkup:
    """Grouped persistent menu; Telegram's native control collapses the keyboard."""
    labels = user_persistent_labels(lang, preview=preview)
    rows = [
        [labels["links"], labels["status"]],
        [labels["settings"], labels["lang"]],
    ]
    if preview:
        rows.append([labels["exitpreview"]])
    rows.extend([
        [labels["help"]],
        [labels["contact"]],
    ])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def back_home(lang: str, extra: list[list] | None = None) -> Kb:
    rows = list(extra or [])
    rows.append([
        _btn(lang, "btn_back", M_HOME),
        _btn(lang, "btn_close", M_CLOSE),
    ])
    return Kb(rows)


def language_menu(lang: str, *, onboarding: bool = False) -> Kb:
    rows = [[Btn(text.LANGS[code], callback_data=f"{LANG_PREFIX}{code}")] for code in text.LANG_ORDER]
    if not onboarding:
        rows.append([
            _btn(lang, "btn_back", M_SETTINGS),
            _btn(lang, "btn_close", M_CLOSE),
        ])
    return Kb(rows)


def user_settings_menu(
    lang: str,
    default_mode: str = "video",
    default_destination: str = "telegram",
) -> Kb:
    """User settings: persistent default format and delivery destination."""
    mode_key = "delivery_mode_video" if default_mode == "video" else "delivery_mode_file"
    destination_key = (
        "delivery_destination_telegram" if default_destination == "telegram"
        else "delivery_destination_link"
    )
    mode = text.t(lang, mode_key)
    destination = text.t(lang, destination_key)
    return Kb([
        [Btn(text.t(lang, "settings_default_mode_btn", value=mode), callback_data=M_PREF_MODE)],
        [Btn(text.t(lang, "settings_default_destination_btn", value=destination), callback_data=M_PREF_DEST)],
        [_btn(lang, "btn_lang", M_LANG)],
        [_btn(lang, "btn_back", M_HOME)],
    ])


def quality_menu(lang: str, draft: Draft) -> Kb:
    videos = [o for o in draft.options if o.kind == "video"]
    audios = [o for o in draft.options if o.kind == "audio"]

    rows: list[list] = []
    pair: list = []
    for opt in videos:
        pair.append(_delivery_btn(
            text.t(lang, "video_btn", label=opt.label),
            f"q|{draft.id}|{opt.code}|v",
        ))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)

    audio_row = [
        _delivery_btn(text.t(lang, "audio_btn", label=opt.label), f"q|{draft.id}|{opt.code}|a")
        for opt in audios
    ]
    if audio_row:
        rows.append(audio_row)

    rows.append([_delivery_btn(text.t(lang, "btn_close"), f"d|{draft.id}")])
    return Kb(rows)


def persistent_admin_labels(lang: str) -> dict[str, str]:
    """برچسب‌های کیبورد ثابت ادمین — فقط بخش‌های مدیریتی، بدون دکمهٔ کاربر عادی."""
    return {
        "stats": text.t(lang, "sec_stats"),
        "users": text.t(lang, "sec_users"),
        "settings": text.t(lang, "sec_settings"),
        "groups": text.t(lang, "sec_groups"),
        "deploy": text.t(lang, "sec_deploy"),
        "debug": text.t(lang, "sec_debug"),
        "cookies": text.t(lang, "sec_cookies"),
    }


def admin_persistent_menu(lang: str) -> ReplyKeyboardMarkup:
    """Persistent admin sections plus a localized language switch."""
    labels = persistent_admin_labels(lang)
    return ReplyKeyboardMarkup(
        [
            [labels["stats"], labels["users"], labels["settings"]],
            [labels["groups"], labels["deploy"], labels["debug"]],
            [labels["cookies"]],
            [text.t(lang, "btn_lang")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def cancel_job(lang: str, job_id: str) -> Kb:
    return Kb([[Btn(text.t(lang, "cancel_btn"), callback_data=f"x|{job_id}")]])


def delivery_start_key(draft: Draft) -> str:
    """Localized label for the final action, based on this link's current choices."""
    if draft.destination == "link":
        return "deliver_start_link_btn"
    return "deliver_start_video_btn" if draft.send_as == "video" else "deliver_start_file_btn"


def delivery_menu(lang: str, draft: Draft) -> Kb:
    """Sectioned per-link choices, optional edits, and a distinct final action."""
    check = "✅ "
    empty = "▫️ "
    rows = [
        [_delivery_btn(text.t(lang, "delivery_tab_format"), f"o|{draft.id}|tab|format", style="primary")],
        [
            _delivery_btn((check if draft.send_as == "video" else empty) + text.t(lang, "deliver_video_btn"),
                          f"o|{draft.id}|format|video"),
            _delivery_btn((check if draft.send_as == "document" else empty) + text.t(lang, "deliver_doc_btn"),
                          f"o|{draft.id}|format|document"),
        ],
        [_delivery_btn(text.t(lang, "delivery_tab_destination"), f"o|{draft.id}|tab|destination", style="primary")],
        [
            _delivery_btn((check if draft.destination == "telegram" else empty) + text.t(lang, "deliver_telegram_btn"),
                          f"o|{draft.id}|destination|telegram"),
            _delivery_btn((check if draft.destination == "link" else empty) + text.t(lang, "deliver_link_btn"),
                          f"o|{draft.id}|destination|link"),
        ],
        [_delivery_btn(text.t(lang, "delivery_tab_edits"), f"o|{draft.id}|tab|edits", style="primary")],
    ]
    if draft.kind != "direct" and not draft.auto_quality:
        rows.append([_delivery_btn(text.t(lang, "deliver_back_btn"), f"o|{draft.id}|q")])
    rows.append([
        _delivery_btn(text.t(lang, "deliver_thumbnail_btn"), f"o|{draft.id}|thumbnail"),
        _delivery_btn(text.t(lang, "deliver_rename_btn"), f"o|{draft.id}|r"),
    ])
    rows.append([
        _delivery_btn(text.t(lang, delivery_start_key(draft)), f"o|{draft.id}|start", style="success")
    ])
    return Kb(rows)


def cookies_menu(lang: str, names: list[str]) -> Kb:
    rows: list[list] = [[
        Btn(text.t(lang, "btn_cookie_add"), callback_data="a|ckadd"),
        Btn(text.t(lang, "btn_cookie_test"), callback_data="a|cktest"),
    ]]
    for name in names[:20]:
        rows.append([Btn(f"🗑 {name}", callback_data=f"a|ckdel|{name}")])
    return Kb(rows)


def link_actions(lang: str, url: str) -> Kb:
    return Kb([[Btn(text.t(lang, "open_link_btn"), url=url)],
               [Btn(text.t(lang, "my_links_btn"), callback_data="u|ls|0")]])


def _debug_toggle_btn(lang: str, enabled: bool) -> Btn:
    return Btn(
        text.t(lang, "btn_debug_toggle", flag="🟢" if enabled else "🔴"),
        callback_data="a|dbtoggle",
    )


# ── پنل ادمین ──────────────────────────────────────────────
def admin_section_menu(lang: str, section: str, *, debug_enabled: bool = False) -> Kb:
    """اکشن‌های یک بخش؛ ناوبری فقط با کیبورد ثابت انجام می‌شود (بدون دکمهٔ بازگشت)."""
    if section == SEC_STATS:
        rows = [
            [_btn(lang, "btn_admin_stats", A_STATS), _btn(lang, "btn_admin_jobs", A_JOBS)],
            [_btn(lang, "btn_admin_traffic", A_TRAFFIC)],
            [_btn(lang, "btn_admin_reports", A_REPORTS), _btn(lang, "btn_admin_logs", A_LOGS)],
            [_btn(lang, "btn_admin_cleanup", A_CLEAN)],
        ]
    elif section == SEC_USERS:
        rows = [
            [_btn(lang, "btn_admin_users", A_USER), _btn(lang, "btn_admin_ban", A_BAN)],
            [_btn(lang, "btn_admin_admins", A_ADMINS), _btn(lang, "btn_admin_broadcast", A_BC)],
        ]
    elif section == SEC_SETTINGS:
        rows = [
            [_btn(lang, "btn_admin_settings", A_SET), _btn(lang, "btn_admin_runtime", A_RUNTIME)],
        ]
    elif section == SEC_GROUPS:
        rows = [
            [_btn(lang, "btn_admin_group", A_GROUP), _btn(lang, "btn_admin_join", "a|join")],
        ]
    elif section == SEC_DEPLOY:
        return deploy_menu(lang)
    elif section == SEC_DEBUG:
        rows = [
            [_debug_toggle_btn(lang, debug_enabled), _btn(lang, "btn_admin_debug", "a|debug")],
        ]
    elif section == SEC_COOKIES:
        rows = [
            [Btn(text.t(lang, "btn_cookie_add"), callback_data="a|ckadd"),
             Btn(text.t(lang, "btn_cookie_test"), callback_data="a|cktest")],
        ]
    else:
        rows = []
    return Kb(rows)


def group_menu(lang: str, configured: bool) -> Kb:
    rows = [
        [Btn(text.t(lang, "btn_admin_group_id"), callback_data="a|groupid")],
        [Btn(text.t(lang, "btn_admin_group_test"), callback_data="a|grouptest")],
    ]
    if configured:
        rows.append([Btn(text.t(lang, "btn_admin_group_off"), callback_data="a|groupoff")])
    return Kb(rows)


def reports_menu(lang: str, report_ids: list[int]) -> Kb:
    rows: list[list] = [
        [Btn(text.t(lang, "btn_reports_refresh"), callback_data=A_REPORTS)]
    ]
    for rid in report_ids[:12]:
        rows.append([Btn(text.t(lang, "btn_report_close", id=rid), callback_data=f"a|rpclose|{rid}")])
    return Kb(rows)


def logs_menu(lang: str) -> Kb:
    return Kb([
        [Btn(text.t(lang, "btn_logs_clear"), callback_data="a|logclear")],
    ])


def runtime_menu(lang: str, items: list[tuple[str, str, str]]) -> Kb:
    rows: list[list] = []
    for key, label, value in items:
        if RUNTIME_SCHEMA.get(key, ("", ""))[0] == "bool":
            # کلیدهای روشن/خاموش با یک ضربه عوض می‌شوند (مثل debug_enabled).
            flag = "🟢" if parse_bool(value, False) else "🔴"
            rows.append([Btn(f"{label}: {flag}", callback_data=f"a|rtoggle|{key}")])
            continue
        shown = value if len(value) <= 24 else f"{value[:21]}…"
        rows.append([Btn(f"{label}: {shown}", callback_data=f"a|redit|{key}")])
    return Kb(rows)


def admins_menu(lang: str, admins: list[int]) -> Kb:
    rows = [[Btn(text.t(lang, "btn_admin_add"), callback_data="a|admadd")]]
    for uid in admins[:20]:
        rows.append([Btn(f"🗑 {uid}", callback_data=f"a|admrm|{uid}")])
    return Kb(rows)


def settings_menu(lang: str, snap: dict) -> Kb:
    def flag(value: bool) -> str:
        return "🟢" if value else "🔴"

    return Kb([
        [Btn(text.t(lang, "set_ttl", v=f"{snap['link_ttl_hours']:g}"), callback_data="a|edit|link_ttl_hours")],
        [Btn(text.t(lang, "set_upload", v=snap["max_upload_mb"]), callback_data="a|edit|max_upload_mb"),
         Btn(text.t(lang, "set_link", v=snap["max_link_mb"]), callback_data="a|edit|max_link_mb")],
        [Btn(text.t(lang, "set_rate", v=f"{snap['rate_limit_seconds']:g}"), callback_data="a|edit|rate_limit_seconds"),
         Btn(text.t(lang, "set_quota", v=snap["daily_quota"]), callback_data="a|edit|daily_quota")],
        [Btn(text.t(lang, "set_maintenance", flag=flag(snap["maintenance"])), callback_data="a|toggle|maintenance"),
         Btn(text.t(lang, "set_nsfw", flag=flag(snap["nsfw_enabled"])), callback_data="a|toggle|nsfw_enabled")],
        [_btn(lang, "btn_admin_runtime", A_RUNTIME)],
    ])


# ── دیپلوی ─────────────────────────────────────────────────
def deploy_menu(lang: str, staged: bool = False, has_backup: bool = False) -> Kb:
    if staged:
        return Kb([
            [_btn(lang, "btn_deploy_apply", "a|dpapply")],
            [_btn(lang, "btn_deploy_cancel", "a|dpcancel")],
        ])
    rows: list[list] = [
        [_btn(lang, "btn_deploy_source", "a|dpsrc"),
         _btn(lang, "btn_deploy_upload", "a|dpup")],
        [_btn(lang, "btn_deploy_ytdlp", "a|dpytdlp"),
         _btn(lang, "btn_deploy_ytdlp_nightly", "a|dpytdlpnight")],
        [_btn(lang, "btn_deploy_version", "a|dpver")],
    ]
    if has_backup:
        rows.append([_btn(lang, "btn_deploy_backup", "a|dpbackup")])
    rows.append([_btn(lang, "btn_deploy_restart", "a|dprestart")])
    return Kb(rows)


def deploy_restart_confirm(lang: str) -> Kb:
    return Kb([
        [_btn(lang, "btn_deploy_restart", "a|dprestartyes")],
        [_btn(lang, "btn_deploy_cancel", "a|dpcancel")],
    ])


# ── عضویت اجباری ───────────────────────────────────────────
def force_join_menu(lang: str, targets: list, enabled: bool) -> Kb:
    flag = "🟢" if enabled else "🔴"
    rows: list[list] = [
        [Btn(text.t(lang, "btn_admin_join_toggle", flag=flag), callback_data="a|jointoggle")],
        [Btn(text.t(lang, "btn_admin_join_add"), callback_data="a|joinadd")],
    ]
    for target in targets[:20]:
        title = getattr(target, "title", str(target))[:28]
        rows.append([Btn(f"🗑 {title}", callback_data=f"a|joinrm|{target.chat_id}")])
    rows.append([Btn(text.t(lang, "btn_admin_join_check"), callback_data="a|joincheck")])
    return Kb(rows)


def join_gate(lang: str, targets: list) -> Kb:
    rows: list[list] = []
    for target in targets:
        url = target.url() if hasattr(target, "url") else ""
        if url:
            rows.append([Btn(f"📣 {target.title[:32]}", url=url)])
    rows.append([Btn(text.t(lang, "join_gate_btn"), callback_data="m|joincheck")])
    return Kb(rows)


# ── عیب‌یابی ───────────────────────────────────────────────
DEBUG_TTLS = (1, 6, 24)


def debug_scope_key(scopes: str) -> str:
    """کلید متن سطح دسترسی: بالاترین سطح موجود در رشتهٔ scope."""
    parts = {p.strip() for p in (scopes or "").split(",")}
    if "restart" in parts:
        return "debug_scope_restart"
    if "write" in parts:
        return "debug_scope_write"
    return "debug_scope_read"


def next_debug_ttl(current: int, max_hours: int) -> int:
    allowed = [hours for hours in DEBUG_TTLS if hours <= max_hours] or [max_hours]
    later = [hours for hours in allowed if hours > current]
    return later[0] if later else allowed[0]


def debug_menu(lang: str, tokens: list, enabled: bool, max_hours: int, ttl: int = 6) -> Kb:
    """یک دکمه برای هر کار؛ مدت اعتبار با یک دکمهٔ چرخشی انتخاب می‌شود."""
    ttl = max(1, min(int(ttl or 6), max_hours))
    rows: list[list] = [
        [_debug_toggle_btn(lang, enabled), _btn(lang, "btn_debug_health", "a|dbhealth")],
    ]
    if enabled:
        rows += [
            [_btn(lang, "btn_debug_ttl", "a|dbttl", hours=ttl)],
            [_btn(lang, "btn_debug_make_read", f"a|dbmake|read|{ttl}"),
             _btn(lang, "btn_debug_make_write", f"a|dbmake|write|{ttl}")],
            [_btn(lang, "btn_debug_make_restart", f"a|dbmake|restart|{ttl}")],
        ]
    # توکن‌ها حتی وقتی دسترسی خاموش است دیده و حذف می‌شوند.
    for row in tokens[:10]:
        expires = time.strftime("%H:%M", time.localtime(row.expires_at))
        rows.append([
            Btn(
                text.t(
                    lang,
                    "debug_token_button",
                    id=row.id,
                    scopes=text.t(lang, debug_scope_key(row.scopes)),
                    expires=expires,
                ),
                callback_data=f"a|dbinfo|{row.id}",
            ),
            Btn("🗑", callback_data=f"a|dbrevoke|{row.id}"),
        ])
    if len(tokens) > 1:
        rows.append([_btn(lang, "btn_debug_revoke_all", "a|dbrevokeall")])
    rows.append([_btn(lang, "btn_admin_preview", "a|preview")])
    return Kb(rows)


def debug_token_menu(lang: str, url: str, token_id: int) -> Kb:
    """زیر پیام توکن تازه: کپی کل آدرس با یک ضربه، حذف همین توکن، بازگشت به پنل."""
    rows: list[list] = []
    if len(url) <= 256:  # سقف CopyTextButton
        rows.append([Btn(text.t(lang, "btn_debug_copy"), copy_text=CopyTextButton(url))])
    rows.append([
        _btn(lang, "btn_debug_revoke_this", f"a|dbrevoke|{token_id}"),
        _btn(lang, "btn_admin_debug", "a|debug"),
    ])
    return Kb(rows)


def debug_back_menu(lang: str) -> Kb:
    return Kb([[_btn(lang, "btn_admin_debug", "a|debug")]])


def preview_menu(lang: str, active: bool) -> Kb:
    if active:
        return Kb([[_btn(lang, "btn_preview_exit", M_EXIT_PREVIEW)]])
    return Kb([
        [_btn(lang, "btn_preview", "a|previewon")],
    ])
