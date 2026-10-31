"""دیتابیس سایت‌های پشتیبانی‌شده.

منبع حقیقت همان اکسترکتورهای yt-dlp است (بیش از ۱۸۰۰ سایت). این ماژول
یک ایندکس قابل‌جست‌وجو می‌سازد تا کاربر بتواند ببیند چه سایت‌هایی پشتیبانی
می‌شوند و ادمین هم آمار داشته باشد.

برای اضافه‌کردن سایت جدید لازم نیست چیزی اینجا عوض شود — کافی است نسخهٔ
yt-dlp را آپدیت کنی (``pip install -U yt-dlp``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger("leechx.sites")

POPULAR: list[tuple[str, str]] = [
    ("YouTube", "youtube.com"),
    ("Instagram", "instagram.com"),
    ("TikTok", "tiktok.com"),
    ("X / Twitter", "x.com"),
    ("Facebook", "facebook.com"),
    ("SoundCloud", "soundcloud.com"),
    ("Vimeo", "vimeo.com"),
    ("Reddit", "reddit.com"),
    ("Twitch", "twitch.tv"),
    ("Dailymotion", "dailymotion.com"),
    ("Pinterest", "pinterest.com"),
    ("Aparat", "aparat.com"),
    ("Bilibili", "bilibili.com"),
    ("LinkedIn", "linkedin.com"),
    ("Snapchat", "snapchat.com"),
]

# نام اکسترکتورهایی که محتوای بزرگسال دارند (برای برچسب و فیلتر اختیاری)
NSFW_EXTRACTORS: set[str] = {
    "pornhub", "xvideos", "xhamster", "xnxx", "redtube", "youporn", "spankbang",
    "eporner", "txxx", "hclips", "tube8", "motherless", "beeg", "porntube",
    "drtuber", "sunporno", "sexu", "pornerbros", "empflix", "gotporn", "xtube",
    "pornhd", "pornhubpremium", "brazzers", "bangbros", "fakehub", "kink",
    "chaturbate", "cam4", "stripchat", "bongacams", "livejasmin", "myfreecams",
    "hanime", "hentaihaven", "nhentai", "rule34", "e621", "gelbooru", "danbooru",
}

NSFW_HOST_WORDS = ("porn", "xxx", "sex", "nude", "hentai", "adult", "cam4", "onlyfans", "erotic")

# دسته‌های gallery-dl که فقط محتوای بزرگسال دارند (برای فیلتر اختیاری NSFW).
# pixiv/artstation و مشابه‌ها عمداً نیستند چون محتوای سالم هم دارند.
GALLERY_NSFW: set[str] = {
    "e621", "danbooru", "gelbooru", "realbooru", "rule34us", "rule34vault",
    "rule34xyz", "sankaku", "sankakucomplex", "exhentai", "nhentai",
    "hentaihere", "imhentai", "myhentaigallery", "hentaicosplays",
    "fapello", "fapachi", "erome", "thefap", "nudostar", "fitnakedgirls",
    "girlsreleased", "poringa", "pornpics", "motherless", "nsfwalbum",
    "imagefap", "sexcom", "xasiat", "vipergirls",
}


@dataclass(frozen=True)
class SiteEntry:
    name: str
    label: str
    description: str
    nsfw: bool


class SiteIndex:
    def __init__(self) -> None:
        self._entries: list[SiteEntry] = []
        self._classes: list = []
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def build(self, force: bool = False) -> None:
        """ایندکس را می‌سازد.

        ``force=True`` باعث بازسازی حتی پس از اولین ساخت می‌شود؛ لازم است وقتی
        نسخهٔ yt-dlp در همان فرآیند عوض می‌شود (دکمهٔ بروزرسانی) تا فهرست
        سایت‌ها کهنه نماند.
        """
        if self._loaded and not force:
            return
        try:
            from yt_dlp.extractor import gen_extractor_classes

            classes = []
            entries = []
            for cls in gen_extractor_classes():
                name = (getattr(cls, "IE_NAME", "") or "").lower()
                if not name or name == "generic":
                    continue
                label = name
                desc = (getattr(cls, "IE_DESC", "") or "").strip()
                nsfw = name in NSFW_EXTRACTORS or any(w in name for w in NSFW_HOST_WORDS)
                classes.append(cls)
                entries.append(
                    SiteEntry(
                        name=name,
                        label=str(label)[:60],
                        description=str(desc)[:120],
                        nsfw=nsfw,
                    )
                )
            self._classes = classes
            self._entries = entries
            self._loaded = True
            log.info("site index built: %d extractors", len(entries))
        except Exception:  # noqa: BLE001 — نبودِ yt-dlp نباید ربات را بخواباند
            log.exception("failed to build site index")

    # ── تشخیص ───────────────────────────────────────────────
    def match(self, url: str) -> SiteEntry | None:
        if not self._loaded:
            self.build()
        found: list[SiteEntry] = []
        for cls, entry in zip(self._classes, self._entries, strict=False):
            try:
                if cls.suitable(url):
                    found.append(entry)
            except Exception:  # noqa: BLE001
                continue
        if not found:
            return None
        # اکسترکتور اصلی را ترجیح می‌دهیم (نه زیراکسترکتورهایی مثل youtube:tab)
        found.sort(key=lambda e: (":" in e.name, len(e.name)))
        return found[0]

    def is_nsfw_url(self, url: str) -> bool:
        entry = self.match(url)
        if entry is not None:
            return entry.nsfw
        try:
            from app.services import gallery

            category = gallery.extractor_name(url)
        except Exception:  # noqa: BLE001 — تشخیص نباید لینک را بشکند
            category = ""
        if category and category in GALLERY_NSFW:
            return True
        host = (url or "").lower()
        return any(word in host for word in NSFW_HOST_WORDS)

    # ── آمار / جست‌وجو ─────────────────────────────────────
    @property
    def count(self) -> int:
        if not self._loaded:
            self.build()
        return len(self._entries)

    def search(self, query: str, limit: int = 25, include_nsfw: bool = True) -> list[SiteEntry]:
        if not self._loaded:
            self.build()
        q = (query or "").strip().lower()
        results: list[SiteEntry] = []
        for entry in self._entries:
            if not include_nsfw and entry.nsfw:
                continue
            if not q or q in entry.name or q in entry.label.lower() or q in entry.description.lower():
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def popular(self, include_nsfw: bool = True) -> list[str]:
        if not self._loaded:
            self.build()
        names = {e.name for e in self._entries if include_nsfw or not e.nsfw}
        lines = []
        for label, domain in POPULAR:
            key = domain.split(".")[0]
            if key in names or key.replace("x", "") in names:
                lines.append(f"• {label} — <code>{domain}</code>")
        if include_nsfw:
            adult = [e for e in self._entries if e.nsfw][:5]
            if adult:
                lines.append("• 🔞 " + "، ".join(f"<code>{e.name}</code>" for e in adult))
        return "\n".join(lines)


sites = SiteIndex()
