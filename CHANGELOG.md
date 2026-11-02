# Changelog

All notable changes to **LeechX** are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

> Rule for maintainers and AI agents: every source change must bump
> `app/version.py`, `pyproject.toml` and add an entry here. `tests/test_version.py`
> fails when these three disagree.

## [5.14.1] - 2026-11-02 — "Tidy"

### Fixed
- The users section showed **two** «🔎 Find user» buttons: the page renderer
  added its own copy on top of the section menu. The list and the empty state
  now rely on the section menu only.
## [5.14.0] - 2026-11-02 — "VIP"

### Added
- **VIP users (`users.vip`).** A user marked as VIP skips every per-user limit:
  the slow-mode interval, the daily quota, `max_links_per_user` and the
  per-user concurrency slot. VIP is **not** an admin right: the admin panel and
  admin-only actions stay closed (`guards.unlimited()` is used only by the
  limit checks; `current_admin()` and `require_admin()` are untouched).
- **«⭐ کاربران ویژه» section.** Admin → «👥 کاربران» → «⭐ کاربران ویژه» lists
  VIP users (paginated) with a one-tap «✕» removal; users are added from the
  user card («⭐ ویژه کن»). The member list marks VIPs with ⭐.

### Changed
- Tapping a name in the member list now opens the user card instead of banning
  immediately; ban/unban and VIP live inside the card, so a mistap cannot lock
  somebody out.

### Verified
- 470 tests green, `ruff` clean; deployed to `3.150.178.157` (v5.14.0, health ok).
## [5.13.0] - 2026-11-02 — "Magnet"

### Added
- **Magnet / torrent support.** `magnet:?xt=urn:btih:...` links are accepted as
  a source and downloaded with the `aria2c` binary that already ships in the
  image (no extra service): `--seed-time=0`, DHT enabled, progress from the
  bytes on disk, and the largest file of the torrent is delivered. Because the
  real container is only known after the download, the bot skips the quality
  probe and shows the delivery screen immediately: pick **Video** and a playable
  video is sent, pick **File** and it arrives as a document. Multi-file torrents
  deliver their largest file; the rest is removed with the job directory.
- **Per-user cover picker (`thumb_picker`).** The 10-frame album from v5.11.0 is
  now **off by default for everyone** and is enabled per user from
  «⚙️ تنظیمات» → «🖼 انتخاب کاور از فریم‌های ویدیو». A new admin setting
  **`thumb_shots`** (4–10, default 10) controls how many frames are extracted.
- **Full cleanup in stats.** «🧹 پاک‌سازی» now clears the whole history in one
  press: jobs, stat events, reports, logs, and it zeroes the lifetime traffic
  counters. No more deleting section by section.
- **User list instead of numeric IDs.** The «👥 کاربران» section opens a
  paginated member list (name, @username, id, ban flag) where every row is a
  ban/unban button, plus a search box that matches name, username or id.

### Fixed
- Nothing yet reported against the previous release; this release is additive.
## [5.12.3] - 2026-11-02 — "Hardened"

### Added
- **Retry button on failures.** Every failed job message now carries
  `Retry` (`talash dobare`): it re-runs the same source URL through the normal
  flow (probe -> quality/delivery -> queue). The callback verifies that the job
  belongs to the caller and that it really failed.
- **Disk-space guard before downloading.** When the source size is known, a job
  is rejected with the new `disk_full` message if the server would drop below
  `size x 1.1 + 512 MB` free space. Previously only the splitter checked space,
  so one large download could fill the disk and break SQLite for everybody.
- **Local Bot API cache health.** Startup checks whether the bot user can read
  `/var/lib/telegram-bot-api/<token>` and logs an actionable warning otherwise;
  the state (`ok` / `unreadable` / `missing` / `off`) is exposed as
  `bot_api_cache` in `/health`.

### Fixed
- **Stat events were never purged.** `repo.purge_events()` existed but had no
  caller, so the `events` table grew without limit; the cleanup loop now purges
  events older than 90 days.
