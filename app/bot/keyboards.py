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
M_CLOSE = "m|close"
M_HOME = "m|home"

A_STATS = "a|stats"
A_JOBS = "a|jobs"
A_ADMINS = "a|admins"
A_SET = "a|set"
A_BC = "a|bc"
A_USER = "a|user"
A_CLEAN = "a|clean"
A_BACK = "a|back"

LANG_PREFIX = "l|"


def main_menu(lang: str, admin: bool) -> Kb:
    rows = [
        [Btn(text.t(lang, "btn_help"), callback_data=M_HELP),
         Btn(text.t(lang, "btn_status"), callback_data=M_STATUS)],
        [Btn(text.t(lang, "btn_sites"), callback_data=M_SITES),
         Btn(text.t(lang, "btn_settings"), callback_data=M_SETTINGS)],
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


def link_actions(lang: str, url: str) -> Kb:
    return Kb([[Btn(text.t(lang, "open_link_btn"), url=url)]])


def admin_menu(lang: str) -> Kb:
    return Kb([
        [Btn(text.t(lang, "btn_admin_stats"), callback_data=A_STATS),
         Btn(text.t(lang, "btn_admin_jobs"), callback_data=A_JOBS)],
        [Btn(text.t(lang, "btn_admin_admins"), callback_data=A_ADMINS),
         Btn(text.t(lang, "btn_admin_settings"), callback_data=A_SET)],
        [Btn(text.t(lang, "btn_admin_users"), callback_data=A_USER),
         Btn(text.t(lang, "btn_admin_broadcast"), callback_data=A_BC)],
        [Btn(text.t(lang, "btn_admin_cleanup"), callback_data=A_CLEAN)],
        [Btn(text.t(lang, "btn_back"), callback_data=A_BACK)],
    ])


def admins_menu(lang: str, admins: list[int]) -> Kb:
    rows = [[Btn("➕ افزودن ادمین", callback_data="a|admadd")]]
    for uid in admins[:20]:
        rows.append([Btn(f"🗑 {uid}", callback_data=f"a|admrm|{uid}")])
    rows.append([Btn(text.t(lang, "btn_back"), callback_data=A_BACK)])
    return Kb(rows)


def settings_menu(lang: str, snap: dict) -> Kb:
    def flag(value: bool) -> str:
        return "🟢" if value else "🔴"

    return Kb([
        [Btn(f"⏳ TTL: {snap['link_ttl_hours']}h", callback_data="a|edit|link_ttl_hours")],
        [Btn(f"📦 Max upload: {snap['max_upload_mb']}MB", callback_data="a|edit|max_upload_mb"),
         Btn(f"🔗 Max link: {snap['max_link_mb']}MB", callback_data="a|edit|max_link_mb")],
        [Btn(f"🐢 Rate: {snap['rate_limit_seconds']}s", callback_data="a|edit|rate_limit_seconds"),
         Btn(f"📉 Quota: {snap['daily_quota']}", callback_data="a|edit|daily_quota")],
        [Btn(f"🛠 Maintenance {flag(snap['maintenance'])}", callback_data="a|toggle|maintenance"),
         Btn(f"🔞 NSFW {flag(snap['nsfw_enabled'])}", callback_data="a|toggle|nsfw_enabled")],
        [Btn(text.t(lang, "btn_back"), callback_data=A_BACK)],
    ])
