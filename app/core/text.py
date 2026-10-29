"""متن‌های چندزبانه (فارسی/انگلیسی/روسی) — تنها منبع رشته‌های کاربری.

برای اضافه‌کردن زبان جدید:
1. یک دیکشنری دیگر بنویس (همهٔ کلیدهای ``FA`` را داشته باشد).
2. آن را در ``LANGS`` و ``MESSAGES`` اضافه کن.
3. در ``FALLBACK`` زنجیرهٔ جایگزینی را تعریف کن.

تست ``tests/test_smoke.py`` کامل‌بودن کلیدها و یکسان‌بودن placeholderها را
بین زبان‌ها بررسی می‌کند.
"""
from __future__ import annotations

LANGS: dict[str, str] = {
    "fa": "🇮🇷 فارسی",
    "en": "🇬🇧 English",
    "ru": "🇷🇺 Русский",
}
LANG_ORDER: tuple[str, ...] = ("fa", "en", "ru")
DEFAULT_LANG = "fa"

# زنجیرهٔ جایگزینی: اگر کلیدی در زبان مقصد نبود، از زبان بعدی استفاده می‌شود.
FALLBACK: dict[str, tuple[str, ...]] = {
    "fa": ("fa",),
    "en": ("en", "fa"),
    "ru": ("ru", "en", "fa"),
}


def normalize_lang(code: str | None) -> str:
    """کد زبان تلگرام/کاربر را به یکی از زبان‌های پشتیبانی‌شده تبدیل می‌کند."""
    raw = (code or "").strip().lower().replace("_", "-")
    if raw.startswith("fa") or raw.startswith("per") or raw.startswith("ir"):
        return "fa"
    if raw.startswith("ru"):
        return "ru"
    if raw.startswith("en"):
        return "en"
    return DEFAULT_LANG


def lang_from_telegram(code: str | None) -> str:
    """زبان پیش‌فرض کاربر جدید بر اساس زبان کلاینت تلگرام."""
    raw = (code or "").strip().lower().replace("_", "-")
    if raw.startswith("fa"):
        return "fa"
    if raw.startswith("ru"):
        return "ru"
    return "en"

