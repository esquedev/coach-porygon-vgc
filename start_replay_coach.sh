#!/usr/bin/env bash
# ============================================================================
# Coach Porygon VGC — Isolated .venv Linux/macOS Installer & Studio Launcher
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "============================================================================"
echo "  Coach Porygon VGC - Replay Coach Studio (Linux / macOS Launcher)"
echo "============================================================================"
echo ""

# 1. Locate Python 3.10+
PY_CMD=""
for cand in python3 python3.12 python3.11 python3.10; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
            PY_CMD="$cand"
            break
        fi
    fi
done

if [ -z "$PY_CMD" ]; then
    echo "[ERROR] Python 3.10 or higher was not found on your PATH."
    echo ""
    echo "Please install Python 3.10+ (e.g. 'sudo apt install python3 python3-venv' on Ubuntu/Debian"
    echo "or 'brew install python@3.12' on macOS), then re-run ./start_replay_coach.sh."
    exit 1
fi

# 2. Create isolated virtual environment if missing (never touches system Python)
if [ ! -x ".venv/bin/python" ]; then
    echo "[1/4] Creating isolated Python virtual environment (.venv) via ${PY_CMD}..."
    if ! "$PY_CMD" -m venv .venv; then
        echo "[ERROR] Failed to create .venv virtual environment."
        echo "        On Debian/Ubuntu, install venv support: sudo apt install python3-venv"
        exit 1
    fi
else
    echo "[1/4] Isolated virtual environment (.venv) found."
fi

# 3. Explicitly activate the isolated virtual environment
# shellcheck disable=SC1091
source ".venv/bin/activate"
VENV_PY=".venv/bin/python"
echo "[2/4] Activated virtual environment: ${SCRIPT_DIR}/.venv"

# 4. Verify requirements.txt SHA-256 stamp + full core package imports
NEED_INSTALL=0
if ! "$VENV_PY" -c "import hashlib, pathlib, sys; h=hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(); s=pathlib.Path('.venv/.requirements.sha256'); sys.exit(0 if s.exists() and s.read_text(encoding='utf-8').strip()==h else 1)" >/dev/null 2>&1; then
    NEED_INSTALL=1
fi

if [ "$NEED_INSTALL" -eq 0 ]; then
    if ! "$VENV_PY" -c "import torch, numpy, scipy, duckdb, py_mini_racer" >/dev/null 2>&1; then
        NEED_INSTALL=1
    fi
fi

# Self-healing CUDA upgrade: if NVIDIA drivers were installed after .venv was created with CPU-only torch
if [ "$NEED_INSTALL" -eq 0 ] && [ "$(uname -s)" = "Linux" ] && command -v nvidia-smi >/dev/null 2>&1; then
    if ! "$VENV_PY" -c "import sys, torch; sys.exit(0 if getattr(torch.version, 'cuda', None) else 1)" >/dev/null 2>&1; then
        echo "[3/4] NVIDIA GPU driver detected, upgrading CPU-only PyTorch in .venv to CUDA 12.4..."
        "$VENV_PY" -m pip install --upgrade --force-reinstall --no-deps torch --index-url https://download.pytorch.org/whl/cu124 || true
        "$VENV_PY" -m pip install torch --index-url https://download.pytorch.org/whl/cu124 || true
    fi
fi

if [ "$NEED_INSTALL" -eq 1 ]; then
    echo "[3/4] Syncing runtime dependencies into .venv (first-time setup may take a few minutes)..."
    "$VENV_PY" -m pip install --upgrade pip

    OS_NAME="$(uname -s)"
    if [ "$OS_NAME" = "Linux" ] && command -v nvidia-smi >/dev/null 2>&1; then
        echo "      NVIDIA GPU detected on Linux - installing CUDA 12.4 PyTorch wheel..."
        if ! "$VENV_PY" -m pip install torch --index-url https://download.pytorch.org/whl/cu124; then
            echo "[WARN] CUDA wheel install failed; falling back to standard CPU PyTorch..."
        fi
    else
        echo "      Installing standard PyTorch wheel for ${OS_NAME} (CPU / Apple Silicon)..."
    fi

    "$VENV_PY" -m pip install -r requirements.txt
    "$VENV_PY" -c "import hashlib, pathlib; pathlib.Path('.venv/.requirements.sha256').write_text(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(), encoding='utf-8')"
    echo "      Dependencies synced and verified inside .venv."
else
    echo "[3/4] All .venv dependencies verified (PyTorch, DuckDB, SciPy, NumPy, MiniRacer)."
fi

# 5. Parse optional --host, --port, and --no-browser arguments
STUDIO_HOST="127.0.0.1"
STUDIO_PORT="8765"
NO_BROWSER="${COACH_NO_BROWSER:-0}"
SERVER_ARGS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --host)
            STUDIO_HOST="${2:-127.0.0.1}"
            SERVER_ARGS+=("$1" "$STUDIO_HOST")
            shift 2
            ;;
        --port)
            STUDIO_PORT="${2:-8765}"
            SERVER_ARGS+=("$1" "$STUDIO_PORT")
            shift 2
            ;;
        --no-browser)
            NO_BROWSER=1
            shift
            ;;
        *)
            SERVER_ARGS+=("$1")
            shift
            ;;
    esac
done

STUDIO_URL="http://${STUDIO_HOST}:${STUDIO_PORT}/"

# 6. Schedule non-blocking browser open once server responds (argv-safe, zero quote injection)
if [ "$NO_BROWSER" != "1" ]; then
    (
        for _ in $(seq 1 60); do
            if "$VENV_PY" -c "import sys, urllib.request; urllib.request.urlopen(sys.argv[1] + 'api/state', timeout=0.5)" "$STUDIO_URL" >/dev/null 2>&1; then
                if command -v xdg-open >/dev/null 2>&1; then
                    xdg-open "$STUDIO_URL" >/dev/null 2>&1 || true
                elif command -v open >/dev/null 2>&1; then
                    open "$STUDIO_URL" >/dev/null 2>&1 || true
                fi
                exit 0
            fi
            sleep 0.5
        done
    ) &
fi

# 7. Boot Replay Coach Studio inside the activated .venv
export PYTHONPATH="src:."
echo "[4/4] Starting Replay Coach Studio at ${STUDIO_URL}"
echo "      Press Ctrl+C to stop the server."
echo ""

if [ "${#SERVER_ARGS[@]}" -gt 0 ]; then
    exec "$VENV_PY" -m apps.replay_coach.server "${SERVER_ARGS[@]}"
else
    exec "$VENV_PY" -m apps.replay_coach.server
fi
