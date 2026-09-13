# AGENTS.md

Instructions for AI agents working in this repository. Read this first — it tells you
what the project is and exactly which file to open for your task.

## Project overview

**ROM Manager** is a self-contained Python/Flask desktop app for browsing and editing
[EmulationStation](https://emulationstation.org/) `gamelist.xml` files on retro-handheld
devices (EmuELEC, ArkOS, JELOS, ROCKNIX). It scans a ROM collection directory for systems,
shows games with screenshots/videos, and edits game metadata directly in the XML.

There is **no frontend framework, no database, and no test suite** — just a single Flask app,
one HTML page of vanilla JS, and a PyInstaller packaging layer.

```
app.py                 # ENTIRE backend: routes, gamelist parsing/writing, media serving
templates/index.html   # ENTIRE frontend: single-page UI (inline CSS + JS), ~2300 LOC
rom_manager/main.py    # Desktop launcher: Flask in a thread + native window / chromium fallback
static/                # PWA bits (sw.js, manifest.json, icons)
requirements.txt       # flask, lxml, pyinstaller (pywebview optional)
setup.sh / build.sh    # One-command setup+PyInstaller build+desktop shortcut
rom-manager.spec       # PyInstaller config (hiddenimports, bundles templates/ + static/)
.github/workflows/release.yml  # PR version-label check + release/rebuild jobs
```

## Where to change things (start here)

| Task | File |
|------|------|
| Any `/api/*` route, gamelist.xml parsing/writing, ROM import, image/media handling, backups | `app.py` |
| All UI/UX: layout, styles, modals, search, detail/edit/import/favorite flows, all `fetch()` calls | `templates/index.html` |
| Desktop window launcher, CLI args (`--port/--host/--width/--height`), port selection, pywebview→Chromium→browser fallback | `rom_manager/main.py` |
| Service worker / PWA manifest / app icons | `static/` |
| Python dependencies | `requirements.txt` |
| Packaging (hidden imports, bundled `templates/` + `static/`, binary name) | `rom-manager.spec` |
| Setup / build / desktop-shortcut automation | `setup.sh` (`build.sh` is just a thin wrapper) |
| CI: PR version-label gate, version bump on merge, release publishing, manual rebuild | `.github/workflows/release.yml` |
| Docs / contribution conventions | `README.md`, `CONTRIBUTING.md` |

## Key facts and gotchas

- **No tests, no linter.** Verify manually (see below). Keep changes lightweight: the repo
  convention (per `CONTRIBUTING.md`) is vanilla JS + Flask only — no JS frameworks/build tools.
- **ROM_ROOT** (module global in `app.py`) points at the ROM collection; default
  `/run/media/portela/EEROMS` or `$ROM_ROOT`. "Systems" = subdirectories containing a
  `gamelist.xml`. It is set from the CLI arg (`python app.py <rom_root>`) or by mutating
  `app_module.ROM_ROOT` in `rom_manager/main.py`.
- **Game IDs are positional** — the index of a `<game>` element in `gamelist.xml` (0-based).
  They shift when games are removed, so the frontend always re-fetches after a mutation.
  Never treat game IDs as stable storage keys.
- **Every gamelist write MUST go through `_write_gamelist()`** in `app.py`: it creates a
  timestamped `.bak` backup before writing (via `_backup_gamelist()`). Never write XML
  directly from new code.
- Media fields (`image`, `video`, `thumbnail`, `mix`) are stored as *relative* paths in the
  XML but returned to the API as `/api/media/<system>/<path>` URLs. `/api/media/...` supports
  HTTP Range requests (required for video playback/seeking) — don't break that when touching
  the media route.
- Editable metadata is a **whitelist** in `api_game_update()` (`editable_fields`). To let the
  UI edit a new gamelist tag, add it there (and mirror the form in `templates/index.html`).
- ROMs/images are imported with safe leaf names: `_sanitize_filename()` + `_unique_path()`
  (no overwrites); images are named after the ROM stem, e.g. `rom.png` → `images/rom.png`.
  New write paths should reuse these helpers.
- Two entry points: `python app.py` (dev, opens browser) vs `python -m rom_manager.main`
  (desktop launcher). Both validate that the ROM root exists and exit(1) otherwise.
- `rom_manager/__init__.py` is intentionally empty; `rom_manager/main.py` inserts the repo
  root into `sys.path` so `from app import app` works from source and from the PyInstaller
  binary (the spec also has a hidden import for `app`).

## Run / verify

```bash
# Browser mode (dev) — needs a real ROM root with gamelist.xml subdirs
python app.py /path/to/your/roms

# Desktop window mode
python -m rom_manager.main /path/to/your/roms

# Full build (venv + PyInstaller binary + desktop shortcut)
./setup.sh        # or ./build.sh
./dist/rom-manager /path/to/your/roms
```

There is no automated test command. Validate backend changes by exercising the affected
endpoints (`curl localhost:5000/api/...`) and UI changes in a browser against a real
`gamelist.xml`, as CI does not run tests.

## Release / PR conventions (important when opening PRs)

- Branch names used in this repo: `feature/*`, `docs/*`, `release/*`. PRs target `main`.
- **PRs must have exactly one** of the labels `patch` / `minor` / `major` — or the
  `no_impact` label to skip the release for changes that don't ship a new version
  (e.g. README/docs-only edits). The `check` job in `.github/workflows/release.yml` fails
  otherwise (treat it as a required status check).
- On merge to `main`, the `release` job auto-detects the merged PR. A PR labeled `no_impact`
  skips the release (no version bump, tag, build, or publish — the job still passes green);
  otherwise it bumps the version from the version label, tags, builds the PyInstaller binary,
  and publishes a GitHub release. Direct pushes to `main` are **not** releaseable (no merged
  PR to derive a version from).
- `workflow_dispatch` input `tag` lets you rebuild/re-publish an existing tag manually.