#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "🎮 Building ROM Manager..."

# Activate venv
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install flask lxml pyinstaller
fi

# Build
pyinstaller --clean rom-manager.spec

echo ""
echo "✅ Build complete!"
echo "📁 Executable: dist/rom-manager"
echo ""
echo "Usage:"
echo "  ./dist/rom-manager                          # Use default EEROMS path"
echo "  ./dist/rom-manager /path/to/roms            # Specify ROM directory"
echo "  ./dist/rom-manager --port 8080              # Custom port"
echo "  ./dist/rom-manager --no-browser             # Don't auto-open browser"
