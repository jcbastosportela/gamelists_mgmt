"""ROM Manager - Standalone launcher.

Starts the Flask backend in a background thread and opens a standalone
desktop window with no browser chrome.  Tries, in order:

1. pywebview  — native OS webview (works from source when GI is available)
2. Chromium --app mode  — standalone window, works with PyInstaller binaries
3. Default browser      — regular tab (last resort)
"""

import os
import sys
import shutil
import socket
import subprocess
import threading
import time
import argparse
from pathlib import Path

try:
    from rom_manager.rom_root import resolve_rom_root  # absolute: works frozen & from source
except ImportError:  # frozen fallback if the package isn't importable
    from rom_root import resolve_rom_root  # type: ignore

# Ensure the project root is importable so ``from app import app`` works
# regardless of how the binary / script is invoked.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ── Chromium-based browsers that support --app mode ──────────
_CHROMIUM_BINS = [
    "chromium", "chromium-browser",
    "google-chrome", "google-chrome-stable",
    "opera", "opera-browser",
    "microsoft-edge", "microsoft-edge-stable",
    "brave-browser", "brave-browser-stable",
    "vivaldi", "vivaldi-stable",
]


def _find_chromium():
    """Return the path to a Chromium-based browser, or None."""
    for name in _CHROMIUM_BINS:
        path = shutil.which(name)
        if path:
            return path
    # Common snap / flatpak paths
    for p in [
        "/snap/bin/chromium",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/opera",
    ]:
        if Path(p).is_file():
            return p
    return None


def _open_with_chromium_app(url, width, height):
    """Open *url* in a Chromium --app standalone window. Returns the Popen."""
    browser = _find_chromium()
    if not browser:
        return None
    try:
        proc = subprocess.Popen(
            [
                browser,
                f"--app={url}",
                f"--window-size={width},{height}",
                "--class=rom-manager",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc
    except Exception:
        return None


def _open_with_pywebview(url, width, height):
    """Open *url* in a native OS webview window. Raises on failure."""
    import webview  # noqa: delayed import so the module is optional

    window = webview.create_window(
        "ROM Manager",
        url,
        width=width,
        height=height,
        min_size=(900, 600),
        text_select=True,
    )
    webview.start(debug=False)


def _find_free_port():
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── CLI ──────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(
        description="ROM Manager - EmulationStation gamelist viewer & editor"
    )
    parser.add_argument(
        "rom_root", nargs="?", default=None,
        help="Path to ROM root directory (default: $ROM_ROOT, saved config, or /run/media/portela/EEROMS; prompts interactively if not found)",
    )
    parser.add_argument("--port", type=int, default=0, help="Port (default: auto-select)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--width", type=int, default=1280, help="Window width")
    parser.add_argument("--height", type=int, default=800, help="Window height")
    parser.add_argument("--no-browser", action="store_true",
                        help="Don't open a window/browser (server only)")
    return parser.parse_args()


# ── Main ─────────────────────────────────────────────────────

def main():
    args = _parse_args()

    rom_root = resolve_rom_root(cli_value=args.rom_root)
    if rom_root is None:
        print("❌ Error: no ROM root directory available.")
        print("   Pass the path as an argument, set the ROM_ROOT environment variable,")
        print("   or select a directory when prompted.")
        sys.exit(1)
    rom_root = str(rom_root)

    # Import and configure the Flask app
    from app import app as flask_app  # noqa: F811
    import app as app_module
    app_module.ROM_ROOT = rom_root

    port = args.port or _find_free_port()
    url = f"http://{args.host}:{port}"

    # Start Flask in a daemon thread
    server_thread = threading.Thread(
        target=lambda: flask_app.run(
            debug=False, host=args.host, port=port, use_reloader=False,
        ),
        daemon=True,
    )
    server_thread.start()

    # Wait for Flask to be ready
    import urllib.request
    for _ in range(50):
        try:
            urllib.request.urlopen(url, timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)

    print(f"🎮 ROM Manager")
    print(f"📂 ROM Root: {rom_root}")
    print(f"🌐 Server:   {url}")

    # ── Try opening a standalone window ──────────────────────
    is_frozen = getattr(sys, 'frozen', False)

    if args.no_browser:
        print("(server only — no window/browser opened)")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass
        return

    # Strategy 1: pywebview (native webview — only works from source with GI)
    if not is_frozen:
        try:
            _open_with_pywebview(url, args.width, args.height)
            return  # pywebview blocks until window is closed
        except ImportError:
            pass  # not installed, try next
        except Exception as e:
            print(f"⚠️  pywebview: {e}")

    # Strategy 2: Chromium --app mode (standalone window, no chrome)
    proc = _open_with_chromium_app(url, args.width, args.height)
    if proc is not None:
        try:
            proc.wait(timeout=3)  # If it exits quickly, the window was handed off to an existing browser
            # Process exited fast — window is managed by the existing browser instance.
            # Keep the server alive until the user kills us (Ctrl+C, app menu close, etc.)
            print("(standalone window opened in your browser)")
            server_thread.join()
        except subprocess.TimeoutExpired:
            # Process is still running — the browser owns the window; wait for it to close
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
        return

    # Strategy 3: default browser (regular tab — last resort)
    print("⚠️  No standalone window available — opening in default browser.")
    print("   For a native window, install pywebview: pip install pywebview")
    import webbrowser
    webbrowser.open(url)
    try:
        server_thread.join()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
