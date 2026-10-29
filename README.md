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
| 👑 **Admin panel** | categorized screens (stats, users, settings, groups, deploy, diagnostics), admin group with topics, ban by forward/username/ID, reports, logs, broadcast, cleanup |
| 🌐 **Site database** | `/sites` search over every yt-dlp extractor |
| 🌍 **i18n** | Persian 🇮🇷, English 🇬🇧 and Russian 🇷🇺 with one-tap switching |
| 🔐 **Forced membership** | require joining one or more channels/groups before the bot works |
| 📦 **In-bot deploy** | export the live source as ZIP, upload a new ZIP, validate, back up and restart |
| 🩺 **Diagnostics tokens** | time-limited (max 24h) scoped `lxdbg_` tokens for AI/remote troubleshooting |
| 👁 **Member preview** | admins can test the bot exactly as a normal user and return with one tap |
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
| `UPDATE_RESTART_COMMAND` | empty | optional restart command used after an in-bot source update (empty = `os.execv`) |
| `MAX_SOURCE_ZIP_MB` | `80` | max size of a source ZIP uploaded from the admin panel |
| `DEBUG_TOKEN_MAX_HOURS` | `24` | max diagnostics-token lifetime (hard cap 24) |

Cookies for restricted sites: use **Admin panel → 🍪 Cookies** to upload a
`cookies.txt` file or paste Netscape text. Files are stored in
`data/cookies/<site>.txt` and selected automatically by URL domain. JSON exports
are converted to Netscape automatically. Full guide:
[`docs/COOKIES.md`](docs/COOKIES.md).

---

## Versioning, in-bot deploy and diagnostics

**Versioning.** `app/version.py` is the only source of truth (`__version__`,
`CODENAME`). `pyproject.toml` and the newest `CHANGELOG.md` entry must match;
`tests/test_version.py` fails otherwise. Bump before every release/change:

```bash
python -m app.version patch   # prints the next version
```

**Deploy from the bot.** Admin panel → 🚀 **Deploy**:

1. **Download source ZIP** — the running code (never `.env`, `data/` or `.git`).
2. **Validate ZIP** — checks `main.py`, `app/version.py`, size, file count,
   symlinks and path traversal; shows the incoming version.
3. **Apply** — backs up the current source to `data/updates/`, replaces files,
   then asks to **restart** (uses `UPDATE_RESTART_COMMAND` or `os.execv`).

**Forced membership.** Admin panel → 👥 **Groups** → 🔐 **Forced join**.
Add `@channel`/numeric IDs, enable the gate, then the bot checks membership
(cached for 3 minutes, fail-open if Telegram errors). Admins are exempt, but
**not** while testing 👁 Member preview.

**Diagnostics tokens.** Admin panel → 🩺 **Diagnostics** creates a one-time
`lxdbg_…` token (read / write / restart, max 24h, hashed in DB, revocable).
It exposes `/debug/health|state|logs|source|restart|ytdlp-update|pytest` on the
same web server only while diagnostics are enabled. Full Persian guide with
`curl` examples: [`docs/DEBUG_API_FA.md`](docs/DEBUG_API_FA.md).

**Local Bot API.** `TELEGRAM_API_URL` / `TELEGRAM_API_FILE_URL` point the bot at
a self-hosted `telegram-bot-api` server (default `http://telegram-bot-api:8081/bot`
and `/file/bot`). It lifts the 50 MB Bot API download limit up to 2 GB and is
optional. Changing these URLs needs a restart because they are read when the
application is built.

**yt-dlp updates.** Admin panel → 🩺 **Diagnostics** → **Update yt-dlp**
(stable or nightly) runs `pip install -U yt-dlp`, then rebuilds the site index.
New sites added by yt-dlp become available immediately after the update.

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