FA: dict[str, str] = {
    # ── عمومی ──
    "start": (
        "<b>👋 خوش آمدی به LeechX</b>\n\n"
        "یک <b>لینک</b> بفرست تا کیفیت‌های موجود را ببینی و دانلود کنی، "
        "یا یک <b>فایل</b> بفرست تا لینک مستقیم بگیری.\n\n"
        "• یوتیوب، اینستاگرام، تیک‌تاک، توییتر، ساندکلاد و هزاران سایت دیگر\n"
        "• فایل بعد از آپلود از سرور پاک می‌شود\n"
        "• لینک مستقیم به‌طور پیش‌فرض <b>{ttl} ساعت</b> معتبر است"
    ),
    "help": (
        "<b>📖 راهنما</b>\n\n"
        "<b>۱) دانلود از لینک</b>\n"
        "لینک را بفرست → کیفیت را انتخاب کن → فایل در تلگرام آپلود می‌شود.\n\n"
        "<b>۲) ساخت لینک مستقیم</b>\n"
        "فایل/ویدیو/موزیک را بفرست → لینک مستقیم با اعتبار {ttl} ساعت می‌گیری.\n\n"
        "<b>نکته‌ها</b>\n"
        "• لینک مستقیم (مثل <code>.mp4</code>) بدون انتخاب کیفیت دانلود می‌شود.\n"
        "• حداکثر حجم: {max_mb} مگابایت.\n"
        "• فایل‌های ساخته‌شده بعد از انقضا خودکار پاک می‌شوند.\n\n"
        "<b>دستورها</b>\n"
        "/start شروع • /help راهنما • /sites لیست سایت‌ها • "
        "/me وضعیت من • /links لینک‌های من • /cancel لغو"
    ),
    "send_link_or_file": "🔗 یک لینک یا فایل بفرست.",
    "probing": "🔍 در حال بررسی لینک…",
    "choose_quality": "<b>{title}</b>\n\n🎬 کیفیت مورد نظر را انتخاب کن:",
    "video_btn": "🎬 {label}",
    "audio_btn": "🎵 {label}",
    "quality_title": "<b>{title}</b>",
    "cancel_btn": "✖️ لغو",
    "my_links_btn": "🔗 لینک‌های من",
    "file_link_progress": "📥 دریافت فایل از تلگرام {pct}%\n{bar}\n{size}",
    "file_link_wait": "📥 دریافت فایل از تلگرام… حجم دریافت‌شده: {size}",
    "upload_wait": "⏳ منتظر تأیید نهایی تلگرام…",
    "canceled": "✖️ لغو شد.",
    "cancel_nothing": "ℹ️ هیچ عملیات یا فرم فعالی برای لغو وجود ندارد.",
    "not_found": "🔎 فایل یا صفحه پیدا نشد (۴۰۴). لینک را بررسی کن.",
    "access_denied": "🔒 دسترسی به این منبع مجاز نیست ({reason}).",
    "download_timeout": "⏱ ارتباط با منبع به پایان مهلت رسید. دوباره تلاش کن.",
    "incomplete_download": "⚠️ دانلود ناقص بود؛ فایل ناقص تحویل داده نشد. {reason}",
    "canceled_btn": "لغو شد",
    "queued": "🕒 در صف… (نفر {pos})",
    "downloading": "⬇️ دانلود {pct}%\n{bar}\n{size} • {speed} • {eta}",
    "uploading": "⬆️ آپلود {pct}%\n{bar}\n{size}",
    "processing": "⚙️ در حال پردازش…",
    "done": "✅ آماده شد",
    "failed": "❌ خطا: {reason}",
    "expired_draft": "⌛ این انتخاب منقضی شده. لینک را دوباره بفرست.",
    "too_many_active": "⏳ یک کار دیگرت هنوز تمام نشده. کمی صبر کن.",
    "rate_limited": "🐢 کمی آهسته‌تر! {seconds} ثانیه صبر کن.",
    "banned": "🚫 دسترسی شما به ربات بسته شده است.",
    "maintenance": "🛠 ربات موقتاً در حال تعمیر است. بعداً سراغت می‌آییم.",
    "issue_reported": "📨 این مورد برای بررسی به ادمین ارسال شد؛ در اولین فرصت بررسی می‌شود.",
    "contact_prompt": (
        "✉️ پیامت برای ادمین را بنویس و بفرست.\n"
        "می‌توانی مشکل، پیشنهاد یا درخواستت را کامل توضیح بدهی."
    ),
    "contact_sent": "✅ پیامت به ادمین رسید. ممنون که اطلاع دادی!",
    "contact_failed": "❌ ارسال پیام ناموفق بود. کمی بعد دوباره تلاش کن.",
    "owner_claimed": (
        "👑 تو اولین کاربر این ربات هستی؛ به‌عنوان <b>مالک</b> شناخته شدی.\n"
        "از این به بعد پنل ادمین در منوی اصلی برایت نمایش داده می‌شود."
    ),
    "quota_exceeded": "📉 سهمیهٔ امروزت تمام شد. فردا دوباره تلاش کن.",
    "no_url": "🤔 لینکی پیدا نکردم. یک لینک معتبر بفرست.",
    "invalid_url": "⚠️ لینک نامعتبر است.",
    "unsupported": "😕 این لینک پشتیبانی نمی‌شود: {reason}",
    "too_big": "📦 حجم فایل ({size}) از حد مجاز ({max}) بیشتر است.",
    "not_media": "📄 این فایل ویدیو/موزیک نیست.",
    "live_unsupported": "🔴 پخش زنده پشتیبانی نمی‌شود.",
    "playlist_detected": "📚 این لینک یک پلی‌لیست است؛ فقط مورد اول دانلود می‌شود.",

    # ── لینک مستقیم ──
    "direct_start": "🔗 لینک مستقیم است — بدون انتخاب کیفیت دانلود می‌شود…",
    "file_received": "📥 فایل دریافت شد. در حال آماده‌سازی لینک…",
    "link_ready": (
        "<b>✅ لینک مستقیم آماده است</b>\n\n"
        "<code>{url}</code>\n\n"
        "📄 {name}\n📦 {size}\n⏳ اعتبار: <b>{ttl} ساعت</b> (تا {expires})\n\n"
        "لینک را کپی کن یا روی دکمه بزن."
    ),
    "open_link_btn": "🌐 باز کردن لینک",
    "copy_hint": "⬆️ برای کپی، روی لینک بالا بزن.",
    "file_too_big_link": "📦 فایل بزرگ‌تر از حد مجاز برای لینک مستقیم است ({size} > {max}).",

    # ── انتخاب نحوهٔ تحویل ──
    "delivery_panel": (
        "<b>📥 فایل پیدا شد</b>\n"
        "<b>{title}</b>\n\n"
        "🎞 کیفیت: <b>{quality}</b>\n"
        "📦 حجم: {size}\n"
        "🏷 نام فایل: <code>{name}</code>\n\n"
        "<b>چطور می‌خواهی فایل را دریافت کنی؟</b>\n\n"
        "🎬 <b>ارسال به‌صورت ویدیو</b>\n"
        "ویدیو همین‌جا در تلگرام ارسال می‌شود و می‌توانی پخشش کنی. "
        "اگر فرمت قابل‌پخش نباشد، به‌صورت فایل فرستاده می‌شود.\n\n"
        "📁 <b>ارسال به‌صورت فایل</b>\n"
        "فایل در همین چت به شکل سند (Document) ارسال می‌شود؛ "
        "بدون فشرده‌سازی دوباره توسط تلگرام.\n\n"
        "🔗 <b>ساخت لینک دانلود</b>\n"
        "فایل روی سرور ذخیره می‌شود و یک لینک قابل کپی و اشتراک‌گذاری "
        "با اعتبار <b>{ttl} ساعت</b> می‌گیری.\n\n"
        "✏️ برای عوض‌کردن نام فایل، «تغییر نام» را بزن.\n"
        "👇 با لمس هر یک از سه گزینهٔ اول، عملیات شروع می‌شود."
    ),
    "quality_auto": "بهترین کیفیت موجود (خودکار)",
    "quality_original": "همان کیفیت فایل اصلی",
    "size_unknown": "فعلاً نامشخص؛ بعد از دانلود معلوم می‌شود",
    "deliver_video_btn": "🎬 ارسال ویدیو در تلگرام",
    "deliver_doc_btn": "📁 ارسال فایل در تلگرام",
    "deliver_link_btn": "🔗 ساخت لینک دانلود مستقیم",
    "deliver_rename_btn": "✏️ تغییر نام فایل",
    "deliver_back_btn": "↩️ تغییر کیفیت",
    "rename_prompt": "✏️ نام جدید فایل را بفرست (پسوند لازم نیست):\nنام فعلی: <code>{name}</code>",
    "rename_done": "✅ نام ذخیره شد: <b>{name}</b>",
    "rename_bad": "❌ نام معتبر نیست؛ یک نام کوتاه بفرست.",

    # ── دکمه‌های منو ──
    "btn_help": "📖 راهنما",
    "btn_status": "📊 وضعیت من",
    "btn_sites": "🌐 سایت‌های پشتیبانی",
    "btn_settings": "⚙️ تنظیمات",
    "btn_contact": "✉️ ارتباط با ادمین",
    "btn_admin": "👑 پنل ادمین",
    "sec_stats": "📊 آمار",
    "sec_users": "👥 کاربران",
    "sec_settings": "⚙️ تنظیمات",
    "sec_groups": "🗂 گروه",
    "sec_deploy": "🚀 دیپلوی",
    "sec_debug": "🩺 عیب‌یابی",
    "sec_cookies": "🍪 کوکی‌ها",
    "sec_cancel": "✖️ لغو کارها",
    "btn_back": "↩️ بازگشت",
    "btn_close": "✖️ بستن",
    "btn_lang": "🌍 زبان",
    "btn_admin_stats": "📈 آمار",
    "btn_admin_jobs": "🧾 کارهای اخیر",
    "btn_admin_admins": "👥 ادمین‌ها",
    "btn_admin_settings": "⚙️ تنظیمات ربات",
    "btn_admin_broadcast": "📢 پیام همگانی",
    "btn_admin_users": "🔎 کاربر",
    "btn_admin_ban": "🚫 بن کردن کاربر",
    "btn_admin_cleanup": "🧹 پاک‌سازی",
    "btn_admin_cookies": "🍪 کوکی‌ها",
    "btn_admin_group": "👥 گروه ادمین",
    "btn_admin_reports": "🚨 گزارش‌ها",
    "btn_admin_logs": "🐞 لاگ‌ها",
    "btn_admin_runtime": "🛠 متغیرهای اجرا",
    "btn_admin_group_id": "🔢 تنظیم با آیدی عددی",
    "btn_admin_group_test": "🧪 تست ارسال",
    "btn_admin_group_off": "🗑 حذف گروه",
    "btn_reports_refresh": "🔄 بروزرسانی",
    "btn_report_close": "✅ بستن #{id}",
    "btn_logs_clear": "🗑 پاک کردن لاگ‌ها",
    "admin_cookies": (
        "<b>🍪 فایل‌های کوکی</b>\n\n"
        "تعداد: <b>{count}</b>\n\n{list}\n\n"
        "برای یوتیوب/اینستاگرام یک فایل <code>cookies.txt</code> (Netscape) بفرست."
    ),
    "btn_cookie_add": "➕ افزودن / آپلود",
    "btn_cookie_test": "🧪 بررسی",
    "cookie_add_prompt": (
        "📄 فایل <code>cookies.txt</code> را بفرست یا متن Netscape را پیست کن.\n\n"
        "راهنمای ساخت کوکی: <code>docs/COOKIES.md</code>"
    ),
    "cookie_saved": "✅ کوکی ذخیره شد: <b>{name}</b>\n🌐 دامنه‌ها: <code>{domains}</code>",
    "cookie_bad": "❌ فایل کوکی معتبر نیست: {reason}",
    "cookie_deleted": "🗑 کوکی حذف شد: <b>{name}</b>",
    "cookie_missing": "❌ چنین فایل کوکی‌ای وجود ندارد.",
    "cookie_test_result": "<b>🧪 نتیجهٔ بررسی کوکی‌ها</b>\n\n{list}",
    "cookie_ok": "✅ سالم",
    "cookie_problem": "⚠️ {reason}",
    "cookie_empty": "—",
    "cookie_text_only": "📄 فایل <code>cookies.txt</code> را بفرست یا متن Netscape را پیست کن.",
    "btn_admin_add": "➕ افزودن ادمین",
    "btn_ban": "🚫 مسدود کردن",
    "btn_unban": "♻️ رفع مسدودی",
    "set_ttl": "⏳ اعتبار لینک: {v} ساعت",
    "set_upload": "📦 سقف آپلود: {v}MB",
    "set_link": "🔗 سقف فایل لینک: {v}MB",
    "set_rate": "🐢 فاصلهٔ درخواست: {v}s",
    "set_quota": "📉 سهمیهٔ روزانه: {v}",
    "set_maintenance": "🛠 حالت تعمیر {flag}",
    "set_nsfw": "🔞 سایت‌های بزرگسال {flag}",
    "admin_limit_reached": "⛔️ سقف ادمین‌ها ({max}) پر است.",
    "admin_env_admin": "این کاربر در ADMIN_IDS تنظیمات است؛ از env حذفش کن.",

    # ── وضعیت ──
    "status": (
        "<b>📊 وضعیت شما</b>\n\n"
        "🆔 شناسه: <code>{uid}</code>\n"
        "⬇️ دانلودها: <b>{downloads}</b>\n"
        "📅 عضو از: {joined}\n"
        "👑 ادمین: {admin}\n"
        "🤖 نسخه: <b>v{version}</b>"
    ),
    "yes": "بله",
    "no": "خیر",

    # ── سایت‌ها ──
    "sites_title": (
        "<b>🌐 سایت‌های پشتیبانی‌شده</b>\n\n"
        "تعداد اکسترکتورهای فعال: <b>{count}</b>\n"
        "برای جست‌وجو: <code>/sites اینستاگرام</code>\n\n"
        "<b>محبوب:</b>\n{popular}"
    ),
    "sites_search": "<b>🔍 نتیجهٔ «{q}»</b> ({count} مورد)\n\n{list}",
    "sites_none": "چیزی پیدا نشد.",

    # ── ادمین ──
    "admin_only": "⛔️ این بخش فقط برای ادمین‌هاست.",
    "admin_panel": "<b>👑 پنل ادمین</b>\n\nیکی از بخش‌ها را انتخاب کن:",
    "admin_stats": (
        "<b>📈 آمار ربات</b>\n\n"
        "👥 کاربران کل: <b>{users}</b>\n"
        "🟢 کاربران فعال (۷ روز): <b>{active_users}</b>\n"
        "🚫 مسدودشده: <b>{banned}</b>\n"
        "⬆️ در حال آپلود: <b>{uploading}</b>\n"
        "🔗 لینک مستقیم فعال: <b>{active_links}</b>\n"
        "🚨 گزارش باز: <b>{reports}</b>\n"
        "🛡 ادمین‌ها: <b>{admins}</b>\n"
        "📥 کارهای ۲۴ ساعت: <b>{jobs}</b> (✅ {done} / ❌ {failed})\n"
        "⚡️ کارهای فعال: <b>{active}</b>\n"
        "💾 فضای دیسک: <b>{disk}</b>\n"
        "⏱ آپتایم: <b>{uptime}</b>\n"
        "🤖 نسخه: <b>v{version}</b>"
    ),
    "admin_jobs": "<b>🧾 کارهای اخیر</b>\n\n{list}",
    "admin_admins": (
        "<b>👥 ادمین‌ها</b>\n\n"
        "👑 مالک: {owners}\n"
        "🛡 ادمین‌های اضافه:\n{admins}"
    ),
    "admin_add_prompt": "شناسهٔ عددی یا یوزرنیم کاربر را بفرست:",
    "admin_add_ok": "✅ ادمین اضافه شد: <code>{uid}</code>",
    "admin_add_fail": "❌ نشد. کاربر را پیدا نکردم (اول باید /start بزند).",
    "admin_remove_ok": "🗑 ادمین حذف شد: <code>{uid}</code>",
    "admin_remove_fail": "❌ این کاربر ادمین نیست.",
    "admin_owner_immutable": "⛔️ مالک را نمی‌توان حذف کرد.",
    "admin_settings": (
        "<b>⚙️ تنظیمات ربات</b>\n\n"
        "⏳ اعتبار لینک: <b>{ttl} ساعت</b>\n"
        "📦 حداکثر آپلود: <b>{max_upload}MB</b>\n"
        "🔗 حداکثر فایل لینک: <b>{max_link}MB</b>\n"
        "🐢 فاصلهٔ درخواست: <b>{rate}s</b>\n"
        "⛔️ حالت تعمیر: <b>{maintenance}</b>\n"
        "🔞 سایت‌های بزرگسال: <b>{nsfw}</b>"
    ),
    "admin_set_value": "مقدار جدید برای <b>{label}</b> را بفرست:",
    "admin_set_ok": "✅ ذخیره شد: {label} = <b>{value}</b>",
    "admin_bad_value": "❌ مقدار نامعتبر.",
    "admin_broadcast_prompt": "متن پیام همگانی را بفرست:",
    "admin_broadcast_started": "📢 ارسال به {count} کاربر شروع شد…",
    "admin_broadcast_done": "✅ پیام همگانی تمام شد.\nموفق: {ok} • ناموفق: {fail}",
    "admin_user_prompt": "شناسهٔ کاربر را بفرست:",
    "admin_user_info": (
        "<b>🔎 کاربر</b>\n\n"
        "🆔 <code>{uid}</code>\n👤 {name}\n🔗 @{username}\n"
        "📥 دانلود: {downloads}\n🚫 مسدود: {banned}\n🛡 ادمین: {admin}\n"
        "📅 عضویت: {joined}"
    ),
    "admin_cleanup_done": "🧹 پاک‌سازی انجام شد.\nفایل حذف‌شده: {files}\nفضای آزاد‌شده: {size}",
    "admin_ban_prompt": (
        "شناسهٔ عددی، @یوزرنیم یا یک پیام فورواردشده از کاربر را بفرست "
        "تا وضعیت مسدودی‌اش را ببینی."
    ),
    "admin_forward_hint": "💡 می‌توانی پیام کاربر را هم فوروارد کنی.",
    "admin_group_panel": (
        "<b>👥 گروه ادمین</b>\n\n"
        "وضعیت: {status}\n"
        "گروه: <b>{title}</b>\n"
        "شناسه: <code>{chat}</code>\n\n"
        "📥 دانلودها: {downloads}\n"
        "📤 آپلودها: {uploads}\n"
        "🚨 گزارش‌ها: {reports}\n"
        "🐞 لاگ‌ها: {logs}\n\n"
        "{hint}"
    ),
    "admin_group_configured": "✅ تنظیم‌شده",
    "admin_group_not_configured": "❌ تنظیم نشده",
    "admin_group_topic_ok": "✅",
    "admin_group_topic_missing": "—",
    "admin_group_hint_ok": (
        "پیام‌های کاربران، خطاها و اعلان دانلود/آپلود به همین تاپیک‌ها می‌رود."
    ),
    "admin_group_hint_setup": (
        "برای تنظیم: ربات را به گروهی با <b>Topics</b> اضافه کن، ادمینش کن، "
        "بعد داخل گروه دستور <code>/setup</code> را بفرست.\n"
        "یا با دکمهٔ «آیدی عددی» شناسهٔ گروه را دستی وارد کن."
    ),
    "admin_group_prompt": "شناسهٔ عددی گروه (مثل <code>-1001234567890</code>) را بفرست:",
    "admin_group_bad_id": "❌ شناسهٔ گروه نامعتبر است.",
    "admin_group_saved": (
        "✅ گروه ادمین ذخیره شد.\n"
        "تاپیک‌های ساخته‌شده: {created}\n"
        "تاپیک‌های ناموفق: {failed}\n\n"
        "اگر تاپیکی ساخته نشد، مطمئن شو گروه <b>Topics</b> دارد و ربات ادمین است."
    ),
    "admin_group_off_done": "🗑 گروه ادمین حذف شد.",
    "admin_group_test_ok": "✅ پیام تست به گروه ادمین ارسال شد.",
    "admin_group_test_fail": "❌ ارسال نشد؛ تنظیمات گروه و دسترسی ربات را بررسی کن.",
    "setup_private": (
        "این دستور باید <b>داخل گروه</b> فرستاده شود.\n"
        "ربات را به گروه دارای Topics اضافه کن و آنجا <code>/setup</code> بزن."
    ),
    "setup_need_admin": "⛔️ فقط ادمین‌های خود ربات اجازهٔ اتصال گروه گزارش‌ها را دارند.",
    "setup_not_group": "این چت گروه نیست.",
    "setup_done": (
        "✅ گروه ادمین تنظیم شد.\n\n"
        "📥 دانلودها: {downloads}\n📤 آپلودها: {uploads}\n"
        "🚨 گزارش‌ها: {reports}\n🐞 لاگ‌ها: {logs}\n\n"
        "اگر موردی «—» بود، Topics گروه را فعال و ربات را ادمین کن."
    ),
    "admin_reports": "<b>🚨 گزارش‌های باز</b> ({count})\n\n{list}",
    "admin_reports_empty": "گزارش بازی وجود ندارد.",
    "admin_report_item": (
        "{icon} <b>#{id}</b> · {kind} · {when}\n"
        "👤 {name} (@{username}) · <code>{uid}</code>\n{body}"
    ),
    "admin_report_kind_contact": "پیام کاربر",
    "admin_report_kind_unsupported": "سایت مشکل‌دار",
    "admin_report_closed": "✅ گزارش #{id} بسته شد.",
    "admin_report_missing": "❌ چنین گزارشی وجود ندارد.",
    "admin_logs": "<b>🐞 لاگ‌های اخیر</b> ({count})\n\n{list}",
    "admin_logs_empty": "لاگی ثبت نشده است.",
    "admin_logs_cleared": "🗑 {count} لاگ پاک شد.",
    "admin_runtime": (
        "<b>🛠 متغیرهای اجرا</b>\n\n"
        "مقادیر را از همین‌جا وارد کن؛ دیگر لازم نیست به سرور دسترسی داشته باشی.\n"
        "برای تغییر، روی هر مورد بزن.\n\n"
        "⚠️ تغییر آدرس Bot API بعد از ری‌استارت اعمال می‌شود."
    ),
    "admin_runtime_prompt": (
        "مقدار جدید برای <b>{label}</b> را بفرست.\n"
        "برای پاک کردن مقدار، یک <code>-</code> بفرست."
    ),
    "admin_runtime_saved": "✅ ذخیره شد: {label} = <b>{value}</b>",
    "admin_runtime_restart": "ℹ️ این مورد بعد از ری‌استارت ربات اعمال می‌شود.",
    "state_text_only": "✍️ لطفاً پاسخ را به‌صورت متن بفرست.",

    # ── منوی تازه / UI ──
    "btn_kb_close": "⌨️ بستن کیبورد",
    "kb_closed": "⌨️ کیبورد بسته شد. هر وقت خواستی با /start دوباره بازش کن.",
    "settings_panel": (
        "<b>⚙️ تنظیمات</b>\n\n"
        "🌍 زبان: <b>{lang}</b>\n"
        "🤖 نسخه: <b>{version}</b>\n\n"
        "از دکمه‌های زیر استفاده کن:"
    ),
    "lang_title": (
        "<b>🌍 انتخاب زبان</b>\n\n"
        "زبان فعلی: <b>{current}</b>\n\n"
        "Language · Язык · زبان"
    ),
    "lang_saved": "✅ زبان به <b>{lang}</b> تغییر کرد.",
    "version_info": (
        "<b>🤖 LeechX v{version}</b> · {codename}\n"
        "📅 انتشار: {date}\n"
        "🐍 Python: {python}\n"
        "🎬 yt-dlp: {ytdlp}\n"
        "🎞 ffmpeg: {ffmpeg}\n"
        "⏱ آپتایم: {uptime}"
    ),
    "btn_local_api_help": "ℹ️ Local Bot API چیست؟",
    "local_api_help": (
        "<b>ℹ️ Local Bot API Server چیست؟</b>\n\n"
        "تلگرام روی سرور عمومی خودش سقف دارد: دانلود فایل تا <b>۲۰ مگابایت</b> و "
        "آپلود تا <b>۵۰ مگابایت</b>. اگر سرور Bot API را خودت روی همان ماشین ربات "
        "اجرا کنی، این سقف تا <b>۲۰۰۰ مگابایت</b> بالا می‌رود و فایل‌ها از دیسک "
        "خودت خوانده می‌شوند (سریع‌تر و بدون دانلود دوباره).\n\n"
        "<b>چطور فعال شود؟</b>\n"
        "۱) از <code>my.telegram.org</code> مقدار <b>API ID</b> و <b>API Hash</b> را بگیر.\n"
        "۲) سرویس را اجرا کن:\n"
        "<code>docker compose --profile localapi up -d</code>\n"
        "۳) در همین پنل (متغیرهای اجرا) این‌ها را بگذار:\n"
        "• آدرس Local Bot API: <code>http://telegram-bot-api:8081/bot</code>\n"
        "• آدرس فایل: <code>http://telegram-bot-api:8081/file/bot</code>\n"
        "• API ID و API Hash\n"
        "۴) ربات را ری‌استارت کن.\n\n"
        "⚠️ این حالت اختیاری است. برای فایل‌های کوچک همان Bot API معمولی کافی است. "
        "پوشهٔ <code>data/tg-bot-api</code> باید بین ربات و سرور Bot API مشترک باشد."
    ),
    "btn_ytdlp_help": "🎬 چطور سایت‌های بیشتری پشتیبانی شود؟",
    "ytdlp_help": (
        "<b>🎬 افزودن سایت‌های جدید</b>\n\n"
        "ربات همهٔ سایت‌هایش را از <b>yt-dlp</b> می‌گیرد؛ هر سایتی که yt-dlp "
        "پشتیبانی کند، خودکار در ربات هم کار می‌کند (بیش از ۱۸۰۰ سایت).\n\n"
        "<b>راه درست:</b> فقط yt-dlp را بروز کن. لازم نیست کد ربات را دست بزنی.\n"
        "از بخش «دیپلوی» دکمهٔ «🔄 بروزرسانی yt-dlp» را بزن؛ نسخهٔ جدید نصب "
        "می‌شود، ایندکس سایت‌ها دوباره ساخته می‌شود و ربات ری‌استارت می‌شود.\n\n"
        "<b>سایت‌های بزرگسال:</b> همان اکسترکتورهای yt-dlp هستند؛ با آپدیت "
        "yt-dlp اضافه/اصلاح می‌شوند. برای سایت‌های نیازمند ورود، فایل "
        "<code>cookies.txt</code> را از پنل (🍪 کوکی‌ها) آپلود کن.\n\n"
        "⚠️ بعضی سایت‌ها خودشان محافظت/ورود اجباری دارند و هیچ ابزاری بدون کوکی "
        "نمی‌تواند دانلود کند."
    ),

    # ── دسته‌بندی پنل ادمین ──
    "btn_cat_stats": "📊 آمار و مانیتورینگ",
    "btn_cat_users": "👥 کاربران و دسترسی",
    "btn_cat_settings": "⚙️ تنظیمات ربات",
    "btn_cat_groups": "🔐 گروه‌ها و عضویت",
    "btn_cat_deploy": "🚀 دیپلوی و بروزرسانی",
    "btn_cat_debug": "🩺 عیب‌یابی",
    "btn_back_cats": "↩️ دسته‌بندی‌ها",
    "admin_cat_stats": "<b>📊 آمار و مانیتورینگ</b>\n\nوضعیت زندهٔ ربات، کارها، گزارش‌ها و لاگ‌ها:",
    "admin_cat_users": "<b>👥 کاربران و دسترسی</b>\n\nجست‌وجوی کاربر، مسدودسازی، ادمین‌ها و پیام همگانی:",
    "admin_cat_settings": "<b>⚙️ تنظیمات ربات</b>\n\nمحدودیت‌ها، متغیرهای اجرا، کوکی‌ها و پاک‌سازی:",
    "admin_cat_groups": "<b>🔐 گروه‌ها و عضویت</b>\n\nگروه گزارش‌ها و عضویت اجباری کانال/گروه:",
    "admin_cat_deploy": "<b>🚀 دیپلوی و بروزرسانی</b>\n\nسورس، بکاپ، ری‌استارت و بروزرسانی yt-dlp:",
    "admin_cat_debug": "<b>🩺 عیب‌یابی</b>\n\nسلامت سرویس‌ها و توکن موقت دسترسی برای هوش مصنوعی:",

    # ── عضویت اجباری ──
    "btn_admin_join": "🔐 عضویت اجباری",
    "btn_admin_join_add": "➕ افزودن کانال/گروه",
    "btn_admin_join_toggle": "🔐 حالت عضویت اجباری {flag}",
    "btn_admin_join_check": "🧪 بررسی دسترسی ربات",
    "admin_join_panel": (
        "<b>🔐 عضویت اجباری</b>\n\n"
        "وضعیت: <b>{status}</b>\n"
        "تعداد مقصد: <b>{count}</b>\n\n{list}\n\n"
        "کاربر تا عضو نشدن در همهٔ موارد بالا، به ربات دسترسی ندارد. "
        "ربات باید در هر کانال/گروه <b>ادمین</b> باشد تا عضویت را بررسی کند."
    ),
    "admin_join_empty": "— هنوز چیزی اضافه نشده.",
    "admin_join_added": "✅ اضافه شد: <b>{title}</b>\n🆔 <code>{chat}</code>",
    "admin_join_removed": "🗑 حذف شد: <b>{title}</b>",
    "admin_join_bad": "❌ پیدا نشد یا دسترسی ندارم. ربات را ادمین کن و دوباره بفرست.",
    "admin_join_admin_needed": "⚠️ برای بررسی عضویت، ربات باید در <b>{title}</b> ادمین باشد.",
    "admin_join_check_ok": "✅ همهٔ مقصدها سالم‌اند و ربات ادمین است.",
    "admin_join_check_mixed": "⚠️ بعضی مقصدها مشکل دارند:\n{list}",
    "admin_join_prompt": (
        "یوزرنیم (<code>@channel</code>)، آیدی عددی (<code>-100...</code>) یا یک "
        "پیام فورواردشده از کانال/گروه را بفرست:"
    ),
    "admin_join_hint": "💡 ربات باید ادمین باشد. برای کانال خصوصی، یک پیام از آن را فوروارد کن.",
    "join_gate_title": (
        "<b>🔐 دسترسی محدود</b>\n\n"
        "برای استفاده از ربات، اول در این کانال/گروه‌ها عضو شو:\n\n{list}\n\n"
        "بعد از عضویت، دکمهٔ «✅ عضو شدم» را بزن."
    ),
    "join_gate_btn": "✅ عضو شدم",
    "join_gate_still": "❌ هنوز عضو نشدی. اول عضو شو، بعد دوباره بررسی کن.",
    "join_gate_ok": "✅ عضویت تأیید شد. حالا می‌توانی از ربات استفاده کنی.",
    "join_gate_error": "⚠️ الان نتوانستم عضویت را بررسی کنم. چند لحظه بعد دوباره بزن.",

    # ── دیپلوی ──
    "btn_admin_deploy": "🚀 دیپلوی",
    "deploy_panel": (
        "<b>🚀 دیپلوی و بروزرسانی</b>\n\n"
        "🤖 نسخهٔ فعلی: <b>v{version}</b> ({codename})\n"
        "🎬 yt-dlp: <b>{ytdlp}</b>\n"
        "🐍 Python: <b>{python}</b>\n"
        "📦 حجم سورس: <b>{size}</b>\n"
        "💾 بکاپ آخر: {backup}\n"
        "🕒 آخرین بروزرسانی: {last_update}\n\n"
        "سورس اصلی همین لحظه را به‌صورت ZIP بگیر، یا ZIP جدید را بفرست تا "
        "اعتبارسنجی، بکاپ و ری‌استارت خودکار انجام شود."
    ),
    "btn_deploy_source": "⬇️ دریافت سورس (ZIP)",
    "deploy_source_caption": (
        "📦 <b>سورس LeechX v{version}</b>\n"
        "🗂 {files} فایل · {size}\n"
        "🚫 بدون <code>.env</code> و پوشهٔ <code>data</code> (اطلاعات خصوصی)\n\n"
        "این فایل را می‌توانی به هوش مصنوعی یا سرور دیگر بدهی."
    ),
    "btn_deploy_upload": "⬆️ آپلود سورس جدید",
    "deploy_upload_prompt": (
        "📦 فایل <b>ZIP</b> سورس جدید را بفرست.\n\n"
        "• می‌تواند ZIP معمولی یا خروجی GitHub باشد\n"
        "• ابتدا اعتبارسنجی می‌شود، بعد از تأیید تو اعمال و ری‌استارت می‌شود\n"
        "• از سورس فعلی خودکار بکاپ گرفته می‌شود"
    ),
    "deploy_zip_bad": "❌ ZIP معتبر نیست: {reason}",
    "deploy_zip_too_big": "❌ فایل بزرگ‌تر از حد مجاز است ({size} > {max}).",
    "deploy_staged": (
        "<b>📦 سورس جدید آماده است</b>\n\n"
        "نسخه: <b>v{current}</b> ← <b>v{new}</b>\n"
        "🗂 فایل‌ها: {files}\n"
        "📦 حجم: {size}\n"
        "{notes}\n\n"
        "با «اعمال» سورس فعلی بکاپ می‌شود، فایل‌ها جای‌گزین می‌شوند و ربات "
        "خودکار ری‌استارت می‌شود."
    ),
    "btn_deploy_apply": "🚀 اعمال و ری‌استارت",
    "btn_deploy_cancel": "✖️ انصراف",
    "deploy_applied": "✅ سورس به <b>v{version}</b> بروزرسانی شد.\n♻️ ربات در چند ثانیه ری‌استارت می‌شود…",
    "deploy_failed": "❌ اعمال سورس ناموفق بود: {reason}\nسورس فعلی دست‌نخورده ماند.",
    "btn_deploy_backup": "🗄 دانلود بکاپ آخر",
    "deploy_no_backup": "⚠️ هنوز بکاپی ساخته نشده است.",
    "deploy_backup_caption": "🗄 بکاپ سورس قبل از بروزرسانی — {when}",
    "btn_deploy_restart": "♻️ ری‌استارت ربات",
    "deploy_restart_confirm": "⚠️ مطمئنی؟ ربات چند ثانیه قطع می‌شود.",
    "deploy_restart_scheduled": "♻️ ری‌استارت شروع شد؛ چند ثانیه بعد دوباره در دسترس است.",
    "btn_deploy_ytdlp": "🔄 بروزرسانی yt-dlp",
    "btn_deploy_ytdlp_nightly": "🌙 نسخهٔ nightly",
    "deploy_ytdlp_done": (
        "✅ yt-dlp بروزرسانی شد: <b>{before}</b> ← <b>{after}</b>\n"
        "🌐 ایندکس سایت‌ها دوباره ساخته شد.\n"
        "♻️ برای فعال‌شدن اکسترکتورهای جدید، ربات را ری‌استارت کن."
    ),
    "deploy_ytdlp_fail": "❌ بروزرسانی yt-dlp ناموفق بود: {reason}",
    "deploy_ytdlp_working": "⏳ در حال بروزرسانی yt-dlp…",
    "btn_deploy_version": "🔢 جزئیات نسخه",
    "deploy_update_note": (
        "ℹ️ اعمال سورس فقط فایل‌های برنامه را عوض می‌کند؛ <code>.env</code>، "
        "دیتابیس و فایل‌های <code>data</code> دست‌نخورده می‌مانند."
    ),

    # ── عیب‌یابی / توکن موقت ──
    "btn_admin_debug": "🩺 عیب‌یابی",
    "debug_panel": (
        "<b>🩺 عیب‌یابی</b>\n\n"
        "وضعیت توکن دسترسی: <b>{state}</b>\n"
        "توکن‌های فعال: <b>{active}</b>\n\n"
        "با «توکن جدید» می‌توانی یک توکن <b>محدود و زمان‌دار</b> بسازی و به هوش "
        "مصنوعی بدهی تا سورس و وضعیت زنده را ببیند، مشکل را پیدا کند، کد را "
        "اصلاح و دیپلوی کند. توکن فقط تا پایان عمرش کار می‌کند و هر لحظه "
        "قابل ابطال است.\n\n"
        "🔒 توکن کامل فقط یک‌بار نمایش داده می‌شود؛ در دیتابیس هش ذخیره می‌شود."
    ),
    "debug_disabled": (
        "⚠️ دسترسی عیب‌یابی خاموش است. با دکمهٔ «🔴 دسترسی عیب‌یابی» در همین "
        "بخش روشنش کن؛ نیازی به «متغیرهای اجرا» نیست."
    ),
    "btn_debug_toggle": "دسترسی عیب‌یابی {flag}",
    "debug_toggle_on": "🟢 دسترسی عیب‌یابی روشن شد.",
    "debug_toggle_off": "🔴 دسترسی عیب‌یابی خاموش شد.",
    "btn_debug_make_read": "🔎 توکن فقط‌خواندنی",
    "btn_debug_make_write": "🛠 توکن خواندن + اصلاح کد",
    "btn_debug_make_restart": "♻️ توکن کامل (شامل ری‌استارت)",
    "btn_debug_ttl": "⏳ {hours} ساعت",
    "debug_scope_read": "فقط خواندن",
    "debug_scope_write": "خواندن + نوشتن",
    "debug_scope_restart": "کامل",
    "debug_token_created": (
        "<b>🔑 توکن عیب‌یابی ساخته شد</b>\n\n"
        "🌐 آدرس: <code>{base}</code>\n"
        "🔑 توکن:\n<code>{token}</code>\n\n"
        "🎚 سطح دسترسی: <b>{scopes}</b>\n"
        "⏳ انقضا: <b>{expires}</b> ({hours} ساعت)\n\n"
        "<b>به هوش مصنوعی این را بده:</b>\n"
        "1) آدرس بالا و توکن\n"
        "2) فایل <code>docs/DEBUG_API_FA.md</code>\n\n"
        "نمونه:\n"
        "<code>curl -H \"Authorization: Bearer {token}\" {base}/debug/health</code>\n\n"
        "⚠️ این پیام را برای کسی نفرست. بعد از کار، توکن را ببند."
    ),
    "debug_no_public_url": (
        "⚠️ <b>PUBLIC_BASE_URL</b> روی <code>{base}</code> است و از اینترنت در "
        "دسترس نیست. توکن فقط از داخل سرور/شبکه کار می‌کند. برای دسترسی "
        "هوش مصنوعی، دامنه یا IP عمومی سرور را در «متغیرهای اجرا» بگذار."
    ),
    "debug_tokens_list": "<b>🔑 توکن‌های فعال</b>\n\n{list}",
    "debug_token_item": "• <code>{id}</code> · {scopes} · انقضا {expires} · استفاده {uses}",
    "debug_none": "— توکن فعالی وجود ندارد.",
    "debug_revoke_ok": "🗑 توکن بسته شد.",
    "debug_revoke_fail": "❌ توکن پیدا نشد.",
    "btn_debug_health": "🧪 بررسی سلامت",
    "debug_health": (
        "<b>🩺 گزارش سلامت</b>\n\n"
        "🤖 نسخه: <b>v{version}</b>\n"
        "🐍 Python: {python}\n"
        "🎬 yt-dlp: {ytdlp}\n"
        "🎞 ffmpeg: {ffmpeg}\n"
        "🗄 دیتابیس: {db}\n"
        "💾 فضای دیسک: {disk}\n"
        "🌐 وب‌سرور: {web}\n"
        "⚡️ کارهای فعال: {jobs}\n"
        "👥 کاربران: {users}\n\n"
        "{problems}"
    ),
    "debug_health_problem": "⚠️ مشکلات:\n{list}",
    "debug_health_ok": "✅ مشکل مشخصی پیدا نشد.",
    "debug_handoff": (
        "🤝 <b>تحویل به هوش مصنوعی</b>\n\n"
        "این متن را همراه توکن بفرست:\n"
        "<code>You have a time-limited LeechX debug token. API base: {base}. "
        "Docs: docs/DEBUG_API_FA.md. Read /debug/health, /debug/logs and "
        "/debug/source first, fix the code, then POST /debug/source and "
        "POST /debug/restart. Never print the token.</code>"
    ),
    "btn_debug_revoke_all": "🗑 بستن همهٔ توکن‌ها",
    "btn_admin_preview": "👁 پیش‌نمایش حالت کاربر",
    "btn_preview": "👁 حالت کاربر",
    "preview_banner": "👁 <b>حالت پیش‌نمایش کاربر</b>\n\nدقیقاً همان چیزی را می‌بینی که یک کاربر عادی می‌بیند. دسترسی مدیریتی موقتاً خاموش است.",
    "btn_preview_exit": "🚪 خروج از حالت کاربر",
    "preview_exit_done": "✅ به حالت مدیریت برگشتی.",
    "preview_blocked": "👁 در حالت پیش‌نمایش کاربر هستی؛ اول خارج ش.",
    "admin_preview_panel": (
        "<b>👁 پیش‌نمایش حالت کاربر</b>\n\n"
        "با فعال‌کردن این حالت، منو و دسترسی‌ها مثل یک کاربر عادی می‌شود؛ "
        "لازم نیست با اکانت دوم تست کنی.\n\n"
        "برای خروج، دکمهٔ «🚪 خروج از حالت کاربر» را بزن."
    ),

    # ── برچسب متغیرهای اجرا ──
    "run_link_ttl_hours": "اعتبار لینک (ساعت)",
    "run_max_upload_mb": "حداکثر حجم آپلود (MB)",
    "run_max_link_mb": "حداکثر حجم فایل لینک (MB)",
    "run_rate_limit_seconds": "فاصلهٔ بین درخواست‌ها (ثانیه)",
    "run_daily_quota": "سهمیهٔ روزانه (0=بی‌نهایت)",
    "run_maintenance": "حالت تعمیر",
    "run_nsfw_enabled": "سایت‌های بزرگسال",
    "run_public_base_url": "آدرس عمومی لینک‌ها",
    "run_proxy": "پروکسی دانلود",
    "run_telegram_api_url": "آدرس Local Bot API",
    "run_telegram_api_file_url": "آدرس فایل Local Bot API",
    "run_telegram_api_id": "Telegram API ID",
    "run_telegram_api_hash": "Telegram API Hash",
    "run_owner_id": "مالک ربات",
    "run_admin_group_id": "شناسهٔ گروه ادمین",
    "run_admin_group_title": "نام گروه ادمین",
    "run_topic_downloads": "تاپیک دانلود",
    "run_topic_uploads": "تاپیک آپلود",
    "run_topic_reports": "تاپیک گزارش‌ها",
    "run_topic_logs": "تاپیک لاگ‌ها",
    "run_topic_cache": "تاپیک کش رسانه‌ها",
    "run_topic_audit": "تاپیک ممیزی عملیات",
    "run_topic_security": "تاپیک امنیت",
    "run_force_join_enabled": "عضویت اجباری",
    "run_force_join_chats": "کانال/گروه‌های عضویت اجباری",
    "run_debug_enabled": "دسترسی عیب‌یابی (توکن)",
    "run_debug_ip_allow": "IPهای مجاز توکن عیب‌یابی",
    "btn_reports_persistent": "📨 گزارش‌ها",
    "btn_cancel_tasks": "✖️ لغو عملیات",
    "btn_home_persistent": "🏠 شروع",
    "debug_token_button": "🔑 توکن #{id} · {scopes}",
}


