"""گروه ادمین با تاپیک‌ها + ارسال گزارش/لاگ/اعلان دانلود و آپلود.

گروه با دستور ``/setup`` داخل خود گروه تنظیم می‌شود (شناسهٔ چت قابل‌اعتماد
است). تاپیک‌ها با Bot API ساخته می‌شوند و شناسهشان در جدول settings ذخیره
می‌شود؛ اگر ساخت تاپیک شکست بخورد، پیام‌ها به چت اصلی گروه می‌روند.

هیچ‌کدام از این ارسال‌ها نباید جریان اصلی ربات را متوقف کند؛ همهٔ خطاها
گرفته و لاگ می‌شوند.
"""
from __future__ import annotations

import logging
from typing import Any

from telegram.constants import ParseMode
from telegram.error import TelegramError

from app.config import Config
from app.core import human
from app.db import repo
from app.services.runtime_settings import RuntimeSettings

log = logging.getLogger("leechx.admin_group")

TOPICS: dict[str, str] = {
    "downloads": "📥 دانلودها",
    "uploads": "📤 آپلودها",
    "reports": "🚨 گزارش‌ها",
    "logs": "🐞 لاگ‌ها",
}


def _username(username: str | None) -> str:
    return f"@{human.esc(username)}" if username else "—"


def _user_block(user_id: int | None, username: str | None, first_name: str | None) -> str:
    uid = f"<code>{user_id}</code>" if user_id else "—"
    return f"👤 <b>{human.esc(first_name or '—')}</b> ({_username(username)})\n🆔 {uid}"


