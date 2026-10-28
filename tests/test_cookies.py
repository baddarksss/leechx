"""تست ذخیره/تشخیص فایل کوکی (Netscape و JSON)."""
from __future__ import annotations

import json
import time

import pytest

from app.services.cookies import (
    MAX_COOKIE_BYTES,
    CookieError,
    CookieStore,
    count_expired,
    infer_name,
    looks_like_cookie_text,
    normalize_cookie_data,
    parse_domains,
)

NETSCAPE = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc123\n"
    ".youtube.com\tTRUE\t/\tFALSE\t0\tHSID\tdef456\n"
)

INSTAGRAM = (
    "# Netscape HTTP Cookie File\n"
    ".instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\txyz789\n"
)

EXPIRED = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t100\tOLD\tabc\n"
    ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tdef\n"
)


def test_normalize_adds_header_and_reads_httponly():
    raw = "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n"
    data = normalize_cookie_data(raw)
    assert data.startswith("# Netscape HTTP Cookie File")
    assert parse_domains(data) == ["youtube.com"]


def test_normalize_converts_json_export():
    payload = json.dumps(
        [
            {
                "domain": ".instagram.com",
                "hostOnly": False,
                "path": "/",
                "secure": True,
                "expirationDate": 1_900_000_000,
                "name": "sessionid",
                "value": "tok",
            }
        ]
    )
    data = normalize_cookie_data(payload)
    assert "sessionid" in data
    assert parse_domains(data) == [".instagram.com"] or parse_domains(data) == ["instagram.com"]
    assert looks_like_cookie_text(data)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   \n\n",
        "<!DOCTYPE html><html><body>login</body></html>",
        "not a cookie file at all",
        "\x00\x01\x02binary",
    ],
)
def test_invalid_cookie_files_are_rejected(raw):
    with pytest.raises(CookieError):
        normalize_cookie_data(raw)


def test_too_large_is_rejected():
    with pytest.raises(CookieError):
        normalize_cookie_data(b"x" * (MAX_COOKIE_BYTES + 1))


def test_infer_name_from_domains():
    assert infer_name(["www.youtube.com"]) == "youtube"
    assert infer_name(["instagram.com", "cdninstagram.com"]) == "instagram"
    assert infer_name(["example.org"]) == "example"
    assert infer_name([]) == "cookies"


def test_count_expired():
    assert count_expired(EXPIRED, now=1000) == 1
    assert count_expired(EXPIRED, now=50) == 0


def test_store_save_find_delete(tmp_path):
    store = CookieStore(tmp_path / "cookies")

    cookie = store.save_text(NETSCAPE)
    assert cookie.name == "youtube"
    assert cookie.path.is_file()
    assert cookie.domains == ("youtube.com",)
    store.save_text(INSTAGRAM)

    youtube = store.find_for_url("https://www.youtube.com/watch?v=abc")
    instagram = store.find_for_url("https://www.instagram.com/reel/xyz/")
    assert youtube is not None
    assert instagram is not None
    assert youtube.name == "youtube.txt"
    assert instagram.name == "instagram.txt"

    # دامنهٔ نامرتبط نباید کوکی بگیرد
    assert store.find_for_url("https://example.com/file.mp4") is None

    names = {item.name for item in store.list_files()}
    assert {"youtube", "instagram"} <= names

    assert store.delete("youtube") is True
    assert store.get("youtube") is None
    assert store.delete("youtube") is False


def test_store_problems_detect_expired(tmp_path):
    store = CookieStore(tmp_path)
    cookie = store.save_text(EXPIRED, name="youtube")
    assert store.problems(cookie) == []

    only_expired = (
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t100\tOLD\tabc\n"
    )
    expired = store.save_text(only_expired, name="old")
    assert "all cookies expired" in store.problems(expired)


def test_save_falls_back_to_inferred_name(tmp_path):
    store = CookieStore(tmp_path)
    cookie = store.save("", NETSCAPE)
    assert cookie.name in ("youtube", "instagram")


def test_describe_contains_name_and_size(tmp_path):
    store = CookieStore(tmp_path)
    cookie = store.save_text(NETSCAPE, name="youtube")
    body = store.describe(cookie)
    assert "youtube" in body
    assert "KB" in body


def test_age_days(tmp_path, monkeypatch):
    store = CookieStore(tmp_path)
    cookie = store.save_text(NETSCAPE, name="youtube")
    monkeypatch.setattr(time, "time", lambda: cookie.modified + 2 * 86400 + 10)
    assert store.age_days(cookie) == 2
