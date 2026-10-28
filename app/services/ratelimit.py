"""محدودکنندهٔ نرخ درخواست (در حافظه، تک‌پروسه).

برای چند پروسه/سرور، این لایه را با Redis عوض کن — رابط همان است.
"""
from __future__ import annotations

import time


class RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = max(0.0, float(min_interval))
        self._last: dict[int, float] = {}
        self._active: dict[int, int] = {}

    def set_interval(self, seconds: float) -> None:
        self.min_interval = max(0.0, float(seconds))

    def hit(self, user_id: int) -> float:
        """ثبت یک درخواست. اگر زودتر از موعد باشد، ثانیه‌های باقی‌مانده را برمی‌گرداند."""
        now = time.monotonic()
        last = self._last.get(user_id, 0.0)
        wait = self.min_interval - (now - last)
        if wait > 0:
            return round(wait, 1)
        self._last[user_id] = now
        self._prune(now)
        return 0.0

    def _prune(self, now: float) -> None:
        if len(self._last) < 2000:
            return
        cutoff = now - max(60.0, self.min_interval * 4)
        for uid, ts in list(self._last.items()):
            if ts < cutoff:
                self._last.pop(uid, None)

    # ── شمارش کارهای همزمان ────────────────────────────────
    def acquire_slot(self, user_id: int, limit: int) -> bool:
        if limit <= 0:
            return True
        if self._active.get(user_id, 0) >= limit:
            return False
        self._active[user_id] = self._active.get(user_id, 0) + 1
        return True

    def release_slot(self, user_id: int) -> None:
        current = self._active.get(user_id, 0)
        if current <= 1:
            self._active.pop(user_id, None)
        else:
            self._active[user_id] = current - 1

    def active_count(self, user_id: int) -> int:
        return self._active.get(user_id, 0)

    def has_slot(self, user_id: int, limit: int) -> bool:
        return limit <= 0 or self._active.get(user_id, 0) < limit
