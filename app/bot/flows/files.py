"""جریان «فایل → لینک مستقیم»."""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import time

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.common import drop_user_input, lang_of, panel, reply, services
from app.bot.guards import require_admin
from app.bot.states import ST_COOKIE_ADD, ST_DEPLOY_ZIP, ST_THUMBNAIL, clear_state, get_state
from app.core import human, text
from app.services.cookies import MAX_COOKIE_BYTES, CookieError

log = logging.getLogger("leechx.files")


def _attachment(message):
    att = message.effective_attachment
    if isinstance(att, (list, tuple)):
        att = att[-1]
    return att


async def _handle_source_zip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ZIP سورس جدید را می‌گیرد، اعتبارسنجی و برای تأیید نگه می‌دارد."""
    svc = services(context)
    lang = lang_of(context)
    if not await require_admin(update, context):
        clear_state(context)
        return

    att = _attachment(update.effective_message)
    if att is None:
        await reply(update, text.t(lang, "deploy_upload_prompt"))
        return

    size = int(getattr(att, "file_size", 0) or 0)
    limit = max(1, int(svc.cfg.max_source_zip_mb)) * 1024 * 1024
    if size and size > limit:
        await reply(
            update,
            text.t(
                lang,
                "deploy_zip_too_big",
                size=human.human_bytes(size),
                max=human.human_bytes(limit),
            ),
        )
        return

    name = getattr(att, "file_name", None) or "source.zip"
    if not name.lower().endswith(".zip"):
        await reply(update, text.t(lang, "deploy_zip_bad", reason="not a .zip file"))
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = svc.updater.workdir / f"incoming-{stamp}.zip"
    try:
        tg_file = await att.get_file()
        download = getattr(tg_file, "download_to_drive", None)
        if download is not None:
            await download(custom_path=target)
        else:  # pragma: no cover - سازگاری با نسخه‌های قدیمی PTB/fakeها
            data = bytes(await tg_file.download_as_bytearray())
            target.write_bytes(data)
    except Exception as exc:  # noqa: BLE001
        log.warning("source zip download failed: %s", exc)
        await reply(update, text.t(lang, "deploy_zip_bad", reason=human.esc(str(exc)[:120])))
        return

    preview = await asyncio.to_thread(svc.updater.inspect_zip, target)
    if not preview.ok:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        await reply(update, text.t(lang, "deploy_zip_bad", reason=human.esc(preview.reason)))
        return

    clear_state(context)
    context.user_data["deploy_staged"] = target
    from app.bot.flows import admin as admin_flow

    await admin_flow._render_staged(update, context)


async def _handle_cookie_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """فایل ``cookies.txt`` ارسالی ادمین را ذخیره می‌کند."""
    svc = services(context)
    lang = lang_of(context)
    if not await require_admin(update, context):
        clear_state(context)
        return

    att = _attachment(update.effective_message)
    if att is None:
        return

    size = int(getattr(att, "file_size", 0) or 0)
    if size > MAX_COOKIE_BYTES:
        await reply(
            update,
            text.t(
                lang,
                "cookie_bad",
                reason=human.esc(f"file is too large ({size} bytes)"),
            ),
        )
        return

    try:
        tg_file = await att.get_file()
        data = bytes(await tg_file.download_as_bytearray())
    except Exception as exc:  # noqa: BLE001 — خطای شبکه/تلگرام
        log.warning("cookie file download failed: %s", exc)
        await reply(update, text.t(lang, "cookie_bad", reason=human.esc(str(exc)[:150])))
        return

    if len(data) > MAX_COOKIE_BYTES:
        await reply(update, text.t(lang, "cookie_bad", reason=human.esc("file is too large")))
        return

    try:
        cookie = svc.cookies.save_text(data)
    except CookieError as exc:
        await reply(update, text.t(lang, "cookie_bad", reason=human.esc(str(exc)[:150])))
        return

    clear_state(context)
    await drop_user_input(update)  # فایل کوکی محرمانه است؛ در چت نماند
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


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = update.effective_user
    message = update.effective_message
    if message is None:
        return

    state = get_state(context)
    if state == ST_THUMBNAIL:
        from app.bot.flows import link as link_flow

        await link_flow.handle_thumbnail(update, context)
        return
    if state == ST_COOKIE_ADD:
        await _handle_cookie_upload(update, context)
        return
    if state == ST_DEPLOY_ZIP:
        await _handle_source_zip(update, context)
        return
    if state:
        await reply(update, text.t(lang, "state_text_only"))
        return

    att = _attachment(message)
    if att is None:
        return

    size = int(getattr(att, "file_size", 0) or 0)
    limit = svc.settings.max_link_bytes
    if size and size > limit:
        await reply(
            update,
            text.t(
                lang,
                "file_too_big_link",
                size=human.human_bytes(size),
                max=human.human_bytes(limit),
            ),
        )
        return

    wait = svc.limiter.hit(user.id)
    if wait > 0:
        await reply(update, text.t(lang, "rate_limited", seconds=f"{wait:g}"))
        return

    name = getattr(att, "file_name", None) or f"{getattr(att, 'file_unique_id', 'file')}"
    if "." not in name:
        guessed = mimetypes.guess_extension(getattr(att, "mime_type", "") or "") or ""
        name += guessed
    name = human.safe_filename(name, 120)

    # Run asynchronously so the user can cancel the transfer with a button
    # while Telegram's file bytes arrive in bounded chunks.
    if svc.file_transfers.tasks_for_user(user.id):
        await reply(update, text.t(lang, "too_many_active"))
        return
    await svc.file_transfers.start(update, lang, att, name, size)
