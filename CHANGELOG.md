# Changelog

All notable changes to **LeechX** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

> Rule for maintainers and AI agents: every source change must bump
> `app/version.py`, `pyproject.toml` and add an entry here. `tests/test_version.py`
> fails when these three disagree.

## [5.6.0] - 2026-10-31 · "Gallery Engine"

### Added
- **gallery-dl engine** (`app/services/gallery.py`): image/album sites that
  yt-dlp rejects (Instagram posts and carousels, Pinterest, X/Twitter media,
  Reddit galleries, Pixiv, Danbooru, Kemono, and adult gallery sites) now
  download through `gallery-dl`, which runs in a cancellable subprocess.
- Automatic fallback: if yt-dlp says `unsupported` during probe or download,
  the link is retried with gallery-dl when it is a known extractor.
- Gallery/album delivery: images are sent as Telegram media groups of 10
  (`send_media_group`), other files individually; `document` mode sends raw
  files. Direct-link mode packs the album into a single ZIP.
- Album size/count guard: `GALLERY_MAX_ITEMS` (default 50, max 200) limits how
  many files one gallery link can download.
- Cookie files and the configured proxy are passed to gallery-dl, so private
  posts work the same way they do with yt-dlp.
- Gallery-only adult categories are recognised by the NSFW filter
  (`GALLERY_NSFW` in `app/services/sites.py`).
- New text keys `quality_gallery` and `gallery_note` in fa/en/ru.

## [5.5.0] - 2026-10-31 · "Durable Deploy"

### Added
- Deploy → **Update yt-dlp** now restarts the bot automatically when the version
  really changed, so the new extractors are loaded and the site index is not stale.
- Source ZIP deploy installs changed `requirements.txt` dependencies **before**
  touching the running source, and aborts with the current source untouched if the
  install fails.
- Source ZIP deploy now runs a Python syntax check (`compileall`) on the staged
  archive before applying it.
- After a successful ZIP deploy a snapshot of the applied source is written to
  `data/updates/leechx-applied-vX.Y.Z-*.zip`, so an in-bot update can still be
  committed to GitHub later.
- `~/.local` is mounted from `./data/pylocal` and `PYTHONUSERBASE` points there,
  so `pip --user` installs (yt-dlp upgrades) survive `docker compose up --build`.
- New database migration pass adds any column that exists in the models but is
  missing from an existing table (additive `ALTER TABLE ... ADD COLUMN` only).

### Fixed
- `SiteIndex.build()` accepts `force=True`; previously it returned immediately
  once loaded, so "site index rebuilt" after a yt-dlp upgrade was a no-op.
- ZIP deploy deletes source files that are no longer part of the uploaded source
  (previously deleted files stayed around forever) and clears stale `__pycache__`.
- ZIP deploy rejects archives that look truncated (fewer than half of the current
  source files) instead of wiping most of the tree.

## [5.4.4] - 2026-10-29 · "Persian Admin"

### Changed
- Admin mode is Persian-only: admins skip language onboarding, admin menus and
  notices ignore older saved locales, and language changes remain available to
  regular users. Leaving user preview restores the Persian admin menu.
- Stale admin language buttons are safely rejected instead of opening the picker
  or falling through to link/file input.

## [5.4.3] - 2026-10-29 · "Localized Flow"

### Fixed
- First-run onboarding now shows only the three language buttons without a caption.
- Persisted language selection is authoritative across user/admin menus; admin language
  switching is available, stale keyboard taps are routed safely, and preview exit keeps
  the selected language instead of falling through to the link prompt.
- Download/upload status replaces numeric percentages with neutral squares that fill
  green, with localized stage labels.

## [5.4.2] - 2026-10-29 · "Focused Colors"

### Fixed
- Blue styling is now limited to delivery section headers; selectable options
  and quality buttons use Telegram's default appearance, while Start remains green.

## [5.4.1] - 2026-10-29 · "Responsive Delivery"

### Added
- Owner notification after startup/restart, sent after services are ready and
  including the running version.
- A callback acknowledgement watchdog that starts before per-user update
  serialization and the onboarding/force-join gate.

### Fixed
- Callback IDs are only marked answered after Telegram confirms the answer, so
  transient failures can be retried; slow callback queue/handler times are logged.
- Delivery and quality controls use native Telegram button styling: blue for
  options and green for the final start action. Section titles point down to
  their controls; the Persian thumbnail button is labeled «تامبنیل».
- Require python-telegram-bot 22.7+ for native inline-button styles.

## [5.4.0] - 2026-10-29 · "Clear Delivery"

### Added
- Admin traffic report with cumulative source-download, Telegram-received,
  Telegram-upload, and direct-link-served file bytes, plus downloaded, uploaded,
  and combined totals. Counters are integer-precise and persist across restarts.
- Traffic is measured as file payload bytes; HTTP headers/protocol overhead are
  excluded, and the new directional counters begin with this release (the older
  aggregate events cannot be reliably split by direction).

