# دسترسی موقت عیب‌یابی (Debug API)

این سند توضیح می‌دهد چطور بدون دادن دسترسی سرور یا پنل ادمین به هوش مصنوعی،
یک پنجرهٔ **زمان‌دار و محدود** برای خواندن وضعیت ربات، اصلاح سورس، اجرای تست و
دیپلوی باز کنیم.

---

## چرا توکن زمان‌دار؟

دادن رمز سرور یا ادمین ربات به یک ابزار بیرونی خطرناک است. به‌جای آن:

- توکن فقط **حداکثر ۲۴ ساعت** زنده است (سقف سخت، حتی اگر
  `DEBUG_TOKEN_MAX_HOURS` بزرگ‌تر باشد).
- در دیتابیس فقط **SHA-256** توکن ذخیره می‌شود؛ خود توکن یک‌بار نمایش داده می‌شود.
- سه سطح دسترسی جدا دارد: `read`، `write`، `restart`.
- هر لحظه از پنل ادمین قابل **ابطال** است (تکی یا همه).
- به‌صورت پیش‌فرض **خاموش** است و تا روشن نشود هیچ مسیری ثبت نمی‌شود.
- می‌توانید فهرست IP مجاز تعیین کنید.

> این API روی همان وب‌سرور لینک مستقیم (`PUBLIC_BASE_URL`) سوار می‌شود، پس
> پورت جدیدی باز نمی‌کند. اگر ربات پشت CDN/پروکسی است، IP واقعی را در
> «IPهای مجاز» بگذارید.

---

## ساختن توکن از ربات

1. پنل ادمین → 🩺 **عیب‌یابی**.
2. اگر خاموش است، «روشن‌کردن» را بزنید.
3. یکی از دکمه‌های مدت (۱، ۶، ۱۲، ۲۴ ساعت) و سطح دسترسی
   (`read` / `write` / `restart`) را انتخاب کنید.
4. توکن (`lxdbg_...`) فقط یک‌بار در پیام نمایش داده می‌شود؛ همان را کپی کنید.
5. پس از پایان کار، «ابطال همه» را بزنید و دسترسی را خاموش کنید.

---

## مسیرها

همهٔ پاسخ‌ها JSON هستند و خطاها شکل `{"ok": false, "error": "..."}` دارند.
احراز هویت با یکی از این دو هدر:

```
Authorization: Bearer lxdbg_...
X-Debug-Token: lxdbg_...
```

| متد | مسیر | سطح | کار |
|---|---|---|---|
| `GET` | `/debug/health` | read | نسخه، پایتون، yt-dlp، ffmpeg، دیتابیس، دیسک، کارهای فعال، مشکلات |
| `GET` | `/debug/state` | read | وضعیت زندهٔ تنظیمات، عضویت اجباری، محدودیت‌ها، آخرین آپدیت |
| `GET` | `/debug/logs?limit=50&level=ERROR` | read | آخرین لاگ‌های دیتابیس |
| `GET` | `/debug/source` | read | فهرست فایل‌های سورس |
| `GET` | `/debug/source?path=app/version.py` | read | محتوای یک فایل + SHA-256 |
| `POST` | `/debug/source` | write | نوشتن یک یا چند فایل سورس (با بکاپ خودکار) |
| `POST` | `/debug/pytest?path=tests/test_x.py` | write | اجرای تست‌ها و برگرداندن ۸۰ خط آخر |
| `POST` | `/debug/restart` | restart | ری‌استارت نرم ربات |
| `POST` | `/debug/ytdlp-update?nightly=1` | restart | به‌روزرسانی yt-dlp + بازسازی فهرست سایت‌ها |

### نمونه‌ها

```bash
BASE="https://bot.example.com"
TOKEN="lxdbg_..."
AUTH="Authorization: Bearer $TOKEN"

curl -s "$BASE/debug/health" -H "$AUTH" | jq
curl -s "$BASE/debug/state"  -H "$AUTH" | jq
curl -s "$BASE/debug/source?path=app/bot/flows/admin.py" -H "$AUTH" | jq -r .content
```

نوشتن فایل (بکاپ در `data/debug-backups/<timestamp>/` ذخیره می‌شود):

```bash
curl -s -X POST "$BASE/debug/source" -H "$AUTH" -H 'Content-Type: application/json' -d '{
  "files": {
    "app/bot/flows/admin.py": "...محتوای کامل فایل..."
  }
}'
```

فقط این مسیرها قابل نوشتن‌اند:
`app/`، `tests/`، `docs/`، `.github/` و فایل‌های ریشه مانند `main.py`،
`pyproject.toml`، `README.md`، `CHANGELOG.md` و `AGENTS.md`.
نوشتن `.env`، `data/`، `.git` و `__pycache__` **همیشه** رد می‌شود.

اجرای تست و ری‌استارت:

```bash
curl -s -X POST "$BASE/debug/pytest?path=tests/test_deploy_debug.py" -H "$AUTH" | jq
curl -s -X POST "$BASE/debug/restart" -H "$AUTH" | jq
```

---

## روند کاری پیشنهادی برای هوش مصنوعی

