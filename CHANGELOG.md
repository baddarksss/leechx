# Changelog

All notable changes to **LeechX** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

> Rule for maintainers and AI agents: every source change must bump
> `app/version.py`, `pyproject.toml` and add an entry here. `tests/test_version.py`
> fails when these three disagree.

## [5.1.3] - 2026-10-29 · "Clean Deck"

### Fixed
- **`POST /debug/pytest` actually works**: the production image now ships
  `pytest` + `pytest-asyncio`, so the diagnostics API can run the test suite
  requested by an AI (before it failed with `No module named pytest`).
- **Docs**: troubleshooting rows for `404` on `/debug/*` (reverse proxy does not
  route `/debug/` to the bot) and for Cloudflare blocking default Python
  `User-Agent` (use `curl`/browser UA).

## [5.1.2] - 2026-10-29 · "Clean Deck"

### Fixed
- **Admin UI is always Persian**: staff accounts (outside preview mode) now always
  get `fa`, no matter what language is stored for them or what Telegram reports.
- **Language switching is for regular users**: `/lang`, the `m|lang` menu button
  and the `l|<code>` callbacks are blocked for admins with a short notice; in
  «preview as user» mode the admin behaves exactly like a normal user and may
  still change the language (the working panel snaps back to Persian on exit).

## [5.1.1] - 2026-10-29 · "Clean Deck"

### Fixed
- **Diagnostics is on by default**: `debug_enabled` now defaults to `True` in
  `runtime_settings`, so the diagnostics section and the token API work on any
  fresh server without touching runtime variables.
- **Runtime toggle for diagnostics**: the 🩺 diagnostics section has a direct
  on/off button (`a|dbtoggle`); boolean runtime keys (including
  `debug_enabled`) are toggles in «Runtime variables» instead of text prompts.
- **No restart needed to enable it**: `/debug/*` routes are always registered and
  access is gated inside `DebugAccess._auth` at request time; `debug_enabled` and
  `debug_ip_allow` were removed from the restart-required keys.
- `debug_disabled` hint now points at the in-section toggle instead of runtime
  variables (FA/EN/RU).

## [5.1.0] - 2026-10-29 · "Clean Deck"

### Changed
- **Admin navigation is now the fixed reply keyboard only**: opening `/start` or
  `/admin` as an admin no longer posts a second inline menu into the chat, so the
  same buttons no longer appear twice.
- **Admin keyboard redesigned**: 3 columns, grouped by section (stats, users,
  settings, groups, deploy, diagnostics, cookies, cancel) and admin-only —
  member buttons ("my links") and the old "start/home/panel" button are gone.
- **One place per section**: pressing a section shows only that section's actions
  (no back/close/home rows, no category menu), and the previous section message is
  removed so the chat stays clean.
- `/settings` and the settings section now open the admin settings for admins and
  the user settings for everyone else; preview mode removes the reply keyboard and
  restores it on exit.
- Text router dispatches fixed-keyboard sections through `show_section`.

## [5.0.0] - 2026-10-29 · "Control Deck"

### Added
- **3-language UI**: Persian 🇮🇷, English 🇬🇧 and Russian 🇷🇺 with a one-tap
  language switcher, per-user persistence and Telegram client language detection.
- **In-bot deployment**: export the running source as a ZIP, upload a new source
  ZIP, validate it, back up the old source and restart safely.
- **Exact versioning**: single source of truth in `app/version.py`, shown to users
  and admins, with a changelog and automated consistency tests.
- **Forced membership**: require joining one or more channels/groups before the
  bot works, with a “joined” re-check button and cached membership lookups.
- **Categorized admin panel**: stats, users, settings, groups, deployment and
  diagnostics instead of one crowded screen.
- **Member preview mode**: admins can view the bot exactly as a normal user and
  leave preview mode with one tap.
- **Native keyboard hiding**: a “close keyboard” button that removes the reply
  keyboard the same way Telegram itself does.
- **Time-limited AI/debug access**: scoped `lxdbg_` tokens (read / write /
  restart) with hashed storage, expiry, revocation and a small HTTP diagnostics
  API for live troubleshooting and hot deployment.
- **yt-dlp updater**: update extractors (stable or nightly) from the admin panel,
  rebuild the site index, and see the live extractor count.
- **Health check** with ffmpeg/yt-dlp/database/disk/web-server diagnostics.
- Persian documentation for Local Bot API, deployment, debug tokens and
  extractor updates.

### Changed
- Main menu and all admin screens re-laid-out into calm two-column groups.
- Admin reply keyboard now includes a native “close keyboard” action.
- `/start`, `/me`, admin stats and settings show the running version.
- Runtime setting labels are localized (fa/en/ru).
- Site index detects more adult extractors and can be rebuilt without restart.

### Fixed
- Flaky signed-link test that could occasionally accept a tampered signature.
- Settings labels are no longer hard-coded Persian-only.
- Language fallback chain is now `ru → en → fa` instead of falling back to
  Persian for every language.

## [4.4.0] — 2026-10-28

### Added
- Telegram group media cache with per-user isolation.
- Social delivery flow, link revocation, audit topics, runtime variables.