- **Upload statistics double-counted after a video->document fallback.** The
  retry reset the progress percentage but not `uploaded_bytes_total`, so the
  first attempt's bytes stayed in the traffic counters; the upload-speed sample
  now also restarts at the retry.
- **A corrupt link file returned 503 forever.** On a size mismatch the link row
  and its file are removed and the request returns `410` instead of a
  permanently broken URL.
- **Zero-byte cache entries were treated as misses.** `cached_delivery` returns
  `int | None`, so a 0-byte archived file is still a valid cache hit.
- **Untracked background tasks in the queue.** `_finish_canceled` runs through a
  tracked task set with error logging, so a failing DB write can no longer leave
  a job stuck in `running`.
- **Blocking filesystem calls in the HTTP handler.** `stat`/`resolve`/`is_file`
  for link downloads run in a worker thread, so concurrent downloads no longer
  stall the event loop.
- **`shell=True` for the operator restart command.** The restart command is now
  split with `shlex` and executed without a shell.

### Tests
- `test_upload_cancel_aborts_task_and_keeps_cancel_button` waited only 3 s for
  the job to settle, which fails under coverage instrumentation; the budget is
  15 s now.
- New `tests/test_v5123_hardening.py` covers the disk guard, cache-state probe,
  retry keyboard/callback ownership and the `None` cache contract.

## [5.12.2] - 2026-11-02 — "Full Delivery"

### Fixed
- **Forwarded file → direct link failed with `Telegram file server HTTP 404`.**
  With the local Bot API (`--local`), `getFile` returns an absolute path
  (`/var/lib/telegram-bot-api/<token>/documents/…`). The bot process (uid 10001)
  cannot traverse that folder (owner uid 101, mode 750), so PTB could not treat it
  as a local file and rewrote it as
  `…/file/bot<token>/var/lib/telegram-bot-api/<token>/documents/…`, which the API
  answers with **404**. The transfer now keeps only the media-relative part of
  the path and requests `…/file/bot<token>/documents/…` (built from
  `TELEGRAM_API_FILE_URL`), falling back to the PTB URL only as a second
  candidate — so a forwarded file becomes a link on the first try. The Bot API
  cache folder is additionally made readable for the bot user, which repairs the
  same 404 for custom thumbnails, `cookies.txt` uploads and source-ZIP deploys.
- **MKV videos arrived as documents.** `PLAYABLE_VIDEO_EXT` only allowed
  `.mp4/.m4v/.mov`, so `.mkv` was forced into document mode both in the delivery
  panel (`can_send_as_video`) and in the uploader. MKV is now delivered as a
  video, keeping the existing automatic fallback to a document when Telegram
  rejects the codec, and a video container served with a generic
  `application/octet-stream` MIME is recognised by its extension too.
- **Slow mode, daily quota and the concurrent-link cap also hit admins.** These
  limits now skip the owner/admins (`current_admin`) and still apply to every
  normal user; an admin in preview mode is treated as a normal user again.

## [5.12.1] - 2026-11-01 — "Honest Progress"

### Changed
- **The upload phase now shows real progress towards Telegram.** Measured on
  the production server: our process hands a 300 MB file to the local Bot API
  server in **1.4 s**, then the server needs **17.5 s** to forward it to
  Telegram — and that second hop reports nothing back, so the message sat on
  `99% / ⏳ waiting for Telegram` and looked frozen. The status line now shows
  `📤 Uploading to Telegram servers` with a bar, speed and ETA estimated from
  the throughput this server actually achieves (a rolling average learned from
  real uploads, ~14 MB/s here).

### Notes
- The wait itself cannot be removed: the file really does have to reach
  Telegram's datacenter. On this machine the server's own uplink is ~640 Mbps
  while the route to Telegram tops out at ~110 Mbps (13.7 MiB/s, constant for
  100 MB and 400 MB), and routing the API server through WARP measured slower
  (12.0 MB/s), so ~14 MB/s is the ceiling here — 400 MB is ~29 s.