1. `GET /debug/health` و `GET /debug/state` → نسخه و وضعیت.
2. `GET /debug/logs?level=ERROR` → خطاهای واقعی.
3. `GET /debug/source?path=...` → خواندن فایل‌های مرتبط.
4. `POST /debug/source` با **فایل کامل** (نه patch ناقص).
5. `POST /debug/pytest` → تا سبز شدن تست‌ها.
6. **بالا بردن نسخه**: `app/version.py`، `pyproject.toml` و `CHANGELOG.md` با هم.
7. `POST /debug/restart` و بعد دوباره `GET /debug/health` برای تأیید نسخهٔ جدید.
8. در پایان: ابطال توکن + خاموش‌کردن دسترسی عیب‌یابی.

> هر تغییر سورس باید نسخه را بالا ببرد. `tests/test_version.py` اگر
> `app/version.py`، `pyproject.toml` و بالاترین ورودی `CHANGELOG.md` یکی نباشند
> شکست می‌خورد.

---

## دیپلوی کامل با ZIP

مسیر جایگزین (بدون API) از خود ربات:

1. پنل ادمین → 🚀 **دیپلوی** → **دانلود ZIP سورس**.
2. ZIP جدید را بسازید (باید `main.py` و `app/version.py` داشته باشد؛ یک پوشهٔ
   والد مثل `leechx-main/` هم مجاز است).
3. **ارسال ZIP** → ربات اعتبارسنجی می‌کند (حجم، تعداد فایل، symlink،
   path traversal) و نسخهٔ ورودی را نشان می‌دهد.
4. **اعمال** → بکاپ سورس فعلی در `data/updates/`، سپس جای‌گزینی فایل‌ها.
5. **ری‌استارت** → اگر `UPDATE_RESTART_COMMAND` تنظیم شده باشد همان اجرا
   می‌شود، وگرنه فرآیند با `os.execv` جای‌گزین می‌شود.

فایل‌های `.env`، `data/`، `.git` و `__pycache__` نه در ZIP خروجی هستند و نه از
ZIP ورودی نوشته می‌شوند.

---

## Local Bot API چیست؟

تلگرام دو نوع API دارد:

- **Bot API ابری** (`api.telegram.org`): ساده، اما سقف دانلود فایل حدود
  **۲۰ مگابایت** و آپلود حدود **۵۰ مگابایت** است.
- **Local Bot API Server**: همان API را خودتان روی سرور اجرا می‌کنید. سقف
  دانلود تا **۲ گیگابایت** بالا می‌رود، فایل‌ها مستقیم روی دیسک شما می‌مانند و
  می‌توانید `TELEGRAM_API_ID`/`HASH` خودتان را بدهید.

در `.env`:

```env
TELEGRAM_API_URL=http://telegram-bot-api:8081/bot
TELEGRAM_API_FILE_URL=http://telegram-bot-api:8081/file/bot
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=abcdef...
```

- این مقادیر هنگام **ساخت اپلیکیشن** خوانده می‌شوند؛ تغییرشان ری‌استارت لازم دارد.
- با `docker compose --profile localapi up -d` سرور محلی بالا می‌آید.
- اگر از Local API استفاده نمی‌کنید، این سه متغیر را خالی بگذارید.

---

## به‌روزرسانی پشتیبانی سایت‌ها (yt-dlp)

پشتیبانی از سایت‌ها (از جمله سایت‌های بزرگسال) از **extractorهای yt-dlp**
می‌آید، نه از کد ربات:

- پنل ادمین → 🩺 **عیب‌یابی** → **به‌روزرسانی yt-dlp** (stable) یا **nightly**.
- یا روی سرور: `pip install -U yt-dlp` و سپس ری‌استارت.
- بعد از آپدیت، فهرست سایت‌ها خودکار بازسازی می‌شود و `/sites` تعداد جدید را
  نشان می‌دهد.
- برای سایت‌های نیازمند لاگین، از 🍪 **کوکی‌ها** استفاده کنید.
- اگر سایتی هنوز کار نمی‌کند، در پنل ادمین → 📨 **گزارش‌ها** ثبت می‌شود تا
  extractor یا کوکی درست شود.

---

## عیب‌یابی خطاهای رایج

| خطا | معنی | راه‌حل |
|---|---|---|
| `403 debug access is disabled` | دسترسی عیب‌یابی خاموش است | از پنل ادمین روشن کنید |
| `403 ip ... is not allow-listed` | IP شما در فهرست مجاز نیست | IP را اضافه/خالی کنید |
| `401 missing bearer token` | هدر توکن ارسال نشده | `Authorization: Bearer ...` |
| `401 token expired` | عمر توکن تمام شده | توکن تازه بگیرید |
| `403 token lacks 'write' scope` | سطح دسترسی کافی نیست | توکن با `write`/`restart` بگیرید |
| `400 unsafe path` | تلاش path traversal | فقط مسیرهای مجاز |

---

## نکتهٔ امنیتی

توکن را در چت‌های عمومی، لاگ‌ها یا مخزن گیت قرار ندهید. بعد از هر کار،
**ابطال همه** و سپس خاموش‌کردن دسترسی عیب‌یابی را فراموش نکنید.
