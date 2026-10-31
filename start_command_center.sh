#!/usr/bin/env bash
# ==============================================================================
# Coach Porygon VGC — Command Center POSIX Launcher
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -n "$PYTHON_BIN" ] && [ -x "$PYTHON_BIN" ]; then
    PY="$PYTHON_BIN"
elif [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PY="$SCRIPT_DIR/.venv/bin/python"
elif [ -x "$SCRIPT_DIR/venv/bin/python" ]; then
    PY="$SCRIPT_DIR/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "[ERROR] No Python 3 interpreter found in PATH or virtual environments."
    exit 1
fi

echo "[Coach Porygon VGC] Syncing Databases & Compiling Bilingual Command Center..."
$PY engine/update_command_center.py

echo "[Coach Porygon VGC] Starting Python Backend Server at http://localhost:8000 ..."

# Attempt to open browser across Linux and macOS
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:8000" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
    open "http://localhost:8000" >/dev/null 2>&1 &
fi

exec $PY engine/ui_server.py
