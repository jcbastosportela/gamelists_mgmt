# 🎮 ROM Manager

A web-based manager for browsing and editing [EmulationStation](https://emulationstation.org/) gamelist XML files. Designed for handheld emulation devices (EmuELEC, ArkOS, JELOS, ROCKNIX, etc.) that store ROM metadata in `gamelist.xml` files.

## Features

- **System browser** — auto-detects all systems with a `gamelist.xml`
- **Game grid & list views** — browse games with screenshots, metadata, and filters
- **Media preview** — view screenshots, thumbnails, and play `.mp4`/`.webm` videos inline
- **System player fallback** — open `.avi` and other unsupported formats with your default video player
- **Gamelist editing** — update game metadata and save directly to XML (edit name, description, genre, rating, etc.)
- **Search** — filter games by name, genre, developer, or publisher
- **Standalone executable** — single binary, no dependencies needed on the target machine

## Quick Start

### Setup & Build (recommended)

```bash
./setup.sh
```

This single script:
1. Installs system dependencies (WebKitGTK for the native window)
2. Creates a Python virtual environment
3. Installs all Python packages
4. Builds a standalone binary at `dist/rom-manager`
5. Creates a desktop shortcut — find **"ROM Manager"** in your app menu

Then launch from your app menu, or:

```bash
./dist/rom-manager                          # Default ROM path
./dist/rom-manager /path/to/roms            # Custom ROM path
```

### Run from source (development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Native desktop window (requires pywebview + WebKitGTK)
python -m rom_manager.main /path/to/your/roms

# Browser-based (dev mode)
python app.py /path/to/your/roms
```

## Usage

```bash
./rom-manager [ROM_ROOT] [OPTIONS]

Positional:
  rom_root              Path to ROM root directory (default: $ROM_ROOT, saved config, or /run/media/portela/EEROMS)

Options:
  --port PORT           Port to listen on (default: auto)
  --host HOST           Host to bind to (default: 127.0.0.1)
  --width WIDTH         Window width (default: 1280)
  --height HEIGHT       Window height (default: 800)
  --no-browser          Don't open a window/browser (server only)
```

### ROM root selection

The ROM root (the directory containing the emulator system folders) is
resolved in this order — the first one that exists wins:

1. The `rom_root` CLI argument
2. The `ROM_ROOT` environment variable
3. The last interactively selected directory (`~/.config/rom-manager/config.json`)
4. The hardcoded default (`/run/media/portela/EEROMS`)

If none of them exists, the app asks you to pick the directory: mounted
storage locations (under `/run/media`, `/media`, `/mnt`) are offered as a
numbered list, or you can type a custom path.  The selection is saved so
the next launch starts without prompting.


## Supported Media

| Format | Browser Playback | System Player |
|--------|:---:|:---:|
| `.mp4`  | ✅ | ✅ |
| `.webm` | ✅ | ✅ |
| `.ogg`  | ✅ | ✅ |
| `.avi`  | ❌ | ✅ |

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/systems` | GET | List all systems with game counts |
| `/api/systems/<id>/games` | GET | Get all games for a system |
| `/api/systems/<id>/games/<id>` | GET | Get a single game's details |
| `/api/systems/<id>/games/<id>` | PUT | Update a game entry |
| `/api/media/<path>` | GET | Serve media files (with Range support) |
| `/api/open/<path>` | GET | Open file with system default application |

## Project Structure

```
.
├── app.py                  # Flask backend (routes + API)
├── rom_manager/
│   ├── __init__.py
│   └── main.py             # Native window launcher (pywebview)
├── templates/
│   └── index.html          # Single-page frontend
├── static/                 # Static assets (icons, manifest, SW)
├── requirements.txt        # Python dependencies
├── setup.sh                # Full setup: system deps + venv + build + shortcut
├── build.sh                # Alias for setup.sh
├── rom-manager.spec        # PyInstaller build config
└── dist/                   # Build output (gitignored)
```

## Tech Stack

- **Backend:** Python, Flask, lxml
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **Native window:** pywebview (WebKitGTK on Linux)
- **Packaging:** PyInstaller

## License

MIT