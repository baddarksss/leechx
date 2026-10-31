"""پیش‌نویس‌های انتخاب کیفیت.

وقتی کاربر لینک می‌فرستد و کیفیت‌ها نمایش داده می‌شوند، اطلاعات لازم برای
دانلود باید جایی بماند تا وقتی دکمه را زد در دسترس باشد. این اطلاعات در
حافظه نگه داشته می‌شود (سبک و کوتاه‌عمر) — نه در دیتابیس.
"""
from __future__ import annotations

import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from app.services.formats import FormatOption

MAX_DRAFTS = 4000
DRAFT_TTL = 3600  # یک ساعت


@dataclass
class Draft:
    id: str
    user_id: int
    chat_id: int
    url: str
    title: str
    options: list[FormatOption] = field(default_factory=list)
    duration: int | None = None
    thumbnail: str | None = None
    uploader: str | None = None
    extractor: str = ""
    # صفحهٔ امبد برای سایت‌های HLS (Cloudflare) — تا زمان دانلود نگه داشته می‌شود.
    embed_url: str = ""
    kind: str = "link"
    lang: str = "fa"
    option: FormatOption | None = None
    custom_name: str = ""
    send_as: str = "video"  # per-link override, initialized from the user's preference
    destination: str = "telegram"  # telegram | link
    custom_thumbnail: bytes | None = None  # bounded Telegram photo bytes, kept only in memory
    auto_quality: bool = False  # Instagram/TikTok skip manual quality selection
    created_at: float = field(default_factory=time.time)


class DraftStore:
    def __init__(self, max_items: int = MAX_DRAFTS, ttl: int = DRAFT_TTL) -> None:
        self._items: OrderedDict[str, Draft] = OrderedDict()
        self.max_items = max_items
        self.ttl = ttl

    def put(self, draft: Draft) -> str:
        self.prune()
        while len(self._items) >= self.max_items:
            self._items.popitem(last=False)
        self._items[draft.id] = draft
        return draft.id

    def new_id(self) -> str:
        while True:
            candidate = secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")
            if candidate not in self._items:
                return candidate

    def get(self, draft_id: str, user_id: int | None = None) -> Draft | None:
        self.prune()
        draft = self._items.get(draft_id)
        if draft is None:
            return None
        if user_id is not None and draft.user_id != user_id:
            return None
        return draft

    def pop(self, draft_id: str, user_id: int | None = None) -> Draft | None:
        draft = self.get(draft_id, user_id)
        if draft is not None:
            self._items.pop(draft_id, None)
        return draft

    def prune(self) -> int:
        cutoff = time.time() - self.ttl
        stale = [k for k, v in self._items.items() if v.created_at < cutoff]
        for key in stale:
            self._items.pop(key, None)
        return len(stale)

    def __len__(self) -> int:
        return len(self._items)

    def clear_user(self, user_id: int, chat_id: int | None = None) -> int:
        """Invalidate all pending choices owned by a user (or one chat)."""
        keys = [key for key, draft in self._items.items()
                if draft.user_id == user_id and (chat_id is None or draft.chat_id == chat_id)]
        for key in keys:
            self._items.pop(key, None)
        return len(keys)
