# 🍪 کوکی‌ها — راهنمای کامل / Cookies Guide

کوکی برای سایت‌هایی لازم است که بدون ورود، محتوا را نشان نمی‌دهند یا ربات را
مسدود می‌کنند: **یوتیوب** («Sign in to confirm you're not a bot»)،
**اینستاگرام** (پست/ریلز خصوصی یا محدود)، تیک‌تاک، توییتر/X، فیس‌بوک و چند سایت دیگر.

LeechX هم فایل **Netscape `cookies.txt`** و هم خروجی **JSON** بعضی افزونه‌ها را
می‌پذیرد و JSON را خودکار به Netscape تبدیل می‌کند.

---

## ۱) سریع‌ترین راه: از پنل ادمین

1. در تلگرام وارد **👑 پنل ادمین → 🍪 کوکی‌ها** شو.
2. **➕ افزودن / آپلود** را بزن.
3. یکی از این دو کار را انجام بده:
   - فایل `cookies.txt` را به‌صورت **Document** بفرست، یا
   - متن Netscape را در پیام **پیست** کن.
4. نام فایل خودکار از دامنه‌ها ساخته می‌شود (`youtube.txt`، `instagram.txt`، …).
5. با **🧪 بررسی** سلامت فایل‌ها را چک کن. فایل خراب یا منقضی با ⚠️ نشان داده می‌شود.
6. برای حذف، روی دکمهٔ 🗑 نام فایل بزن.

> سقف حجم فایل کوکی **۲ مگابایت** است. فایل HTML (صفحهٔ لاگین) یا فایل باینری
> رد می‌شود.

---

## ۲) ساخت فایل کوکی در مرورگر

### الف) افزونهٔ مرورگر (پیشنهادی)

1. در مرورگر وارد سایت شو و **لاگین کن** (مثلاً `youtube.com` یا `instagram.com`).
2. یکی از افزونه‌های زیر را نصب کن:
   - **Get cookies.txt LOCALLY** (Chrome / Firefox / Edge)
   - **EditThisCookie** (Chrome)
   - **cookies.txt** (Firefox)
3. در همان تبِ سایت، افزونه را باز کن و **Export / Download** بزن.
4. فایل `cookies.txt` را از پنل ادمین آپلود کن.

نکته‌ها:

- حتماً از همان دامنه‌ای export بگیر که می‌خواهی دانلود کنی. کوکی `youtube.com`
  برای `instagram.com` کار نمی‌کند.
- اگر افزونه خروجی JSON می‌دهد، همان را هم می‌توانی آپلود کنی؛ خودکار تبدیل می‌شود.
- حالت **Incognito/Private** معمولاً کوکی معتبر نمی‌دهد؛ از پنجرهٔ عادی استفاده کن.

### ب) با yt-dlp

اگر `yt-dlp` روی سیستم/سرور نصب است:

```bash
# کروم
yt-dlp --cookies-from-browser chrome --cookies youtube.txt "https://www.youtube.com/watch?v=..."

# فایرفاکس
yt-dlp --cookies-from-browser firefox --cookies youtube.txt "https://www.youtube.com/watch?v=..."
```

فایل تولیدشده را در پنل ادمین آپلود کن یا مستقیم در پوشهٔ کوکی‌ها بگذار.

---

## ۳) گذاشتن دستی فایل روی سرور

اگر به پنل ادمین دسترسی نداری، فایل را داخل `COOKIES_DIR` (پیش‌فرض
`./data/cookies`) بگذار:

```text
data/cookies/youtube.txt
data/cookies/instagram.txt
data/cookies/tiktok.txt
```

**انتخاب خودکار:** هنگام دانلود، ربات دامنهٔ لینک را با دامنه‌های داخل فایل
مقایسه می‌کند و دقیق‌ترین تطبیق را انتخاب می‌کند. اگر دامنهٔ داخل فایل خوانده
نشود، نام فایل هم بررسی می‌شود (`youtube.txt` → `youtube.com`).

فایل باید با UTF-8 ذخیره شود. خط اول استاندارد این است:

```text
# Netscape HTTP Cookie File
```

---

## ۴) فرمت درست (Netscape)

هر خط ۷ ستون دارد و با **Tab** جدا می‌شود:

```text
domain  include_subdomains  path  secure  expires  name  value
.youtube.com	TRUE	/	TRUE	0	SID	abc123
.youtube.com	TRUE	/	TRUE	0	HSID	def456
```

- `expires = 0` یعنی کوکی سشن است.
- خطوطی که با `#` شروع می‌شوند (به‌جز `#HttpOnly_`) نادیده گرفته می‌شوند.
- پیشوند `#HttpOnly_` پشتیبانی می‌شود.

---

## ۵) خطاهای رایج

| پیام | معنی | راه‌حل |
|---|---|---|
| `no cookie lines` | فایل، خط معتبر Netscape ندارد | با افزونهٔ درست دوباره export کن |
| `HTML page, not a cookie file` | فایل HTML صفحهٔ لاگین است | فایل `cookies.txt` را از افزونه بگیر |
| `file is not UTF-8 text` | فایل باینری/رمزگذاری‌شده است | فایل متنی UTF-8 بفرست |
| `all cookies expired` | همهٔ کوکی‌ها منقضی شده‌اند | دوباره لاگین و export کن |
| `Login required` هنگام دانلود | کوکی اشتباه/منقضی است | کوکی همان دامنه را دوباره بگیر |
| `Private content` | محتوا واقعاً خصوصی است | با همان اکانتی که دسترسی دارد کوکی بگیر |

---

## ۶) امنیت

- فایل کوکی مثل **رمز عبور** است؛ هر کسی آن را داشته باشد می‌تواند وارد حساب شود.
- فایل‌ها فقط روی سرور خودت در `COOKIES_DIR` ذخیره می‌شوند و در دیتابیس یا
  پیام‌های تلگرام نگه‌داری نمی‌شوند.
- دسترسی پوشه را محدود کن:

  ```bash
  chmod 700 data/cookies
  chmod 600 data/cookies/*.txt
  ```

- کوکی‌ها را در Git یا بکاپ عمومی نگذار (`.gitignore` پروژه `data/` را کنار می‌گذارد).
- اگر فایل لو رفت، از حساب خارج شو (Log out all sessions) و کوکی جدید بگیر.

---

## ۷) انقضا و به‌روزرسانی

کوکی‌های یوتیوب/اینستاگرام معمولاً چند هفته تا چند ماه عمر می‌کنند. اگر دانلود
دوباره «Login required» داد:

1. در مرورگر از حساب خارج و دوباره وارد شو.
2. کوکی جدید export کن.
3. فایل قدیمی را با همان نام آپلود کن (جایگزین می‌شود) یا اول حذفش کن.
4. با **🧪 بررسی** مطمئن شو `all cookies expired` نداشته باشد.

---

## English (short version)

Cookies are needed for sites that hide content from anonymous clients, mainly
**YouTube** (“Sign in to confirm you’re not a bot”) and **Instagram** (private or
restricted posts/reels), plus TikTok, X/Twitter, Facebook and others.

### Add cookies from the bot

1. Open **👑 Admin panel → 🍪 Cookies**.
2. Tap **➕ Add / upload**.
3. Send a `cookies.txt` file as a document **or** paste Netscape text.
4. The file name is inferred from its domains (`youtube.txt`, `instagram.txt`, …).
5. Use **🧪 Validate** to check for expired or malformed files; 🗑 removes a file.

The limit is **2 MB**. HTML pages and binary files are rejected.

### Export cookies

- Install **Get cookies.txt LOCALLY** (Chrome/Firefox/Edge) or **EditThisCookie**.
- Log in to the target site in a normal (not private) window.
- Export cookies for that exact domain and upload the file.
- JSON exports are accepted and converted to Netscape automatically.

Or use yt-dlp:

```bash
yt-dlp --cookies-from-browser chrome --cookies youtube.txt "URL"
```

### Manual placement

Put UTF-8 files into `COOKIES_DIR` (default `./data/cookies`):

```text
data/cookies/youtube.txt
data/cookies/instagram.txt
```

The downloader matches the URL host against the domains inside each file and
falls back to the file name, so `youtube.txt` is used for `youtube.com` even if
the domain rows are unusual.

### Format

Tab-separated Netscape rows:

```text
domain  include_subdomains  path  secure  expires  name  value
.youtube.com	TRUE	/	TRUE	0	SID	abc123
```

`expires = 0` means a session cookie. `#HttpOnly_` prefixes are supported.

### Security

Treat cookie files like passwords: keep `data/cookies` at mode `700`, the files
at `600`, never commit them, and re-export after logging out all sessions if a
file leaks.

---

**حقوقی:** کوکی فقط برای دسترسی به محتوایی استفاده شود که اجازهٔ دانلودش را داری.
مسئولیت رعایت قوانین و شرایط استفادهٔ سرویس‌ها با اپراتور است.