class AdminGroup:
    def __init__(self, cfg: Config, settings: RuntimeSettings) -> None:
        self.cfg = cfg
        self.settings = settings
        self.bot: Any = None

    def attach(self, bot) -> None:
        self.bot = bot

    # ── وضعیت ──────────────────────────────────────────────
    @property
    def chat_id(self) -> int | None:
        return self.settings.get_optional_int("admin_group_id")

    @property
    def configured(self) -> bool:
        return self.chat_id is not None

    @property
    def title(self) -> str:
        return self.settings.get_str("admin_group_title")

    def topic_id(self, key: str) -> int | None:
        return self.settings.get_optional_int(f"topic_{key}")

    def status(self) -> dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "title": self.title,
            "topics": {key: self.topic_id(key) for key in TOPICS},
        }

    # ── تنظیم گروه ─────────────────────────────────────────
    async def configure(self, chat_id: int, title: str = "") -> dict[str, int | None]:
        """شناسهٔ گروه را ذخیره و تاپیک‌ها را می‌سازد (اگر ممکن باشد)."""
        await self.settings.set("admin_group_id", str(chat_id))
        await self.settings.set("admin_group_title", (title or "")[:128])
        created: dict[str, int | None] = {}
        for key, name in TOPICS.items():
            thread: int | None = None
            if self.bot is not None:
                try:
                    topic = await self.bot.create_forum_topic(chat_id=chat_id, name=name)
                    thread = int(getattr(topic, "message_thread_id", 0) or 0) or None
                except TelegramError as exc:
                    log.warning("could not create topic %s: %s", name, exc)
                except Exception:  # noqa: BLE001
                    log.exception("unexpected error creating topic %s", name)
            await self.settings.set(f"topic_{key}", str(thread or ""))
            created[key] = thread
        return created

    async def disable(self) -> None:
        await self.settings.set("admin_group_id", "")
        await self.settings.set("admin_group_title", "")
        for key in TOPICS:
            await self.settings.set(f"topic_{key}", "")

    # ── ارسال ──────────────────────────────────────────────
    async def send(self, topic: str, body: str, reply_markup=None) -> bool:
        chat_id = self.chat_id
        if self.bot is None or chat_id is None:
            return False
        thread = self.topic_id(topic)
        kwargs: dict[str, Any] = {
            "parse_mode": ParseMode.HTML,
            "disable_web_page_preview": True,
        }
        if thread:
            kwargs["message_thread_id"] = thread
        try:
            await self.bot.send_message(chat_id, body, reply_markup=reply_markup, **kwargs)
            return True
        except TelegramError as exc:
            log.warning("admin group send failed (%s): %s", topic, exc)
            if not thread:
                return False
        # تاپیک پاک شده یا شناسه عوض شده: به چت اصلی گروه برمی‌گردیم.
        kwargs.pop("message_thread_id", None)
        try:
            await self.bot.send_message(chat_id, body, reply_markup=reply_markup, **kwargs)
            return True
        except TelegramError as exc:
            log.warning("admin group fallback failed: %s", exc)
            return False

    # ── اعلان‌های کار ───────────────────────────────────────
    async def notify_job(self, kind: str, task, result=None) -> None:
        """اعلان شروع دانلود یا شروع آپلود با مشخصات کامل کاربر."""
        try:
            user = await repo.get_user(task.user_id)
            username = user.username if user else None
            first_name = user.first_name if user else None
            title = (result.title if result is not None else task.title) or task.url
            size = (result.size if result is not None else 0) or (
                task.option.filesize if task.option is not None else 0
            )
            if kind == "download":
                heading = "📥 <b>دانلود جدید</b>"
                topic = "downloads"
            else:
                heading = "📤 <b>آپلود جدید</b>"
                topic = "uploads"
            mode = {
                "video": "ویدیو",
                "document": "فایل",
                "link": "لینک مستقیم",
            }.get(getattr(task, "mode", ""), getattr(task, "mode", "—"))
            body = (
                f"{heading}\n\n"
                f"{_user_block(task.user_id, username, first_name)}\n\n"
                f"🎬 <b>{human.esc(human.truncate(str(title), 180))}</b>\n"
                f"🎚 کیفیت/نوع: {human.esc(getattr(task.option, 'label', '') or '—')}\n"
                f"📦 حجم: {human.human_bytes(size)}\n"
                f"📤 تحویل: {mode}\n"
                f"🆔 کار: <code>{task.id}</code>\n"
                f"🌐 {human.esc(human.truncate(task.url, 300))}"
            )
            await self.send(topic, body)
        except Exception:  # noqa: BLE001
            log.exception("job notification failed")

    async def notify_file_upload(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        name: str,
        size: int,
    ) -> None:
        """کاربر فایلی به ربات داد تا لینک مستقیم بگیرد."""
        try:
            body = (
                "📤 <b>آپلود فایل کاربر</b>\n\n"
                f"{_user_block(user_id, username, first_name)}\n\n"
                f"📄 <b>{human.esc(human.truncate(name, 180))}</b>\n"
                f"📦 حجم: {human.human_bytes(size)}\n"
                "🔗 تحویل: لینک مستقیم"
            )
            await self.send("uploads", body)
        except Exception:  # noqa: BLE001
            log.exception("upload notification failed")

    # ── گزارش‌ها ────────────────────────────────────────────
    async def notify_report(self, report) -> None:
        try:
            label = {
                "contact": "✉️ پیام کاربر به ادمین",
                "unsupported": "🚨 سایت/لینک مشکل‌دار",
            }.get(report.kind, "🚨 گزارش")
            parts = [
                f"<b>{label}</b>",
                "",
                _user_block(report.user_id, report.username, report.first_name),
            ]
            if report.url:
                parts += ["", f"🌐 <code>{human.esc(human.truncate(report.url, 500))}</code>"]
            if report.text:
                parts += ["", f"📝 {human.esc(human.truncate(report.text, 1500))}"]
            parts += ["", f"🆔 گزارش: <code>#{report.id}</code>"]
            await self.send("reports", "\n".join(parts))
        except Exception:  # noqa: BLE001
            log.exception("report notification failed")

    async def report_issue(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        url: str,
        reason: str,
    ):
        """گزارش مشکل را در دیتابیس ذخیره و به تاپیک گزارش‌ها می‌فرستد."""
        try:
            report = await repo.add_report(
                "unsupported",
                user_id,
                username=username,
                first_name=first_name,
                text=reason[:1500],
                url=url,
            )
            await repo.add_log(
                "WARNING",
                "report",
                f"{url} — {reason}"[:2000],
                user_id,
            )
            await self.notify_report(report)
            return report
        except Exception:  # noqa: BLE001
            log.exception("could not record issue report")
            return None

    # ── لاگ‌ها ─────────────────────────────────────────────
    async def record_log(
        self,
        level: str,
        source: str,
        message: str,
        user_id: int | None = None,
    ) -> None:
        try:
            row = await repo.add_log(level, source, message, user_id)
        except Exception:  # noqa: BLE001
            log.exception("could not persist log")
            return
        await self.notify_log(row)

    async def notify_log(self, row) -> None:
        try:
            icon = {"ERROR": "❌", "WARNING": "⚠️", "INFO": "ℹ️"}.get(row.level, "•")
            body = (
                f"{icon} <b>{human.esc(row.level)}</b> · <code>{human.esc(row.source)}</code>\n"
                f"{human.esc(human.truncate(row.message, 2500))}"
            )
            if row.user_id:
                body += f"\n🆔 کاربر: <code>{row.user_id}</code>"
            body += f"\n🆔 لاگ: <code>#{row.id}</code>"
            await self.send("logs", body)
        except Exception:  # noqa: BLE001
            log.exception("log notification failed")
