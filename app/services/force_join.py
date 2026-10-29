"""عضویت اجباری در کانال/گروه.

کاربر تا وقتی عضو همهٔ مقصدهای تعریف‌شده نشود، به ربات دسترسی ندارد.
مقصدها در تنظیمات زمان اجرا (کلید ``force_join_chats``) به‌صورت JSON
ذخیره می‌شوند تا ادمین بدون ری‌استارت اضافه/حذف کند.

نکته‌های امنیتی/عملی:
* برای بررسی عضویت، ربات باید در هر کانال/گروه **ادمین** باشد.
* نتیجهٔ بررسی چند دقیقه کش می‌شود تا هر پیام باعث درخواست به تلگرام نشود.
* اگر تلگرام خطا بدهد (قطعی/دسترسی)، سیستم «قفل نمی‌کند» و کاربر را رد
  نمی‌کند؛ فقط بررسی دوباره پیشنهاد می‌شود.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass

from telegram.error import TelegramError

from app.services.runtime_settings import RuntimeSettings

log = logging.getLogger("leechx.force_join")

CACHE_SECONDS = 180
SETTINGS_KEY = "force_join_chats"


@dataclass
class JoinTarget:
    chat_id: int
    title: str
    username: str = ""
    link: str = ""

    def url(self) -> str:
        if self.link:
            return self.link
        if self.username:
            return f"https://t.me/{self.username.lstrip('@')}"
        return ""

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, raw: dict) -> JoinTarget | None:
        try:
            chat_id = int(raw.get("chat_id"))
        except (TypeError, ValueError):
            return None
        return cls(
            chat_id=chat_id,
            title=str(raw.get("title") or chat_id)[:120],
            username=str(raw.get("username") or ""),
            link=str(raw.get("link") or ""),
        )


class ForceJoin:
    def __init__(self, settings: RuntimeSettings) -> None:
        self.settings = settings
        # user_id → (timestamp, frozenset(chat_idهایی که کاربر عضو نیست))
        self._cache: dict[int, tuple[float, frozenset[int]]] = {}

    # ── خواندن/نوشتن مقصدها ────────────────────────────────
    @property
    def enabled(self) -> bool:
        return self.settings.get_bool("force_join_enabled")

    @property
    def targets(self) -> list[JoinTarget]:
        raw = self.settings.get_str(SETTINGS_KEY).strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except ValueError:
            log.warning("force_join_chats is not valid JSON")
            return []
        out: list[JoinTarget] = []
        for item in data if isinstance(data, list) else []:
            if isinstance(item, dict):
                target = JoinTarget.from_json(item)
                if target is not None:
                    out.append(target)
        return out

    def active_targets(self) -> list[JoinTarget]:
        if not self.enabled:
            return []
        return self.targets

    async def _save(self, targets: list[JoinTarget]) -> None:
        payload = json.dumps([t.to_json() for t in targets], ensure_ascii=False)
        await self.settings.set(SETTINGS_KEY, payload)
        self.clear_cache()

    async def add(self, target: JoinTarget) -> JoinTarget:
        targets = [t for t in self.targets if t.chat_id != target.chat_id]
        targets.append(target)
        await self._save(targets)
        return target

    async def remove(self, chat_id: int) -> JoinTarget | None:
        targets = self.targets
        found = next((t for t in targets if t.chat_id == chat_id), None)
        if found is None:
            return None
        await self._save([t for t in targets if t.chat_id != chat_id])
        return found

    async def set_enabled(self, value: bool) -> None:
        await self.settings.set("force_join_enabled", value)
        self.clear_cache()

    def clear_cache(self, user_id: int | None = None) -> None:
        if user_id is None:
            self._cache.clear()
        else:
            self._cache.pop(user_id, None)

    # ── ساخت مقصد از ورودی ادمین ──────────────────────────
    async def resolve(self, bot, raw: str) -> JoinTarget:
        """ورودی ``@name``/آیدی عددی را به مقصد تبدیل می‌کند."""
        token = (raw or "").strip()
        if not token:
            raise ValueError("empty")
        if token.lstrip("-").isdigit():
            chat_id: int | str = int(token)
        else:
            chat_id = token if token.startswith("@") else f"@{token.lstrip('@')}"
        chat = await bot.get_chat(chat_id)
        return self.from_chat(chat)

    @staticmethod
    def from_chat(chat) -> JoinTarget:
        chat_id = int(getattr(chat, "id", 0) or 0)
        if not chat_id:
            raise ValueError("chat has no id")
        username = (getattr(chat, "username", None) or "").lstrip("@")
        link = getattr(chat, "invite_link", None) or ""
        return JoinTarget(
            chat_id=chat_id,
            title=str(getattr(chat, "title", None) or username or chat_id)[:120],
            username=username,
            link=str(link),
        )

    # ── بررسی عضویت ─────────────────────────────────────────
    async def missing(self, bot, user_id: int, *, use_cache: bool = True) -> tuple[list[JoinTarget], bool]:
        """(مقصدهایی که کاربر عضو نیست، آیا بررسی کامل انجام شد)

        اگر تلگرام خطا بدهد، مقصد خطادار «عضو» فرض می‌شود تا کاربر قفل نشود؛
        مقدار دوم False یعنی بعضی بررسی‌ها ناموفق بودند.
        """
        targets = self.active_targets()
        if not targets:
            return [], True

        now = time.monotonic()
        if use_cache:
            cached = self._cache.get(user_id)
            if cached and now - cached[0] < CACHE_SECONDS:
                ids = cached[1]
                return [t for t in targets if t.chat_id in ids], True

        missing: list[JoinTarget] = []
        complete = True
        for target in targets:
            try:
                member = await bot.get_chat_member(target.chat_id, user_id)
                status = str(getattr(member, "status", "") or "")
                if status in ("creator", "administrator", "member"):
                    continue
                if status == "restricted" and getattr(member, "is_member", False):
                    continue
                missing.append(target)
            except TelegramError as exc:
                complete = False
                log.info("membership check failed for %s: %s", target.chat_id, exc)
                continue

        self._cache[user_id] = (now, frozenset(t.chat_id for t in missing))
        return missing, complete

    async def check_access(self, bot) -> list[tuple[JoinTarget, bool, str]]:
        """آیا ربات می‌تواند عضویت را در هر مقصد بررسی کند؟"""
        results: list[tuple[JoinTarget, bool, str]] = []
        bot_id = getattr(bot, "id", None)
        for target in self.targets:
            try:
                if bot_id is not None:
                    me = await bot.get_chat_member(target.chat_id, bot_id)
                    status = str(getattr(me, "status", "") or "")
                    if status not in ("administrator", "creator"):
                        results.append((target, False, f"bot is {status or 'not admin'}"))
                        continue
                chat = await bot.get_chat(target.chat_id)
                results.append((target, True, str(getattr(chat, "title", "") or "")))
            except TelegramError as exc:
                results.append((target, False, str(exc)[:120]))
        return results

    def status_text(self) -> str:
        return "on" if self.enabled else "off"
