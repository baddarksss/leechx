# Changelog

All notable changes to **LeechX** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

> Rule for maintainers and AI agents: every source change must bump
> `app/version.py`, `pyproject.toml` and add an entry here. `tests/test_version.py`
> fails when these three disagree.

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
