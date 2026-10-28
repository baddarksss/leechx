"""تست ساخت کپشن و هشتگ‌ها."""
from __future__ import annotations

from app.core.caption import CAPTION_LIMIT, build_caption, hashtags_for


def test_youtube_hashtags():
    tags = hashtags_for("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video")
    assert "#YouTube" in tags
    assert "#Video" in tags


def test_youtube_shorts_hashtag():
    tags = hashtags_for("https://www.youtube.com/shorts/abc123", "video")
    assert "#YouTube" in tags
    assert "#Shorts" in tags


def test_instagram_reels_hashtag():
    tags = hashtags_for("https://www.instagram.com/reel/abc123/", "video")
    assert "#Instagram" in tags
    assert "#Reels" in tags


def test_audio_and_document_kind_tags():
    assert "#Audio" in hashtags_for("https://youtu.be/abc", "audio")
    assert "#File" in hashtags_for("https://youtu.be/abc", "document")


def test_unknown_site_uses_domain():
    tags = hashtags_for("https://media.example.org/video.mp4", "video")
    assert "#example" in tags
    assert "#Video" in tags


def test_tags_are_unique_and_extra_is_supported():
    tags = hashtags_for("https://youtu.be/abc", "video", extra="Shorts, #Music")
    assert tags.count("#Video") == 1
    assert "#Shorts" in tags
    assert "#Music" in tags


def test_caption_includes_title_source_and_tags():
    body = build_caption("My <Clip>", "https://youtu.be/abc", "video")
    assert "<b>My &lt;Clip&gt;</b>" in body
    assert 'href="https://youtu.be/abc"' in body
    assert "#YouTube" in body
    assert "#Video" in body


def test_caption_without_source():
    body = build_caption("Only title", "", "audio")
    assert "<b>Only title</b>" in body
    assert "#Audio" in body
    assert "Source" not in body


def test_long_caption_is_truncated():
    body = build_caption("x" * 5000, "https://www.youtube.com/watch?v=abc", "video")
    assert len(body) <= CAPTION_LIMIT
    assert "#Video" in body


def test_long_caption_drops_source_before_tags():
    body = build_caption("y" * 5000, "https://youtu.be/" + "a" * 900, "video")
    assert len(body) <= CAPTION_LIMIT
    assert "#YouTube" in body