## [5.12.0] - 2026-11-01 — "Tuned Connections"

### Added
- **Tunable download connections.** The number of parallel `aria2c`
  connections for progressive downloads is now an admin setting
  (`aria2c_connections`, default **8**). In the admin panel: Settings →
  `🔌 Download connections (1–32): N`. Useful range is 1–32: a single
  connection is throttled by most CDNs (~0.1–1 MB/s measured), 8 already
  reaches ~10–30 MB/s, and above ~16 the extra sockets are often dropped or
  rate-limited per IP while the 2-core VPS spends more CPU on `aria2c`.
  Out-of-range values are clamped to the nearest limit and the saved value is
  shown in the confirmation and on the button.

## [5.11.4] - 2026-11-01 — "Real Progress"

### Fixed
- **Stuck download progress (0% / `0 B / ?`).** v5.11.0 handed progressive
  MP4 downloads to `aria2c`, which reports nothing back to yt-dlp: the progress
  hooks never fired, so the message stayed at `0%` for the whole download even
  while the file was arriving at ~27 MB/s. `downloader.watch_disk_progress`
  now reads the real byte count from the files on disk (`st_blocks`, so
  aria2c's sparse pre-allocation is not counted as downloaded data) and fills
  percent, speed and ETA. Direct/KVS downloads (`advance_progress`) now report
  speed and ETA too, instead of `— · —`.
- **Videos delivered with `00:00` duration.** Sites reached through yt-dlp's
  generic extractor (fpo.xxx, porntrex, …) have no duration in their metadata;
  Telegram then shows `00:00` (it does not probe large files itself). The
  downloaded file is now probed with `ffprobe` (`thumbs.probe_media`) and its
  real duration — plus the display width/height — is sent with the upload;
  split parts are probed individually.
- **Thumbnail picker skipped.** The 「Frame Pick」 album needs the duration to
  pick frame times; with `duration = 0` it silently fell back to the default
  cover. The same `ffprobe` probe fixes it, so the picker appears for those
  sites again.
- **AV1 delivered as a plain file.** Selecting an AV1 quality forced document
  mode. Telegram accepts AV1 MP4 as `sendVideo` (verified: `ok: true`), so AV1
  now arrives as a video; if Telegram ever refuses it, the uploader still
  falls back to a document instead of failing.
- **`Untitled` captions.** Eporner pages are downloaded through the embed URL,
  whose metadata has no title, so the caption and file name became
  `Untitled [id].mp4`. The download result now uses the same slug-based
  fallback title as the probe.
- **`AttributeError: 'NoneType' object has no attribute 'get'`** in
  `common.lang_of` when `context.user_data` is `None` (channel posts / anonymous
  admins) — no longer crashes the file handler.

### Changed
- While Telegram is still confirming an upload, the status line shows the
  elapsed time so a long server-side confirmation no longer looks frozen.

## [5.11.3] - 2026-11-01 — "Caption Link"

### Changed
- **The caption itself is the link.** Media captions no longer carry the
  `🔗 Source` label or hashtags: the title is rendered as a Telegram HTML link
  (`<a href="URL"><b>Title</b></a>`), so tapping the caption opens the original
  page of that video. The title stays bold and is truncated so the whole caption
  fits Telegram's 1024-character limit — truncation happens before escaping, so
  an HTML entity is never cut in half. If the URL alone is too long to leave room
  for a title, the caption falls back to the plain bold title.

## [5.11.2] - 2026-11-01 — "Quiet Reports"

### Fixed
- **False "crash: Timed out" reports after a successful delivery.** The Bot API
  client used python-telegram-bot's 5-second default read/write timeout, but the
  local Bot API server only answers after it has forwarded the whole file to
  Telegram (minutes for big videos). The upload was actually delivered while the
  bot marked the job as failed and filed an error report. Uploads now wait up to
  300 s for a response (600 s for the request body), and a network timeout is no
  longer retried as a document — that retry could send a second copy of the same
  file. Only an explicit `BadRequest` (e.g. unsupported codec) falls back to
  document delivery.
- **No more owner DMs for reports.** Job failures and user contact messages are
  sent only to the admin group's 🚨 reports topic; when no admin group is
  configured they stay in the admin panel, logs and stats instead of arriving as
  a private message. Contact messages now confirm as received once they are
  stored, even without a configured group.

## [5.11.1] - 2026-11-01 — "Sharp Frame"

### Fixed
- **Stretched / blurry thumbnails on Telegram Desktop.** The video's declared
  width/height are now read from the downloaded file with `ffprobe` (rotation
  and non-square pixels included), so the aspect ratio Telegram Desktop uses to
  draw the cover matches the real video and the image is no longer stretched.
  Frames and site covers are also encoded at `-q:v 2` with Lanczos scaling,
  `setsar=1` and a light sharpen pass (quality is stepped down only if a file
  would exceed Telegram's 200 KB limit), so the upscaled desktop preview looks
  sharp instead of blurry.

## [5.11.0] - 2026-10-31 — "Frame Pick"

### Added
- **Pick the cover yourself.** After a video download the bot grabs **10 frames**
  at random, spread-out timestamps and sends them as an album with a small
  panel: reply to any frame (any text) to use it as the thumbnail, or press
  **⏭ Skip** to upload immediately. If the user does nothing, the upload
  continues automatically with the default cover after the configured wait.
- Settings → **⏱ Thumbnail wait** (`thumb_wait_seconds`, 0–600 s, default 30;
  0 disables the album). Runtime setting, no restart needed.

### Fixed
- **Black / missing thumbnails.** When the site cover is missing or rejected,
  a real frame is now extracted from the downloaded video itself, so the file
  never arrives without a cover.

### Changed
- **Faster downloads.** Progressive MP4s are downloaded through `aria2c` with
  8 connections when the binary is present (`aria2` added to the Docker image),
  and HLS/DASH fragments are fetched 8 at a time instead of 4.

## [5.10.2] - 2026-10-31 · "Sharp Cover"

### Fixed
- **Half-rendered video thumbnails.** Covers are now downloaded completely
  (the body is checked against `Content-Length`, the silent 6 MB cut is gone)
  and normalized to a real, small JPEG (≤320×320, ≤200 KB) with ffmpeg, so
  WebP/AVIF/oversized or slightly broken covers can no longer reach Telegram
  as a truncated image. Without ffmpeg only complete JPEG/PNG covers are used.
- **Progress bar out of sync with the percentage.** The green cells were
  rounded up while the percentage was floored, so 95% could show a fully green
  bar. Both now use the same floored value; 100% is the only fully green bar.

## [5.10.1] - 2026-10-31 · "Archive Kept"

### Changed
- NSFW deliveries are archived in the admin group again, exactly like any other
  media; only the copy inside the user's chat is removed on schedule.
- Private DM copies are gone: the bot no longer sends an extra copy to the
  user's private chat (Saved Messages is not writable by bots), and the
  `📥 NSFW private copy` toggle was removed from Settings.
- NSFW media is no longer sent with a spoiler and keeps the normal delivery
  routine.
- NSFW jobs are still excluded from cache replay, so every adult delivery gets
  its own delete timer instead of a cached copy without one.

## [5.10.0] - 2026-10-31 · "Clean Chat"

### Added
- **NSFW auto-delete (temporary adult media).** When a delivery comes from an
  adult site, the bot announces under the file that it will disappear from the
  chat (default 30 s), counts down, then deletes every sent part. In private
  chats it just deletes; in groups/channels it first copies the parts to the
  user's DM so nothing is lost ("Saved Messages" is not writable by bots).
- Settings → **🔞 NSFW auto-delete** (off by default), delete delay (5–600 s),
  and **private copy** toggle; all three are runtime settings, no restart.
- Anti-restriction safeguards: NSFW files are sent with a spoiler in groups,
  are never cached in the admin group, DM copies are capped (30 files), and the
  countdown edits at most once every 10 s to avoid Telegram flood limits.

### Changed
- NSFW media is excluded from the delivery cache, so a cached adult file can
  never bypass the temporary-media policy.

## [5.9.1] - 2026-10-31 · "Split Delivery"

### Changed
- Upload cap raised to Telegram's real local-Bot-API ceiling: `MAX_UPLOAD_MB=1999`.
  Telegram's "2000 MB" is binary (2000 MiB = 2,097,152,000 bytes; verified by
  uploading a 1,999.9 MiB file), so a ~1.95 GB file is now delivered as a single
  file instead of being split into two parts.

### Fixed
- If Telegram still rejects a single upload as too large, the job no longer fails:
  `splitter.retry_limit()` picks a cap that guarantees at least two parts, the
  file is split on the spot and the parts are delivered automatically.

## [5.9.0] - 2026-10-31 · "Split Delivery"

### Added
- **Automatic splitting of files above the Telegram upload limit.** Before any
  download starts, the bot reports the real size and asks how many parts it will
  produce (e.g. a 2.7 GB video → 2 parts). Confirming splits the file into
  independent, playable video parts (`ffmpeg -c copy`) or byte parts for other
  files, then uploads each part separately with its own progress and caption.
- Part progress (“Part 2 of 3”) and localized part captions in fa/en/ru.
- `SplitTooMany`, `NotEnoughSpace` and `SplitFailed` errors with localized text.

### Changed
- The effective upload limit is centralized in `uploader.upload_limit()` and
  honours the Local Bot API configuration.
- The Local Bot API runs PTB in local mode, so downloaded files are read from
  disk instead of being re-uploaded through HTTP.

### Fixed
- Cancelling or failing a split upload removes every part already sent.

## [5.8.1] - 2026-10-31 · "App Shelf"

### Changed
- Every progress message (Telegram file receive, download, upload) now shows the
  **percentage on the line under the square bar** — e.g.
  `🟩 🟩 🟩 ⬜ …` then `42%` — in all three languages. The value is floored, so
  `100%` only appears once that step has actually finished.

## [5.8.0] - 2026-10-31 · "App Shelf"

### Added
- **Google Play links → APK/XAPK builds.** Send a `play.google.com/store/apps/details?id=…`
  (or `market://details?id=…`) link and the bot lists the available builds from
  APKPure — `arm64-v8a`, `armeabi-v7a`, `universal` — each with its version and
  real file size, instead of meaningless video qualities. Picking one downloads
  that exact file (Cloudflare cookies are obtained through byparr and refreshed
  automatically on `403`) and delivers it through the normal job pipeline.
- Builds larger than the Bot API limit automatically switch to **direct link**
  delivery, and the delivery button refuses (instead of downloading 150 MB and
  then failing) when Telegram cannot take the file.
- Admin **stats** now runs its queries concurrently, caches the disk-size walk
  for 30 s and reuses the rendered page for 3 s.

### Changed
- Admin audit events are dispatched in the background, so a slow Telegram send
  to the admin group no longer delays panel buttons by a few seconds.

### Fixed
- **Support messages** are now really delivered: if the reports topic is not
  configured or the group send fails, the message is sent to the owners in a
  private chat. The confirmation is a **new message** and only says
  “delivered” when a send actually succeeded; otherwise the user is told to
  retry instead of being lied to.

## [5.7.0] - 2026-10-31 · "Link Guard"

### Added
- **Concurrent direct-link cap** (`max_links_per_user`, default `0` = off).
  When an admin sets it to N, a user can keep at most N *active* signed links
  (unexpired, shared files). Asking for the next one is refused with a clear
  message and the draft stays alive, so the user only has to delete one old
  link from **My links** and tap the button again. Enforced at queue time, at
  delivery time (race-safe) and for file→link uploads.
- The cap is editable from **Admin → Settings → 🔗 Concurrent links** (three
  languages), and is also readable from `MAX_LINKS_PER_USER` in `.env`.

### Changed
- The request interval is now explicitly **processing-only** (download a link
  or upload a file). Menus, quality buttons, cancel and link management never
  consume it, and rejected attempts (quota/NSFW/concurrency) no longer start
  the timer. Labels renamed to «فاصلهٔ بین پردازش لینک/فایل».

## [5.6.8] - 2026-10-31 · "Site Rescue"

### Added
- **VK wall posts** (`vk.com/wall…`, `vk.ru/wall…`). yt-dlp returns an empty
  playlist for some wall posts and does not know `vk.ru` at all; the bot now
  reads the wall page with a crawler user-agent (OG tags, no captcha), extracts
  the real `video_ext.php` owner/id, and probes that video URL with the normal
  VK extractor. Downloads use the resolved video URL, not the wall page.
- **missav-style pages with no player iframe**: when the Cloudflare-solved page
  carries the master playlist inside Dean-Edwards-packed JavaScript, the package
  is unpacked and every `.m3u8` is considered (entries containing `playlist`
  first). Media-only playlists (no `#EXT-X-STREAM-INF`) are accepted as a single
  variant.
- HLS quality menu now shows an approximate size per variant, computed from the
  media playlist (`sum(EXTINF) × BANDWIDTH / 8`), so stream-only sites are not
  left with a bare `720p MP4` label.

### Fixed
- **TNAFlix locale URLs** (`/es/…`, `/de/…`, …) are rewritten to the canonical
  path before extraction, so the real resolutions (144p…1080p) are listed
  instead of anonymous `0 MP4`, `1 MP4` entries.
- Formats without `height` but with the resolution in the file name
  (`…-1080p.mp4`), format note, or format id get their height inferred; the
  quality menu no longer collapses such sites into one option.
- **Sizes for every site**, not only Eporner: at probe time missing sizes are
  filled in parallel with `HEAD` and, for CDNs that reject HEAD, a
  `Range: bytes=0-0` request. HLS/DASH variants without a HEAD-able file are
  estimated from duration × advertised bitrate.
- HLS downloads accept a manifest URL directly (missav) and fall back to the
  page's `.m3u8` links when no `hls3`/`hls2` config object exists.
- Aggregator pages whose video is hosted on **DoodStream/playmogo** (e.g.
  pornhoarder) now fail with a clear `captcha_wall` message instead of a generic
  403: those hosts gate the player behind an interactive Turnstile widget that
  no headless browser can pass without a human click.

## [5.6.7] - 2026-10-31 · "Cloud HLS"

### Added
- Support for tube sites behind a Cloudflare managed challenge (e.g.
  pornxday.com). When yt-dlp gets a 403, the bot asks **byparr** (Camoufox) to
  solve the challenge, finds the embedded player iframe, and unpacks its
  Dean-Edwards-packed JavaScript to read the real HLS links. The quality menu
  then lists every variant (480p/720p/1080p/2160p) with codec and format.
- Native HLS downloader: playlists and segments with unofficial extensions
  (`.txt` playlists, `.woff2` segments) are fetched segment by segment with
  progress and cancel support, concatenated, and remuxed to MP4 by ffmpeg
  without re-encoding. Segments are pulled over six parallel connections
  (the CDN throttles a single connection to ~0.6 MB/s), then joined in order.
  Audio options (`MP3 192k` / `M4A`) download the best variant once and
  extract the audio.
- HLS URLs are re-resolved from the embed page at download time because the
  CDN host rotates per request; the embed address travels with the quality
  draft, so no second Cloudflare solve is needed.

### Changed
- byparr is optional: set `BYPARR_URL` (default empty = disabled) to the
  byparr endpoint reachable from the bot container (host gateway
  `http://172.18.0.1:8191` in the current deployment).

## [5.6.6] - 2026-10-31 · "Quality List"

### Fixed
- Sites that label their versions instead of giving a resolution (e.g. fpo.xxx
  with `LQ` and `HQ`) no longer show a single quality. Formats without a height
  are listed as their own buttons (`LQ MP4`, `HQ 720p MP4`) instead of being
  dropped behind the best quality, and pages where *no* format has a height now
  get one button per named version. The site's own version name is kept in the
  label whenever it is one of `LQ/HQ/SD/HD/FHD/UHD`.

## [5.6.5] - 2026-10-31 · "KVS Rescue"

### Added
- Direct fallback for Kernel Video Sharing (KVS) sites such as pornwex.tv.
  yt-dlp's generic extractor currently fails with "Unable to extract
  flashvars" when the site randomizes the flashvars variable name. The bot now
  finds that object itself, rebuilds the signed media URL with yt-dlp's own KVS
  algorithm, and reads the real file size via a ranged request.
- KVS downloads re-read the page at download time, because the signed CDN URL
  expires. Audio options (`MP3 192k` / `M4A`) work too: the file is downloaded
  once and ffmpeg extracts the audio.
- Pages without resolution metadata now show `Best MP4` (plus size) instead of
  a bare `Best`, so the format is always visible.

## [5.6.4] - 2026-10-31 · "Format Labels"

### Changed
- The quality menu now shows the file format/codec for every site, not only
  Eporner: e.g. `1080p MP4 · 78.5 MB` or `720p WEBM`. The codec comes from the
  best-ranked format at each height, matching what the download selector picks.
- Sizes still appear whenever yt-dlp provides them; unknown sizes simply omit
  the size part.

## [5.6.3] - 2026-10-31 · "Codec Menu"

### Added
- Eporner quality menu now lists all ten versions: five MP4 and five AV1
  variants, one button per codec and resolution. AV1 versions are synthesized
  from the MP4 CDN URLs because yt-dlp's extractor only returns the MP4 set.
- Every video button shows the codec and the file size, e.g.
  `1080p MP4 · 78.5 MB` / `1080p AV1 · 27.2 MB`. Missing sizes are filled with
  bounded HEAD requests at probe time (Eporner only), and the hint line under
  the menu explains what the labels mean.
- Split-codec menus use the exact `format_id` so the chosen codec is really
  downloaded; synthesized AV1 variants download straight from their CDN URL
  while keeping the original title.

### Changed
- Formats with unknown `vcodec` (like Eporner's plain MP4 entries) are no
  longer treated as audio-only, so real quality options appear.
- Eporner videos keep a human title derived from the URL slug instead of
  "Untitled" (the embed page has no title).
- AV1 options default to document delivery because Telegram does not play AV1.

## [5.6.2] - 2026-10-31 · "Quiet Errors"

### Fixed
- Unsupported-link replies no longer include the raw extractor error or its
  GitHub issue URL. The user gets one short localized line; the full reason is
  still written to the log and the admin report.
- Other user-facing error reasons are stripped of URLs and collapsed to a
  single line (`errors.public_reason`).
- NSFW-blocked links get their own localized message instead of the generic
  unsupported text.

### Added
- `Downloader.extractor_url()` rewrites Eporner `/video-<id>/...` links to the
  `/embed/<id>/` endpoint. yt-dlp's normal Eporner path fails with
  "Unable to extract hash" for some regions/IPs (open upstream issue), while
  the embed endpoint extracts normally from the same host.

## [5.6.1] - 2026-10-31 · "Audit Clock"

### Fixed
- Direct-link HTTP access auditing compares `time.monotonic()` with a `None`
  sentinel instead of `0`. On a freshly booted host (monotonic below 300 s,
  e.g. CI runners) the first access was treated as "just logged" and skipped,
  so no audit entry was written for the first five minutes of uptime.
- `tests/test_cache_audit_v4.py` now waits for the link handler to finish
  while the test server is still alive before asserting the audit entry, so it
  no longer depends on shutdown timing.

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
