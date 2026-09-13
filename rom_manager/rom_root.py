"""ROM root directory resolution.

Resolves the ROM root (the directory containing the emulator system
folders) in the following order:

1. CLI argument (``rom_root`` positional argument)
2. ``ROM_ROOT`` environment variable
3. Last saved selection (``~/.config/rom-manager/config.json``)
4. Hardcoded default (``DEFAULT_ROM_ROOT``)

The first candidate that exists as a directory wins.  If none of them
exists, the user is prompted interactively to pick a directory: detected
storage candidates (mounted media) are offered as a numbered list, and a
custom path can also be typed in.  A directory chosen interactively is
persisted so it is remembered on the next launch.
"""

import json
import os
import sys
from pathlib import Path

# Configurable root path - defaults to EEROMS
DEFAULT_ROM_ROOT = "/run/media/portela/EEROMS"

# Where the last user-selected root is remembered.
CONFIG_DIR = Path(os.environ.get(
    "XDG_CONFIG_HOME", Path.home() / ".config"
)) / "rom-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Common locations where removable/emulator storage is mounted.
_MOUNT_BASES = ("/run/media", "/media", "/mnt")


def load_saved_root():
    """Return the ROM root saved by a previous interactive selection, or None."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        root = data.get("rom_root")
        return str(root) if root else None
    except (OSError, ValueError):
        return None


def save_root(rom_root):
    """Persist the ROM root so the next launch uses it automatically."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"rom_root": str(rom_root)}, f, indent=2)
    except OSError as e:
        print(f"⚠️  Could not save ROM root to {CONFIG_FILE}: {e}")


def _candidate_mounts():
    """Return existing directories that may hold ROM storage."""
    candidates = []
    seen = set()
    for base in _MOUNT_BASES:
        base_path = Path(base)
        if not base_path.is_dir():
            continue
        for entry in sorted(base_path.iterdir()):
            if not entry.is_dir():
                continue
            try:
                children = sorted(entry.iterdir())
            except OSError:
                children = []  # e.g. permission denied on /run/media/<other-user>
            # e.g. /run/media/<user>/<disk> — include the disk level too
            for path in (entry, *children):
                if path.is_dir() and str(path) not in seen:
                    seen.add(str(path))
                    candidates.append(path)
    return candidates


def _prompt_for_root(missing_path):
    """Interactively ask the user for a ROM root directory.

    Returns a Path, or None if the user aborts.
    """
    print(f"\n❌ ROM root directory not found: {missing_path}")
    print("   Select the directory where your emulator systems live.\n")

    mounts = _candidate_mounts()
    for i, mount in enumerate(mounts, start=1):
        print(f"  {i}) {mount}")
    print("  0) Enter a custom path")
    if not mounts:
        print("  (no mounted storage locations detected)")

    while True:
        try:
            choice = input(f"\nSelect a location [0-{len(mounts)}]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n❌ Aborted — no ROM root selected.")
            return None

        if not choice:
            print("❌ Aborted — no ROM root selected.")
            return None

        if choice == "0":
            try:
                raw = input("Enter ROM root directory path: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n❌ Aborted — no ROM root selected.")
                return None
            if not raw:
                print("❌ Aborted — no ROM root selected.")
                return None
            candidate = Path(raw).expanduser().resolve()
        else:
            try:
                index = int(choice)
            except ValueError:
                print("⚠️  Invalid selection — enter a number from the list.")
                continue
            if not 1 <= index <= len(mounts):
                print("⚠️  Invalid selection — enter a number from the list.")
                continue
            candidate = mounts[index - 1]

        if candidate.is_dir():
            return candidate
        print(f"⚠️  Not a directory: {candidate} — try again.")


def resolve_rom_root(cli_value=None, interactive=True):
    """Resolve the ROM root directory.

    Tries, in order: CLI argument, ``ROM_ROOT`` env var, saved config,
    hardcoded default.  The first existing directory wins.  If none
    exists and *interactive* is true, prompts the user (see
    ``_prompt_for_root``) and persists the selection.

    Returns a ``Path`` to a valid directory, or ``None`` if unavailable.
    """
    candidates = (
        ("command line", cli_value),
        ("environment variable ROM_ROOT", os.environ.get("ROM_ROOT")),
        ("saved configuration", load_saved_root()),
        ("default", DEFAULT_ROM_ROOT),
    )

    for source, candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_dir():
            return path

    if not interactive:
        return None
    chosen = _prompt_for_root(candidates[-1][1])
    if chosen is not None:
        save_root(chosen)
        print(f"✅ ROM root saved for future launches: {chosen}")
    return chosen