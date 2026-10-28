# معماری LeechX

## نگاه کلی

```
Telegram ──► python-telegram-bot ──► flows (bot layer)
                                        │
                                        ▼
                                  Services (container)
                    ┌───────────────┼────────────────┐
                    ▼               ▼                ▼
              Downloader        JobManager       LinkServer
              (yt-dlp/HTTP)      (queue)         (aiohttp)
                    │               │                │
                    └───────────────┴────────────────┘
                                    ▼
                              SQLAlchemy (DB)
```

سه لایه:

1. **`app/bot/`** — فقط با تلگرام حرف می‌زند. هیچ منطق دانلودی اینجا نیست.
2. **`app/services/`** — منطق دامنه. مستقل از تلگرام (به‌جز `uploader`).
3. **`app/db/`** — دسترسی به داده. تنها جایی که SQL/ORM نوشته می‌شود.

`app/container.py` سرویس‌ها را یک‌بار می‌سازد و در `bot_data["services"]` می‌گذارد.

---

## جریان ۱ — لینک → کیفیت → آپلود

```
کاربر: لینک
  │
  ├─ gate()            upsert کاربر، چک مسدودی/تعمیرات
  ├─ rate limit        RateLimiter.hit()
  ├─ per-user slot     RateLimiter.has_slot()
  ├─ NSFW check        SiteIndex.is_nsfw_url()
  ├─ Downloader.probe()
  │     ├─ اگر پسوند رسانه‌ای بود → HEAD/GET سبک → MediaInfo(direct=True)
  │     └─ وگرنه yt-dlp extract_info(download=False)
  │
  ├─ direct?  ──► JobTask(kind="direct") ──► صف
  │
  └─ ویدیو/صدا ──► DraftStore.put() + کیبورد کیفیت
                      │
           کاربر دکمه می‌زند (q|draft|code|kind)
                      │
                      ▼
                 JobTask ──► JobManager.submit()
```

`JobManager`:

```
_queue ──► worker[i] ──► _take_next()  (چک per-user slot)
                          │
                          ├─ Downloader.download()   ← هوک پیشرفت
                          ├─ fetch_thumbnail()
                          ├─ Uploader.send()         ← ProgressReader
                          └─ finally: drop_job_dir()
```

`_publisher_loop` هر ~۲ ثانیه پیام وضعیت کارهای فعال را ویرایش می‌کند.

### لغو

`asyncio.Event` در `JobTask`:

- صف: کار از صف حذف و «لغو شد» ثبت می‌شود.
- در حال اجرا: هوک پیشرفت `JobCancelled` می‌دهد → yt-dlp متوقف می‌شود.

---

## جریان ۲ — فایل → لینک مستقیم

```
کاربر: فایل
  ├─ سقف حجم (settings.max_link_mb)
  ├─ att.get_file().download_to_drive()  → data/files/links/<id>/<name>
  ├─ repo.create_shared(ttl)
  ├─ token = HMAC(f, u, exp)
  └─ PUBLIC_BASE_URL/f/<token>
```

سرور لینک (`link_server.py`):

- `read_token` → امضا + انقضا
- `repo.get_shared` → رکورد
- اعتبارسنجی مسیر داخل `data/files/links`
- `Range` → `206 Partial Content`
- `HEAD` → هدرها بدون بدنه
- شمارش دانلود (`touch_shared`)

پاک‌سازی: `Services._cleanup_loop` هر `CLEANUP_INTERVAL_SECONDS`:

1. رکوردهای منقضی → حذف فایل + رکورد
2. پوشه‌های کار قدیمی‌تر از ۶ ساعت
3. `DraftStore.prune()`

---

## مدل داده

| جدول | نقش |
|---|---|
| `users` | کاربر تلگرام، زبان، مسدودی، شمارندهٔ دانلود |
| `admins` | ادمین‌های اضافه‌شده از پنل |
| `jobs` | هر درخواست دانلود با وضعیت و اندازه |
| `shared_files` | فایل‌های لینک مستقیم با `expires_at` |
| `settings` | تنظیمات زمان اجرا (روی env سوار می‌شود) |
| `stat_events` | رویدادهای سبک برای آمار/سهمیه |

`jobs.status`: `queued → running → done | failed | canceled`

روی استارتاپ، `fail_stale_jobs()` کارهای نیمه‌تمام را `failed` می‌کند.

---

## همزمانی

- یک حلقهٔ asyncio؛ کارهای مسدودکننده (`yt-dlp`) در `asyncio.to_thread`.
- `WORKERS` کارگر مستقل از صف.
- `PER_USER_CONCURRENCY` با `RateLimiter.acquire_slot` (اتمیک در حلقه).
- `concurrent_updates(48)` در PTB → هندلرها موازی می‌شوند.

### محدودیت‌های شناخته‌شده

| مورد | توضیح | راه‌حل مقیاس |
|---|---|---|
| صف در حافظه | با ری‌استارت کارهای در صف از دست می‌روند (در DB `failed` می‌شوند) | Redis/RQ یا Celery |
| `DraftStore` در حافظه | انتخاب کیفیت پس از ری‌استارت منقضی است | Redis با TTL |
| `RateLimiter` در حافظه | بین چند پروسه مشترک نیست | Redis |
| SQLite | نوشتن همزمان محدود | Postgres |

همهٔ این‌ها پشت یک رابط ساده‌اند؛ جای‌گزینی بدون تغییر در لایهٔ ربات.

---

## امنیت

- HMAC-SHA256 روی payload + انقضا؛ مقایسه با `hmac.compare_digest`.
- کلید امضا: `LINK_SECRET` یا فایل `data/.link_secret` (chmod 600).
- Path traversal: `resolved.startswith(store.links.resolve())`.
- ادمین: `OWNER_IDS` + `ADMIN_IDS` (env) + جدول `admins`.
- گیت سراسری: مسدودی + حالت تعمیر قبل از هر هندلر.
- هیچ توکنی در DB یا لاگ نوشته نمی‌شود.

---

## نقاط شکست و رفتار

| خطا | رفتار |
|---|---|
| سایت پشتیبانی نمی‌شود | پیام دوستانه با دلیل (`map_error`) |
| فایل بزرگ‌تر از سقف | `TooLarge` قبل از آپلود |
| تلگرام خطای حجم داد | `TooLarge` با راهنمای Local Bot API |
| ری‌استارت وسط کار | `fail_stale_jobs` + پاک‌سازی پوشه‌ها |
| کاربر بلاک کرده | در broadcast شمرده می‌شود، کار نمی‌شکند |
| دیتابیس قفل/خطا | `gate` ادامه می‌دهد و لاگ می‌کند |
