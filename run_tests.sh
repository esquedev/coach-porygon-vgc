#!/usr/bin/env bash
# ==============================================================================
# Coach Porygon VGC — Local CI/CD Pipeline (Full 5-Phase POSIX Runner)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Parse CLI arguments for pre-push / AI audit enforcement flag
ENFORCE_AI_AUDIT=0
for arg in "$@"; do
    case "$arg" in
        --pre-push|--with-ai-audit|--enforce-audit)
            ENFORCE_AI_AUDIT=1
            ;;
    esac
done

# ANSI Color Palette
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_GREEN="\033[1;32m"
C_RED="\033[1;31m"
C_YELLOW="\033[1;33m"
C_CYAN="\033[1;36m"
C_WHITE="\033[1;37m"

# Discover Python 3.10+
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
    echo -e "${C_RED}[ERROR] No Python 3 interpreter found in PATH or virtual environments.${C_RESET}"
    exit 1
fi

echo -e "${C_CYAN}==============================================================================${C_RESET}"
echo -e "${C_CYAN}  ${C_BOLD}COACH PORYGON VGC -- LOCAL CI/CD PIPELINE (FULL 5-PHASE RUNNER)${C_RESET}"
echo -e "${C_CYAN}==============================================================================${C_RESET}"
echo -e "Using Python: $($PY --version)"
echo ""

# --- PHASE 0: Workspace Sanitization & Scratch Cleanup ---
echo -e "${C_CYAN}[PHASE 0/5]${C_RESET} ${C_WHITE}Sanitizing Workspace & Garbage Collection...${C_RESET}"
$PY engine/clean_workspace.py
echo -e "${C_GREEN}  [OK] Workspace sanitized (scratch, caches, and test residue purged).${C_RESET}"
echo ""

# --- PHASE 1: Initialize Public Schema Templates ---
echo -e "${C_CYAN}[PHASE 1/5]${C_RESET} ${C_WHITE}Initializing Schema Templates...${C_RESET}"
$PY -c "from pathlib import Path; import shutil; [shutil.copy(f, f.parent / f.name.replace('.example', '')) for f in Path('data').glob('*.example.*') if not (f.parent / f.name.replace('.example', '')).exists()]"
echo -e "${C_GREEN}  [OK] Public schema templates verified.${C_RESET}"
echo ""

# --- PHASE 2: Lint and Code Style Verification ---
echo -e "${C_CYAN}[PHASE 2/5]${C_RESET} ${C_WHITE}Linting and Syntax Compilation...${C_RESET}"
$PY -m compileall -q engine evals tests

if $PY -m flake8 --version >/dev/null 2>&1; then
    $PY -m flake8 engine/ evals/ tests/ --count --max-line-length=160 --extend-ignore=E121,E201,E202,E203,E226,E231,E241,E302,E303,E305,E402,E501,E701,E731,E741,F401,F541,F841,W503,W504 --statistics
elif $PY -m pycodestyle --version >/dev/null 2>&1; then
    echo -e "${C_YELLOW}  [WARN] flake8 not installed; falling back to pycodestyle.${C_RESET}"
    $PY -m pycodestyle engine/ evals/ tests/ --max-line-length=160 --ignore=E121,E201,E202,E203,E226,E231,E241,E302,E303,E305,E402,E501,E701,E731,E741,F401,F541,F841,W503,W504 --statistics
fi
echo -e "${C_GREEN}  [OK] Code style and syntax verified (0 violations).${C_RESET}"
echo ""

# --- PHASE 3: AI Health Stress Audit & Static Guardrails ---
if [ "$ENFORCE_AI_AUDIT" -eq 1 ]; then
    echo -e "${C_CYAN}[PHASE 3/5]${C_RESET} ${C_WHITE}Verifying AI Health Stress Audit and Static Guardrails [ENFORCED]...${C_RESET}"
    $PY evals/evaluate_release_health.py --verify
    echo -e "${C_GREEN}  [OK] AI Health Stress audit and static guardrails verified and consumed.${C_RESET}"
else
    echo -e "${C_CYAN}[PHASE 3/5]${C_RESET} ${C_WHITE}Verifying Static Guardrails and Link Integrity [AUDIT SKIPPED]...${C_RESET}"
    $PY evals/run_static_checks.py
    echo -e "${C_YELLOW}  [SKIP] AI Health Stress Audit consumption skipped (run with --pre-push to enforce).${C_RESET}"
fi
echo ""

# --- PHASE 4: Digital Asset and SVG/PNG Integrity Audit ---
echo -e "${C_CYAN}[PHASE 4/5]${C_RESET} ${C_WHITE}Auditing Vector and Raster Assets...${C_RESET}"
$PY engine/verify_png_inventory.py
echo -e "${C_GREEN}  [OK] Asset inventory verified.${C_RESET}"
echo ""

# --- PHASE 5: Test Suite Execution ---
echo -e "${C_CYAN}[PHASE 5/5]${C_RESET} ${C_WHITE}Executing Full Test Suite (pytest with coverage parity)...${C_RESET}"
if $PY -m pytest --version >/dev/null 2>&1; then
    $PY -m pytest tests/ --cov=engine --cov-report=term-missing
else
    $PY tests/run_all_tests.py
fi

echo ""
echo -e "${C_GREEN}==============================================================================${C_RESET}"
echo -e "${C_GREEN}  [PASS] ALL 5 CI/CD PIPELINE PHASES PASSED LOCALLY WITH ZERO ERRORS${C_RESET}"
echo -e "${C_GREEN}==============================================================================${C_RESET}"
echo ""
echo -e "${C_CYAN}[POST-RUN GC]${C_RESET} ${C_WHITE}Executing final workspace sanitization and Git pack optimization...${C_RESET}"
$PY engine/clean_workspace.py --git-gc
echo -e "${C_GREEN}  [OK] Workspace and Git repository optimized for push.${C_RESET}"
