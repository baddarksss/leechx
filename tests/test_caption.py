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


def test_caption_is_the_title_linked_to_the_source():
    body = build_caption("My <Clip>", "https://youtu.be/abc", "video")
    assert body == '<a href="https://youtu.be/abc"><b>My &lt;Clip&gt;</b></a>'
    # هیچ متن اضافه‌ای (برچسب منبع یا هشتگ) نباید در کپشن باشد
    assert "Source" not in body
    assert "#" not in body


def test_caption_without_source_is_just_the_title():
    assert build_caption("Only title", "", "audio") == "<b>Only title</b>"


def test_caption_escapes_the_url_inside_href():
    body = build_caption("t", "https://e.com/v?x=1&y=2")
    assert 'href="https://e.com/v?x=1&amp;y=2"' in body


def test_caption_without_title_falls_back_to_the_domain():
    body = build_caption("", "https://www.pornhub.com/view_video.php?viewkey=x")
    assert "<b>pornhub.com</b>" in body


def test_long_caption_stays_within_the_limit_and_keeps_valid_html():
    body = build_caption("x" * 5000, "https://www.youtube.com/watch?v=abc", "video")
    assert len(body) <= CAPTION_LIMIT
    assert body.startswith('<a href="https://www.youtube.com/watch?v=abc"><b>')
    assert body.endswith("</b></a>")
    assert body.count("</b></a>") == 1


def test_caption_truncates_after_escaping_without_breaking_entities():
    body = build_caption("&" * 2000, "https://youtu.be/abc")
    assert len(body) <= CAPTION_LIMIT
    assert body.endswith("</b></a>")
    assert "&amp;" in body
    assert "&am…" not in body  # entity نصفه‌کاره ساخته نمی‌شود


def test_caption_drops_the_link_when_the_url_is_too_long():
    body = build_caption("Title", "https://youtu.be/" + "a" * 1000)
    assert body == "<b>Title</b>"
    assert "href" not in body
