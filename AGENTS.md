# AGENTS.md

Instructions for AI agents and contributors working on **LeechX**.

## Golden rules

1. **Version first.** Every source change must bump the version in **all three**
   places, consistently:
   - `app/version.py` → `__version__` (single source of truth)
   - `pyproject.toml` → `[project].version`
   - `CHANGELOG.md` → newest `## [x.y.z]` entry

   `tests/test_version.py` fails when they disagree. Check the current version:

   ```bash
   python -m app.version          # vX.Y.Z "Codename" (date)
   python -m app.version patch    # prints the next patch version
   ```

2. **Never commit secrets.** No `.env`, tokens, cookies, `data/`, `*.db`,
   `keys_en.json`. Diagnostics tokens (`lxdbg_...`) are one-time secrets.
3. **Do not break Persian/English/Russian parity.** `app/core/text.py` is the only
   source of UI strings. Every key must exist in `FA`, `EN`, `RU` and be non-empty.
   Fallback chain: `ru → en → fa`; unknown languages fall back to Persian.
4. **Keep the admin UI uncluttered.** Use the categorized admin panels and
   two-column menus in `app/bot/keyboards.py`; do not add dense flat keyboards.
5. **Respect the source-write boundaries.** `.env`, `data/`, `.git`,
   `__pycache__`, `.venv` are never written by ZIP import or the debug API.

## Project layout

```
app/
  bot/          Telegram layer: app.py, keyboards.py, guards.py,
                flows/ (start, link, callbacks, admin, files, text_router, …)
  services/     downloader, uploader, jobs, link server, updater,
                force_join, debug_access, runtime_settings, …
  db/           SQLAlchemy models + repo (all DB access goes through repo)
  core/         text (i18n), human helpers, errors, urlcheck
tests/          pytest suite (no network); see tests/conftest.py for fixtures
docs/           Persian documentation (debug API, cookies, architecture, …)
main.py         entrypoint (also `--check`)
```

## Development workflow

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py --check

python -m ruff check app main.py tests
python -m pytest -q
```

CI runs exactly those two commands (with `BOT_TOKEN`, `OWNER_IDS`, `LINK_SECRET`
set). Fix lint before pushing.

## Feature pointers

- **Runtime settings** (`runtime_settings.py`): add to `SCHEMA`, `_default`,
  optionally `RUNTIME_KEYS`, expose a property, and add localized `run_<key>`
  labels to `text.py`.
- **New admin action**: add callback data in `keyboards.py`, route it in
  `flows/admin.py` (`on_callback`), add text keys, and a state in
  `bot/states.py` if you need free-text input.
- **New language**: add a dict with every key to `text.py`, register it in
  `LANGS`/`MESSAGES`/`FALLBACK`, and keep the flag emoji.
- **Deploy**: `services/updater.py` (ZIP export/validate/apply, backup,
  restart, yt-dlp upgrade). Restart hook lives in `container.Services.teardown`.
- **Diagnostics**: `services/debug_access.py`. Tokens are hashed, max 24h,
  scoped `read`/`write`/`restart`. `/debug/*` routes are always registered and
  gated at request time by `debug_enabled` (default on), so the admin can toggle
  it from the 🩺 section without a restart.
- **Forced join**: `services/force_join.py` + the gate at the top of
  `bot/app.py`. Membership checks are cached and fail-open on Telegram errors.
- **Preview mode**: `bot/guards.py` + `flows/start.py`; admins in preview must
  behave exactly like normal users (including the force-join gate).

## Tests

- `tests/test_smoke.py` — translations parity, config, handler registration.
- `tests/test_flows.py`, `test_new_features.py`, etc. — flow/keyboard behavior.
- `tests/test_version.py` — version consistency.
- `tests/test_languages.py` — three languages, flags, fallback.
- `tests/test_force_join.py`, `test_preview_gate.py` — membership and preview.
- `tests/test_deploy_debug.py` — ZIP roundtrip/traversal and debug API.

Tests must not touch the network, the real `data/` directory or the real source
tree (use `tmp_path` and pass `root=` to `SourceUpdater`).

## Live deployment

Admin panel → 🚀 **Deploy**: download the source ZIP, upload a new one, validate,
apply (automatic backup in `data/updates/`) and restart. For remote/AI work use a
short-lived diagnostics token — see [`docs/DEBUG_API_FA.md`](docs/DEBUG_API_FA.md).
