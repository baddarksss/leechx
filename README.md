# 🔥 LeechX — Telegram Leecher Bot

[![CI](https://github.com/baddarksss/leechx/actions/workflows/ci.yml/badge.svg)](https://github.com/baddarksss/leechx/actions/workflows/ci.yml)

Download from **any site** and upload straight to Telegram, or turn any file into
a **direct link** with automatic expiry. Built for high traffic: job queue,
per-user concurrency limits, automatic disk cleanup and a modular design.

---

## Features

| | |
|---|---|
| 🔗 **Link → quality → upload** | 1700+ sites via yt-dlp (YouTube, Instagram, TikTok, X, SoundCloud, Twitch, Reddit…) |
| 🎚 **Quality buttons** | video `144p`–`2160p` + `MP3 192k` / `M4A` |
| 📁 **File → direct link** | signed URL, `Range` support, 6h TTL by default |
| 🧹 **Zero leftovers** | the working directory is removed right after upload |
| ⚡️ **Job queue** | `WORKERS` global + `PER_USER_CONCURRENCY` per user |
| 👑 **Admin panel** | stats, admins, live settings, broadcast, ban, cleanup |
| 🌐 **Site database** | `/sites` search over every yt-dlp extractor |
| 🌍 **i18n** | Persian + English |
| 🐳 **Docker** | compose file with optional local Bot API server (2 GB) |

---

## Quick start

```bash
cp .env.example .env     # set BOT_TOKEN and OWNER_IDS
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
| `OWNER_IDS` | — | comma-separated numeric IDs (always admin) |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:8080` | public URL used in direct links |
| `LINK_TTL_HOURS` | `6` | default link lifetime |
| `MAX_UPLOAD_MB` | `2000` | Telegram upload cap |
| `MAX_LINK_FILE_MB` | `2000` | max size accepted for direct links |
| `WORKERS` | `2` | concurrent download/upload workers |
| `PER_USER_CONCURRENCY` | `1` | concurrent jobs per user |
| `RATE_LIMIT_SECONDS` | `3` | minimum delay between requests |
| `DAILY_QUOTA` | `0` | downloads per day (0 = unlimited) |
| `PROXY` | — | download proxy |
| `DATABASE_URL` | SQLite | set a Postgres URL for scale |

Cookies for restricted sites: `data/cookies/youtube.txt`, `data/cookies/instagram.txt`
(Netscape format).

---

## Architecture

```
app/
├── bot/          Telegram layer (flows, keyboards, guards)
├── services/     downloader, uploader, queue, link server, sites, storage
├── db/           SQLAlchemy models + data access
└── core/         text, errors, helpers
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
