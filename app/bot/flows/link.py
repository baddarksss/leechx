"""جریان «لینک → کیفیت → نحوهٔ تحویل → دانلود/آپلود».

مسیر کاربر:
1. لینک می‌فرستد.
2. اگر چند کیفیت دارد، کیفیت را انتخاب می‌کند (لینک مستقیم این مرحله را ندارد).
3. صفحهٔ «نحوهٔ تحویل» می‌آید: ویدیو / فایل / لینک مستقیم / تغییر نام.
4. فقط بعد از انتخاب، کار در صف قرار می‌گیرد.
"""
from __future__ import annotations

import logging
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import keyboards as kb
from app.bot.common import edit, lang_of, reply, services
from app.bot.states import ST_RENAME, clear_state, get_data, set_state
from app.core import errors, human, text
from app.db import repo
from app.services.drafts import Draft
from app.services.formats import FormatOption, all_options

log = logging.getLogger("leechx.link")

# پسوندهایی که اگر انتهای عنوان بودند، با پسوند کیفیت انتخاب‌شده جایگزین می‌شوند
_MEDIA_SUFFIXES = {
    ".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".3gp", ".ts",
    ".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus",
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".pdf", ".zip", ".rar", ".7z", ".apk",
}


SOCIAL_AUTO_QUALITY_DOMAINS = (
    "instagram.com",
    "instagr.am",
    "tiktok.com",
)


def auto_quality_for_social(url: str, extractor: str = "") -> bool:
    """Instagram/TikTok URLs, including vm/vt short links and extractor redirects.

    Match whole domain boundaries only: not-actually-tiktok.com is not TikTok.
    """
    try:
        host = (urlsplit(url).hostname or "").rstrip(".").lower()
    except ValueError:
        host = ""
    if any(host == domain or host.endswith("." + domain)
           for domain in SOCIAL_AUTO_QUALITY_DOMAINS):
        return True
    key = (extractor or "").casefold()
    return key.startswith(("instagram", "tiktok"))


def new_job_id() -> str:
    return secrets.token_hex(6)


