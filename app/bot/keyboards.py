"""کیبوردهای شیشه‌ای — همهٔ callback dataها کوتاه و بدون فاصله هستند.

چیدمان تازه: منوی کاربر ۲×۲، منوی ادمین در شش دستهٔ روشن، و دکمهٔ
«بستن کیبورد» که مثل تلگرام بومی عمل می‌کند (نه دستور).
"""
from __future__ import annotations

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Kb
from telegram import ReplyKeyboardMarkup

from app.core import text
from app.services.drafts import Draft

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
M_KB_CLOSE = "m|kbclose"
M_PREVIEW = "m|preview"
M_EXIT_PREVIEW = "m|exitpreview"

A_STATS = "a|stats"
A_JOBS = "a|jobs"
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

# دسته‌بندی پنل ادمین
CAT_STATS = "stats"
CAT_USERS = "users"
CAT_SETTINGS = "settings"
CAT_GROUPS = "groups"
CAT_DEPLOY = "deploy"
CAT_DEBUG = "debug"
CATEGORIES = (CAT_STATS, CAT_USERS, CAT_SETTINGS, CAT_GROUPS, CAT_DEPLOY, CAT_DEBUG)

LANG_PREFIX = "l|"


def _btn(lang: str, key: str, data: str, **kwargs) -> Btn:
    return Btn(text.t(lang, key, **kwargs), callback_data=data)


def main_menu(lang: str, admin: bool, preview: bool = False) -> Kb:
    rows = [
        [_btn(lang, "btn_help", M_HELP), _btn(lang, "btn_status", M_STATUS)],
        [_btn(lang, "btn_sites", M_SITES), _btn(lang, "my_links_btn", "u|ls|0")],
        [_btn(lang, "btn_settings", M_SETTINGS), _btn(lang, "btn_contact", M_CONTACT)],
    ]
    if preview:
        rows.append([_btn(lang, "btn_preview_exit", M_EXIT_PREVIEW)])
    elif admin:
        rows.append([_btn(lang, "btn_admin", M_ADMIN), _btn(lang, "btn_preview", M_PREVIEW)])
    rows.append([_btn(lang, "btn_close", M_CLOSE)])
    return Kb(rows)


def back_home(lang: str, extra: list[list] | None = None) -> Kb:
    rows = list(extra or [])
    rows.append([
        _btn(lang, "btn_back", M_HOME),
        _btn(lang, "btn_close", M_CLOSE),
    ])
    return Kb(rows)


def language_menu(lang: str) -> Kb:
    rows = [[Btn(text.LANGS[code], callback_data=f"{LANG_PREFIX}{code}")] for code in text.LANG_ORDER]
    rows.append([
        _btn(lang, "btn_back", M_SETTINGS),
        _btn(lang, "btn_close", M_CLOSE),
    ])
    return Kb(rows)


def user_settings_menu(lang: str) -> Kb:
    """تنظیمات کاربر: زبان و بستن کیبورد (بدون شلوغی)."""
    return Kb([
        [_btn(lang, "btn_lang", M_LANG)],
        [_btn(lang, "btn_kb_close", M_KB_CLOSE)],
        [
            _btn(lang, "btn_back", M_HOME),
            _btn(lang, "btn_close", M_CLOSE),
        ],
    ])


