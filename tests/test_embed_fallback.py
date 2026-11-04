"""Embedded-player fallback helpers (no network)."""
from __future__ import annotations

from app.services.downloader import _looks_unsupported, embed_candidates


def test_embed_candidates_absolutize_and_dedupe():
    html = (
        '<iframe src="/e/abc"></iframe>'
        '<iframe data-src="https://player.example/e/1"></iframe>'
        '<iframe data-litespeed-src="//cdn.example/e/2"></iframe>'
        '<iframe src="/e/abc"></iframe>'
    )
    got = embed_candidates(html, "https://site.test/page")
    assert got == [
        "https://site.test/e/abc",
        "https://player.example/e/1",
        "https://cdn.example/e/2",
    ]


def test_embed_candidates_skip_ads_and_non_http():
    html = (
        '<iframe src="https://doubleclick.net/x"></iframe>'
        '<iframe src="https://pagead2.googlesyndication.com/y"></iframe>'
        '<iframe src="about:blank"></iframe>'
        '<iframe src="https://good.example/e/9"></iframe>'
    )
    assert embed_candidates(html, "https://site.test/") == ["https://good.example/e/9"]


def test_looks_unsupported_markers():
    assert _looks_unsupported("Unsupported URL")
    assert _looks_unsupported("No video formats found")
    assert not _looks_unsupported("HTTP Error 403")
    assert not _looks_unsupported(None)
