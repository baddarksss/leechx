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
        "<b>{title}</b>\n\n"
        "🎚 کیفیت: <b>{quality}</b>\n"
        "📦 حجم تقریبی: <b>{size}</b>\n"
        "🏷 نام فایل: <b>{name}</b>\n\n"
        "📤 قبل از شروع، نحوهٔ تحویل را انتخاب کن:"
    ),
    "deliver_video_btn": "🎬 ویدیو / رسانه",
    "deliver_doc_btn": "📄 فایل (Document)",
    "deliver_link_btn": "🔗 لینک مستقیم",
    "deliver_rename_btn": "✏️ تغییر نام",
    "deliver_back_btn": "↩️ انتخاب کیفیت",
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
    "setup_need_admin": "⛔️ فقط ادمین‌های ربات یا ادمین‌های گروه می‌توانند گروه را تنظیم کنند.",
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
        "<b>{title}</b>\n\n"
        "🎚 Quality: <b>{quality}</b>\n"
        "📦 Estimated size: <b>{size}</b>\n"
        "🏷 File name: <b>{name}</b>\n\n"
        "📤 Before we start, choose how to deliver it:"
    ),
    "deliver_video_btn": "🎬 Video / media",
    "deliver_doc_btn": "📄 File (document)",
    "deliver_link_btn": "🔗 Direct link",
    "deliver_rename_btn": "✏️ Rename",
    "deliver_back_btn": "↩️ Choose quality",
    "rename_prompt": "✏️ Send the new file name (extension not required):\nCurrent name: <code>{name}</code>",
    "rename_done": "✅ Name saved: <b>{name}</b>",
    "rename_bad": "❌ Invalid name; send a short name.",
    "btn_help": "📖 Help",
    "btn_status": "📊 My status",
    "btn_sites": "🌐 Supported sites",
    "btn_settings": "⚙️ Settings",
    "btn_contact": "✉️ Contact admin",
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
        "⏱ Uptime: <b>{uptime}</b>"
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
    "setup_need_admin": "⛔️ Only bot admins or group admins can configure the group.",
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
