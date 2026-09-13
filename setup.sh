#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  ROM Manager — Setup & Build Script
#  Installs system deps, creates venv, installs Python packages,
#  builds a standalone binary, and optionally creates a desktop
#  shortcut so you can launch with one click.
# ─────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
BINARY="dist/rom-manager"
APP_NAME="ROM Manager"
DESKTOP_FILE="$HOME/.local/share/applications/rom-manager.desktop"

# ── Colours ──────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}✔${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
error() { echo -e "${RED}✘${NC} $*"; }

# ── 1. Check prerequisites ───────────────────────────────────
check_prereqs() {
    echo ""
    echo "── Prerequisites ──"

    # Check for a Chromium-based browser (used for standalone window)
    local found=""
    for bin in chromium chromium-browser google-chrome opera microsoft-edge brave-browser vivaldi /snap/bin/chromium; do
        if command -v "$bin" &>/dev/null || [[ -x "$bin" ]]; then
            found="$bin"
            break
        fi
    done

    if [[ -n "$found" ]]; then
        info "Browser found: $found"
    else
        warn "No Chromium-based browser found."
        warn "The app needs one for the standalone window (no tabs/address bar)."
        warn "Install any of: chromium, google-chrome, opera, microsoft-edge, brave"
        warn "Falling back to default browser if none found."
    fi
}

# ── 2. Python virtual environment ────────────────────────────
setup_venv() {
    echo ""
    echo "── Python environment ──"

    if [[ -d "$VENV_DIR" ]]; then
        info "Virtual environment already exists at $VENV_DIR"
    else
        python3 -m venv "$VENV_DIR"
        info "Created virtual environment"
    fi

    source "$VENV_DIR/bin/activate"
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    info "Python dependencies installed"
}

# ── 3. Build standalone binary ───────────────────────────────
build_binary() {
    echo ""
    echo "── Building binary ──"

    source "$VENV_DIR/bin/activate"
    pyinstaller --clean --noconfirm rom-manager.spec
    info "Binary built: $BINARY"
}

# ── 4. Desktop shortcut (Linux) ──────────────────────────────
create_desktop_shortcut() {
    if [[ "$(uname)" != "Linux" ]]; then
        return
    fi

    echo ""
    echo "── Desktop shortcut ──"

    local binary_path
    binary_path="$(realpath "$BINARY")"
    local icon_path
    icon_path="$(realpath static/icon-512.png)"

    mkdir -p "$(dirname "$DESKTOP_FILE")"

    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=$APP_NAME
Comment=Manage your EmulationStation game collection
Exec=$binary_path
Icon=$icon_path
Terminal=false
Type=Application
Categories=Game;Utility;
StartupWMClass=rom-manager
StartupNotify=true
EOF

    chmod +x "$DESKTOP_FILE"

    # Update desktop database if available
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$(dirname "$DESKTOP_FILE")" 2>/dev/null || true
    fi

    info "Desktop shortcut created: $DESKTOP_FILE"
    info "Find '$APP_NAME' in your app menu to launch"
}

# ── Main ─────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════"
echo "  🎮 ROM Manager — Setup & Build"
echo "═══════════════════════════════════"

check_prereqs
setup_venv
build_binary
create_desktop_shortcut

echo ""
echo "═══════════════════════════════════"
echo "  ✅ All done!"
echo "═══════════════════════════════════"
echo ""
echo "  Run directly:     ./dist/rom-manager [ROM_ROOT]"
echo "  From app menu:    Look for '$APP_NAME'"
echo ""
