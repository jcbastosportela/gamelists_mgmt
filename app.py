"""ROM Manager - Web application for managing EmulationStation gamelists."""

import os
import sys
import re
import shutil
import threading
import webbrowser
import mimetypes
import urllib.request
import uuid
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


from datetime import datetime


def _backup_gamelist(gamelist_path):
    """Create a timestamped backup of the gamelist before modifying it."""
    if not gamelist_path.exists():
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = gamelist_path.parent / f"{gamelist_path.stem}.{ts}.bak"
    # Don't overwrite if same-second backup already exists
    if not backup.exists():
        shutil.copy2(str(gamelist_path), str(backup))


def _write_gamelist(tree, gamelist_path):
    """Backup then write the gamelist with proper pretty-printing."""
    _backup_gamelist(gamelist_path)
    tree.write(
        str(gamelist_path),
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    )


# --- Routes ---

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/manifest.json")
def serve_manifest():
    """Serve the PWA manifest with correct content type."""
    return send_from_directory(str(BASE_DIR / "static"), "manifest.json", mimetype="application/manifest+json")


@app.route("/sw.js")
def serve_sw():
    """Serve the service worker from root scope so it can control all routes."""
    return send_from_directory(str(BASE_DIR / "static"), "sw.js", mimetype="application/javascript")


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

    # Allowed fields to edit (everything except resource paths)
    editable_fields = [
        "name", "desc",
        "genre", "developer", "publisher", "releasedate", "rating",
        "players", "lang", "region", "sortname",
        "favorite", "hidden",
        "playcount", "lastplayed", "gametime",
        "emulator", "core", "web", "system", "software", "provider", "hash",
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
    _write_gamelist(tree, gamelist_path)
    return jsonify({"status": "ok", "message": "Game updated successfully"})


@app.route("/api/systems/<system_id>/games/<int:game_id>/favorite", methods=["POST"])
def api_toggle_favorite(system_id, game_id):
    """Toggle the favorite flag on a game entry."""
    tree, root, game_el, gamelist_path = get_game_element(system_id, game_id)
    fav_el = game_el.find("favorite")
    if fav_el is not None and fav_el.text and fav_el.text.strip().lower() in ("true", "1", "yes"):
        # Currently favorited → remove
        game_el.remove(fav_el)
        new_state = False
    else:
        # Not favorited → set
        if fav_el is None:
            fav_el = etree.SubElement(game_el, "favorite")
        fav_el.text = "true"
        new_state = True
    _write_gamelist(tree, gamelist_path)
    return jsonify({"status": "ok", "favorite": new_state})


@app.route("/api/systems/<system_id>/games/<int:game_id>", methods=["DELETE"])
def api_delete_game(system_id, game_id):
    """Remove a game from the gamelist, optionally deleting its files from disk."""
    data = request.get_json(silent=True) or {}
    delete_files = data.get("delete_files", False)

    tree, root, game_el, gamelist_path = get_game_element(system_id, game_id)

    # Collect associated file paths before removing the element
    files_to_delete = []
    if delete_files:
        system_dir = Path(ROM_ROOT) / system_id
        path_el = game_el.find("path")
        if path_el is not None and path_el.text:
            rom_path = system_dir / path_el.text.strip().lstrip("./")
            if rom_path.exists() and rom_path.is_file():
                files_to_delete.append(rom_path)
        for tag in ("image", "video", "thumbnail", "mix"):
            el = game_el.find(tag)
            if el is not None and el.text:
                media_path_str = el.text.strip()
                if media_path_str.startswith("./"):
                    media_path = system_dir / media_path_str[2:]
                elif not media_path_str.startswith("/") and not media_path_str.startswith("http"):
                    media_path = system_dir / media_path_str
                else:
                    continue
                if media_path.exists() and media_path.is_file():
                    files_to_delete.append(media_path)

    # Remove from gamelist
    game_name_el = game_el.find("name")
    game_name = game_name_el.text.strip() if game_name_el is not None and game_name_el.text else "Unknown"
    root.remove(game_el)
    _write_gamelist(tree, gamelist_path)

    # Delete files if requested
    deleted_files = []
    if delete_files and files_to_delete:
        for f in files_to_delete:
            try:
                f.unlink()
                deleted_files.append(str(f.relative_to(Path(ROM_ROOT))))
            except OSError:
                pass
        # Clean up empty parent dirs (like images/) but not the system dir itself
        for f in files_to_delete:
            parent = f.parent
            if parent != Path(ROM_ROOT) / system_id:
                try:
                    if parent.exists() and not any(parent.iterdir()):
                        parent.rmdir()
                except OSError:
                    pass

    return jsonify({
        "status": "ok",
        "message": f"Removed \"{game_name}\" from gamelist",
        "deleted_files": deleted_files,
    })


def _sanitize_filename(name):
    """Remove or replace characters unsafe for filenames."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = name.strip('. ')
    return name[:200] if name else 'image'


def _get_images_dir(system_id):
    """Get (and create) the images directory for a system."""
    images_dir = Path(ROM_ROOT) / system_id / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    return images_dir


def _unique_path(target_dir, filename):
    """Return a unique file path in target_dir, appending a suffix if needed."""
    p = target_dir / filename
    if not p.exists():
        return p
    stem = p.stem
    suffix = p.suffix
    for i in range(1, 1000):
        p = target_dir / f"{stem}_{i}{suffix}"
        if not p.exists():
            return p
    return target_dir / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"


def _set_game_image_field(system_id, game_index, field_name, new_value):
    """Set an image-related field on a game element and save the gamelist."""
    tree, root, game_el, gamelist_path = get_game_element(system_id, game_index)
    el = game_el.find(field_name)
    if new_value is None or new_value == "":
        if el is not None:
            game_el.remove(el)
    else:
        if el is None:
            el = etree.SubElement(game_el, field_name)
        el.text = new_value
    _write_gamelist(tree, gamelist_path)


def _rom_stem_for_game(system_id, game_index):
    """Get the ROM filename stem for a game (without extension), for image naming."""
    _, _, game_el, _ = get_game_element(system_id, game_index)
    path_el = game_el.find("path")
    if path_el is not None and path_el.text:
        rom_name = path_el.text.strip().lstrip("./")
        return _sanitize_filename(Path(rom_name).stem)
    # Fallback to game name
    name_el = game_el.find("name")
    if name_el is not None and name_el.text:
        return _sanitize_filename(name_el.text.strip())
    return f"game_{game_index}"


def _resolve_rom_path(system_id, relative_path):
    """Resolve a relative path (like ./snap/foo.png or images/foo.png) to absolute."""
    rel = relative_path.lstrip("./")
    return Path(ROM_ROOT) / system_id / rel


ROM_EXTENSIONS = {
    ".nes", ".sfc", ".smc", ".gba", ".gb", ".gbc", ".gen", ".md", ".smd",
    ".n64", ".z64", ".v64", ".nds", ".3ds", ".nds", ".gba", ".gb",
    ".iso", ".bin", ".cue", ".img", ".mdf", ".chd",
    ".zip", ".7z", ".rar",
    ".pce", ".sgx", ".ngp", ".ngc", ".ws", ".wsc",
    ".rom", ".col", ".sg", ".sms", ".gg", ".int",
    ".j64", ".lnx", ".a26", ".a52", ".a78",
    ".mgw", ".uze", ".vec", ".vb",
    ".scummvm", ".svm",
    ".pbp", ".cso", ".elf",
    ".d64", ".t64", ".tap", ".prg",
    ".cas", ".dsk", ".m3u",
    ".rvz", ".gcm", ".gcz",
    ".lha", ".adf", ".hdf",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".webm", ".ogv"}


@app.route("/api/systems/<system_id>/games/<int:game_id>/image", methods=["POST"])
def api_upload_image(system_id, game_id):
    """
    Add or replace a game image.
    Accepts:
      - multipart file upload (field: "file")
      - JSON body with {"url": "https://..."} for downloading from the internet
      - JSON body with {"path": "./snap/existing.png"} for an image already on the ROM filesystem
    In all cases, "field" specifies which gamelist field to set (default: "image").
    Images are named after the ROM file (same stem, different extension).
    """
    images_dir = _get_images_dir(system_id)
    field_name = request.form.get("field") or request.args.get("field", "image")
    if field_name not in ("image", "thumbnail", "mix"):
        abort(400, description="field must be one of: image, thumbnail, mix")

    # Get ROM stem for image naming (Req2 addendum: same name as ROM, different ext)
    rom_stem = _rom_stem_for_game(system_id, game_id)

    # --- Scenario A: file uploaded from host ---
    if "file" in request.files:
        upload = request.files["file"]
        if not upload.filename:
            abort(400, description="No file selected")
        ext = Path(upload.filename).suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            abort(400, description=f"Unsupported image format: {ext}")
        safe_name = f"{rom_stem}{ext}"
        dest = _unique_path(images_dir, safe_name)
        upload.save(str(dest))

    else:
        data = request.get_json(silent=True) or {}
        # --- Scenario C: download from URL ---
        if "url" in data and data["url"]:
            url = data["url"]
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "ROMManager/1.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    ext = _ext_from_content_type(content_type) or _ext_from_url(url) or ".png"
                    img_data = resp.read()
                safe_name = f"{rom_stem}{ext}"
                dest = _unique_path(images_dir, safe_name)
                dest.write_bytes(img_data)
            except Exception as e:
                abort(400, description=f"Failed to download image: {e}")

        # --- Scenario B: path already on ROM filesystem ---
        elif "path" in data and data["path"]:
            source = _resolve_rom_path(system_id, data["path"])
            if not source.exists():
                abort(404, description=f"Source image not found: {data['path']}")
            if not source.is_file():
                abort(400, description="Source path is not a file")
            # Just point to the existing file — no copy needed
            rel = data["path"]
            if not rel.startswith("./"):
                rel = "./" + rel
            _set_game_image_field(system_id, game_id, field_name, rel)
            return jsonify({
                "status": "ok",
                "message": f"Image path set to {rel}",
                "new_path": rel,
                "api_path": f"/api/media/{system_id}/{rel.lstrip('./')}"
            })

        else:
            abort(400, description="Provide 'file' (upload), 'url', or 'path'")

    # For upload/download: compute relative path and update gamelist
    rel = f"./images/{dest.name}"
    _set_game_image_field(system_id, game_id, field_name, rel)
    return jsonify({
        "status": "ok",
        "message": f"Image saved and {field_name} updated",
        "new_path": rel,
        "api_path": f"/api/media/{system_id}/images/{dest.name}"
    })


@app.route("/api/systems/<system_id>/games/<int:game_id>/image", methods=["DELETE"])
def api_remove_image(system_id, game_id):
    """Remove an image field from a game entry (does not delete the file)."""
    field_name = request.args.get("field", "image")
    if field_name not in ("image", "thumbnail", "mix", "video"):
        abort(400, description="field must be one of: image, thumbnail, mix, video")
    _set_game_image_field(system_id, game_id, field_name, None)
    return jsonify({"status": "ok", "message": f"{field_name} removed from game"})


@app.route("/api/systems/<system_id>/browse-images")
def api_browse_images(system_id):
    """List all image files under a system directory (for picking existing images)."""
    system_dir = Path(ROM_ROOT) / system_id
    if not system_dir.exists():
        abort(404, description="System not found")
    results = []
    for p in sorted(system_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
            rel = "./" + str(p.relative_to(system_dir))
            results.append({
                "path": rel,
                "name": p.name,
                "api_path": f"/api/media/{system_id}/{p.relative_to(system_dir)}",
                "dir": str(p.parent.relative_to(system_dir)),
            })
    return jsonify(results)


def _get_gamelist_path(system_id):
    """Return the path to a system's gamelist.xml, creating it if needed."""
    system_dir = Path(ROM_ROOT) / system_id
    if not system_dir.exists():
        abort(404, description=f"System not found: {system_id}")
    gamelist_path = system_dir / "gamelist.xml"
    if not gamelist_path.exists():
        # Create a minimal gamelist.xml
        gamelist_path.write_text('<?xml version="1.0"?>\n<gameList />\n', encoding="utf-8")
    return gamelist_path


def _add_game_to_gamelist(system_id, rom_relative_path, name=None, **extra_fields):
    """Add a new <game> entry to the gamelist.xml. Returns the new game index."""
    gamelist_path = _get_gamelist_path(system_id)
    tree = etree.parse(str(gamelist_path))
    root = tree.getroot()

    # Check for duplicate path
    for existing in root.findall("game"):
        p = existing.find("path")
        if p is not None and p.text and p.text.strip() == rom_relative_path:
            abort(409, description=f"ROM already in gamelist: {rom_relative_path}")

    game_el = etree.SubElement(root, "game")

    path_el = etree.SubElement(game_el, "path")
    path_el.text = rom_relative_path

    if name:
        name_el = etree.SubElement(game_el, "name")
        name_el.text = name
    else:
        # Derive name from filename
        stem = Path(rom_relative_path.lstrip("./")).stem
        name_el = etree.SubElement(game_el, "name")
        name_el.text = stem

    for key, value in extra_fields.items():
        if value:
            el = etree.SubElement(game_el, key)
            el.text = str(value)

    _write_gamelist(tree, gamelist_path)

    # Return new index
    return len(root.findall("game")) - 1


@app.route("/api/systems/<system_id>/browse-roms")
def api_browse_roms(system_id):
    """List ROM files in a system directory, marking which are already in the gamelist."""
    system_dir = Path(ROM_ROOT) / system_id
    if not system_dir.exists():
        abort(404, description="System not found")

    # Collect paths already in gamelist
    listed_paths = set()
    gamelist_path = system_dir / "gamelist.xml"
    if gamelist_path.exists():
        try:
            tree = etree.parse(str(gamelist_path))
            for game in tree.findall(".//game"):
                p = game.find("path")
                if p is not None and p.text:
                    listed_paths.add(p.text.strip())
        except Exception:
            pass

    results = []
    for p in sorted(system_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in ROM_EXTENSIONS:
            rel = "./" + str(p.relative_to(system_dir))
            results.append({
                "path": rel,
                "name": p.stem,
                "filename": p.name,
                "size": p.stat().st_size,
                "listed": rel in listed_paths,
                "subdir": str(p.parent.relative_to(system_dir)) if p.parent != system_dir else "",
            })
    return jsonify(results)


@app.route("/api/systems/<system_id>/import", methods=["POST"])
def api_import_rom(system_id):
    """
    Import a ROM into a system.
    Accepts:
      - JSON body with {"path": "./existing/file.nes"} for a ROM already on the filesystem
      - multipart file upload (field: "file") for a ROM from the host
      - JSON body with {"url": "https://..."} for downloading a ROM
    Optional fields: "name", "subdir" (subfolder within the system dir)
    """
    system_dir = Path(ROM_ROOT) / system_id
    if not system_dir.exists():
        abort(404, description=f"System not found: {system_id}")

    subdir = ""
    name = None

    # --- Scenario A: ROM already on filesystem ---
    if request.content_type and "json" in request.content_type:
        data = request.get_json(silent=True) or {}
        subdir = data.get("subdir", "")
        name = data.get("name")

        # Scenario A: path on ROM filesystem
        if "path" in data and data["path"]:
            source = _resolve_rom_path(system_id, data["path"])
            if not source.exists():
                abort(404, description=f"ROM file not found: {data['path']}")
            if not source.is_file():
                abort(400, description="Path is not a file")
            rel = data["path"]
            if not rel.startswith("./"):
                rel = "./" + rel
            game_index = _add_game_to_gamelist(system_id, rel, name=name)
            return jsonify({
                "status": "ok",
                "message": f"ROM added to gamelist: {source.name}",
                "game_index": game_index,
            })

        # Scenario C: download from URL
        elif "url" in data and data["url"]:
            url = data["url"]
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "ROMManager/1.0"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    rom_data = resp.read()
                # Guess extension from URL or content
                url_path = url.split("?")[0].split("#")[0]
                ext = Path(url_path).suffix.lower()
                if ext not in ROM_EXTENSIONS:
                    # Try to guess from content-type
                    ct = resp.headers.get("Content-Type", "")
                    ext = _ext_from_content_type(ct) or ".zip"
                rom_name = _sanitize_filename(Path(url_path).stem or "downloaded") + ext
            except Exception as e:
                abort(400, description=f"Failed to download ROM: {e}")

            target_dir = system_dir / subdir if subdir else system_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            dest = _unique_path(target_dir, rom_name)
            dest.write_bytes(rom_data)

            rel = "./" + str(dest.relative_to(system_dir))
            if not name:
                name = dest.stem
            game_index = _add_game_to_gamelist(system_id, rel, name=name)
            return jsonify({
                "status": "ok",
                "message": f"ROM downloaded and imported: {dest.name}",
                "game_index": game_index,
            })

        else:
            abort(400, description="Provide 'path', 'url', or upload a file")

    # --- Scenario B: file upload from host ---
    elif "file" in request.files:
        upload = request.files["file"]
        subdir = request.form.get("subdir", "")
        name = request.form.get("name")

        if not upload.filename:
            abort(400, description="No file selected")
        ext = Path(upload.filename).suffix.lower()
        if ext not in ROM_EXTENSIONS:
            abort(400, description=f"Unsupported ROM format: {ext}")

        target_dir = system_dir / subdir if subdir else system_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        safe_name = _sanitize_filename(Path(upload.filename).stem) + ext
        dest = _unique_path(target_dir, safe_name)
        upload.save(str(dest))

        rel = "./" + str(dest.relative_to(system_dir))
        if not name:
            name = dest.stem
        game_index = _add_game_to_gamelist(system_id, rel, name=name)
        return jsonify({
            "status": "ok",
            "message": f"ROM uploaded and imported: {dest.name}",
            "game_index": game_index,
        })

    else:
        abort(400, description="Provide a file upload, 'path', or 'url'")


def _ext_from_content_type(ct):
    """Guess file extension from Content-Type header."""
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }
    ct_lower = ct.split(";")[0].strip().lower()
    return mapping.get(ct_lower)


def _ext_from_url(url):
    """Guess file extension from URL path."""
    path = url.split("?")[0].split("#")[0]
    ext = Path(path).suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
        return ext
    return None


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
    # ── Development mode (browser-based) ──
    # For the native desktop window, use:  python -m rom_manager.main
    # Or build with:  ./setup.sh
    import argparse

    parser = argparse.ArgumentParser(description="ROM Manager (dev mode — opens in browser)")
    parser.add_argument("rom_root", nargs="?", default=os.environ.get("ROM_ROOT", "/run/media/portela/EEROMS"),
                        help="Path to ROM root directory (default: $ROM_ROOT or /run/media/portela/EEROMS)")
    parser.add_argument("--port", type=int, default=5000, help="Port (default: 5000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    ROM_ROOT = args.rom_root
    if not Path(ROM_ROOT).exists():
        print(f"❌ Error: ROM root path does not exist: {ROM_ROOT}")
        sys.exit(1)

    url = f"http://{args.host}:{args.port}"
    print(f"🎮 ROM Manager (dev mode)")
    print(f"📂 ROM Root: {ROM_ROOT}")
    print(f"🌐 {url}")
    print(f"   For native desktop window: python -m rom_manager.main")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(debug=False, host=args.host, port=args.port)
