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

### Run from source

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask lxml

# Default ROM path: /run/media/portela/EEROMS
python app.py

# Custom ROM path
python app.py /path/to/your/roms

# Custom port
python app.py --port 8080
```

Then open http://localhost:5000 in your browser.

### Build standalone executable

```bash
./build.sh
```

This creates a single executable at `dist/rom-manager`:

```bash
./dist/rom-manager                          # Default ROM path
./dist/rom-manager /path/to/roms            # Custom ROM path
./dist/rom-manager --port 8080              # Custom port
./dist/rom-manager --no-browser             # Don't auto-open browser
```

## Usage

```bash
./rom-manager [ROM_ROOT] [OPTIONS]

Positional:
  rom_root              Path to ROM root directory (default: /run/media/portela/EEROMS)

Options:
  --port PORT           Port to listen on (default: 5000)
  --host HOST           Host to bind to (default: 127.0.0.1)
  --no-browser          Don't auto-open browser
```

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
├── app.py              # Flask backend
├── templates/
│   └── index.html      # Single-page frontend
├── static/             # Static assets
├── rom-manager.spec    # PyInstaller build config
├── build.sh            # Build script
└── dist/               # Build output (gitignored)
```

## Tech Stack

- **Backend:** Python, Flask, lxml
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **Packaging:** PyInstaller

## License

MIT