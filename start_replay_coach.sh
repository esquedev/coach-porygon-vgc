#!/usr/bin/env bash
# ============================================================================
# Coach Porygon VGC — Isolated .venv Linux/macOS Installer & Studio Launcher
# Plain-text, human-auditable. Never touches system-wide Python packages.
# If the executable bit was lost (zip extraction): bash start_replay_coach.sh
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# UTF-8 everywhere so Studio logs never crash under C/POSIX locales; never prompt for pip upgrades.
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export PIP_DISABLE_PIP_VERSION_CHECK=1
PIP_OPTS=(--disable-pip-version-check --retries 5 --timeout 60)

die() {
    echo "[ERROR] $*" >&2
    exit 1
}

echo ""
echo "============================================================================"
echo "  Coach Porygon VGC - Replay Coach Studio (Linux / macOS Launcher)"
echo "============================================================================"
echo ""

case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        die "Git-Bash / MSYS detected. On Windows run start_replay_coach.bat instead."
        ;;
esac

# 0. Sanity: must run from the extracted project folder
if [ ! -f "requirements.txt" ] || [ ! -f "apps/replay_coach/server.py" ]; then
    die "requirements.txt / apps/replay_coach not found next to this script. Extract the FULL release archive first."
fi

# 1. Locate a 64-bit Python 3.10+ (prefers 3.12 / 3.11 which have the widest PyTorch wheel support)
PY_CMD=""
for cand in python3.12 python3.11 python3.13 python3.10 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c "import sys; sys.exit(0 if (sys.version_info >= (3, 10) and sys.maxsize > 2**32) else 1)" >/dev/null 2>&1; then
            PY_CMD="$cand"
            break
        fi
    fi
done

if [ -z "$PY_CMD" ]; then
    echo "[ERROR] A 64-bit Python 3.10 or higher was not found on your PATH." >&2
    echo "" >&2
    echo "Please install Python 3.10+ (e.g. 'sudo apt install python3 python3-venv' on Ubuntu/Debian" >&2
    echo "or 'brew install python@3.12' on macOS), then re-run ./start_replay_coach.sh." >&2
    exit 1
fi

# 2. Create the virtual environment if missing, or recreate it if broken / outdated
if [ -e ".venv" ] && ! .venv/bin/python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
    echo "[WARN] The existing .venv is broken or outdated - recreating it..."
    rm -rf .venv
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "[1/4] Creating isolated Python virtual environment (.venv) via ${PY_CMD}..."
    if ! "$PY_CMD" -m venv .venv || [ ! -x ".venv/bin/python" ]; then
        rm -rf .venv
        die "Failed to create .venv. On Debian/Ubuntu install venv support: sudo apt install python3-venv"
    fi
else
    echo "[1/4] Isolated virtual environment (.venv) found."
fi

