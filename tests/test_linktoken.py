import time

from app.services.linktoken import make_token, read_token

SECRET = "s3cr3t"


def test_roundtrip():
    token = make_token("abc123", SECRET, 60, user_id=42)
    payload = read_token(token, SECRET)
    assert payload is not None
    assert payload["f"] == "abc123"
    assert payload["u"] == 42


def test_wrong_secret_rejected():
    token = make_token("abc", SECRET, 60)
    assert read_token(token, "other") is None


def test_tampered_rejected():
    token = make_token("abc", SECRET, 60)
    head, sig = token.split(".")
    assert read_token(f"{head}.{sig[:-1]}X", SECRET) is None
    assert read_token("garbage", SECRET) is None
    assert read_token("", SECRET) is None


def test_expired():
    token = make_token("abc", SECRET, 60)
    assert read_token(token, SECRET, verify_exp=False) is not None
    # دستکاری payload برای گذشته‌بودن انقضا نباید کار کند چون امضا می‌شکند
    expired_token = make_token("abc", SECRET, -10)
    assert read_token(expired_token, SECRET) is None


def test_expiry_is_in_future():
    before = int(time.time())
    payload = read_token(make_token("f", SECRET, 3600), SECRET)
    assert payload["e"] >= before + 3600
