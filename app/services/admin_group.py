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
from app.services.cache import safe_source
from app.db import repo
from app.services.runtime_settings import RuntimeSettings

log = logging.getLogger("leechx.admin_group")

TOPICS: dict[str, str] = {
    "downloads": "📥 دانلودها",
    "uploads": "📤 آپلودها",
    "reports": "🚨 گزارش‌ها",
    "logs": "🐞 لاگ‌ها",
    "cache": "📦 کش رسانه‌ها",
    "audit": "🧾 ممیزی و وضعیت عملیات",
    "security": "🔐 امنیت و تنظیمات",
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
        # /setup is idempotent: do not duplicate existing topics on each call.
        same_group = self.chat_id == chat_id
        created: dict[str, int | None] = {}
        for key, name in TOPICS.items():
            thread: int | None = self.topic_id(key) if same_group else None
            if thread is None and self.bot is not None:
                try:
                    topic = await self.bot.create_forum_topic(chat_id=chat_id, name=name)
                    thread = int(getattr(topic, "message_thread_id", 0) or 0) or None
                except TelegramError as exc:
                    log.warning("could not create topic %s: %s", name, exc)
                except Exception:
                    log.exception("unexpected error creating topic %s", name)
            # Existing topics survive partially failed reconfiguration.
            created[key] = thread
        # Only persist new group settings after topic provisioning is attempted.
        await self.settings.set("admin_group_id", str(chat_id))
        await self.settings.set("admin_group_title", (title or "")[:128])
        for key, thread in created.items():
            await self.settings.set(f"topic_{key}", str(thread or ""))
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
        if not thread:
            log.warning("cannot send %s without a configured topic", topic)
            return False
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
            log.warning("admin group topic send failed (%s): %s", topic, exc)
            return False

    async def cache_event(self, component: str, action: str, summary: str) -> bool:
        """Diagnostics without sending user URLs, secrets or file bodies."""
        if not self.topic_id("cache"):
            return False
        body = (
            f"📦 <b>{human.esc(component)}</b> | <b>{human.esc(action)}</b>\n"
            f"<code>{human.esc(human.truncate(summary, 140))}</code>"
        )
        try:
            return await self.send("cache", body)
        except Exception:
            log.debug("cache event logging failed", exc_info=True)
            return False

    async def audit(self, category: str, action: str, user_id: int | None = None,
                    details: str = "", severity: str = "INFO") -> None:
        """Store events in SQLite and route to audit or security topic."""
        message = f"{action}" + (f" • {details[:350]}" if details else "")
        topic = "security" if category == "security" else "audit"
        try:
            row = await repo.add_log(severity, category[:64], message[:1300], user_id)
            label = "🔐" if category == "security" else "🧾"
            body = (
                f"{label} <b>{human.esc(action)}</b>\n"
                f"بخش: <code>{human.esc(category)}</code>\n"
                f"جزئیات: {human.esc(human.truncate(details or '—', 350))}\n"
                f"کاربر: <code>{user_id if user_id is not None else '—'}</code>\n"
                f"لاگ: <code>#{row.id}</code>"
            )
            await self.send(topic, body)
        except Exception:
            log.warning("audit event could not be saved", exc_info=True)

    async def notify_job_result(self, task, status: str, size: int = 0,
                                reason: str = "") -> None:
        """Lifecycle status for every URL download, upload, link or cancel."""
        mode = getattr(task, "mode", "video")
        topic = "downloads" if mode == "link" else "uploads"
        message = (
            f"🧾 <b>پایان عملیات {human.esc(status)}</b>\n"
            f"کار: <code>{human.esc(task.id)}</code>\n"
            f"کاربر: <code>{task.user_id}</code>\n"
            f"روش تحویل: {human.esc(mode)}\n"
            f"حجم: {human.human_bytes(size)}\n"
            f"خطا: {human.esc(human.truncate(reason or '—', 200))}"
        )
        await self.send(topic, message)
        await self.audit("job", status, task.user_id, f"{task.id}, {mode}, {size}B")

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
                f"🌐 {human.esc(human.truncate(safe_source(task.url), 200))}"
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
