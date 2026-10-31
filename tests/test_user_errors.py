"""پیام خطای کاربر: بدون لینک داخلی، و بازنویسی لینک‌های embed-only."""
from __future__ import annotations

from app.core import errors, text
from app.services.downloader import extractor_url


def test_public_reason_strips_links_and_collapses_whitespace():
    raw = (
        "ERROR: [Eporner] 09fBSkYy45O: Unable to extract hash; please report "
        "this issue on https://github.com/yt-dlp/yt-dlp/issues?q= , thanks"
    )
    clean = errors.public_reason(raw)
    assert "http" not in clean.lower()
    assert "github" not in clean.lower()
    assert "Eporner" in clean
    assert "\n" not in clean


def test_unsupported_message_is_generic_in_every_language():
    for lang in text.LANGS:
        msg = text.t(lang, "unsupported")
        assert "{reason}" not in msg
        assert "http" not in msg.lower()
        assert "github" not in msg.lower()
        assert text.t(lang, "nsfw_blocked").strip()


def test_eporner_video_url_uses_embed_endpoint():
    url = "https://www.eporner.com/video-09fBSkYy45O/woman-anal-foot-fucking/"
    assert extractor_url(url) == "https://www.eporner.com/embed/09fBSkYy45O/"


def test_extractor_url_keeps_other_urls_untouched():
    url = "https://example.com/watch?v=abc"
    assert extractor_url(url) == url