# 3. Explicitly activate the isolated virtual environment (activate scripts are not nounset-safe)
set +u
if [ -f ".venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
fi
set -u
VENV_PY=".venv/bin/python"
export PIP_REQUIRE_VIRTUALENV=1
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

# Detect a WORKING NVIDIA driver on Linux (native or WSL2); macOS has no CUDA.
NVSMI=""
DRIVER_VER="unknown"
if [ "$(uname -s)" = "Linux" ]; then
    for cand in "$(command -v nvidia-smi 2>/dev/null || true)" /usr/lib/wsl/lib/nvidia-smi; do
        if [ -n "$cand" ] && [ -x "$cand" ] && "$cand" -L >/dev/null 2>&1; then
            NVSMI="$cand"
            DRIVER_VER="$("$cand" --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n 1 || true)"
            DRIVER_VER="${DRIVER_VER:-unknown}"
            break
        fi
    done
fi

torch_cuda_ok() {
    "$VENV_PY" -c "import sys, torch; sys.exit(0 if (getattr(torch.version, 'cuda', None) and torch.cuda.is_available()) else 1)" >/dev/null 2>&1
}

install_cuda_torch() {
    # NEVER uninstall first: pip downloads before it replaces, so an offline/failed attempt keeps the working torch.
    for cu_tag in cu128 cu126 cu124 cu121; do
        if ! torch_cuda_ok; then
            echo "      Trying official PyTorch CUDA wheel index (${cu_tag})..."
            "$VENV_PY" -m pip install "${PIP_OPTS[@]}" --upgrade --force-reinstall --no-cache-dir torch --index-url "https://download.pytorch.org/whl/${cu_tag}" || true
        fi
    done
    if ! torch_cuda_ok; then
        echo "[WARN] No compatible CUDA PyTorch wheel could be installed - keeping the CPU PyTorch build."
        if ! "$VENV_PY" -c "import torch" >/dev/null 2>&1; then
            "$VENV_PY" -m pip install "${PIP_OPTS[@]}" torch || true
        fi
    fi
    # Remember the driver already tried so unsupported GPUs never reinstall torch on every launch.
    printf '%s\n' "$DRIVER_VER" > .venv/.cuda_attempt
}

# Self-healing CUDA upgrade: NVIDIA driver installed after .venv was created with CPU-only torch
if [ "$NEED_INSTALL" -eq 0 ] && [ -n "$NVSMI" ] && ! torch_cuda_ok; then
    PREV_MARK=""
    [ -f .venv/.cuda_attempt ] && PREV_MARK="$(head -n 1 .venv/.cuda_attempt || true)"
    if [ "$PREV_MARK" != "$DRIVER_VER" ]; then
        echo "[3/4] NVIDIA GPU driver ${DRIVER_VER} detected, replacing CPU-only PyTorch in .venv with CUDA PyTorch..."
        install_cuda_torch
    else
        echo "[WARN] NVIDIA GPU found but no compatible CUDA PyTorch wheel for driver ${DRIVER_VER} - running on CPU."
    fi
fi

if [ "$NEED_INSTALL" -eq 1 ]; then
    echo "[3/4] Syncing runtime dependencies into .venv (first-time setup may take a few minutes)..."
    "$VENV_PY" -m pip install "${PIP_OPTS[@]}" --upgrade pip || echo "[WARN] pip self-upgrade failed; continuing."

    if [ -n "$NVSMI" ]; then
        echo "      NVIDIA GPU detected on Linux - installing CUDA PyTorch wheel..."
        install_cuda_torch
    else
        echo "      Installing standard PyTorch wheel for $(uname -s) (CPU / Apple Silicon)..."
    fi

    "$VENV_PY" -m pip install "${PIP_OPTS[@]}" -r requirements.txt \
        || die "Dependency installation failed. Check your internet connection and retry (delete .venv if it persists)."

    # Guard against requirements.txt replacing CUDA torch with a CPU wheel
    if [ -n "$NVSMI" ] && ! torch_cuda_ok; then
        install_cuda_torch
    fi

    "$VENV_PY" -c "import torch, numpy, scipy, duckdb, py_mini_racer" >/dev/null 2>&1 \
        || die "Dependencies installed but imports still fail. Delete .venv and run this script again."
    "$VENV_PY" -c "import hashlib, pathlib; pathlib.Path('.venv/.requirements.sha256').write_text(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(), encoding='utf-8')"
    echo "      Dependencies synced and verified inside .venv."
else
    echo "[3/4] All .venv dependencies verified (PyTorch, DuckDB, SciPy, NumPy, MiniRacer)."
fi

# 5. Parse optional --host, --port, and --no-browser arguments (--no-browser is launcher-only)
STUDIO_HOST="127.0.0.1"
STUDIO_PORT="8765"
NO_BROWSER="${COACH_NO_BROWSER:-0}"
SERVER_ARGS=()

while [ $# -gt 0 ]; do
    case "$1" in
        --host)
            STUDIO_HOST="${2:-127.0.0.1}"
            SERVER_ARGS+=("$1" "$STUDIO_HOST")
            if [ $# -ge 2 ]; then shift 2; else shift; fi
            ;;
        --host=*)
            STUDIO_HOST="${1#--host=}"
            SERVER_ARGS+=("$1")
            shift
            ;;
        --port)
            STUDIO_PORT="${2:-8765}"
            SERVER_ARGS+=("$1" "$STUDIO_PORT")
            if [ $# -ge 2 ]; then shift 2; else shift; fi
            ;;
        --port=*)
            STUDIO_PORT="${1#--port=}"
            SERVER_ARGS+=("$1")
            shift
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

if ! [[ "$STUDIO_PORT" =~ ^[0-9]+$ ]] || [ "$STUDIO_PORT" -lt 1 ] || [ "$STUDIO_PORT" -gt 65535 ]; then
    die "Invalid --port '${STUDIO_PORT}' (expected 1-65535)."
fi
if ! [[ "$STUDIO_HOST" =~ ^[][A-Za-z0-9._:-]+$ ]]; then
    die "Invalid --host '${STUDIO_HOST}'."
fi

URL_HOST="$STUDIO_HOST"
[ "$URL_HOST" = "0.0.0.0" ] && URL_HOST="127.0.0.1"
case "$URL_HOST" in
    \[*) ;;
    *:*) URL_HOST="[${URL_HOST}]" ;;
esac
STUDIO_URL="http://${URL_HOST}:${STUDIO_PORT}/"

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