EN: dict[str, str] = {
    "start": (
        "<b>👋 Welcome to LeechX</b>\n\n"
        "Send a <b>link</b> to pick a quality and download it, "
        "or send a <b>file</b> to get a direct link.\n\n"
        "• YouTube, Instagram, TikTok, Twitter, SoundCloud and thousands more\n"
        "• Files are deleted from the server after upload\n"
        "• Direct links live for <b>{ttl} hours</b> by default"
    ),
    "help": (
        "<b>📖 Help</b>\n\n"
        "<b>1) Download from a link</b>\n"
        "Send link → choose quality → file is uploaded to Telegram.\n\n"
        "<b>2) Direct link</b>\n"
        "Send a file → get a direct link valid for {ttl} hours.\n\n"
        "<b>Notes</b>\n"
        "• Direct media links (e.g. <code>.mp4</code>) download without asking.\n"
        "• Max size: {max_mb} MB.\n"
        "• Shared files are removed automatically after expiry.\n\n"
        "<b>Commands</b>\n"
        "/start /help /sites /me /links /cancel"
    ),
    "send_link_or_file": "🔗 Send a link or a file.",
    "probing": "🔍 Inspecting link…",
    "choose_quality": "<b>{title}</b>\n\n🎬 Pick a quality:",
    "video_btn": "🎬 {label}",
    "audio_btn": "🎵 {label}",
    "quality_title": "<b>{title}</b>",
    "cancel_btn": "✖️ Cancel",
    "my_links_btn": "🔗 My links",
    "file_link_progress": "📥 Receiving Telegram file {pct}%\n{bar}\n{size}",
    "file_link_wait": "📥 Receiving file from Telegram… received: {size}",
    "upload_wait": "⏳ Waiting for Telegram confirmation…",
    "canceled": "✖️ Canceled.",
    "cancel_nothing": "ℹ️ No active operation or form to cancel.",
    "not_found": "🔎 File or page not found (404). Check the URL.",
    "access_denied": "🔒 Access denied ({reason}).",
    "download_timeout": "⏱ Download timed out. Please try again.",
    "incomplete_download": "⚠️ Download incomplete. No partial file was delivered: {reason}",
    "canceled_btn": "Canceled",
    "queued": "🕒 Queued… (position {pos})",
    "downloading": "⬇️ Downloading {pct}%\n{bar}\n{size} • {speed} • {eta}",
    "uploading": "⬆️ Uploading {pct}%\n{bar}\n{size}",
    "processing": "⚙️ Processing…",
    "done": "✅ Done",
    "failed": "❌ Error: {reason}",
    "expired_draft": "⌛ This selection expired. Send the link again.",
    "too_many_active": "⏳ Your other job is still running. Please wait.",
    "rate_limited": "🐢 Slow down! Wait {seconds}s.",
    "banned": "🚫 You are blocked.",
    "maintenance": "🛠 Maintenance mode. Try again later.",
    "issue_reported": "📨 This issue was sent to the admin and will be checked as soon as possible.",
    "contact_prompt": (
        "✉️ Write your message to the admin and send it.\n"
        "Describe the problem, suggestion, or request in detail."
    ),
    "contact_sent": "✅ Your message reached the admin. Thanks for letting us know!",
    "contact_failed": "❌ Could not send your message. Please try again shortly.",
    "owner_claimed": (
        "👑 You are the first user of this bot, so you are now the <b>owner</b>.\n"
        "The admin panel will appear in your main menu from now on."
    ),
    "quota_exceeded": "📉 Daily quota reached.",
    "no_url": "🤔 No link found. Send a valid link.",
    "invalid_url": "⚠️ Invalid link.",
    "unsupported": "😕 Unsupported link: {reason}",
    "too_big": "📦 File size ({size}) exceeds the limit ({max}).",
    "not_media": "📄 Not a video/audio file.",
    "live_unsupported": "🔴 Live streams are not supported.",
    "playlist_detected": "📚 Playlist detected; only the first item is downloaded.",
    "direct_start": "🔗 Direct link detected — downloading without quality selection…",
    "file_received": "📥 File received. Preparing your link…",
    "link_ready": (
        "<b>✅ Direct link ready</b>\n\n"
        "<code>{url}</code>\n\n"
        "📄 {name}\n📦 {size}\n⏳ Valid for <b>{ttl}h</b> (until {expires})\n\n"
        "Copy it or tap the button."
    ),
    "open_link_btn": "🌐 Open link",
    "copy_hint": "⬆️ Tap the link above to copy.",
    "file_too_big_link": "📦 File is larger than the direct-link limit ({size} > {max}).",
    "delivery_panel": (
        "<b>📥 Media found</b>\n"
        "<b>{title}</b>\n\n"
        "🎞 Quality: <b>{quality}</b>\n"
        "📦 Size: {size}\n"
        "🏷 Filename: <code>{name}</code>\n\n"
        "<b>How would you like to receive this file?</b>\n\n"
        "🎬 <b>Send as playable media</b>\n"
        "Send it to this Telegram chat for playback. If Telegram cannot "
        "play its format, it will arrive as a document instead.\n\n"
        "📁 <b>Send as a file</b>\n"
        "Send it as a Telegram document without extra Telegram compression.\n\n"
        "🔗 <b>Create a download link</b>\n"
        "Store the file on the server and receive a shareable link valid for "
        "<b>{ttl} hours</b>.\n\n"
        "✏️ Use Rename to change the output filename.\n"
        "👇 Tapping one of the three delivery buttons starts the transfer."
    ),
    "quality_auto": "Best available (automatic)",
    "quality_original": "As provided by the source",
    "size_unknown": "Unknown until the download finishes",
    "deliver_video_btn": "🎬 Send media in Telegram",
    "deliver_doc_btn": "📁 Send file in Telegram",
    "deliver_link_btn": "🔗 Create direct download link",
    "deliver_rename_btn": "✏️ Rename file",
    "deliver_back_btn": "↩️ Change quality",
    "rename_prompt": "✏️ Send the new file name (extension not required):\nCurrent name: <code>{name}</code>",
    "rename_done": "✅ Name saved: <b>{name}</b>",
    "rename_bad": "❌ Invalid name; send a short name.",
    "btn_help": "📖 Help",
    "btn_status": "📊 My status",
    "btn_sites": "🌐 Supported sites",
    "btn_settings": "⚙️ Settings",
    "btn_contact": "✉️ Contact admin",
    "btn_admin": "👑 Admin panel",
    "sec_stats": "📊 Stats",
    "sec_users": "👥 Users",
    "sec_settings": "⚙️ Settings",
    "sec_groups": "🗂 Groups",
    "sec_deploy": "🚀 Deploy",
    "sec_debug": "🩺 Diagnostics",
    "sec_cookies": "🍪 Cookies",
    "sec_cancel": "✖️ Cancel tasks",
    "btn_back": "↩️ Back",
    "btn_close": "✖️ Close",
    "btn_lang": "🌍 Language",
    "btn_admin_stats": "📈 Stats",
    "btn_admin_jobs": "🧾 Recent jobs",
    "btn_admin_admins": "👥 Admins",
    "btn_admin_settings": "⚙️ Bot settings",
    "btn_admin_broadcast": "📢 Broadcast",
    "btn_admin_users": "🔎 User",
    "btn_admin_ban": "🚫 Ban user",
    "btn_admin_cleanup": "🧹 Cleanup",
    "btn_admin_cookies": "🍪 Cookies",
    "btn_admin_group": "👥 Admin group",
    "btn_admin_reports": "🚨 Reports",
    "btn_admin_logs": "🐞 Logs",
    "btn_admin_runtime": "🛠 Runtime variables",
    "btn_admin_group_id": "🔢 Set by numeric ID",
    "btn_admin_group_test": "🧪 Send test",
    "btn_admin_group_off": "🗑 Remove group",
    "btn_reports_refresh": "🔄 Refresh",
    "btn_report_close": "✅ Close #{id}",
    "btn_logs_clear": "🗑 Clear logs",
    "admin_cookies": (
        "<b>🍪 Cookie files</b>\n\n"
        "Count: <b>{count}</b>\n\n{list}\n\n"
        "For YouTube/Instagram send a <code>cookies.txt</code> (Netscape) file."
    ),
    "btn_cookie_add": "➕ Add / upload",
    "btn_cookie_test": "🧪 Validate",
    "cookie_add_prompt": (
        "📄 Send a <code>cookies.txt</code> file or paste the Netscape text.\n\n"
        "How to export: <code>docs/COOKIES.md</code>"
    ),
    "cookie_saved": "✅ Cookies saved: <b>{name}</b>\n🌐 Domains: <code>{domains}</code>",
    "cookie_bad": "❌ Invalid cookie file: {reason}",
    "cookie_deleted": "🗑 Cookie file removed: <b>{name}</b>",
    "cookie_missing": "❌ No such cookie file.",
    "cookie_test_result": "<b>🧪 Cookie validation</b>\n\n{list}",
    "cookie_ok": "✅ OK",
    "cookie_problem": "⚠️ {reason}",
    "cookie_empty": "—",
    "cookie_text_only": "📄 Send a <code>cookies.txt</code> file or paste the Netscape text.",
    "btn_admin_add": "➕ Add admin",
    "btn_ban": "🚫 Ban",
    "btn_unban": "♻️ Unban",
    "set_ttl": "⏳ Link TTL: {v}h",
    "set_upload": "📦 Max upload: {v}MB",
    "set_link": "🔗 Max link file: {v}MB",
    "set_rate": "🐢 Rate limit: {v}s",
    "set_quota": "📉 Daily quota: {v}",
    "set_maintenance": "🛠 Maintenance {flag}",
    "set_nsfw": "🔞 NSFW sites {flag}",
    "admin_limit_reached": "⛔️ Admin limit reached ({max}).",
    "admin_env_admin": "This user is listed in ADMIN_IDS; remove them from env.",
    "status": (
        "<b>📊 Your status</b>\n\n"
        "🆔 <code>{uid}</code>\n⬇️ Downloads: <b>{downloads}</b>\n"
        "📅 Joined: {joined}\n👑 Admin: {admin}\n🤖 Version: <b>v{version}</b>"
    ),
    "yes": "yes",
    "no": "no",
    "sites_title": (
        "<b>🌐 Supported sites</b>\n\n"
        "Active extractors: <b>{count}</b>\n"
        "Search: <code>/sites instagram</code>\n\n<b>Popular:</b>\n{popular}"
    ),
    "sites_search": "<b>🔍 Results for “{q}”</b> ({count})\n\n{list}",
    "sites_none": "Nothing found.",
    "admin_only": "⛔️ Admins only.",
    "admin_panel": "<b>👑 Admin panel</b>\n\nPick a section:",
    "admin_stats": (
        "<b>📈 Bot stats</b>\n\n"
        "👥 Total users: <b>{users}</b>\n"
        "🟢 Active users (7d): <b>{active_users}</b>\n"
        "🚫 Banned: <b>{banned}</b>\n"
        "⬆️ Uploading now: <b>{uploading}</b>\n"
        "🔗 Active direct links: <b>{active_links}</b>\n"
        "🚨 Open reports: <b>{reports}</b>\n"
        "🛡 Admins: <b>{admins}</b>\n"
        "📥 Jobs 24h: <b>{jobs}</b> (✅ {done} / ❌ {failed})\n"
        "⚡️ Active jobs: <b>{active}</b>\n"
        "💾 Disk: <b>{disk}</b>\n"
        "⏱ Uptime: <b>{uptime}</b>\n"
        "🤖 Version: <b>v{version}</b>"
    ),
    "admin_jobs": "<b>🧾 Recent jobs</b>\n\n{list}",
    "admin_admins": "<b>👥 Admins</b>\n\n👑 Owner: {owners}\n🛡 Extra admins:\n{admins}",
    "admin_add_prompt": "Send the user's numeric ID or @username:",
    "admin_add_ok": "✅ Admin added: <code>{uid}</code>",
    "admin_add_fail": "❌ Not found (the user must /start first).",
    "admin_remove_ok": "🗑 Admin removed: <code>{uid}</code>",
    "admin_remove_fail": "❌ Not an admin.",
    "admin_owner_immutable": "⛔️ The owner cannot be removed.",
    "admin_settings": (
        "<b>⚙️ Bot settings</b>\n\n⏳ Link TTL: <b>{ttl}h</b>\n📦 Max upload: <b>{max_upload}MB</b>\n"
        "🔗 Max link file: <b>{max_link}MB</b>\n🐢 Rate limit: <b>{rate}s</b>\n"
        "⛔️ Maintenance: <b>{maintenance}</b>\n🔞 NSFW sites: <b>{nsfw}</b>"
    ),
    "admin_set_value": "Send a new value for <b>{label}</b>:",
    "admin_set_ok": "✅ Saved: {label} = <b>{value}</b>",
    "admin_bad_value": "❌ Invalid value.",
    "admin_broadcast_prompt": "Send the broadcast text:",
    "admin_broadcast_started": "📢 Sending to {count} users…",
    "admin_broadcast_done": "✅ Broadcast finished.\nOK: {ok} • Failed: {fail}",
    "admin_user_prompt": "Send the user ID:",
    "admin_user_info": (
        "<b>🔎 User</b>\n\n🆔 <code>{uid}</code>\n👤 {name}\n🔗 @{username}\n"
        "📥 Downloads: {downloads}\n🚫 Banned: {banned}\n🛡 Admin: {admin}\n📅 Joined: {joined}"
    ),
    "admin_cleanup_done": "🧹 Cleanup done.\nFiles removed: {files}\nFreed: {size}",
    "admin_ban_prompt": (
        "Send a numeric ID, @username, or a forwarded message from the user "
        "to find them and change their ban status."
    ),
    "admin_forward_hint": "💡 You can also forward a message from the user.",
    "admin_group_panel": (
        "<b>👥 Admin group</b>\n\n"
        "Status: {status}\n"
        "Group: <b>{title}</b>\n"
        "Chat ID: <code>{chat}</code>\n\n"
        "📥 Downloads topic: {downloads}\n"
        "📤 Uploads topic: {uploads}\n"
        "🚨 Reports topic: {reports}\n"
        "🐞 Logs topic: {logs}\n\n"
        "{hint}"
    ),
    "admin_group_configured": "✅ Configured",
    "admin_group_not_configured": "❌ Not configured",
    "admin_group_topic_ok": "✅",
    "admin_group_topic_missing": "—",
    "admin_group_hint_ok": (
        "User messages, errors, and download/upload alerts are sent to these topics."
    ),
    "admin_group_hint_setup": (
        "To set it up: add the bot to a group with <b>Topics</b> enabled, make it admin, "
        "then send <code>/setup</code> inside the group.\n"
        "Or use the “numeric ID” button to enter the group ID manually."
    ),
    "admin_group_prompt": "Send the group's numeric ID (e.g. <code>-1001234567890</code>):",
    "admin_group_bad_id": "❌ Invalid group ID.",
    "admin_group_saved": (
        "✅ Admin group saved.\n"
        "Topics created: {created}\n"
        "Topics failed: {failed}\n\n"
        "If a topic was not created, make sure the group has <b>Topics</b> and the bot is an admin."
    ),
    "admin_group_off_done": "🗑 Admin group removed.",
    "admin_group_test_ok": "✅ Test message sent to the admin group.",
    "admin_group_test_fail": "❌ Send failed; check the group settings and bot permissions.",
    "setup_private": (
        "This command must be sent <b>inside a group</b>.\n"
        "Add the bot to a group with Topics enabled and send <code>/setup</code> there."
    ),
    "setup_need_admin": "⛔️ Only authorized bot admins can configure the log group.",
    "setup_not_group": "This chat is not a group.",
    "setup_done": (
        "✅ Admin group configured.\n\n"
        "📥 Downloads: {downloads}\n📤 Uploads: {uploads}\n"
        "🚨 Reports: {reports}\n🐞 Logs: {logs}\n\n"
        "If an item is “—”, enable Topics and make the bot an admin."
    ),
    "admin_reports": "<b>🚨 Open reports</b> ({count})\n\n{list}",
    "admin_reports_empty": "There are no open reports.",
    "admin_report_item": (
        "{icon} <b>#{id}</b> · {kind} · {when}\n"
        "👤 {name} (@{username}) · <code>{uid}</code>\n{body}"
    ),
    "admin_report_kind_contact": "User message",
    "admin_report_kind_unsupported": "Failing site",
    "admin_report_closed": "✅ Report #{id} closed.",
    "admin_report_missing": "❌ No such report.",
    "admin_logs": "<b>🐞 Recent logs</b> ({count})\n\n{list}",
    "admin_logs_empty": "No logs have been recorded.",
    "admin_logs_cleared": "🗑 {count} log entries cleared.",
    "admin_runtime": (
        "<b>🛠 Runtime variables</b>\n\n"
        "Enter values right here; no need to touch the server.\n"
        "Tap an item to change it.\n\n"
        "⚠️ Bot API URL changes take effect after a restart."
    ),
    "admin_runtime_prompt": (
        "Send the new value for <b>{label}</b>.\n"
        "Send <code>-</code> to clear it."
    ),
    "admin_runtime_saved": "✅ Saved: {label} = <b>{value}</b>",
    "admin_runtime_restart": "ℹ️ This value takes effect after the bot restarts.",
    "state_text_only": "✍️ Please send your answer as text.",

    # ── Fresh UI ──
    "btn_kb_close": "⌨️ Close keyboard",
    "kb_closed": "⌨️ Keyboard closed. Send /start whenever you want it back.",
    "settings_panel": (
        "<b>⚙️ Settings</b>\n\n"
        "🌍 Language: <b>{lang}</b>\n"
        "🤖 Version: <b>{version}</b>\n\n"
        "Use the buttons below:"
    ),
    "lang_title": (
        "<b>🌍 Choose your language</b>\n\n"
        "Current: <b>{current}</b>\n\n"
        "Language · Язык · زبان"
    ),
    "lang_saved": "✅ Language changed to <b>{lang}</b>.",
    "version_info": (
        "<b>🤖 LeechX v{version}</b> · {codename}\n"
        "📅 Released: {date}\n"
        "🐍 Python: {python}\n"
        "🎬 yt-dlp: {ytdlp}\n"
        "🎞 ffmpeg: {ffmpeg}\n"
        "⏱ Uptime: {uptime}"
    ),
    "btn_local_api_help": "ℹ️ What is the Local Bot API?",
    "local_api_help": (
        "<b>ℹ️ What is a Local Bot API Server?</b>\n\n"
        "Telegram's public Bot API limits downloads to <b>20 MB</b> and uploads "
        "to <b>50 MB</b>. If you run the Bot API server yourself on the same "
        "machine, the limit rises to <b>2000 MB</b> and files are read straight "
        "from your disk (faster, no second download).\n\n"
        "<b>How to enable it</b>\n"
        "1) Get <b>API ID</b> and <b>API Hash</b> from <code>my.telegram.org</code>.\n"
        "2) Start the service:\n"
        "<code>docker compose --profile localapi up -d</code>\n"
        "3) In this panel (runtime variables) set:\n"
        "• Local Bot API URL: <code>http://telegram-bot-api:8081/bot</code>\n"
        "• File URL: <code>http://telegram-bot-api:8081/file/bot</code>\n"
        "• API ID and API Hash\n"
        "4) Restart the bot.\n\n"
        "⚠️ Optional. For small files the normal Bot API is enough. The "
        "<code>data/tg-bot-api</code> folder must be shared between the bot and "
        "the Bot API server."
    ),
    "btn_ytdlp_help": "🎬 How do I support more sites?",
    "ytdlp_help": (
        "<b>🎬 Adding new sites</b>\n\n"
        "Every site comes from <b>yt-dlp</b>: anything yt-dlp supports works in "
        "the bot automatically (1800+ sites).\n\n"
        "<b>The right way:</b> just update yt-dlp. No bot code changes needed.\n"
        "Open «Deploy» → «🔄 Update yt-dlp». The new version is installed, the "
        "site index is rebuilt and the bot restarts.\n\n"
        "<b>Adult sites:</b> they are regular yt-dlp extractors and improve with "
        "yt-dlp updates. For login-protected sites upload a <code>cookies.txt</code> "
        "from the admin panel (🍪 Cookies).\n\n"
        "⚠️ Some sites enforce login/anti-bot protection; no tool can download "
        "them without cookies."
    ),

    # ── Admin categories ──
    "btn_cat_stats": "📊 Stats & monitoring",
    "btn_cat_users": "👥 Users & access",
    "btn_cat_settings": "⚙️ Bot settings",
    "btn_cat_groups": "🔐 Groups & membership",
    "btn_cat_deploy": "🚀 Deploy & update",
    "btn_cat_debug": "🩺 Diagnostics",
    "btn_back_cats": "↩️ Categories",
    "admin_cat_stats": "<b>📊 Stats & monitoring</b>\n\nLive status, jobs, reports and logs:",
    "admin_cat_users": "<b>👥 Users & access</b>\n\nLook up users, ban, admins and broadcast:",
    "admin_cat_settings": "<b>⚙️ Bot settings</b>\n\nLimits, runtime variables, cookies and cleanup:",
    "admin_cat_groups": "<b>🔐 Groups & membership</b>\n\nAdmin log group and forced channel/group membership:",
    "admin_cat_deploy": "<b>🚀 Deploy & update</b>\n\nSource, backup, restart and yt-dlp updates:",
    "admin_cat_debug": "<b>🩺 Diagnostics</b>\n\nService health and a temporary AI access token:",

    # ── Forced membership ──
    "btn_admin_join": "🔐 Forced membership",
    "btn_admin_join_add": "➕ Add channel/group",
    "btn_admin_join_toggle": "🔐 Forced join {flag}",
    "btn_admin_join_check": "🧪 Check bot access",
    "admin_join_panel": (
        "<b>🔐 Forced membership</b>\n\n"
        "Status: <b>{status}</b>\n"
        "Targets: <b>{count}</b>\n\n{list}\n\n"
        "Users cannot use the bot before joining every item above. The bot must "
        "be an <b>admin</b> in each channel/group to verify membership."
    ),
    "admin_join_empty": "— Nothing added yet.",
    "admin_join_added": "✅ Added: <b>{title}</b>\n🆔 <code>{chat}</code>",
    "admin_join_removed": "🗑 Removed: <b>{title}</b>",
    "admin_join_bad": "❌ Not found or no access. Make the bot an admin and try again.",
    "admin_join_admin_needed": "⚠️ The bot must be an admin in <b>{title}</b> to verify membership.",
    "admin_join_check_ok": "✅ All targets are healthy and the bot is an admin.",
    "admin_join_check_mixed": "⚠️ Some targets have problems:\n{list}",
    "admin_join_prompt": (
        "Send a username (<code>@channel</code>), a numeric ID (<code>-100...</code>) "
        "or a message forwarded from the channel/group:"
    ),
    "admin_join_hint": "💡 The bot must be an admin. For a private channel, forward one of its messages.",
    "join_gate_title": (
        "<b>🔐 Access restricted</b>\n\n"
        "To use the bot, join these channels/groups first:\n\n{list}\n\n"
        "Then tap «✅ I joined»."
    ),
    "join_gate_btn": "✅ I joined",
    "join_gate_still": "❌ You have not joined yet. Join first, then check again.",
    "join_gate_ok": "✅ Membership verified. You can use the bot now.",
    "join_gate_error": "⚠️ Could not verify membership right now. Try again in a moment.",

    # ── Deploy ──
    "btn_admin_deploy": "🚀 Deploy",
    "deploy_panel": (
        "<b>🚀 Deploy & update</b>\n\n"
        "🤖 Current version: <b>v{version}</b> ({codename})\n"
        "🎬 yt-dlp: <b>{ytdlp}</b>\n"
        "🐍 Python: <b>{python}</b>\n"
        "📦 Source size: <b>{size}</b>\n"
        "💾 Last backup: {backup}\n"
        "🕒 Last update: {last_update}\n\n"
        "Download the exact running source as a ZIP, or upload a new ZIP to "
        "validate, back up and restart automatically."
    ),
    "btn_deploy_source": "⬇️ Download source (ZIP)",
    "deploy_source_caption": (
        "📦 <b>LeechX v{version} source</b>\n"
        "🗂 {files} files · {size}\n"
        "🚫 No <code>.env</code> and no <code>data</code> folder (private data)\n\n"
        "You can hand this file to an AI or another server."
    ),
    "btn_deploy_upload": "⬆️ Upload new source",
    "deploy_upload_prompt": (
        "📦 Send the new source <b>ZIP</b>.\n\n"
        "• A plain ZIP or a GitHub archive both work\n"
        "• It is validated first; nothing is applied before you confirm\n"
        "• The current source is backed up automatically"
    ),
    "deploy_zip_bad": "❌ Invalid ZIP: {reason}",
    "deploy_zip_too_big": "❌ File too large ({size} > {max}).",
    "deploy_staged": (
        "<b>📦 New source staged</b>\n\n"
        "Version: <b>v{current}</b> → <b>v{new}</b>\n"
        "🗂 Files: {files}\n"
        "📦 Size: {size}\n"
        "{notes}\n\n"
        "Apply backs up the current source, replaces the files and restarts "
        "the bot automatically."
    ),
    "btn_deploy_apply": "🚀 Apply & restart",
    "btn_deploy_cancel": "✖️ Cancel",
    "deploy_applied": "✅ Source updated to <b>v{version}</b>.\n♻️ Restarting in a few seconds…",
    "deploy_failed": "❌ Update failed: {reason}\nThe current source was left untouched.",
    "btn_deploy_backup": "🗄 Download last backup",
    "deploy_no_backup": "⚠️ No backup has been created yet.",
    "deploy_backup_caption": "🗄 Source backup from before the update — {when}",
    "btn_deploy_restart": "♻️ Restart bot",
    "deploy_restart_confirm": "⚠️ Are you sure? The bot goes offline for a few seconds.",
    "deploy_restart_scheduled": "♻️ Restarting; back online in a few seconds.",
    "btn_deploy_ytdlp": "🔄 Update yt-dlp",
    "btn_deploy_ytdlp_nightly": "🌙 Nightly build",
    "deploy_ytdlp_done": (
        "✅ yt-dlp updated: <b>{before}</b> → <b>{after}</b>\n"
        "🌐 Site index rebuilt.\n"
        "♻️ Restart the bot to load the new extractors."
    ),
    "deploy_ytdlp_fail": "❌ yt-dlp update failed: {reason}",
    "deploy_ytdlp_working": "⏳ Updating yt-dlp…",
    "btn_deploy_version": "🔢 Version details",
    "deploy_update_note": (
        "ℹ️ Applying a source only replaces program files; <code>.env</code>, the "
        "database and <code>data</code> files stay untouched."
    ),

    # ── Diagnostics / temporary token ──
    "btn_admin_debug": "🩺 Diagnostics",
    "debug_panel": (
        "<b>🩺 Diagnostics</b>\n\n"
        "Token access: <b>{state}</b>\n"
        "Active tokens: <b>{active}</b>\n\n"
        "Create a <b>scoped, time-limited</b> token and give it to an AI so it can "
        "read the live source and state, find the bug, fix the code and deploy. "
        "The token dies at expiry and can be revoked at any moment.\n\n"
        "🔒 The full token is shown once; only its hash is stored."
    ),
    "debug_disabled": (
        "⚠️ Debug access is off. Turn it on with the «🔴 Debug access» button in "
        "this section — no need for «Runtime variables»."
    ),
    "btn_debug_toggle": "Debug access {flag}",
    "debug_toggle_on": "🟢 Debug access is on.",
    "debug_toggle_off": "🔴 Debug access is off.",
    "btn_debug_make_read": "🔎 Read-only token",
    "btn_debug_make_write": "🛠 Read + fix code",
    "btn_debug_make_restart": "♻️ Full token (with restart)",
    "btn_debug_ttl": "⏳ {hours} hours",
    "debug_scope_read": "read only",
    "debug_scope_write": "read + write",
    "debug_scope_restart": "full",
    "debug_token_created": (
        "<b>🔑 Debug token created</b>\n\n"
        "🌐 Base URL: <code>{base}</code>\n"
        "🔑 Token:\n<code>{token}</code>\n\n"
        "🎚 Scopes: <b>{scopes}</b>\n"
        "⏳ Expires: <b>{expires}</b> ({hours}h)\n\n"
        "<b>Give the AI:</b>\n"
        "1) The base URL and token\n"
        "2) <code>docs/DEBUG_API_FA.md</code>\n\n"
        "Example:\n"
        "<code>curl -H \"Authorization: Bearer {token}\" {base}/debug/health</code>\n\n"
        "⚠️ Do not forward this message. Revoke the token when done."
    ),
    "debug_no_public_url": (
        "⚠️ <b>PUBLIC_BASE_URL</b> is <code>{base}</code>, which is not reachable "
        "from the internet. The token only works from inside the server/LAN. Set "
        "a public domain or IP under «Runtime variables» for AI access."
    ),
    "debug_tokens_list": "<b>🔑 Active tokens</b>\n\n{list}",
    "debug_token_item": "• <code>{id}</code> · {scopes} · expires {expires} · used {uses}×",
    "debug_none": "— No active tokens.",
    "debug_revoke_ok": "🗑 Token revoked.",
    "debug_revoke_fail": "❌ Token not found.",
    "btn_debug_health": "🧪 Health check",
    "debug_health": (
        "<b>🩺 Health report</b>\n\n"
        "🤖 Version: <b>v{version}</b>\n"
        "🐍 Python: {python}\n"
        "🎬 yt-dlp: {ytdlp}\n"
        "🎞 ffmpeg: {ffmpeg}\n"
        "🗄 Database: {db}\n"
        "💾 Disk: {disk}\n"
        "🌐 Web server: {web}\n"
        "⚡️ Active jobs: {jobs}\n"
        "👥 Users: {users}\n\n"
        "{problems}"
    ),
    "debug_health_problem": "⚠️ Problems:\n{list}",
    "debug_health_ok": "✅ No obvious problem found.",
    "debug_handoff": (
        "🤝 <b>AI hand-off</b>\n\n"
        "Send this text together with the token:\n"
        "<code>You have a time-limited LeechX debug token. API base: {base}. "
        "Docs: docs/DEBUG_API_FA.md. Read /debug/health, /debug/logs and "
        "/debug/source first, fix the code, then POST /debug/source and "
        "POST /debug/restart. Never print the token.</code>"
    ),
    "btn_debug_revoke_all": "🗑 Revoke all tokens",
    "btn_admin_preview": "👁 Preview member view",
    "btn_preview": "👁 Member view",
    "preview_banner": "👁 <b>Member preview mode</b>\n\nYou see exactly what a normal user sees. Admin access is temporarily disabled.",
    "btn_preview_exit": "🚪 Exit member view",
    "preview_exit_done": "✅ Back to admin mode.",
    "preview_blocked": "👁 You are in member preview mode; exit it first.",
    "admin_preview_panel": (
        "<b>👁 Member preview</b>\n\n"
        "Enabling this makes the menu and permissions behave like a normal user, "
        "so you do not need a second account to test.\n\n"
        "Tap «🚪 Exit member view» to return."
    ),

    # ── Runtime labels ──
    "run_link_ttl_hours": "Link TTL (hours)",
    "run_max_upload_mb": "Max upload (MB)",
    "run_max_link_mb": "Max link file (MB)",
    "run_rate_limit_seconds": "Request interval (seconds)",
    "run_daily_quota": "Daily quota (0 = unlimited)",
    "run_maintenance": "Maintenance mode",
    "run_nsfw_enabled": "Adult sites",
    "run_public_base_url": "Public link base URL",
    "run_proxy": "Download proxy",
    "run_telegram_api_url": "Local Bot API URL",
    "run_telegram_api_file_url": "Local Bot API file URL",
    "run_telegram_api_id": "Telegram API ID",
    "run_telegram_api_hash": "Telegram API Hash",
    "run_owner_id": "Bot owner",
    "run_admin_group_id": "Admin group ID",
    "run_admin_group_title": "Admin group title",
    "run_topic_downloads": "Downloads topic",
    "run_topic_uploads": "Uploads topic",
    "run_topic_reports": "Reports topic",
    "run_topic_logs": "Logs topic",
    "run_topic_cache": "Media cache topic",
    "run_topic_audit": "Audit topic",
    "run_topic_security": "Security topic",
    "run_force_join_enabled": "Forced membership",
    "run_force_join_chats": "Forced join channels/groups",
    "run_debug_enabled": "Debug token access",
    "run_debug_ip_allow": "Debug token allowed IPs",
    "btn_reports_persistent": "📨 Reports",
    "btn_cancel_tasks": "✖️ Cancel tasks",
    "btn_home_persistent": "🏠 Home",
    "debug_token_button": "🔑 Token #{id} · {scopes}",
}

