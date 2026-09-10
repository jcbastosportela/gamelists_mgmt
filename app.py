"""ROM Manager - Web application for managing EmulationStation gamelists."""

import os
import sys
import threading
import webbrowser
import mimetypes
from pathlib import Path
from lxml import etree
from flask import Flask, jsonify, request, send_from_directory, abort, render_template, Response, stream_with_context


def get_base_path():
    """Get the base path for bundled resources (PyInstaller support)."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


BASE_DIR = get_base_path()
app = Flask(
    __name__,
    static_folder=str(BASE_DIR / "static"),
    template_folder=str(BASE_DIR / "templates"),
)

# Configurable root path - defaults to EEROMS
ROM_ROOT = os.environ.get("ROM_ROOT", "/run/media/portela/EEROMS")


def get_systems():
    """List all system directories that contain a gamelist.xml."""
    root = Path(ROM_ROOT)
    if not root.exists():
        return []
    systems = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and (d / "gamelist.xml").exists():
            gamelist = d / "gamelist.xml"
            count = 0
            try:
                tree = etree.parse(str(gamelist))
                count = len(tree.findall(".//game"))
            except Exception:
                pass
            systems.append({
                "id": d.name,
                "name": d.name.replace("-", " ").replace("_", " ").title(),
                "game_count": count,
            })
    return systems


def parse_gamelist(system_id):
    """Parse a gamelist.xml and return structured game data."""
    gamelist_path = Path(ROM_ROOT) / system_id / "gamelist.xml"
    if not gamelist_path.exists():
        abort(404, description=f"Gamelist not found for system: {system_id}")

    tree = etree.parse(str(gamelist_path))
    root = tree.getroot()
    games = []

    for idx, game_el in enumerate(root.findall("game")):
        game = {"id": idx}
        # Parse all child elements
        for child in game_el:
            tag = child.tag
            text = child.text.strip() if child.text else ""
            # Resolve relative paths for media
            if tag in ("image", "video", "thumbnail", "mix"):
                if text.startswith("./"):
                    text = f"/api/media/{system_id}/{text[2:]}"
                elif not text.startswith("/") and not text.startswith("http"):
                    text = f"/api/media/{system_id}/{text}"
            game[tag] = text
        games.append(game)

    return games


def get_game_element(system_id, game_index):
    """Get the lxml element for a specific game by index."""
    gamelist_path = Path(ROM_ROOT) / system_id / "gamelist.xml"
    if not gamelist_path.exists():
        abort(404, description="Gamelist not found")
    tree = etree.parse(str(gamelist_path))
    root = tree.getroot()
    games = root.findall("game")
    if game_index < 0 or game_index >= len(games):
        abort(404, description="Game not found")
    return tree, root, games[game_index], gamelist_path


# --- Routes ---

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/systems")
def api_systems():
    return jsonify(get_systems())


@app.route("/api/systems/<system_id>/games")
def api_games(system_id):
    games = parse_gamelist(system_id)
    return jsonify(games)


@app.route("/api/systems/<system_id>/games/<int:game_id>", methods=["GET"])
def api_game_detail(system_id, game_id):
    games = parse_gamelist(system_id)
    if game_id < 0 or game_id >= len(games):
        abort(404, description="Game not found")
    return jsonify(games[game_id])


@app.route("/api/systems/<system_id>/games/<int:game_id>", methods=["PUT"])
def api_game_update(system_id, game_id):
    """Update a game entry in the gamelist.xml."""
    data = request.get_json()
    if not data:
        abort(400, description="No data provided")

    tree, root, game_el, gamelist_path = get_game_element(system_id, game_id)

    # Allowed fields to edit
    editable_fields = [
        "name", "desc", "image", "video", "thumbnail", "mix",
        "rating", "releasedate", "developer", "publisher", "genre",
        "players", "lang", "region", "sortname", "favorite", "hidden",
    ]

    for field in editable_fields:
        if field in data:
            el = game_el.find(field)
            value = data[field]
            if value is None or value == "":
                # Remove empty elements
                if el is not None:
                    game_el.remove(el)
            else:
                if el is None:
                    el = etree.SubElement(game_el, field)
                el.text = str(value)

    # Write back
    tree.write(str(gamelist_path), xml_declaration=True, encoding="UTF-8", pretty_print=True)
    return jsonify({"status": "ok", "message": "Game updated successfully"})


@app.route("/api/media/<path:filepath>")
def serve_media(filepath):
    """Serve media files with HTTP Range support (required for video playback)."""
    full_path = Path(ROM_ROOT) / filepath
    if not full_path.exists():
        abort(404, description="Media file not found")
    if not full_path.is_file():
        abort(404, description="Not a file")

    file_size = full_path.stat().st_size
    mime_type = mimetypes.guess_type(str(full_path))[0] or "application/octet-stream"

    # Handle Range requests (essential for video/audio seeking and playback)
    range_header = request.headers.get("Range")
    if range_header:
        # Parse "bytes=start-end"
        try:
            ranges = range_header.replace("bytes=", "").split("-")
            start = int(ranges[0]) if ranges[0] else 0
            end = int(ranges[1]) if ranges[1] else file_size - 1
        except (ValueError, IndexError):
            start, end = 0, file_size - 1

        # Clamp values
        start = max(0, min(start, file_size - 1))
        end = max(start, min(end, file_size - 1))
        chunk_size = end - start + 1

        def generate():
            with open(full_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    read_size = min(65536, remaining)
                    data = f.read(read_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        response = Response(
            stream_with_context(generate()),
            status=206,
            mimetype=mime_type,
        )
        response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Content-Length"] = chunk_size
        return response

    # No Range header — send full file
    def generate_full():
        with open(full_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data

    response = Response(
        stream_with_context(generate_full()),
        mimetype=mime_type,
    )
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Content-Length"] = file_size
    return response


@app.route("/api/open/<path:filepath>")
def open_with_system(filepath):
    """Open a file with the system's default application."""
    import subprocess
    full_path = Path(ROM_ROOT) / filepath
    if not full_path.exists():
        abort(404, description="File not found")
    if not full_path.is_file():
        abort(404, description="Not a file")

    try:
        if sys.platform == "linux":
            subprocess.Popen(["xdg-open", str(full_path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(full_path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            os.startfile(str(full_path))
        else:
            abort(500, description="Unsupported platform")
        return jsonify({"status": "ok", "message": f"Opened {full_path.name}"})
    except Exception as e:
        abort(500, description=str(e))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ROM Manager - EmulationStation gamelist viewer & editor")
    parser.add_argument("rom_root", nargs="?", default=os.environ.get("ROM_ROOT", "/run/media/portela/EEROMS"),
                        help="Path to ROM root directory (default: /run/media/portela/EEROMS)")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    ROM_ROOT = args.rom_root
    if not Path(ROM_ROOT).exists():
        print(f"❌ Error: ROM root path does not exist: {ROM_ROOT}")
        sys.exit(1)

    url = f"http://{args.host}:{args.port}"
    print(f"🎮 ROM Manager starting...")
    print(f"📂 ROM Root: {ROM_ROOT}")
    print(f"🌐 Opening {url} in your browser")

    if not args.no_browser:
        threading.Timer(1.25, lambda: webbrowser.open(url)).start()

    app.run(debug=False, host=args.host, port=args.port)
