"""جریان «فایل → لینک مستقیم»."""
from __future__ import annotations

import logging
import mimetypes
import secrets
import time
from datetime import UTC, datetime

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from app.bot import keyboards as kb
from app.bot.common import edit, lang_of, reply, services
from app.bot.states import get_state
from app.core import human, text
from app.db import repo
from app.services.linktoken import make_token

log = logging.getLogger("leechx.files")


def _attachment(message):
    att = message.effective_attachment
    if isinstance(att, (list, tuple)):
        att = att[-1]
    return att


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    svc = services(context)
    lang = lang_of(context)
    user = update.effective_user
    message = update.effective_message
    if message is None:
        return

    if get_state(context):
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

    status = await reply(update, text.t(lang, "file_received"))
    if status is None:
        return

    file_id = secrets.token_hex(6)
    dest = svc.store.link_path(file_id, name)

    try:
        tg_file = await att.get_file()
        if svc.cfg.uses_local_api:
            await tg_file.download_to_drive(custom_path=str(dest))
        else:
            await tg_file.download_to_drive(custom_path=str(dest))
    except TelegramError as exc:
        log.warning("telegram download failed: %s", exc)
        svc.store.drop_link_dir(file_id)
        await edit(
            status,
            text.t(
                lang,
                "failed",
                reason=human.esc(
                    "Telegram download failed — for files >20MB enable a local Bot API server"
                ),
            ),
        )
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("file download crashed")
        svc.store.drop_link_dir(file_id)
        await edit(status, text.t(lang, "failed", reason=human.esc(str(exc)[:150])))
        return

    if not dest.exists() or dest.stat().st_size == 0:
        svc.store.drop_link_dir(file_id)
        await edit(status, text.t(lang, "failed", reason="empty file"))
        return

    real_size = dest.stat().st_size
    mime = getattr(att, "mime_type", None) or mimetypes.guess_type(name)[0] or "application/octet-stream"
    ttl = svc.settings.ttl_seconds

    await repo.create_shared(file_id, user.id, str(dest), name, mime, real_size, ttl)
    await repo.log_event(user.id, "link_created", real_size)

    token = make_token(file_id, svc.cfg.link_secret, ttl, user_id=user.id)
    url = f"{svc.cfg.public_base_url.rstrip('/')}/f/{token}"
    expires = datetime.fromtimestamp(int(time.time()) + ttl, tz=UTC).strftime("%H:%M UTC")

    await edit(
        status,
        text.t(
            lang,
            "link_ready",
            url=url,
            name=human.esc(name),
            size=human.human_bytes(real_size),
            ttl=f"{svc.settings.ttl_hours:g}",
            expires=expires,
        ),
        reply_markup=kb.link_actions(lang, url),
    )
