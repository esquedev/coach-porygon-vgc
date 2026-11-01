#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Coach Porygon VGC — Workspace Sanitization & Volatile Artifact Garbage Collector.

Removes:
1. Volatile temporary test files and scratchpads in `scratch/`.
2. Python bytecode caches (`__pycache__`) and `.pytest_cache`.
3. Test coverage artifacts (`.coverage`, `.coverage.*`, `htmlcov/`, `.temp/`).
4. Build distribution artifacts (`build/`, `dist/`, `*.egg-info/`).
5. Temporary runtime logs, backups (`*.tmp`, `*.bak`), and editor artifacts.
6. Optional Git loose object packing (`git gc --auto --quiet`).
"""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent


def sanitize_scratch_directory(dry_run: bool = False) -> int:
    """Remove all transient scripts and assets inside the scratch directory.

    Args:
        dry_run: When True, count removable items without unlinking.

    Returns:
        Number of items removed.
    """
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
    """Recursively remove __pycache__ directories and .pytest_cache.

    Args:
        dry_run: When True, count removable items without unlinking.

    Returns:
        Number of directories removed.
    """
    removed = 0
    # 1. Clean __pycache__
    for p in REPO_ROOT.rglob("__pycache__"):
        if ".venv" in str(p) or ".git" in str(p):
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
    """Remove dangling temporary files (*.tmp, *.bak, tempCodeRunnerFile.py).

    Args:
        dry_run: When True, count removable items without unlinking.

    Returns:
        Number of files removed.
    """
    patterns = ["*.tmp", "*.bak", "tempCodeRunnerFile.py"]
    removed = 0
    for pat in patterns:
        for p in REPO_ROOT.rglob(pat):
            if ".venv" in str(p) or ".git" in str(p) or "assets" in str(p):
                continue
            try:
                if not dry_run:
                    p.unlink(missing_ok=True)
                removed += 1
            except Exception:
                pass
    return removed


def sanitize_coverage_and_test_artifacts(dry_run: bool = False) -> int:
    """Remove coverage database files, htmlcov reports, and .temp directory contents.

    Args:
        dry_run: When True, count removable items without unlinking.

    Returns:
        Number of files/directories removed.
    """
    removed = 0
    for p in REPO_ROOT.glob(".coverage*"):
        try:
            if not dry_run:
                p.unlink(missing_ok=True)
            removed += 1
        except Exception:
            pass

    htmlcov_dir = REPO_ROOT / "htmlcov"
    if htmlcov_dir.exists():
        try:
            if not dry_run:
                shutil.rmtree(htmlcov_dir, ignore_errors=True)
            removed += 1
        except Exception:
            pass

    temp_dir = REPO_ROOT / ".temp"
    if temp_dir.exists():
        for item in temp_dir.iterdir():
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
            except Exception:
                pass

    return removed


def sanitize_build_artifacts(dry_run: bool = False) -> int:
    """Remove build, dist, and egg-info directories.

    Args:
        dry_run: When True, count removable items without unlinking.

    Returns:
        Number of directories removed.
    """
    removed = 0
    targets = ["build", "dist"]
    for t in targets:
        p = REPO_ROOT / t
        if p.exists() and p.is_dir():
            try:
                if not dry_run:
                    shutil.rmtree(p, ignore_errors=True)
                removed += 1
            except Exception:
                pass

    for p in REPO_ROOT.glob("*.egg-info"):
        if p.exists() and p.is_dir():
            try:
                if not dry_run:
                    shutil.rmtree(p, ignore_errors=True)
                removed += 1
            except Exception:
                pass

    return removed


def run_git_maintenance(dry_run: bool = False) -> bool:
    """Execute Git auto garbage collection to pack loose objects and optimize deltas.

    Args:
        dry_run: When True, skip command execution.

    Returns:
        True if git command succeeded or was skipped, False otherwise.
    """
    if dry_run:
        return True
    try:
        res = subprocess.run(
            ["git", "gc", "--auto", "--quiet"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            check=False,
            text=True
        )
        return res.returncode == 0
    except Exception:
        return False


def main():
    """CLI entry point for workspace sanitization and garbage collection."""
    parser = argparse.ArgumentParser(description="Coach Porygon VGC Workspace Sanitizer & Garbage Collector")
    parser.add_argument("--scratch-only", action="store_true", help="Clean only the scratch/ directory")
    parser.add_argument("--all", action="store_true", help="Clean scratch, pycache, temp, coverage, and build artifacts (default)")
    parser.add_argument("--git-gc", action="store_true", help="Run git auto garbage collection (git gc --auto --quiet)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without deleting files")
    args = parser.parse_args()

    action_label = "Scanning (dry-run)" if args.dry_run else "Sanitizing"
    print(f"=== COACH PORYGON VGC -- {action_label.upper()} WORKSPACE & GARBAGE COLLECTION ===")

    scratch_count = sanitize_scratch_directory(dry_run=args.dry_run)
    print(f"  • Scratch items removed: {scratch_count}")

    if not args.scratch_only:
        pycache_count = sanitize_pycache_directories(dry_run=args.dry_run)
        temp_count = sanitize_temp_files(dry_run=args.dry_run)
        coverage_count = sanitize_coverage_and_test_artifacts(dry_run=args.dry_run)
        build_count = sanitize_build_artifacts(dry_run=args.dry_run)
        print(f"  • Bytecode cache directories removed: {pycache_count}")
        print(f"  • Transient files removed (*.tmp, *.bak): {temp_count}")
        print(f"  • Test coverage & temp cache artifacts removed: {coverage_count}")
        print(f"  • Build & distribution directories removed: {build_count}")

    if args.git_gc:
        gc_success = run_git_maintenance(dry_run=args.dry_run)
        status_str = "Completed" if gc_success else "Skipped/Failed"
        print(f"  • Git auto garbage collection: {status_str}")

    print("✔ Workspace sanitization completed successfully.")


if __name__ == "__main__":
    main()