async def _quota_left(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    svc = services(context)
    quota = svc.settings.daily_quota
    if quota <= 0:
        return True
    used = await repo.user_events_since(user_id, "download_done", int(time.time()) - 86400)
    return used < quota


REPORTABLE = {"unsupported", "live_unsupported"}


def error_text(lang: str, exc: errors.LeechError) -> str:
    kwargs = dict(exc.extra)
    kwargs.setdefault("reason", human.esc(exc.reason or "?"))
    return text.t(lang, exc.key, **kwargs)


async def _report_issue(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    reason: str,
) -> bool:
    """Return true only if the issue was actually recorded for admins."""
    svc = services(context)
    hub = getattr(svc, "admin_group", None)
    user = update.effective_user
    if hub is None or user is None:
        return False
    try:
        report = await hub.report_issue(
            user.id,
            user.username,
            user.first_name,
            url,
            reason,
        )
        return report is not None
    except Exception:  # noqa: BLE001 — گزارش نباید تجربهٔ کاربر را خراب کند
        log.exception("could not report issue")
        return False


def draft_extension(draft: Draft) -> str:
    if draft.option is not None and draft.option.ext:
        return "." + draft.option.ext.lstrip(".").lower()
    return ""


def draft_name(draft: Draft) -> str:
    """نام نمایشی فایل؛ تغییر نام کاربر هم لحاظ می‌شود."""
    ext = draft_extension(draft)
    base = human.safe_filename(draft.custom_name or draft.title, 150)
    suffix = Path(base).suffix.lower()
    if suffix and suffix in _MEDIA_SUFFIXES:
        if not ext or suffix == ext:
            return base
        base = base[: -len(suffix)].rstrip(" .") or "file"
    if ext and not base.lower().endswith(ext):
        base = f"{base}{ext}"
    return base


def delivery_text(lang: str, draft: Draft, ttl_hours: float = 6.0) -> str:
    """Explain *what happens* before the user starts any network transfer."""
    size = draft.option.filesize if draft.option is not None else None
    quality = (
        text.t(lang, "quality_auto")
        if draft.auto_quality
        else text.t(lang, "quality_original") if draft.kind == "direct"
        else draft.option.label if draft.option is not None
        else "—"
    )
    return text.t(
        lang,
        "delivery_panel",
        title=human.esc(draft.title),
        quality=human.esc(quality),
        size=human.human_bytes(size) if size else text.t(lang, "size_unknown"),
        name=human.esc(draft_name(draft)),
        ttl=f"{ttl_hours:g}",
    )


def quality_text(lang: str, draft: Draft, note: str = "") -> str:
    lines = [f"<b>{human.esc(draft.title)}</b>"]
    meta = []
    if draft.duration:
        meta.append(f"⏱ {human.human_duration(draft.duration)}")
    if draft.uploader:
        meta.append(f"👤 {human.esc(draft.uploader)}")
    if meta:
        lines.append(" • ".join(meta))
    if note:
        lines.append(note)
    lines.append("")
    lines.append(text.t(lang, "choose_quality", title="").replace("<b></b>", "").strip())
    return "\n".join(lines)


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
        info = (await svc.cache.probe(user.id, url, svc.downloader.probe)
                if getattr(svc, "cache", None) is not None
                else await svc.downloader.probe(url))
    except errors.LeechError as exc:
        body = error_text(lang, exc)
        if exc.key in REPORTABLE:
            if await _report_issue(update, context, url, f"{exc.key}: {exc.reason}"):
                body += "\n\n" + text.t(lang, "issue_reported")
        await edit(status, body)
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("probe crashed")
        await edit(
            status,
            text.t(lang, "failed", reason=human.esc(str(exc)[:150]))
            + ("\n\n" + text.t(lang, "issue_reported")
               if await _report_issue(update, context, url, f"probe crashed: {exc}") else ""),
        )
        return

    # ── لینک مستقیم: بدون انتخاب کیفیت، مستقیم به صفحهٔ تحویل ──
    if info.direct:
        option = FormatOption(
            kind="direct",
            code="direct",
            label="direct",
            selector="",
            ext=info.ext,
            filesize=info.filesize,
        )
        draft = Draft(
            id=svc.drafts.new_id(),
            user_id=user.id,
            chat_id=update.effective_chat.id,
            url=info.url,
            title=info.title,
            options=[option],
            option=option,
            duration=info.duration,
            thumbnail=info.thumbnail,
            uploader=info.uploader,
            extractor=info.extractor,
            kind="direct",
            lang=lang,
        )
        svc.drafts.put(draft)
        await edit(status, delivery_text(lang, draft, svc.settings.ttl_hours),
                   reply_markup=kb.delivery_menu(lang, draft))
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
    if auto_quality_for_social(url, info.extractor) or auto_quality_for_social(info.url):
        # Skip the quality menu only for Instagram/TikTok. Let yt-dlp pick the
        # best available media, then ask only how the user wants to receive it.
        # No download begins before delivery mode has been chosen.
        draft.auto_quality = True
        draft.option = FormatOption(
            kind="video",
            code="auto",
            label=text.t(lang, "quality_auto"),
            selector="bv*+ba/b",
            ext="mp4",
        )
        draft.options = [draft.option]
        svc.drafts.put(draft)
        await edit(
            status, delivery_text(lang, draft, svc.settings.ttl_hours),
            reply_markup=kb.delivery_menu(lang, draft),
        )
        return

    svc.drafts.put(draft)
    note = text.t(lang, "playlist_detected") if info.playlist else ""
    await edit(status, quality_text(lang, draft, note), reply_markup=kb.quality_menu(lang, draft))


async def start_rename(update: Update, context: ContextTypes.DEFAULT_TYPE, draft: Draft) -> None:
    """حالت انتظار برای نام جدید؛ پیام راهنما را ویرایش می‌کند."""
    lang = lang_of(context)
    set_state(context, ST_RENAME, draft_id=draft.id)
    query = update.callback_query
    body = text.t(lang, "rename_prompt", name=human.esc(draft_name(draft)))
    if query is not None:
        await edit(query.message, body)
    else:
        await reply(update, body)


async def handle_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """متن ارسالی کاربر در حالت تغییر نام."""
    svc = services(context)
    lang = lang_of(context)
    message = update.effective_message
    raw = (message.text or "").strip() if message else ""
    draft_id = get_data(context).get("draft_id", "")
    draft = svc.drafts.get(draft_id, update.effective_user.id)
    clear_state(context)

    if draft is None:
        await reply(update, text.t(lang, "expired_draft"))
        return
    if not raw:
        await reply(update, text.t(lang, "rename_bad"))
        return

    name = human.safe_filename(raw, 150)
    if not name or name == "file":
        await reply(update, text.t(lang, "rename_bad"))
        return

    draft.custom_name = name
    await reply(
        update,
        text.t(lang, "rename_done", name=human.esc(draft_name(draft)))
        + "\n\n"
        + delivery_text(lang, draft, svc.settings.ttl_hours),
        reply_markup=kb.delivery_menu(lang, draft),
    )


async def enqueue(
    context: ContextTypes.DEFAULT_TYPE,
    status,
    draft: Draft,
    mode: str,
    lang: str | None = None,
) -> None:
    """ساخت کار با کیفیت/نام انتخاب‌شده و گذاشتن در صف."""
    from app.services.downloader import MediaInfo
    from app.services.jobs import JobTask

    svc = services(context)
    lang = lang or draft.lang or "fa"
    option = draft.option
    if option is None:
        return

    info = MediaInfo(
        url=draft.url,
        title=draft.title,
        duration=draft.duration,
        uploader=draft.uploader,
        thumbnail=draft.thumbnail,
        extractor=draft.extractor,
        direct=option.kind == "direct",
        ext=option.ext,
        filesize=option.filesize,
    )
    task = JobTask(
        id=new_job_id(),
        user_id=draft.user_id,
        chat_id=status.chat_id,
        url=draft.url,
        option=option,
        title=draft.title,
        status_message_id=status.message_id,
        info=info,
        lang=lang,
        kind=draft.kind,
        mode=mode,
        custom_name=draft.custom_name,
    )
    position = await svc.jobs.submit(task)
    await edit(
        status,
        text.t(lang, "queued", pos=position),
        reply_markup=kb.cancel_job(lang, task.id),
    )


# نام قبلی برای سازگاری با تست‌ها و کدهای قدیمی
_enqueue = enqueue
