# Contributing

Contributions are welcome! Here's how to get started.

## Development Setup

```bash
git clone git@github.com:jcbastosportela/gamelists_mgmt.git
cd gamelists_mgmt

python3 -m venv .venv
source .venv/bin/activate
pip install flask lxml

python app.py /path/to/your/roms
```

## Project Layout

- `app.py` — Flask backend with REST APIs and media serving
- `templates/index.html` — Single-page frontend (HTML + CSS + JS, no build step)
- `rom-manager.spec` — PyInstaller build configuration
- `build.sh` — One-command build script

## Making Changes

1. Create a branch: `git checkout -b feature/my-feature`
2. Make your changes
3. Test locally: `python app.py /path/to/roms`
4. Test the build: `./build.sh && ./dist/rom-manager --no-browser`
5. Commit and push
6. Open a Pull Request against `main`
7. Label the PR for the release: add exactly one of `patch` / `minor` / `major`
   so CI can version the next release — or use `no_impact` for changes that
   should skip the release entirely (e.g. README/docs-only edits). The `check`
   job blocks merging without one of these labels.

## Guidelines

- Keep the app lightweight — no heavy JS frameworks, no build tools
- Backend changes go in `app.py`
- Frontend changes go in `templates/index.html`
- Test against real gamelist.xml files when possible
- Follow existing code style
- Label docs-only / non-user-facing changes (README, CI config, etc.) with `no_impact`
  so merging them does not cut a new release

## Ideas for Contributions

- Gamelist XML editing UI (form-based)
- Bulk operations (rename, delete, reorganize)
- Thumbnail/mix image generation
- Multi-language support
- Dark/light theme toggle
- ROM file management (copy, move, delete)
