"""User's active, signed links and self-service revocation."""
from __future__ import annotations

import time
from pathlib import Path

from telegram import Update, CopyTextButton
from telegram.ext import ContextTypes

from app.bot import keyboards as kb
from app.bot.common import edit, lang_of, reply, safe_answer, services
from app.core import human
from app.db import repo
from app.services.linktoken import make_token

PAGE_SIZE = 5


def _caption(lang: str, count: int, page: int, lines: list[str]) -> str:
    if lang == "en":
        title = f"<b>🔗 My active links ({count})</b>"
        footer = "Tap a link to open it, or delete it from the server."
    else:
        title = f"<b>🔗 لینک‌های فعال من ({count})</b>"
        footer = "می‌توانی لینک را باز کنی یا فایل را برای همیشه از سرور حذف کنی."
    return title + f"\n📄 {page + 1}\n\n" + ("\n\n".join(lines) if lines else ("No active links." if lang == "en" else "لینک فعالی نداری.")) + "\n\n" + footer


def _signed_url(svc, row) -> str:
    ttl = max(1, row.expires_at - int(time.time()))
    token = make_token(row.id, svc.cfg.link_secret, ttl, user_id=row.user_id)
    return f"{svc.cfg.public_base_url.rstrip('/')}/f/{token}"


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    svc = services(context)
    lang = lang_of(context)
    if getattr(update.effective_chat, "type", "private") != "private":
        warning = ("Open a private chat with the bot to manage your links."
                   if lang == "en" else "برای مشاهده و مدیریت لینک‌ها وارد گفت‌وگوی خصوصی با ربات شو.")
        if update.callback_query:
            await safe_answer(update.callback_query, warning, alert=True)
        else:
            await reply(update, warning)
        return
    user_id = update.effective_user.id
    count = await repo.count_user_shared(user_id)
    max_page = max(0, (count - 1) // PAGE_SIZE)
    page = max(0, min(int(page), max_page))
    rows = await repo.user_shared(user_id, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    lines = []
    menu_rows = []
    for index, row in enumerate(rows, 1):
        num = page * PAGE_SIZE + index
        remain = max(0, row.expires_at - int(time.time()))
        hours, minutes = divmod(remain // 60, 60)
        lines.append(
            f"<b>{num}. {human.esc(human.truncate(row.name, 65))}</b>\n"
            f"📦 {human.human_bytes(row.size)} · ⏳ {hours}h {minutes}m · ⬇️ {row.downloads}\n"
            f"<code>{human.esc(_signed_url(svc, row))}</code>"
        )
        menu_rows.append([
            kb.Btn(f"🔗 {num}", url=_signed_url(svc, row)),
            kb.Btn(f"📋 {num}", copy_text=CopyTextButton(_signed_url(svc, row))),
            kb.Btn(f"🗑 {num}", callback_data=f"u|ask|{row.id}|{page}"),
        ])
    if page > 0:
        menu_rows.append([kb.Btn("◀️" if lang == "en" else "➡️ قبلی", callback_data=f"u|ls|{page-1}")])
    if page < max_page:
        menu_rows.append([kb.Btn("Next ➡️" if lang == "en" else "بعدی ⬅️", callback_data=f"u|ls|{page+1}")])
    menu_rows.append([kb.Btn("🔄" if lang == "en" else "🔄 به‌روزرسانی", callback_data=f"u|ls|{page}")])
    body = _caption(lang, count, page, lines)
    if update.callback_query:
        await safe_answer(update.callback_query)
        await edit(update.callback_query.message, body, reply_markup=kb.Kb(menu_rows))
    else:
        await reply(update, body, reply_markup=kb.Kb(menu_rows))


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    query = update.callback_query
    if query is None:
        return
    lang = lang_of(context)
    if getattr(update.effective_chat, "type", "private") != "private":
        await safe_answer(query, "لینک‌ها فقط در چت خصوصی مدیریت می‌شوند.", alert=True)
        return
    if args and args[0] == "ls":
        try:
            page = int(args[1])
        except (IndexError, ValueError):
            page = 0
        await show(update, context, page)
        return
    if len(args) < 3 or args[0] not in ("ask", "del"):
        await safe_answer(query)
        return
    operation, file_id = args[:2]
    try:
        page = max(0, int(args[2]))
    except ValueError:
        page = 0
    row = await repo.get_user_shared(file_id, update.effective_user.id)
    if not row:
        await safe_answer(query, "Link unavailable" if lang == "en" else "لینک پیدا نشد", alert=True)
        await show(update, context, page)
        return
    if operation == "ask":
        await safe_answer(query)
        prompt = ("Delete this link AND file from the server permanently?" if lang == "en"
                  else "این لینک و فایلش برای همیشه از سرور حذف شود؟")
        await edit(query.message, f"🗑 <b>{human.esc(row.name)}</b>\n\n{prompt}",
                   reply_markup=kb.Kb([
                       [kb.Btn("✅ Delete" if lang == "en" else "✅ حذف قطعی",
                               callback_data=f"u|del|{file_id}|{page}")],
                       [kb.Btn("↩️ Back" if lang == "en" else "↩️ بازگشت",
                               callback_data=f"u|ls|{page}")],
                   ]))
        return
    # Authorization is checked and consumed atomically by the DB layer.
    removed_path = await repo.pop_user_shared(file_id, update.effective_user.id)
    if removed_path:
        svc = services(context)
        target = Path(removed_path).resolve()
        root = svc.store.links.resolve()
        if target.is_relative_to(root):
            svc.store.remove(target)
            # Drop only a single directory controlled by the file id.
            if (root / file_id).resolve().is_relative_to(root):
                svc.store.drop_link_dir(file_id)
        await repo.log_event(update.effective_user.id, "link_revoked")
        if getattr(svc, "admin_group", None) is not None:
            await svc.admin_group.audit("security", "direct_link_deleted",
                                        update.effective_user.id, f"file_id={file_id}")
        await safe_answer(query, "Deleted" if lang == "en" else "فایل حذف شد")
    else:
        await safe_answer(query, "Already removed" if lang == "en" else "قبلاً حذف شده")
    await show(update, context, page)


async def cmd_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show(update, context)
