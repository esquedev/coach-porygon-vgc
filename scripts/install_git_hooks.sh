#!/usr/bin/env bash
# Activate versioned Coach Porygon VGC Git pre-commit & pre-push hooks
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

chmod +x .githooks/pre-commit .githooks/pre-push scripts/scan_repo_hallucinations.py
git config core.hooksPath .githooks

echo "[Coach Porygon VGC] Git hooks activated via core.hooksPath=.githooks"
echo "  - pre-commit : Anti-Hallucination, Zero p1/p2 AST & V8 JS syntax check"
echo "  - pre-push   : Full pytest + Acceptance Model Fuzzer on develop/main (Acceptance Gate on feature branches)"