RU: dict[str, str] = {
    # ── Общее ──
    "start": (
        "<b>👋 Добро пожаловать в LeechX</b>\n\n"
        "Отправь <b>ссылку</b>, чтобы выбрать качество и скачать, "
        "или отправь <b>файл</b>, чтобы получить прямую ссылку.\n\n"
        "• YouTube, Instagram, TikTok, Twitter, SoundCloud и тысячи других\n"
        "• Файлы удаляются с сервера после загрузки\n"
        "• Прямые ссылки живут <b>{ttl} ч.</b> по умолчанию"
    ),
    "help": (
        "<b>📖 Помощь</b>\n\n"
        "<b>1) Скачивание по ссылке</b>\n"
        "Отправь ссылку → выбери качество → файл загрузится в Telegram.\n\n"
        "<b>2) Прямая ссылка</b>\n"
        "Отправь файл → получи прямую ссылку на {ttl} ч.\n\n"
        "<b>Заметки</b>\n"
        "• Прямые медиа-ссылки (например, <code>.mp4</code>) скачиваются без вопросов.\n"
        "• Максимальный размер: {max_mb} МБ.\n"
        "• Общие файлы удаляются автоматически после истечения срока.\n\n"
        "<b>Команды</b>\n"
        "/start /help /sites /me /links /cancel"
    ),
    "send_link_or_file": "🔗 Отправь ссылку или файл.",
    "probing": "🔍 Проверяю ссылку…",
    "choose_quality": "<b>{title}</b>\n\n🎬 Выбери качество:",
    "video_btn": "🎬 {label}",
    "audio_btn": "🎵 {label}",
    "quality_title": "<b>{title}</b>",
    "cancel_btn": "✖️ Отмена",
    "my_links_btn": "🔗 Мои ссылки",
    "file_link_progress": "📥 Получение файла из Telegram {pct}%\n{bar}\n{size}",
    "file_link_wait": "📥 Получение файла из Telegram… получено: {size}",
    "upload_wait": "⏳ Жду подтверждения Telegram…",
    "canceled": "✖️ Отменено.",
    "cancel_nothing": "ℹ️ Нет активной операции или формы для отмены.",
    "not_found": "🔎 Файл или страница не найдены (404). Проверь ссылку.",
    "access_denied": "🔒 Доступ запрещён ({reason}).",
    "download_timeout": "⏱ Время ожидания истекло. Попробуй снова.",
    "incomplete_download": "⚠️ Загрузка неполная; частичный файл не отправлен: {reason}",
    "canceled_btn": "Отменено",
    "queued": "🕒 В очереди… (позиция {pos})",
    "downloading": "⬇️ Скачивание {pct}%\n{bar}\n{size} • {speed} • {eta}",
    "uploading": "⬆️ Загрузка {pct}%\n{bar}\n{size}",
    "processing": "⚙️ Обработка…",
    "done": "✅ Готово",
    "failed": "❌ Ошибка: {reason}",
    "expired_draft": "⌛ Выбор устарел. Отправь ссылку снова.",
    "too_many_active": "⏳ Другая задача ещё выполняется. Подожди.",
    "rate_limited": "🐢 Помедленнее! Подожди {seconds} с.",
    "banned": "🚫 Вы заблокированы.",
    "maintenance": "🛠 Режим обслуживания. Попробуй позже.",
    "issue_reported": "📨 Проблема отправлена администратору и будет проверена.",
    "contact_prompt": "✉️ Напиши сообщение администратору и отправь его.\nОпиши проблему, предложение или запрос подробно.",
    "contact_sent": "✅ Сообщение дошло до администратора. Спасибо!",
    "contact_failed": "❌ Не удалось отправить сообщение. Попробуй позже.",
    "owner_claimed": "👑 Вы первый пользователь этого бота и стали <b>владельцем</b>.\nТеперь панель администратора видна в главном меню.",
    "quota_exceeded": "📉 Дневная квота исчерпана.",
    "no_url": "🤔 Ссылка не найдена. Отправь корректную ссылку.",
    "invalid_url": "⚠️ Некорректная ссылка.",
    "unsupported": "😕 Ссылка не поддерживается: {reason}",
    "too_big": "📦 Размер файла ({size}) превышает лимит ({max}).",
    "not_media": "📄 Это не видео/аудио файл.",
    "live_unsupported": "🔴 Прямые трансляции не поддерживаются.",
    "playlist_detected": "📚 Обнаружен плейлист; скачивается только первый элемент.",
    "direct_start": "🔗 Прямая ссылка — скачиваю без выбора качества…",
    "file_received": "📥 Файл получен. Готовлю ссылку…",
    "link_ready": "<b>✅ Прямая ссылка готова</b>\n\n<code>{url}</code>\n\n📄 {name}\n📦 {size}\n⏳ Действует <b>{ttl} ч.</b> (до {expires})\n\nСкопируй её или нажми кнопку.",
    "open_link_btn": "🌐 Открыть ссылку",
    "copy_hint": "⬆️ Нажми на ссылку выше, чтобы скопировать.",
    "file_too_big_link": "📦 Файл больше лимита прямой ссылки ({size} > {max}).",
    "delivery_panel": (
        "<b>📥 Медиа найдено</b>\n<b>{title}</b>\n\n"
        "🎞 Качество: <b>{quality}</b>\n📦 Размер: {size}\n"
        "🏷 Имя файла: <code>{name}</code>\n\n"
        "<b>Как получить файл?</b>\n\n"
        "🎬 <b>Отправить как воспроизводимое медиа</b>\n"
        "Файл придёт в этот чат и его можно будет воспроизвести. Если формат "
        "не поддерживается, он придёт документом.\n\n"
        "📁 <b>Отправить как файл</b>\n"
        "Придёт документом без дополнительного сжатия Telegram.\n\n"
        "🔗 <b>Создать ссылку для скачивания</b>\n"
        "Файл сохранится на сервере, и ты получишь ссылку на <b>{ttl} ч.</b>\n\n"
        "✏️ Через «Переименовать» можно изменить имя файла.\n"
        "👇 Нажатие любой из трёх кнопок запускает передачу."
    ),
    "quality_auto": "Лучшее доступное (авто)",
    "quality_original": "Как в источнике",
    "size_unknown": "Неизвестно до окончания загрузки",
    "deliver_video_btn": "🎬 Отправить медиа в Telegram",
    "deliver_doc_btn": "📁 Отправить файл в Telegram",
    "deliver_link_btn": "🔗 Создать прямую ссылку",
    "deliver_rename_btn": "✏️ Переименовать файл",
    "deliver_back_btn": "↩️ Изменить качество",
    "rename_prompt": "✏️ Отправь новое имя файла (расширение не нужно):\nТекущее имя: <code>{name}</code>",
    "rename_done": "✅ Имя сохранено: <b>{name}</b>",
    "rename_bad": "❌ Некорректное имя; отправь короткое имя.",

    # ── Кнопки меню ──
    "btn_help": "📖 Помощь",
    "btn_status": "📊 Мой статус",
    "btn_sites": "🌐 Поддерживаемые сайты",
    "btn_settings": "⚙️ Настройки",
    "btn_contact": "✉️ Связаться с админом",
    "btn_admin": "👑 Панель администратора",
    "sec_stats": "📊 Статистика",
    "sec_users": "👥 Пользователи",
    "sec_settings": "⚙️ Настройки",
    "sec_groups": "🗂 Группы",
    "sec_deploy": "🚀 Деплой",
    "sec_debug": "🩺 Диагностика",
    "sec_cookies": "🍪 Куки",
    "sec_cancel": "✖️ Отменить задачи",
    "btn_back": "↩️ Назад",
    "btn_close": "✖️ Закрыть",
    "btn_lang": "🌍 Язык",
    "btn_admin_stats": "📈 Статистика",
    "btn_admin_jobs": "🧾 Последние задачи",
    "btn_admin_admins": "👥 Администраторы",
    "btn_admin_settings": "⚙️ Настройки бота",
    "btn_admin_broadcast": "📢 Рассылка",
    "btn_admin_users": "🔎 Пользователь",
    "btn_admin_ban": "🚫 Заблокировать",
    "btn_admin_cleanup": "🧹 Очистка",
    "btn_admin_cookies": "🍪 Cookies",
    "btn_admin_group": "👥 Группа админов",
    "btn_admin_reports": "🚨 Жалобы",
    "btn_admin_logs": "🐞 Логи",
    "btn_admin_runtime": "🛠 Переменные",
    "btn_admin_group_id": "🔢 По числовому ID",
    "btn_admin_group_test": "🧪 Тест отправки",
    "btn_admin_group_off": "🗑 Удалить группу",
    "btn_reports_refresh": "🔄 Обновить",
    "btn_report_close": "✅ Закрыть #{id}",
    "btn_logs_clear": "🗑 Очистить логи",
    "admin_cookies": "<b>🍪 Файлы cookie</b>\n\nКоличество: <b>{count}</b>\n\n{list}\n\nДля YouTube/Instagram отправь файл <code>cookies.txt</code> (Netscape).",
    "btn_cookie_add": "➕ Добавить / загрузить",
    "btn_cookie_test": "🧪 Проверить",
    "cookie_add_prompt": "📄 Отправь файл <code>cookies.txt</code> или вставь текст Netscape.\n\nИнструкция: <code>docs/COOKIES.md</code>",
    "cookie_saved": "✅ Cookies сохранены: <b>{name}</b>\n🌐 Домены: <code>{domains}</code>",
    "cookie_bad": "❌ Некорректный файл cookie: {reason}",
    "cookie_deleted": "🗑 Файл cookie удалён: <b>{name}</b>",
    "cookie_missing": "❌ Такого файла cookie нет.",
    "cookie_test_result": "<b>🧪 Проверка cookie</b>\n\n{list}",
    "cookie_ok": "✅ В порядке",
    "cookie_problem": "⚠️ {reason}",
    "cookie_empty": "—",
    "cookie_text_only": "📄 Отправь файл <code>cookies.txt</code> или вставь текст Netscape.",
    "btn_admin_add": "➕ Добавить админа",
    "btn_ban": "🚫 Заблокировать",
    "btn_unban": "♻️ Разблокировать",
    "set_ttl": "⏳ Срок ссылки: {v} ч.",
    "set_upload": "📦 Макс. загрузка: {v} МБ",
    "set_link": "🔗 Макс. файл ссылки: {v} МБ",
    "set_rate": "🐢 Интервал запросов: {v} с.",
    "set_quota": "📉 Дневная квота: {v}",
    "set_maintenance": "🛠 Обслуживание {flag}",
    "set_nsfw": "🔞 Взрослые сайты {flag}",
    "admin_limit_reached": "⛔️ Достигнут лимит админов ({max}).",
    "admin_env_admin": "Этот пользователь указан в ADMIN_IDS; удали его из env.",

    # ── Статус ──
    "status": (
        "<b>📊 Ваш статус</b>\n\n"
        "🆔 ID: <code>{uid}</code>\n"
        "⬇️ Загрузок: <b>{downloads}</b>\n"
        "📅 С нами с: {joined}\n"
        "👑 Админ: {admin}\n"
        "🤖 Версия: <b>v{version}</b>"
    ),
    "yes": "да",
    "no": "нет",

    # ── Сайты ──
    "sites_title": (
        "<b>🌐 Поддерживаемые сайты</b>\n\n"
        "Активных экстракторов: <b>{count}</b>\n"
        "Поиск: <code>/sites instagram</code>\n\n"
        "<b>Популярные:</b>\n{popular}"
    ),
    "sites_search": "<b>🔍 Результаты «{q}»</b> ({count})\n\n{list}",
    "sites_none": "Ничего не найдено.",

    # ── Админ ──
    "admin_only": "⛔️ Только для администраторов.",
    "admin_panel": "<b>👑 Панель администратора</b>\n\nВыбери раздел:",
    "admin_stats": (
        "<b>📈 Статистика бота</b>\n\n"
        "👥 Всего пользователей: <b>{users}</b>\n"
        "🟢 Активных (7 дней): <b>{active_users}</b>\n"
        "🚫 Заблокировано: <b>{banned}</b>\n"
        "⬆️ Загружается сейчас: <b>{uploading}</b>\n"
        "🔗 Активных прямых ссылок: <b>{active_links}</b>\n"
        "🚨 Открытых жалоб: <b>{reports}</b>\n"
        "🛡 Админов: <b>{admins}</b>\n"
        "📥 Задач за 24 ч: <b>{jobs}</b> (✅ {done} / ❌ {failed})\n"
        "⚡️ Активных задач: <b>{active}</b>\n"
        "💾 Диск: <b>{disk}</b>\n"
        "⏱ Аптайм: <b>{uptime}</b>\n"
        "🤖 Версия: <b>v{version}</b>"
    ),
    "admin_jobs": "<b>🧾 Последние задачи</b>\n\n{list}",
    "admin_admins": "<b>👥 Администраторы</b>\n\n👑 Владелец: {owners}\n🛡 Дополнительные админы:\n{admins}",
    "admin_add_prompt": "Отправь числовой ID или @username пользователя:",
    "admin_add_ok": "✅ Админ добавлен: <code>{uid}</code>",
    "admin_add_fail": "❌ Не найдено (пользователь должен сначала отправить /start).",
    "admin_remove_ok": "🗑 Админ удалён: <code>{uid}</code>",
    "admin_remove_fail": "❌ Это не администратор.",
    "admin_owner_immutable": "⛔️ Владельца нельзя удалить.",
    "admin_settings": (
        "<b>⚙️ Настройки бота</b>\n\n"
        "⏳ Срок ссылки: <b>{ttl} ч.</b>\n"
        "📦 Макс. загрузка: <b>{max_upload} МБ</b>\n"
        "🔗 Макс. файл ссылки: <b>{max_link} МБ</b>\n"
        "🐢 Интервал запросов: <b>{rate} с.</b>\n"
        "⛔️ Обслуживание: <b>{maintenance}</b>\n"
        "🔞 Взрослые сайты: <b>{nsfw}</b>"
    ),
    "admin_set_value": "Отправь новое значение для <b>{label}</b>:",
    "admin_set_ok": "✅ Сохранено: {label} = <b>{value}</b>",
    "admin_bad_value": "❌ Некорректное значение.",
    "admin_broadcast_prompt": "Отправь текст рассылки:",
    "admin_broadcast_started": "📢 Отправка {count} пользователям…",
    "admin_broadcast_done": "✅ Рассылка завершена.\nУспешно: {ok} • Ошибок: {fail}",
    "admin_user_prompt": "Отправь ID пользователя:",
    "admin_user_info": (
        "<b>🔎 Пользователь</b>\n\n🆔 <code>{uid}</code>\n👤 {name}\n🔗 @{username}\n"
        "📥 Загрузок: {downloads}\n🚫 Заблокирован: {banned}\n"
        "🛡 Админ: {admin}\n📅 Регистрация: {joined}"
    ),
    "admin_cleanup_done": "🧹 Очистка выполнена.\nУдалено файлов: {files}\nОсвобождено: {size}",
    "admin_ban_prompt": "Отправь числовой ID, @username или пересланное сообщение пользователя, чтобы изменить блокировку.",
    "admin_forward_hint": "💡 Можно также переслать сообщение пользователя.",
    "admin_group_panel": (
        "<b>👥 Группа администраторов</b>\n\n"
        "Статус: {status}\nГруппа: <b>{title}</b>\nID чата: <code>{chat}</code>\n\n"
        "📥 Тема загрузок: {downloads}\n📤 Тема выгрузок: {uploads}\n"
        "🚨 Тема жалоб: {reports}\n🐞 Тема логов: {logs}\n\n{hint}"
    ),
    "admin_group_configured": "✅ Настроена",
    "admin_group_not_configured": "❌ Не настроена",
    "admin_group_topic_ok": "✅",
    "admin_group_topic_missing": "—",
    "admin_group_hint_ok": "Сообщения пользователей, ошибки и уведомления о загрузке идут в эти темы.",
    "admin_group_hint_setup": "Чтобы настроить: добавь бота в группу с включёнными <b>Topics</b>, сделай его админом и отправь <code>/setup</code> в группе.\nИли нажми «числовой ID», чтобы ввести ID группы вручную.",
    "admin_group_prompt": "Отправь числовой ID группы (например, <code>-1001234567890</code>):",
    "admin_group_bad_id": "❌ Некорректный ID группы.",
    "admin_group_saved": "✅ Группа админов сохранена.\nСоздано тем: {created}\nОшибок: {failed}\n\nЕсли тема не создана, проверь <b>Topics</b> и права админа у бота.",
    "admin_group_off_done": "🗑 Группа админов удалена.",
    "admin_group_test_ok": "✅ Тестовое сообщение отправлено в группу.",
    "admin_group_test_fail": "❌ Отправка не удалась; проверь настройки группы и права бота.",
    "setup_private": "Эту команду нужно отправлять <b>внутри группы</b>.\nДобавь бота в группу с Topics и отправь <code>/setup</code> там.",
    "setup_need_admin": "⛔️ Только админы бота могут настроить группу логов.",
    "setup_not_group": "Этот чат не является группой.",
    "setup_done": "✅ Группа админов настроена.\n\n📥 Загрузки: {downloads}\n📤 Выгрузки: {uploads}\n🚨 Жалобы: {reports}\n🐞 Логи: {logs}\n\nЕсли значение «—», включи Topics и сделай бота админом.",
    "admin_reports": "<b>🚨 Открытые жалобы</b> ({count})\n\n{list}",
    "admin_reports_empty": "Открытых жалоб нет.",
    "admin_report_item": "{icon} <b>#{id}</b> · {kind} · {when}\n👤 {name} (@{username}) · <code>{uid}</code>\n{body}",
    "admin_report_kind_contact": "Сообщение пользователя",
    "admin_report_kind_unsupported": "Проблемный сайт",
    "admin_report_closed": "✅ Жалоба #{id} закрыта.",
    "admin_report_missing": "❌ Такой жалобы нет.",
    "admin_logs": "<b>🐞 Последние логи</b> ({count})\n\n{list}",
    "admin_logs_empty": "Логи не записаны.",
    "admin_logs_cleared": "🗑 Удалено записей: {count}.",
    "admin_runtime": "<b>🛠 Переменные окружения</b>\n\nВводи значения здесь; доступ к серверу не нужен.\nНажми на пункт, чтобы изменить.\n\n⚠️ Изменения Bot API применяются после перезапуска.",
    "admin_runtime_prompt": "Отправь новое значение для <b>{label}</b>.\nОтправь <code>-</code>, чтобы очистить.",
    "admin_runtime_saved": "✅ Сохранено: {label} = <b>{value}</b>",
    "admin_runtime_restart": "ℹ️ Применится после перезапуска бота.",
    "state_text_only": "✍️ Отправь ответ текстом.",

    # ── Новый интерфейс ──
    "btn_kb_close": "⌨️ Закрыть клавиатуру",
    "kb_closed": "⌨️ Клавиатура закрыта. Отправь /start, чтобы вернуть её.",
    "settings_panel": "<b>⚙️ Настройки</b>\n\n🌍 Язык: <b>{lang}</b>\n🤖 Версия: <b>{version}</b>\n\nИспользуй кнопки ниже:",
    "lang_title": "<b>🌍 Выбор языка</b>\n\nТекущий: <b>{current}</b>\n\nLanguage · Язык · زبان",
    "lang_saved": "✅ Язык изменён на <b>{lang}</b>.",
    "version_info": (
        "<b>🤖 LeechX v{version}</b> · {codename}\n"
        "📅 Выпуск: {date}\n🐍 Python: {python}\n🎬 yt-dlp: {ytdlp}\n"
        "🎞 ffmpeg: {ffmpeg}\n⏱ Аптайм: {uptime}"
    ),
    "btn_local_api_help": "ℹ️ Что такое Local Bot API?",
    "local_api_help": (
        "<b>ℹ️ Что такое Local Bot API Server?</b>\n\n"
        "Публичный Bot API Telegram ограничивает скачивание <b>20 МБ</b>, а "
        "загрузку — <b>50 МБ</b>. Если запустить сервер Bot API на той же машине, "
        "лимит поднимается до <b>2000 МБ</b>, а файлы читаются прямо с диска "
        "(быстрее, без повторной загрузки).\n\n"
        "<b>Как включить</b>\n"
        "1) Получи <b>API ID</b> и <b>API Hash</b> на <code>my.telegram.org</code>.\n"
        "2) Запусти сервис:\n<code>docker compose --profile localapi up -d</code>\n"
        "3) В этой панели (переменные) задай:\n"
        "• Local Bot API URL: <code>http://telegram-bot-api:8081/bot</code>\n"
        "• File URL: <code>http://telegram-bot-api:8081/file/bot</code>\n"
        "• API ID и API Hash\n"
        "4) Перезапусти бота.\n\n"
        "⚠️ Необязательно. Для небольших файлов хватает обычного Bot API. "
        "Папка <code>data/tg-bot-api</code> должна быть общей у бота и сервера."
    ),
    "btn_ytdlp_help": "🎬 Как добавить больше сайтов?",
    "ytdlp_help": (
        "<b>🎬 Добавление новых сайтов</b>\n\n"
        "Все сайты берутся из <b>yt-dlp</b>: всё, что он поддерживает, работает "
        "в боте автоматически (1800+ сайтов).\n\n"
        "<b>Правильный путь:</b> просто обнови yt-dlp, код бота менять не нужно.\n"
        "Открой «Деплой» → «🔄 Обновить yt-dlp». Новая версия установится, "
        "индекс сайтов пересоберётся, бот перезапустится.\n\n"
        "<b>Взрослые сайты:</b> это обычные экстракторы yt-dlp; они добавляются "
        "и исправляются с обновлениями. Для сайтов с входом загрузи "
        "<code>cookies.txt</code> в панели (🍪 Cookies).\n\n"
        "⚠️ Некоторые сайты требуют вход/защиту от ботов; без cookie их не "
        "скачает ни один инструмент."
    ),

    # ── Категории админки ──
    "btn_cat_stats": "📊 Статистика и мониторинг",
    "btn_cat_users": "👥 Пользователи и доступ",
    "btn_cat_settings": "⚙️ Настройки бота",
    "btn_cat_groups": "🔐 Группы и подписка",
    "btn_cat_deploy": "🚀 Деплой и обновления",
    "btn_cat_debug": "🩺 Диагностика",
    "btn_back_cats": "↩️ Категории",
    "admin_cat_stats": "<b>📊 Статистика и мониторинг</b>\n\nЖивой статус, задачи, жалобы и логи:",
    "admin_cat_users": "<b>👥 Пользователи и доступ</b>\n\nПоиск, блокировка, админы и рассылка:",
    "admin_cat_settings": "<b>⚙️ Настройки бота</b>\n\nЛимиты, переменные, cookies и очистка:",
    "admin_cat_groups": "<b>🔐 Группы и подписка</b>\n\nГруппа логов и обязательная подписка:",
    "admin_cat_deploy": "<b>🚀 Деплой и обновления</b>\n\nИсходники, бэкап, перезапуск и обновление yt-dlp:",
    "admin_cat_debug": "<b>🩺 Диагностика</b>\n\nЗдоровье сервисов и временный токен для ИИ:",

    # ── Обязательная подписка ──
    "btn_admin_join": "🔐 Обязательная подписка",
    "btn_admin_join_add": "➕ Добавить канал/группу",
    "btn_admin_join_toggle": "🔐 Подписка {flag}",
    "btn_admin_join_check": "🧪 Проверить доступ бота",
    "admin_join_panel": (
        "<b>🔐 Обязательная подписка</b>\n\n"
        "Статус: <b>{status}</b>\nЦелей: <b>{count}</b>\n\n{list}\n\n"
        "Пока пользователь не подпишется на всё выше, бот ему недоступен. "
        "Бот должен быть <b>админом</b> в каждом канале/группе для проверки."
    ),
    "admin_join_empty": "— Пока ничего не добавлено.",
    "admin_join_added": "✅ Добавлено: <b>{title}</b>\n🆔 <code>{chat}</code>",
    "admin_join_removed": "🗑 Удалено: <b>{title}</b>",
    "admin_join_bad": "❌ Не найдено или нет доступа. Сделай бота админом и повтори.",
    "admin_join_admin_needed": "⚠️ Чтобы проверять подписку, бот должен быть админом в <b>{title}</b>.",
    "admin_join_check_ok": "✅ Все цели в порядке, бот является админом.",
    "admin_join_check_mixed": "⚠️ Есть проблемы:\n{list}",
    "admin_join_prompt": "Отправь username (<code>@channel</code>), числовой ID (<code>-100...</code>) или пересланное сообщение из канала/группы:",
    "admin_join_hint": "💡 Бот должен быть админом. Для приватного канала перешли одно из его сообщений.",
    "join_gate_title": (
        "<b>🔐 Доступ ограничен</b>\n\n"
        "Чтобы пользоваться ботом, сначала подпишись:\n\n{list}\n\n"
        "После подписки нажми «✅ Я подписался»."
    ),
    "join_gate_btn": "✅ Я подписался",
    "join_gate_still": "❌ Ты ещё не подписан. Подпишись и проверь снова.",
    "join_gate_ok": "✅ Подписка подтверждена. Теперь можно пользоваться ботом.",
    "join_gate_error": "⚠️ Сейчас не удалось проверить подписку. Попробуй через минуту.",

    # ── Деплой ──
    "btn_admin_deploy": "🚀 Деплой",
    "deploy_panel": (
        "<b>🚀 Деплой и обновления</b>\n\n"
        "🤖 Версия: <b>v{version}</b> ({codename})\n"
        "🎬 yt-dlp: <b>{ytdlp}</b>\n🐍 Python: <b>{python}</b>\n"
        "📦 Размер исходников: <b>{size}</b>\n"
        "💾 Последний бэкап: {backup}\n🕒 Последнее обновление: {last_update}\n\n"
        "Скачай текущие исходники в ZIP или загрузи новый ZIP — проверка, "
        "бэкап и перезапуск произойдут автоматически."
    ),
    "btn_deploy_source": "⬇️ Скачать исходники (ZIP)",
    "deploy_source_caption": (
        "📦 <b>Исходники LeechX v{version}</b>\n"
        "🗂 Файлов: {files} · {size}\n"
        "🚫 Без <code>.env</code> и папки <code>data</code> (приватные данные)\n\n"
        "Этот файл можно передать ИИ или на другой сервер."
    ),
    "btn_deploy_upload": "⬆️ Загрузить новые исходники",
    "deploy_upload_prompt": "📦 Отправь <b>ZIP</b> с новыми исходниками.\n\n• Подойдёт обычный ZIP или архив GitHub\n• Сначала проверка, применение только после подтверждения\n• Текущие исходники сохраняются в бэкап",
    "deploy_zip_bad": "❌ Некорректный ZIP: {reason}",
    "deploy_zip_too_big": "❌ Файл слишком большой ({size} > {max}).",
    "deploy_staged": (
        "<b>📦 Новые исходники готовы</b>\n\n"
        "Версия: <b>v{current}</b> → <b>v{new}</b>\n"
        "🗂 Файлов: {files}\n📦 Размер: {size}\n{notes}\n\n"
        "После «Применить» текущие исходники уйдут в бэкап, файлы заменятся, "
        "а бот перезапустится автоматически."
    ),
    "btn_deploy_apply": "🚀 Применить и перезапустить",
    "btn_deploy_cancel": "✖️ Отмена",
    "deploy_applied": "✅ Исходники обновлены до <b>v{version}</b>.\n♻️ Перезапуск через несколько секунд…",
    "deploy_failed": "❌ Не удалось применить: {reason}\nТекущие исходники не изменены.",
    "btn_deploy_backup": "🗄 Скачать последний бэкап",
    "deploy_no_backup": "⚠️ Бэкапов пока нет.",
    "deploy_backup_caption": "🗄 Бэкап исходников до обновления — {when}",
    "btn_deploy_restart": "♻️ Перезапустить бота",
    "deploy_restart_confirm": "⚠️ Уверен? Бот будет недоступен несколько секунд.",
    "deploy_restart_scheduled": "♻️ Перезапуск начат; вернётся через несколько секунд.",
    "btn_deploy_ytdlp": "🔄 Обновить yt-dlp",
    "btn_deploy_ytdlp_nightly": "🌙 Ночная сборка",
    "deploy_ytdlp_done": "✅ yt-dlp обновлён: <b>{before}</b> → <b>{after}</b>\n🌐 Индекс сайтов пересобран.\n♻️ Перезапусти бота, чтобы загрузить новые экстракторы.",
    "deploy_ytdlp_fail": "❌ Не удалось обновить yt-dlp: {reason}",
    "deploy_ytdlp_working": "⏳ Обновляю yt-dlp…",
    "btn_deploy_version": "🔢 Детали версии",
    "deploy_update_note": "ℹ️ Применение исходников меняет только файлы программы; <code>.env</code>, база и <code>data</code> остаются.",

    # ── Диагностика / временный токен ──
    "btn_admin_debug": "🩺 Диагностика",
    "debug_panel": (
        "<b>🩺 Диагностика</b>\n\n"
        "Доступ по токену: <b>{state}</b>\nАктивных токенов: <b>{active}</b>\n\n"
        "Создай <b>ограниченный по времени</b> токен и передай ИИ, чтобы он "
        "увидел живые исходники и состояние, нашёл проблему, исправил код и "
        "задеплоил. Токен умирает по истечении срока и отзывается в любой момент.\n\n"
        "🔒 Полный токен показывается один раз; в базе хранится только хэш."
    ),
    "debug_disabled": (
        "⚠️ Доступ для отладки выключен. Включи его кнопкой «🔴 Доступ для "
        "отладки» в этом разделе — «Переменные» не нужны."
    ),
    "btn_debug_toggle": "Доступ для отладки {flag}",
    "debug_toggle_on": "🟢 Доступ для отладки включён.",
    "debug_toggle_off": "🔴 Доступ для отладки выключен.",
    "btn_debug_make_read": "🔎 Только чтение",
    "btn_debug_make_write": "🛠 Чтение + правка кода",
    "btn_debug_make_restart": "♻️ Полный (с перезапуском)",
    "btn_debug_ttl": "⏳ {hours} ч.",
    "debug_scope_read": "только чтение",
    "debug_scope_write": "чтение + запись",
    "debug_scope_restart": "полный",
    "debug_token_created": (
        "<b>🔑 Токен отладки создан</b>\n\n"
        "🌐 Адрес: <code>{base}</code>\n🔑 Токен:\n<code>{token}</code>\n\n"
        "🎚 Права: <b>{scopes}</b>\n⏳ Истекает: <b>{expires}</b> ({hours} ч.)\n\n"
        "<b>Передай ИИ:</b>\n1) Адрес и токен\n2) <code>docs/DEBUG_API_FA.md</code>\n\n"
        "Пример:\n<code>curl -H \"Authorization: Bearer {token}\" {base}/debug/health</code>\n\n"
        "⚠️ Не пересылай это сообщение. Закрой токен после работы."
    ),
    "debug_no_public_url": "⚠️ <b>PUBLIC_BASE_URL</b> = <code>{base}</code>, недоступен из интернета. Токен работает только внутри сервера/сети. Укажи публичный домен или IP в «Переменных».",
    "debug_tokens_list": "<b>🔑 Активные токены</b>\n\n{list}",
    "debug_token_item": "• <code>{id}</code> · {scopes} · до {expires} · использован {uses}×",
    "debug_none": "— Активных токенов нет.",
    "debug_revoke_ok": "🗑 Токен закрыт.",
    "debug_revoke_fail": "❌ Токен не найден.",
    "btn_debug_health": "🧪 Проверка здоровья",
    "debug_health": (
        "<b>🩺 Отчёт о здоровье</b>\n\n"
        "🤖 Версия: <b>v{version}</b>\n🐍 Python: {python}\n🎬 yt-dlp: {ytdlp}\n"
        "🎞 ffmpeg: {ffmpeg}\n🗄 База: {db}\n💾 Диск: {disk}\n🌐 Веб-сервер: {web}\n"
        "⚡️ Активных задач: {jobs}\n👥 Пользователей: {users}\n\n{problems}"
    ),
    "debug_health_problem": "⚠️ Проблемы:\n{list}",
    "debug_health_ok": "✅ Явных проблем не найдено.",
    "debug_handoff": (
        "🤝 <b>Передача ИИ</b>\n\nОтправь этот текст вместе с токеном:\n"
        "<code>You have a time-limited LeechX debug token. API base: {base}. "
        "Docs: docs/DEBUG_API_FA.md. Read /debug/health, /debug/logs and "
        "/debug/source first, fix the code, then POST /debug/source and "
        "POST /debug/restart. Never print the token.</code>"
    ),
    "btn_debug_revoke_all": "🗑 Закрыть все токены",
    "btn_admin_preview": "👁 Просмотр глазами пользователя",
    "btn_preview": "👁 Режим пользователя",
    "preview_banner": "👁 <b>Режим просмотра пользователя</b>\n\nТы видишь ровно то же, что обычный пользователь. Права админа временно отключены.",
    "btn_preview_exit": "🚪 Выйти из режима пользователя",
    "preview_exit_done": "✅ Вернулся в режим администратора.",
    "preview_blocked": "👁 Ты в режиме пользователя; сначала выйди из него.",
    "admin_preview_panel": "<b>👁 Просмотр глазами пользователя</b>\n\nМеню и права станут как у обычного пользователя — второй аккаунт не нужен.\n\nНажми «🚪 Выйти из режима пользователя», чтобы вернуться.",

    # ── Названия переменных ──
    "run_link_ttl_hours": "Срок ссылки (часы)",
    "run_max_upload_mb": "Макс. загрузка (МБ)",
    "run_max_link_mb": "Макс. файл ссылки (МБ)",
    "run_rate_limit_seconds": "Интервал запросов (секунды)",
    "run_daily_quota": "Дневная квота (0 = без лимита)",
    "run_maintenance": "Режим обслуживания",
    "run_nsfw_enabled": "Взрослые сайты",
    "run_public_base_url": "Публичный адрес ссылок",
    "run_proxy": "Прокси загрузки",
    "run_telegram_api_url": "Local Bot API URL",
    "run_telegram_api_file_url": "Local Bot API file URL",
    "run_telegram_api_id": "Telegram API ID",
    "run_telegram_api_hash": "Telegram API Hash",
    "run_owner_id": "Владелец бота",
    "run_admin_group_id": "ID группы админов",
    "run_admin_group_title": "Название группы админов",
    "run_topic_downloads": "Тема загрузок",
    "run_topic_uploads": "Тема выгрузок",
    "run_topic_reports": "Тема жалоб",
    "run_topic_logs": "Тема логов",
    "run_topic_cache": "Тема кэша медиа",
    "run_topic_audit": "Тема аудита",
    "run_topic_security": "Тема безопасности",
    "run_force_join_enabled": "Обязательная подписка",
    "run_force_join_chats": "Каналы/группы подписки",
    "run_debug_enabled": "Доступ по токену отладки",
    "run_debug_ip_allow": "Разрешённые IP для токена",
    "btn_reports_persistent": "📨 Жалобы",
    "btn_cancel_tasks": "✖️ Отменить задачи",
    "btn_home_persistent": "🏠 Домой",
    "debug_token_button": "🔑 Токен #{id} · {scopes}",
}

MESSAGES: dict[str, dict[str, str]] = {"fa": FA, "en": EN, "ru": RU}


def t(lang: str, key: str, **kwargs) -> str:
    if lang not in FALLBACK:
        lang = normalize_lang(lang)
    chain = FALLBACK[lang]
    raw = None
    for code in chain:
        table = MESSAGES.get(code)
        if table and key in table:
            raw = table[key]
            break
    if raw is None:
        raw = FA.get(key) or key
    if kwargs:
        try:
            return raw.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return raw
    return raw
