# 🔥 LeechX — Telegram Leecher Bot

[![CI](https://github.com/baddarksss/leechx/actions/workflows/ci.yml/badge.svg)](https://github.com/baddarksss/leechx/actions/workflows/ci.yml)

Download from **any site** and upload straight to Telegram, or turn any file into
a **direct link** with automatic expiry. Built for high traffic: job queue,
per-user concurrency limits, automatic disk cleanup and a modular design.

---

## Features

| | |
|---|---|
| 🔗 **Link → quality → delivery** | 1700+ sites via yt-dlp (YouTube, Instagram, TikTok, X, SoundCloud, Twitch, Reddit…) |
| 🎚 **Quality buttons** | video `144p`–`2160p` + `MP3 192k` / `M4A` |
| 📤 **Delivery menu** | before upload choose **video**, **document**, **direct link** or **rename** |
| 🍪 **Cookies** | upload/paste `cookies.txt` (Netscape or JSON) from the admin panel for YouTube/Instagram |
| 🏷 **Captions + hashtags** | title, source link and automatic hashtags on the media message itself |
| 📁 **File → direct link** | signed URL, `Range` support, 6h TTL by default |
| 🧹 **Zero leftovers** | the working directory is removed right after upload |
| ⚡️ **Job queue** | `WORKERS` global + `PER_USER_CONCURRENCY` per user |
| 👑 **Admin panel** | live stats, admin group with topics, ban by forward/username/ID, reports, logs, runtime variables, broadcast, cleanup |
| 🌐 **Site database** | `/sites` search over every yt-dlp extractor |
| 🌍 **i18n** | Persian + English |
| 🐳 **Docker** | compose file with optional local Bot API server (2 GB) |

---

## Quick start

```bash
cp .env.example .env     # set BOT_TOKEN only (OWNER_IDS is optional)
docker compose up -d --build
```

Local development:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# ffmpeg must be installed (apt install ffmpeg / winget install Gyan.FFmpeg)
python main.py --check
python main.py
```

> **Token-only setup:** if `BOT_TOKEN` is missing, `python main.py` asks for it and
> saves it to `.env`. The first user who sends `/start` becomes the **owner** and sees
> the admin panel. For the admin group, add the bot to a group with Topics enabled,
> make it admin, then send `/setup` inside the group.

Large files (>50 MB upload / >20 MB download) need the local Bot API server:

```bash
docker compose --profile localapi up -d
```

and in `.env`:

```env
TELEGRAM_API_URL=http://telegram-bot-api:8081/bot
TELEGRAM_API_FILE_URL=http://telegram-bot-api:8081/file/bot
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
```

---

## Configuration

See [`.env.example`](.env.example). Key values:

| Key | Default | Meaning |
|---|---|---|
| `BOT_TOKEN` | — | from @BotFather |
| `OWNER_IDS` | empty | optional; if empty the first `/start` becomes owner |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8080` | public URL used in direct links |
| `LINK_TTL_HOURS` | `6` | default link lifetime |
| `MAX_UPLOAD_MB` | `2000` | Telegram upload cap |
| `MAX_LINK_FILE_MB` | `2000` | max size accepted for direct links |
| `WORKERS` | `2` | concurrent download/upload workers |
| `PER_USER_CONCURRENCY` | `1` | concurrent jobs per user |
| `RATE_LIMIT_SECONDS` | `3` | minimum delay between requests |
| `DAILY_QUOTA` | `0` | downloads per day (0 = unlimited) |
| `PROXY` | — | download proxy |
| `COOKIES_DIR` | `./data/cookies` | cookie files for YouTube/Instagram and other restricted sites |
| `DATABASE_URL` | SQLite | set a Postgres URL for scale |

Cookies for restricted sites: use **Admin panel → 🍪 Cookies** to upload a
`cookies.txt` file or paste Netscape text. Files are stored in
`data/cookies/<site>.txt` and selected automatically by URL domain. JSON exports
are converted to Netscape automatically. Full guide:
[`docs/COOKIES.md`](docs/COOKIES.md).

---

## Admin group, reports and logs

1. Create a group with **Topics** enabled and add the bot as an administrator.
2. Send `/setup` inside the group. Four topics are created automatically:
   **Downloads**, **Uploads**, **Reports**, **Logs**.
3. Every download/upload notification includes the user's name, `@username` and
   numeric ID. Failing sites and user messages go to **Reports**; errors go to **Logs**.
4. In the admin panel you can ban by forwarding a message, typing `@username`, or
   entering a numeric ID, then close reports and clear logs.
5. **Runtime variables** (API ID/hash, Local Bot API URLs, proxy, public base URL) can
   be entered from the bot itself. Bot API URL changes apply after a restart.

## Architecture

```
app/
├── bot/          Telegram layer (flows, keyboards, guards)
├── services/     downloader, cookies, uploader, queue, link server, sites, storage
├── db/           SQLAlchemy models + data access
└── core/         text, errors, caption/hashtags, helpers
```

Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
Adding features: [`docs/ADD_FEATURE.md`](docs/ADD_FEATURE.md) ·
Persian guide: [`README.fa.md`](README.fa.md)

---

## Security

- Direct links are HMAC-signed and expire; they cannot be guessed.
- Served paths are validated against the storage root (no traversal).
- Secrets live in env only, never in the database.
- Keep the bot private and set `OWNER_IDS` carefully.

---

## Tests

```bash
pip install pytest pytest-asyncio
pytest
```

## License

MIT — see [LICENSE](LICENSE). Use it only for content you have the right to download.