def quality_menu(lang: str, draft: Draft) -> Kb:
    videos = [o for o in draft.options if o.kind == "video"]
    audios = [o for o in draft.options if o.kind == "audio"]

    rows: list[list] = []
    pair: list = []
    for opt in videos:
        pair.append(Btn(text.t(lang, "video_btn", label=opt.label), callback_data=f"q|{draft.id}|{opt.code}|v"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)

    audio_row = [
        Btn(text.t(lang, "audio_btn", label=opt.label), callback_data=f"q|{draft.id}|{opt.code}|a")
        for opt in audios
    ]
    if audio_row:
        rows.append(audio_row)

    rows.append([Btn(text.t(lang, "btn_close"), callback_data=f"d|{draft.id}")])
    return Kb(rows)


def persistent_admin_labels(lang: str) -> dict[str, str]:
    """برچسب‌های کیبورد ثابت؛ کلیدها در ``text_router`` استفاده می‌شوند."""
    return {
        "panel": text.t(lang, "btn_admin"),
        "stats": text.t(lang, "btn_admin_stats"),
        "jobs": text.t(lang, "btn_admin_jobs"),
        "deploy": text.t(lang, "btn_admin_deploy"),
        "settings": text.t(lang, "btn_admin_settings"),
        "reports": text.t(lang, "btn_reports_persistent"),
        "links": text.t(lang, "my_links_btn"),
        "cancel": text.t(lang, "btn_cancel_tasks"),
        "home": text.t(lang, "btn_home_persistent"),
    }


def admin_persistent_menu(lang: str) -> ReplyKeyboardMarkup:
    labels = persistent_admin_labels(lang)
    return ReplyKeyboardMarkup(
        [[labels["panel"], labels["stats"]],
         [labels["jobs"], labels["reports"]],
         [labels["deploy"], labels["settings"]],
         [labels["links"], labels["home"]],
         [labels["cancel"]]],
        resize_keyboard=True, is_persistent=True,
    )


def cancel_job(lang: str, job_id: str) -> Kb:
    return Kb([[Btn(text.t(lang, "cancel_btn"), callback_data=f"x|{job_id}")]])


def delivery_menu(lang: str, draft: Draft) -> Kb:
    """کیبورد انتخاب نحوهٔ تحویل + تغییر نام."""
    rows = [
        [Btn(text.t(lang, "deliver_video_btn"), callback_data=f"o|{draft.id}|v")],
        [Btn(text.t(lang, "deliver_doc_btn"), callback_data=f"o|{draft.id}|d")],
        [Btn(text.t(lang, "deliver_link_btn"), callback_data=f"o|{draft.id}|l")],
        [Btn(text.t(lang, "deliver_rename_btn"), callback_data=f"o|{draft.id}|r")],
    ]
    if draft.kind != "direct" and not draft.auto_quality:
        rows.append([Btn(text.t(lang, "deliver_back_btn"), callback_data=f"o|{draft.id}|q")])
    rows.append([Btn(text.t(lang, "btn_close"), callback_data=f"d|{draft.id}")])
    return Kb(rows)


def cookies_menu(lang: str, names: list[str]) -> Kb:
    rows: list[list] = [[
        Btn(text.t(lang, "btn_cookie_add"), callback_data="a|ckadd"),
        Btn(text.t(lang, "btn_cookie_test"), callback_data="a|cktest"),
    ]]
    for name in names[:20]:
        rows.append([Btn(f"🗑 {name}", callback_data=f"a|ckdel|{name}")])
    rows.append([
        _btn(lang, "btn_back", A_BACK),
        _btn(lang, "btn_close", M_CLOSE),
    ])
    return Kb(rows)


def link_actions(lang: str, url: str) -> Kb:
    return Kb([[Btn(text.t(lang, "open_link_btn"), url=url)],
               [Btn(text.t(lang, "my_links_btn"), callback_data="u|ls|0")]])


# ── پنل ادمین ──────────────────────────────────────────────
def admin_menu(lang: str) -> Kb:
    cat_btn = {
        CAT_STATS: "btn_cat_stats",
        CAT_USERS: "btn_cat_users",
        CAT_SETTINGS: "btn_cat_settings",
        CAT_GROUPS: "btn_cat_groups",
        CAT_DEPLOY: "btn_cat_deploy",
        CAT_DEBUG: "btn_cat_debug",
    }
    rows = [
        [_btn(lang, cat_btn[CAT_STATS], f"a|cat|{CAT_STATS}"),
         _btn(lang, cat_btn[CAT_USERS], f"a|cat|{CAT_USERS}")],
        [_btn(lang, cat_btn[CAT_SETTINGS], f"a|cat|{CAT_SETTINGS}"),
         _btn(lang, cat_btn[CAT_GROUPS], f"a|cat|{CAT_GROUPS}")],
        [_btn(lang, cat_btn[CAT_DEPLOY], f"a|cat|{CAT_DEPLOY}"),
         _btn(lang, cat_btn[CAT_DEBUG], f"a|cat|{CAT_DEBUG}")],
        [_btn(lang, "btn_home_persistent", M_HOME), _btn(lang, "btn_close", M_CLOSE)],
    ]
    return Kb(rows)


def admin_cat_menu(lang: str, category: str) -> Kb:
    """زیرمنوی هر دسته — عمداً کوتاه و قابل‌فهم."""
    if category == CAT_STATS:
        rows = [
            [_btn(lang, "btn_admin_stats", A_STATS), _btn(lang, "btn_admin_jobs", A_JOBS)],
            [_btn(lang, "btn_admin_reports", A_REPORTS), _btn(lang, "btn_admin_logs", A_LOGS)],
            [_btn(lang, "btn_admin_cleanup", A_CLEAN)],
        ]
    elif category == CAT_USERS:
        rows = [
            [_btn(lang, "btn_admin_users", A_USER), _btn(lang, "btn_admin_ban", A_BAN)],
            [_btn(lang, "btn_admin_admins", A_ADMINS), _btn(lang, "btn_admin_broadcast", A_BC)],
        ]
    elif category == CAT_SETTINGS:
        rows = [
            [_btn(lang, "btn_admin_settings", A_SET), _btn(lang, "btn_admin_runtime", A_RUNTIME)],
            [_btn(lang, "btn_admin_cookies", A_COOKIES)],
        ]
    elif category == CAT_GROUPS:
        rows = [
            [_btn(lang, "btn_admin_group", A_GROUP), _btn(lang, "btn_admin_join", "a|join")],
        ]
    elif category == CAT_DEPLOY:
        rows = [
            [_btn(lang, "btn_admin_deploy", "a|deploy")],
        ]
    elif category == CAT_DEBUG:
        rows = [
            [_btn(lang, "btn_admin_debug", "a|debug"), _btn(lang, "btn_admin_preview", "a|preview")],
        ]
    else:
        rows = []

    rows.append([
        _btn(lang, "btn_back_cats", A_BACK),
        _btn(lang, "btn_close", M_CLOSE),
    ])
    return Kb(rows)


def group_menu(lang: str, configured: bool) -> Kb:
    rows = [
        [Btn(text.t(lang, "btn_admin_group_id"), callback_data="a|groupid")],
        [Btn(text.t(lang, "btn_admin_group_test"), callback_data="a|grouptest")],
    ]
    if configured:
        rows.append([Btn(text.t(lang, "btn_admin_group_off"), callback_data="a|groupoff")])
    rows.append([
        _btn(lang, "btn_back", A_BACK),
        _btn(lang, "btn_close", M_CLOSE),
    ])
    return Kb(rows)


def reports_menu(lang: str, report_ids: list[int]) -> Kb:
    rows: list[list] = [
        [Btn(text.t(lang, "btn_reports_refresh"), callback_data=A_REPORTS)]
    ]
    for rid in report_ids[:12]:
        rows.append([Btn(text.t(lang, "btn_report_close", id=rid), callback_data=f"a|rpclose|{rid}")])
    rows.append([
        _btn(lang, "btn_back", A_BACK),
        _btn(lang, "btn_close", M_CLOSE),
    ])
    return Kb(rows)


def logs_menu(lang: str) -> Kb:
    return Kb([
        [Btn(text.t(lang, "btn_logs_clear"), callback_data="a|logclear")],
        [_btn(lang, "btn_back", A_BACK), _btn(lang, "btn_close", M_CLOSE)],
    ])


def runtime_menu(lang: str, items: list[tuple[str, str, str]]) -> Kb:
    rows: list[list] = []
    for key, label, value in items:
        shown = value if len(value) <= 24 else f"{value[:21]}…"
        rows.append([Btn(f"{label}: {shown}", callback_data=f"a|redit|{key}")])
    rows.append([
        _btn(lang, "btn_back", A_BACK),
        _btn(lang, "btn_close", M_CLOSE),
    ])
    return Kb(rows)


def admins_menu(lang: str, admins: list[int]) -> Kb:
    rows = [[Btn(text.t(lang, "btn_admin_add"), callback_data="a|admadd")]]
    for uid in admins[:20]:
        rows.append([Btn(f"🗑 {uid}", callback_data=f"a|admrm|{uid}")])
    rows.append([
        _btn(lang, "btn_back", A_BACK),
        _btn(lang, "btn_close", M_CLOSE),
    ])
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
        [_btn(lang, "btn_back", A_BACK), _btn(lang, "btn_close", M_CLOSE)],
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
    rows.append([
        _btn(lang, "btn_back", A_BACK),
        _btn(lang, "btn_close", M_CLOSE),
    ])
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
    rows.append([
        _btn(lang, "btn_back", A_BACK),
        _btn(lang, "btn_close", M_CLOSE),
    ])
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
def debug_menu(lang: str, tokens: list, enabled: bool, max_hours: int) -> Kb:
    rows: list[list] = [
        [_btn(lang, "btn_debug_health", "a|dbhealth")],
    ]
    if enabled:
        rows += [
            [_btn(lang, "btn_debug_make_read", "a|dbmake|read|6"),
             _btn(lang, "btn_debug_make_write", "a|dbmake|write|6")],
            [_btn(lang, "btn_debug_make_restart", "a|dbmake|restart|6")],
            [_btn(lang, "btn_debug_make_read", "a|dbmake|read|24"),
             _btn(lang, "btn_debug_make_write", "a|dbmake|write|24")],
        ]
        for row in tokens[:10]:
            rows.append([Btn(
                text.t(lang, "debug_token_button", id=row.id, scopes=row.scopes),
                callback_data=f"a|dbrevoke|{row.id}",
            )])
        if tokens:
            rows.append([_btn(lang, "btn_debug_revoke_all", "a|dbrevokeall")])
    rows.append([
        _btn(lang, "btn_back", A_BACK),
        _btn(lang, "btn_close", M_CLOSE),
    ])
    return Kb(rows)


def preview_menu(lang: str, active: bool) -> Kb:
    if active:
        return Kb([[_btn(lang, "btn_preview_exit", M_EXIT_PREVIEW)]])
    return Kb([
        [_btn(lang, "btn_preview", "a|previewon")],
        [_btn(lang, "btn_back", A_BACK), _btn(lang, "btn_close", M_CLOSE)],
    ])
