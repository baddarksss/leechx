"""متن‌های دوزبانه (فارسی/انگلیسی) — تنها منبع رشته‌های کاربری.

برای اضافه‌کردن زبان جدید: یک دیکشنری دیگر بنویس و در ``LANGS`` اضافه کن.
"""
from __future__ import annotations

LANGS: dict[str, str] = {"fa": "فارسی", "en": "English"}
DEFAULT_LANG = "fa"

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
        "/me وضعیت من • /cancel لغو"
    ),
    "send_link_or_file": "🔗 یک لینک یا فایل بفرست.",
    "probing": "🔍 در حال بررسی لینک…",
    "choose_quality": "<b>{title}</b>\n\n🎬 کیفیت مورد نظر را انتخاب کن:",
    "video_btn": "🎬 {label}",
    "audio_btn": "🎵 {label}",
    "quality_title": "<b>{title}</b>",
    "cancel_btn": "✖️ لغو",
    "canceled": "✖️ لغو شد.",
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

    # ── دکمه‌های منو ──
    "btn_help": "📖 راهنما",
    "btn_status": "📊 وضعیت من",
    "btn_sites": "🌐 سایت‌های پشتیبانی",
    "btn_settings": "⚙️ تنظیمات",
    "btn_admin": "👑 پنل ادمین",
    "btn_back": "↩️ بازگشت",
    "btn_close": "✖️ بستن",
    "btn_lang": "🌍 زبان",
    "btn_admin_stats": "📈 آمار",
    "btn_admin_jobs": "🧾 کارهای اخیر",
    "btn_admin_admins": "👥 ادمین‌ها",
    "btn_admin_settings": "⚙️ تنظیمات ربات",
    "btn_admin_broadcast": "📢 پیام همگانی",
    "btn_admin_users": "🔎 کاربر",
    "btn_admin_cleanup": "🧹 پاک‌سازی",

    # ── وضعیت ──
    "status": (
        "<b>📊 وضعیت شما</b>\n\n"
        "🆔 شناسه: <code>{uid}</code>\n"
        "⬇️ دانلودها: <b>{downloads}</b>\n"
        "📅 عضو از: {joined}\n"
        "👑 ادمین: {admin}"
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
        "👥 کاربران: <b>{users}</b>\n"
        "🛡 ادمین‌ها: <b>{admins}</b>\n"
        "📥 کارهای ۲۴ ساعت: <b>{jobs}</b> (✅ {done} / ❌ {failed})\n"
        "⚡️ کارهای فعال: <b>{active}</b>\n"
        "🔗 فایل‌های لینک‌دار: <b>{shared}</b> ({shared_size})\n"
        "💾 فضای دیسک: <b>{disk}</b>\n"
        "⏱ آپتایم: <b>{uptime}</b>"
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
    "state_text_only": "✍️ لطفاً پاسخ را به‌صورت متن بفرست.",
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
        "/start /help /sites /me /cancel"
    ),
    "send_link_or_file": "🔗 Send a link or a file.",
    "probing": "🔍 Inspecting link…",
    "choose_quality": "<b>{title}</b>\n\n🎬 Pick a quality:",
    "video_btn": "🎬 {label}",
    "audio_btn": "🎵 {label}",
    "quality_title": "<b>{title}</b>",
    "cancel_btn": "✖️ Cancel",
    "canceled": "✖️ Canceled.",
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
    "btn_help": "📖 Help",
    "btn_status": "📊 My status",
    "btn_sites": "🌐 Supported sites",
    "btn_settings": "⚙️ Settings",
    "btn_admin": "👑 Admin panel",
    "btn_back": "↩️ Back",
    "btn_close": "✖️ Close",
    "btn_lang": "🌍 Language",
    "btn_admin_stats": "📈 Stats",
    "btn_admin_jobs": "🧾 Recent jobs",
    "btn_admin_admins": "👥 Admins",
    "btn_admin_settings": "⚙️ Bot settings",
    "btn_admin_broadcast": "📢 Broadcast",
    "btn_admin_users": "🔎 User",
    "btn_admin_cleanup": "🧹 Cleanup",
    "status": (
        "<b>📊 Your status</b>\n\n"
        "🆔 <code>{uid}</code>\n⬇️ Downloads: <b>{downloads}</b>\n"
        "📅 Joined: {joined}\n👑 Admin: {admin}"
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
        "<b>📈 Bot stats</b>\n\n👥 Users: <b>{users}</b>\n🛡 Admins: <b>{admins}</b>\n"
        "📥 Jobs 24h: <b>{jobs}</b> (✅ {done} / ❌ {failed})\n⚡️ Active: <b>{active}</b>\n"
        "🔗 Shared links: <b>{shared}</b> ({shared_size})\n💾 Disk: <b>{disk}</b>\n⏱ Uptime: <b>{uptime}</b>"
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
    "state_text_only": "✍️ Please send your answer as text.",
}

MESSAGES: dict[str, dict[str, str]] = {"fa": FA, "en": EN}


def t(lang: str, key: str, **kwargs) -> str:
    table = MESSAGES.get(lang) or MESSAGES[DEFAULT_LANG]
    text = table.get(key) or FA.get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text