### Changed
- Delivery choices now have clear "Upload as" and "Upload to" sections, a
  separate optional-edits group, and a prominent final action. The initial
  release used colored emoji; 5.4.1 switches to Telegram's native button styles.
- Removed the redundant Admin "Cancel tasks" menu item. Cancellation of the
  admin's own jobs/forms and each user's inbound/file-transfer cancellation
  paths remain available; old persistent keyboards keep routing safely.

## [5.3.0] - 2026-10-29 · "Clean Chat"

### Fixed
- Buttons no longer need two or three taps: every callback is answered within
  0.6 s, link probing, broadcasts, yt-dlp upgrades and ZIP sends run outside the
  per-user lock, and edits that Telegram rejected silently (reply keyboards on
  edited messages, media captions, "not modified") now fall back correctly.
- Admin "home", "help", "status" and "admin panel" inline buttons, and the
  preview switch, no longer fail silently because of a reply keyboard on edit.
- Toast texts lost after a first empty answer (admin removal, cookie/join
  target deletion, log clearing, token revocation) are now shown; HTML tags are
  stripped from toasts.
- Deploy results no longer try to edit the admin's uploaded file message.
- Admins and the owner can no longer be banned from the user card.
- Unhandled errors show only the error type to users and ignore transient
  Telegram errors instead of posting raw exception text.

### Changed
- Single-message UI: every menu edits the user's panel message instead of
  sending a new one; persistent-keyboard taps, typed commands and form inputs
  (including cookie text) are deleted from the chat after they are handled.
- Diagnostics: no duplicate buttons (one duration selector + one button per
  scope), each token row has its own 🗑, and a new token is shown as one full
  copyable URL (`/debug/k/<token>`) with a short message. `GET` on that URL
  returns a self-describing list of endpoints for the AI.
- Broadcast uses a rate-limited worker pool and honours Telegram `RetryAfter`.
- Debug API writes refuse symlinks that resolve outside the project.

## [5.2.1] - 2026-10-29 · "Smooth Delivery"

### Fixed
- Switching language now refreshes Telegram's persistent keyboard; stale buttons
  from any supported language still route to their intended action.
- Fixed stale-language status taps falling through to the generic link prompt.

### Changed
- Shortened the per-link delivery summary, kept only key file/quality/size and
  selected delivery details, and made the final action label reflect the choice.
- Clarified ZIP deployment limits: removed files are not deleted, dependencies
  are not installed, and an in-bot ZIP apply does not update GitHub.

## [5.2.0] - 2026-10-29 · "Delivery Presets"

### Added
- Added per-user defaults for Telegram format and destination, with per-link
  overrides, a paired delivery panel, and optional custom thumbnails.
- Added per-user upload/delivery totals alongside successful download totals.

### Changed
- The user keyboard now relies on Telegram's native collapse control; help is
  lower, support is the final full-width row, and only `/start` is listed as a
  bot command.
- Removed the user-facing admin marker from My status and refreshed all three
  language interfaces with grouped emoji styling.

## [5.1.7] - 2026-10-29 · "Steady Keys"

### Changed
- Replaced the user's scattered inline main menu with a persistent, localized
  two-column reply keyboard, grouping site/link tools, help/status, settings/
  language, and contact/keyboard controls into consistent rows.
- Routed user keyboard taps through the existing handlers; language updates,
  membership-gate completion, and preview mode now refresh the correct keyboard.
- Kept inline keyboards for language selection, join checks, and task-specific
  actions; the admin keyboard remains unchanged.

## [5.1.6] - 2026-10-29 · "Language Gate"

### Fixed
- Fixed the user settings screen failure caused by passing `lang` both as the
  translation selector and as a format placeholder; settings and language
  changes now render normally.

### Added
- Added a persistent first-use language choice (Persian, English, Russian)
  before forced-channel membership checks, then continues to the join gate or
  bot welcome screen. Existing users are prompted once after the upgrade.
- Added a direct user-menu language shortcut and a SQLite/Postgres migration
  for the language-choice flag.

## [5.1.5] - 2026-10-29 · "Clean Deck"

### Fixed
- **Diagnostics token scopes are now cumulative**: `write` implies `read` and
  `restart` implies `read`+`write`. Before, the button labelled "Read + fix
  code" created a `write`-only token that could not read source or logs, and
  the "Full token" button created a `restart`-only token that answered
  `403 token lacks 'read' scope` on `/debug/health`, `/debug/logs` and
  `/debug/source`. Scope checks also accept the hierarchy, so tokens issued
  before this version start working without re-issuing.
- Docs: scope hierarchy, default-on diagnostics, and a troubleshooting row for
  the old `token lacks 'read' scope` error.

## [5.1.4] - 2026-10-29 · "Clean Deck"

### Fixed
- **Diagnostics can really read and test the source**: `tests/`, `docs/`,
  `CHANGELOG.md` and `AGENTS.md` are no longer stripped from the image by
  `.dockerignore`, so `GET /debug/source?path=tests/...` and
  `POST /debug/pytest?path=tests/...` work on a live deployment.

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
