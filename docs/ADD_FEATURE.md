# افزودن قابلیت جدید

این پروژه عمداً طوری چیده شده که هر ایدهٔ جدیدی با کمترین تغییر اضافه شود.
چند دستور آشپزی:

> **قانون نسخه:** بعد از هر تغییر، نسخه را در `app/version.py`،
> `pyproject.toml` و بالاترین ورودی `CHANGELOG.md` با هم بالا ببرید.
> `tests/test_version.py` این سه را مقایسه می‌کند.

---

## ۱) افزودن یک دکمه/دستور ساده

### دکمه در منوی اصلی

1. `app/bot/keyboards.py` → یک `callback_data` جدید:
   ```python
   M_QUEUE = "m|queue"
   ```
2. در `main_menu` دکمه را اضافه کن.
3. `app/bot/flows/start.py` → در `on_menu` شاخهٔ `action == "queue"` را بنویس.
4. متن‌ها را در `app/core/text.py` (هر دو زبان) اضافه کن.

### دستور

```python
# app/bot/app.py
app.add_handler(CommandHandler("queue", my_flow.cmd_queue))
```

و در `COMMANDS` (همان فایل) برای منوی تلگرام ثبتش کن.

---

## ۲) افزودن تنظیمات زمان اجرا

1. `app/services/runtime_settings.py` → در `SCHEMA`:
   ```python
   "max_duration_min": ("int", "حداکثر مدت ویدیو (دقیقه)"),
   ```
2. در `_default` مقدار پیش‌فرض را از `cfg` بده (اگر لازم است).
3. یک property اضافه کن:
   ```python
   @property
   def max_duration_seconds(self) -> int:
       return self.get_int("max_duration_min") * 60
   ```
4. در `snapshot()` هم بیاور تا در پنل دیده شود.
5. `app/bot/keyboards.py` → `settings_menu` یک دکمه با
   `callback_data="a|edit|max_duration_min"` اضافه کن. بقیهٔ کارها
   (ورودی مقدار، ذخیره، رندر) خودکار انجام می‌شود.

---

## ۳) افزودن یک بک‌اند دانلود جدید (مثلاً aria2 یا qBittorrent)

`app/services/downloader.py` را نگاه کن. رابط مورد انتظار:

```python
class MyBackend:
    async def probe(self, url) -> MediaInfo
    async def download(self, url, option, workdir, progress, cancel, info) -> DownloadResult
```

سپس در `handle_link` بر اساس دامنه/نوع لینک، بک‌اند مناسب را انتخاب کن:

```python
if is_torrent(url):
    backend = torrent_backend
else:
    backend = svc.downloader
```

هیچ چیز دیگری عوض نمی‌شود: صف، آپلود، پاک‌سازی و پیام‌ها مستقل‌اند.

---

## ۴) افزودن زبان جدید

1. `app/core/text.py` → یک دیکشنری مثل `FA` کپی کن (مثلاً `RU`).
2. در `LANGS` و `MESSAGES` ثبتش کن.
3. تمام. (`RTL` برای فارسی در خود تلگرام مدیریت می‌شود.)

---

## ۵) افزودن جدول دیتابیس

1. `app/db/models.py` → کلاس جدید با `Base`.
2. `app/db/repo.py` → توابع دسترسی.
3. جدول‌ها در استارتاپ با `create_all` ساخته می‌شوند (بدون مهاجرت).
   اگر ستون اضافه می‌کنی و دیتابیس موجود داری، یا `ALTER TABLE` دستی بزن یا
   از `alembic` استفاده کن.

---

## ۶) افزودن نوع خروجی جدید در آپلود

`app/services/uploader.py` → در `send()` یک شاخهٔ MIME جدید اضافه کن
(مثلاً `application/pdf` → `send_document` با کاور).

برای آپلود به کانال دیگر یا با ادمین متفاوت، `bot.send_*` را با
`chat_id=...` دلخواه صدا بزن.

---

## ۷) افزودن آمار/گزارش

`repo.log_event(user_id, kind, value)` را هر جا لازم داری صدا بزن و با
`repo.events_since(ts)` بخوان. برای گزارش دوره‌ای، یک task در
`Services._cleanup_loop` یا یک loop مستقل اضافه کن.

---

## ۸) اتصال به Redis (برای چند سرور)

سه نقطه کافی است:

| فعلی | جای‌گزین |
|---|---|
| `DraftStore` | `HSET` با `EXPIRE` |
| `RateLimiter` | `INCR` + `EXPIRE` یا `SET NX` |
| `JobManager._queue` | `LPUSH/BRPOP` یا RQ |

رابط هر سه ساده و مستند است؛ لایهٔ ربات تغییری نمی‌خواهد.

---

## چک‌لیست قبل از پوش

```bash
python -m ruff check app main.py tests
python -m pytest -q
python main.py --check
```

- متن‌های جدید در **هر دو** زبان اضافه شده باشند.
- خطاهای جدید از `LeechError` ارث ببرند تا پیام دوستانه بگیرند.
- فایل موقت در `finally` پاک شود.
