#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Workspace Sanitization & Volatile Artifact Cleaner
Removes:
1. Volatile temporary test files and scratchpads in `scratch/`.
2. Python bytecode caches (`__pycache__`) and `.pytest_cache`.
3. Temporary runtime logs, backups (`*.tmp`, `*.bak`), and editor artifacts.
"""

import argparse
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO_ROOT = Path(__file__).resolve().parent.parent


def sanitize_scratch_directory(dry_run: bool = False) -> int:
    """Removes all transient scripts and assets inside the scratch directory."""
    scratch_dir = REPO_ROOT / "scratch"
    if not scratch_dir.exists():
        return 0

    removed = 0
    for item in scratch_dir.iterdir():
        if item.name == ".gitkeep":
            continue
        try:
            if item.is_dir():
                if not dry_run:
                    shutil.rmtree(item, ignore_errors=True)
                removed += 1
            else:
                if not dry_run:
                    item.unlink(missing_ok=True)
                removed += 1
        except Exception as exc:
            print(f"  [WARN] Failed to remove {item.name}: {exc}")
    return removed


def sanitize_pycache_directories(dry_run: bool = False) -> int:
    """Recursively removes __pycache__ directories and .pytest_cache."""
    removed = 0
    # 1. Clean __pycache__
    for p in REPO_ROOT.rglob("__pycache__"):
        if ".venv" in str(p):
            continue
        try:
            if not dry_run:
                shutil.rmtree(p, ignore_errors=True)
            removed += 1
        except Exception:
            pass

    # 2. Clean .pytest_cache
    pytest_cache = REPO_ROOT / ".pytest_cache"
    if pytest_cache.exists():
        try:
            if not dry_run:
                shutil.rmtree(pytest_cache, ignore_errors=True)
            removed += 1
        except Exception:
            pass

    return removed


def sanitize_temp_files(dry_run: bool = False) -> int:
    """Removes dangling temporary files (*.tmp, *.bak, tempCodeRunnerFile.py)."""
    patterns = ["*.tmp", "*.bak", "tempCodeRunnerFile.py"]
    removed = 0
    for pat in patterns:
        for p in REPO_ROOT.rglob(pat):
            if ".venv" in str(p) or ".git" in str(p):
                continue
            try:
                if not dry_run:
                    p.unlink(missing_ok=True)
                removed += 1
            except Exception:
                pass
    return removed


def main():
    """CLI entry point for workspace sanitization."""
    parser = argparse.ArgumentParser(description="Coach Porygon VGC Workspace Sanitizer")
    parser.add_argument("--scratch-only", action="store_true", help="Clean only the scratch/ directory")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without deleting files")
    args = parser.parse_args()

    action_label = "Scanning (dry-run)" if args.dry_run else "Sanitizing"
    print(f"=== COACH PORYGON VGC -- {action_label.upper()} WORKSPACE ===")

    scratch_count = sanitize_scratch_directory(dry_run=args.dry_run)
    print(f"  • Scratch items removed: {scratch_count}")

    if not args.scratch_only:
        pycache_count = sanitize_pycache_directories(dry_run=args.dry_run)
        temp_count = sanitize_temp_files(dry_run=args.dry_run)
        print(f"  • Bytecode cache directories removed: {pycache_count}")
        print(f"  • Transient files removed (*.tmp, *.bak): {temp_count}")

    print("✔ Workspace sanitization completed successfully.")


if __name__ == "__main__":
    main()
