"""کیبوردهای شیشه‌ای — همهٔ callback dataها کوتاه و بدون فاصله هستند."""
from __future__ import annotations

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Kb

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

LANG_PREFIX = "l|"


def main_menu(lang: str, admin: bool) -> Kb:
    rows = [
        [Btn(text.t(lang, "btn_help"), callback_data=M_HELP),
         Btn(text.t(lang, "btn_status"), callback_data=M_STATUS)],
        [Btn(text.t(lang, "btn_sites"), callback_data=M_SITES),
         Btn(text.t(lang, "btn_settings"), callback_data=M_SETTINGS)],
        [Btn(text.t(lang, "btn_contact"), callback_data=M_CONTACT)],
    ]
    if admin:
        rows.append([Btn(text.t(lang, "btn_admin"), callback_data=M_ADMIN)])
    return Kb(rows)


def back_home(lang: str, extra: list[list] | None = None) -> Kb:
    rows = list(extra or [])
    rows.append([
        Btn(text.t(lang, "btn_back"), callback_data=M_HOME),
        Btn(text.t(lang, "btn_close"), callback_data=M_CLOSE),
    ])
    return Kb(rows)


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


def cancel_job(lang: str, job_id: str) -> Kb:
    return Kb([[Btn(text.t(lang, "cancel_btn"), callback_data=f"x|{job_id}")]])


def delivery_menu(lang: str, draft: Draft) -> Kb:
    """کیبورد انتخاب نحوهٔ تحویل + تغییر نام."""
    rows = [
        [
            Btn(text.t(lang, "deliver_video_btn"), callback_data=f"o|{draft.id}|v"),
            Btn(text.t(lang, "deliver_doc_btn"), callback_data=f"o|{draft.id}|d"),
        ],
        [Btn(text.t(lang, "deliver_link_btn"), callback_data=f"o|{draft.id}|l")],
        [Btn(text.t(lang, "deliver_rename_btn"), callback_data=f"o|{draft.id}|r")],
    ]
    if draft.kind != "direct":
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
    rows.append([Btn(text.t(lang, "btn_back"), callback_data=A_BACK)])
    return Kb(rows)


def link_actions(lang: str, url: str) -> Kb:
    return Kb([[Btn(text.t(lang, "open_link_btn"), url=url)]])


def admin_menu(lang: str) -> Kb:
    return Kb([
        [Btn(text.t(lang, "btn_admin_stats"), callback_data=A_STATS),
         Btn(text.t(lang, "btn_admin_jobs"), callback_data=A_JOBS)],
        [Btn(text.t(lang, "btn_admin_users"), callback_data=A_USER),
         Btn(text.t(lang, "btn_admin_ban"), callback_data=A_BAN)],
        [Btn(text.t(lang, "btn_admin_group"), callback_data=A_GROUP),
         Btn(text.t(lang, "btn_admin_reports"), callback_data=A_REPORTS)],
        [Btn(text.t(lang, "btn_admin_logs"), callback_data=A_LOGS),
         Btn(text.t(lang, "btn_admin_runtime"), callback_data=A_RUNTIME)],
        [Btn(text.t(lang, "btn_admin_admins"), callback_data=A_ADMINS),
         Btn(text.t(lang, "btn_admin_settings"), callback_data=A_SET)],
        [Btn(text.t(lang, "btn_admin_broadcast"), callback_data=A_BC),
         Btn(text.t(lang, "btn_admin_cookies"), callback_data=A_COOKIES)],
        [Btn(text.t(lang, "btn_admin_cleanup"), callback_data=A_CLEAN),
         Btn(text.t(lang, "btn_back"), callback_data=A_BACK)],
    ])


def group_menu(lang: str, configured: bool) -> Kb:
    rows = [
        [Btn(text.t(lang, "btn_admin_group_id"), callback_data="a|groupid")],
        [Btn(text.t(lang, "btn_admin_group_test"), callback_data="a|grouptest")],
    ]
    if configured:
        rows.append([Btn(text.t(lang, "btn_admin_group_off"), callback_data="a|groupoff")])
    rows.append([Btn(text.t(lang, "btn_back"), callback_data=A_BACK)])
    return Kb(rows)


def reports_menu(lang: str, report_ids: list[int]) -> Kb:
    rows: list[list] = [
        [Btn(text.t(lang, "btn_reports_refresh"), callback_data=A_REPORTS)]
    ]
    for rid in report_ids[:12]:
        rows.append([Btn(text.t(lang, "btn_report_close", id=rid), callback_data=f"a|rpclose|{rid}")])
    rows.append([Btn(text.t(lang, "btn_back"), callback_data=A_BACK)])
    return Kb(rows)


def logs_menu(lang: str) -> Kb:
    return Kb([
        [Btn(text.t(lang, "btn_logs_clear"), callback_data="a|logclear")],
        [Btn(text.t(lang, "btn_back"), callback_data=A_BACK)],
    ])


def runtime_menu(lang: str, items: list[tuple[str, str, str]]) -> Kb:
    rows: list[list] = []
    for key, label, value in items:
        shown = value if len(value) <= 28 else f"{value[:25]}…"
        rows.append([Btn(f"{label}: {shown}", callback_data=f"a|redit|{key}")])
    rows.append([Btn(text.t(lang, "btn_back"), callback_data=A_BACK)])
    return Kb(rows)


def admins_menu(lang: str, admins: list[int]) -> Kb:
    rows = [[Btn(text.t(lang, "btn_admin_add"), callback_data="a|admadd")]]
    for uid in admins[:20]:
        rows.append([Btn(f"🗑 {uid}", callback_data=f"a|admrm|{uid}")])
    rows.append([Btn(text.t(lang, "btn_back"), callback_data=A_BACK)])
    return Kb(rows)


def settings_menu(lang: str, snap: dict) -> Kb:
    def flag(value: bool) -> str:
        return "🟢" if value else "🔴"

    return Kb([
        [Btn(text.t(lang, "set_ttl", v=snap["link_ttl_hours"]), callback_data="a|edit|link_ttl_hours")],
        [Btn(text.t(lang, "set_upload", v=snap["max_upload_mb"]), callback_data="a|edit|max_upload_mb"),
         Btn(text.t(lang, "set_link", v=snap["max_link_mb"]), callback_data="a|edit|max_link_mb")],
        [Btn(text.t(lang, "set_rate", v=snap["rate_limit_seconds"]), callback_data="a|edit|rate_limit_seconds"),
         Btn(text.t(lang, "set_quota", v=snap["daily_quota"]), callback_data="a|edit|daily_quota")],
        [Btn(text.t(lang, "set_maintenance", flag=flag(snap["maintenance"])), callback_data="a|toggle|maintenance"),
         Btn(text.t(lang, "set_nsfw", flag=flag(snap["nsfw_enabled"])), callback_data="a|toggle|nsfw_enabled")],
        [Btn(text.t(lang, "btn_back"), callback_data=A_BACK)],
    ])
