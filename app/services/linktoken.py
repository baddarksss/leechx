"""امضای لینک‌های مستقیم (HMAC) — بدون نیاز به جدول توکن."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(payload_b64: str, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64e(mac[:24])


def make_token(file_id: str, secret: str, ttl_seconds: int, user_id: int = 0) -> str:
    payload = {
        "f": file_id,
        "u": int(user_id),
        "e": int(time.time()) + int(ttl_seconds),
    }
    encoded = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{encoded}.{_sign(encoded, secret)}"


def read_token(token: str, secret: str, verify_exp: bool = True) -> dict[str, Any] | None:
    if not token or token.count(".") != 1:
        return None
    encoded, signature = token.split(".", 1)
    expected = _sign(encoded, secret)
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64d(encoded))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or "f" not in payload:
        return None
    if verify_exp and int(payload.get("e", 0)) <= int(time.time()):
        return None
    return payload
