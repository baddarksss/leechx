"""جریان «لینک → انتخاب کیفیت → آپلود»."""
from __future__ import annotations

import logging
import secrets
import time

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards as kb
from app.bot.common import edit, lang_of, reply, services
from app.core import errors, human, text
from app.db import repo
from app.services.drafts import Draft
from app.services.formats import FormatOption, all_options

log = logging.getLogger("leechx.link")


def new_job_id() -> str:
    return secrets.token_hex(6)


async def _quota_left(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    svc = services(context)
    quota = svc.settings.daily_quota
    if quota <= 0:
        return True
    used = await repo.user_events_since(user_id, "download_done", int(time.time()) - 86400)
    return used < quota


def error_text(lang: str, exc: errors.LeechError) -> str:
    kwargs = dict(exc.extra)
    kwargs.setdefault("reason", human.esc(exc.reason or "?"))
    return text.t(lang, exc.key, **kwargs)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = update.effective_user

    wait = svc.limiter.hit(user.id)
    if wait > 0:
        await reply(update, text.t(lang, "rate_limited", seconds=f"{wait:g}"))
        return

    if not svc.limiter.has_slot(user.id, svc.cfg.per_user_concurrency):
        await reply(update, text.t(lang, "too_many_active"))
        return

    if not await _quota_left(context, user.id):
        await reply(update, text.t(lang, "quota_exceeded"))
        return

    if svc.sites.is_nsfw_url(url) and not svc.settings.nsfw_enabled:
        await reply(update, text.t(lang, "unsupported", reason="NSFW disabled"))
        return

    status = await reply(update, text.t(lang, "probing"))
    if status is None:
        return

    try:
        info = await svc.downloader.probe(url)
    except errors.LeechError as exc:
        await edit(status, error_text(lang, exc))
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("probe crashed")
        await edit(status, text.t(lang, "failed", reason=human.esc(str(exc)[:150])))
        return

    # ── لینک مستقیم: بدون انتخاب کیفیت ──────────────────────
    if info.direct:
        option = FormatOption(
            kind="direct",
            code="direct",
            label="direct",
            selector="",
            ext=info.ext,
            filesize=info.filesize,
        )
        await _enqueue(context, status, url, info, option, lang, user.id, kind="direct")
        return

    # ── صفحهٔ انتخاب کیفیت ──────────────────────────────────
    options = all_options(info.formats, svc.cfg.max_height)
    draft = Draft(
        id=svc.drafts.new_id(),
        user_id=user.id,
        chat_id=update.effective_chat.id,
        url=info.url,
        title=info.title,
        options=options,
        duration=info.duration,
        thumbnail=info.thumbnail,
        uploader=info.uploader,
        extractor=info.extractor,
        kind="link",
        lang=lang,
    )
    svc.drafts.put(draft)

    lines = [f"<b>{human.esc(info.title)}</b>"]
    meta = []
    if info.duration:
        meta.append(f"⏱ {human.human_duration(info.duration)}")
    if info.uploader:
        meta.append(f"👤 {human.esc(info.uploader)}")
    if meta:
        lines.append(" • ".join(meta))
    if info.playlist:
        lines.append(text.t(lang, "playlist_detected"))
    lines.append("")
    lines.append(text.t(lang, "choose_quality", title="").strip())

    await edit(status, "\n".join(lines), reply_markup=kb.quality_menu(lang, draft))


async def _enqueue(
    context: ContextTypes.DEFAULT_TYPE,
    status,
    url: str,
    info,
    option: FormatOption,
    lang: str,
    user_id: int,
    kind: str = "link",
) -> None:
    from app.services.jobs import JobTask

    svc = services(context)
    task = JobTask(
        id=new_job_id(),
        user_id=user_id,
        chat_id=status.chat_id,
        url=url,
        option=option,
        title=info.title,
        status_message_id=status.message_id,
        info=info,
        lang=lang,
        kind=kind,
    )
    position = await svc.jobs.submit(task)
    await edit(
        status,
        text.t(lang, "queued", pos=position),
        reply_markup=kb.cancel_job(lang, task.id),
    )
