"""Conservative sharing and social-source policy tests."""
from __future__ import annotations

from app.services.source_policy import is_social_source, public_cache_eligible


def test_social_platforms_are_classified_for_thumbnail_choices():
    assert is_social_source("https://youtu.be/abc")
    assert is_social_source("https://www.instagram.com/reel/abc/")
    assert is_social_source("https://vm.tiktok.com/abc/")
    assert is_social_source("https://v.redd.it/abc", "Reddit")
    assert not is_social_source("https://example.org/video.mp4", "Generic")
    assert not is_social_source("https://www.pornhub.com/view_video.php")


def test_only_public_cookie_free_non_nsfw_sources_are_shareable():
    assert public_cache_eligible("https://www.youtube.com/watch?v=public")
    assert public_cache_eligible("https://www.instagram.com/reel/public/", "Instagram")
    # X uses `s=20` as a public share/tracking parameter; signature-style
    # parameters on Instagram's CDN are private and must not be shared.
    assert public_cache_eligible("https://x.com/user/status/1?s=20", "Twitter")
    assert not public_cache_eligible(
        "https://cdninstagram.com/image.jpg?oh=signed&oe=1234", "Instagram"
    )
    assert not public_cache_eligible(
        "https://www.youtube.com/watch?v=public", has_cookie=True
    )
    assert not public_cache_eligible(
        "https://www.youtube.com/watch?v=public", nsfw=True
    )
    assert not public_cache_eligible(
        "https://www.youtube.com/watch?v=public&access_token=secret"
    )
    assert not public_cache_eligible("https://user:pass@youtube.com/watch?v=public")
    assert not public_cache_eligible("https://example.org/video.mp4", "Generic")
    assert not public_cache_eligible("magnet:?xt=urn:btih:abc", "")
