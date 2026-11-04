"""Conservative source classification for social thumbnails and shared caching."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlsplit

SOCIAL_DOMAINS = (
    "youtube.com", "youtu.be",
    "instagram.com", "instagr.am", "cdninstagram.com",
    "tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "tiktokcdn.com",
    "twitter.com", "x.com", "t.co",
    "facebook.com", "fb.com", "fb.watch",
    "reddit.com", "v.redd.it", "redditmedia.com",
    "pinterest.com", "pin.it",
    "vimeo.com", "dailymotion.com", "twitch.tv", "soundcloud.com",
    "snapchat.com", "linkedin.com", "threads.net",
    "vk.com", "vk.ru", "bilibili.com", "b23.tv", "aparat.com",
)

SOCIAL_EXTRACTORS = (
    "youtube", "instagram", "tiktok", "twitter", "facebook", "reddit",
    "pinterest", "vimeo", "dailymotion", "twitch", "soundcloud", "snapchat",
    "linkedin", "threads", "vk", "bilibili", "aparat",
)

# Allow cross-user reuse only on well-known public platforms. Even there, a
# cookie, NSFW marker, URL credential, or token-like query disables sharing.
PUBLIC_CACHE_DOMAINS = SOCIAL_DOMAINS
PUBLIC_CACHE_EXTRACTORS = SOCIAL_EXTRACTORS
_PRIVATE_QUERY_MARKERS = (
    "token", "auth", "secret", "session", "signature", "credential", "cookie",
    "password", "passwd", "private", "jwt", "apikey", "api_key", "dtsg",
)
_PRIVATE_QUERY_NAMES = {
    "key", "sig", "expires", "expire", "exp", "hdnea", "oh", "oe", "__gda__",
}


def _host_matches(host: str, domains: tuple[str, ...]) -> bool:
    host = (host or "").rstrip(".").casefold()
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _extractor_matches(extractor: str, names: tuple[str, ...]) -> bool:
    key = re.sub(r"[^a-z0-9]+", "", (extractor or "").casefold())
    return any(key.startswith(name.replace("_", "")) for name in names)


def is_social_source(url: str, extractor: str = "") -> bool:
    """Whether a video is from a social/video-sharing platform."""
    try:
        host = urlsplit(url or "").hostname or ""
    except ValueError:
        host = ""
    return _host_matches(host, SOCIAL_DOMAINS) or _extractor_matches(
        extractor, SOCIAL_EXTRACTORS
    )


def public_cache_eligible(
    url: str,
    extractor: str = "",
    *,
    has_cookie: bool = False,
    nsfw: bool = False,
    allow_any_host: bool = False,
    allow_nsfw: bool = False,
) -> bool:
    """Fail closed unless a source is public and unauthenticated.

    Default policy shares only well-known social platforms and never adult media.
    The admin toggle ``cache_cross_user`` widens this to every public, cookie-free
    source (``allow_any_host``) including NSFW (``allow_nsfw``); signed/tokenised
    or credential-bearing URLs and cookie sources are still never shared.
    """
    if has_cookie:
        return False
    if nsfw and not allow_nsfw:
        return False
    try:
        parts = urlsplit(url or "")
        host = parts.hostname or ""
        if parts.scheme.casefold() not in {"http", "https"} or not host:
            return False
        if parts.username is not None or parts.password is not None:
            return False
    except ValueError:
        return False

    if not allow_any_host and not (
        _host_matches(host, PUBLIC_CACHE_DOMAINS)
        or _extractor_matches(extractor, PUBLIC_CACHE_EXTRACTORS)
    ):
        return False

    for name, _value in parse_qsl(parts.query, keep_blank_values=True):
        normalized = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
        if normalized in _PRIVATE_QUERY_NAMES or any(
            marker in normalized for marker in _PRIVATE_QUERY_MARKERS
        ):
            return False
    fragment = (parts.fragment or "").casefold()
    if any(marker in fragment for marker in _PRIVATE_QUERY_MARKERS):
        return False
    return True
