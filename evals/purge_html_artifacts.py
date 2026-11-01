#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BeRightVGC / Coach Porygon VGC — HTML Artifact Purger Pre-Hook
Part of the Pre-Push & Pre-Commit Verification Pipeline.

Removes transient, generated, and volatile HTML reports across the workspace
to ensure clean, non-bloated Git commits and release integrity.
"""

import argparse
from pathlib import Path
import subprocess
import sys
from typing import List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent

# Core asset files that define the master user interface
PROTECTED_CORE_ASSETS = {
    "command_center.html",
    "command_center_en.html",
    "command_center_es.html",
    "ai_health_stress_report.html",
}

EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "agent_audits",
}


def find_html_files(purge_all: bool = False) -> List[Path]:
    """
    Locates HTML files according to the purge scope.

    Args:
        purge_all: When True, finds ALL html files in the repo (except .venv/.git).
                   When False, finds all generated reports in reports/, data/munchstats/output/, and scratch/.
    """
    html_files: List[Path] = []

    if purge_all:
        for p in REPO_ROOT.rglob("*.html"):
            if any(part in EXCLUDED_DIRECTORIES for part in p.parts):
                continue
            html_files.append(p)
    else:
        target_dirs = [
            REPO_ROOT / "reports",
            REPO_ROOT / "scratch",
            REPO_ROOT / "data" / "munchstats" / "output",
        ]
        for td in target_dirs:
            if td.exists():
                for p in td.rglob("*.html"):
                    if any(part in EXCLUDED_DIRECTORIES for part in p.parts):
                        continue
                    if p.name in PROTECTED_CORE_ASSETS:
                        continue
                    html_files.append(p)

    return sorted(html_files)


def purge_html_artifacts(purge_all: bool = False, dry_run: bool = False, rebuild_ui: bool = True) -> int:
    """
    Unlinks target HTML files and optionally reconstitutes command center UI.

    Returns:
        Number of unlinked HTML files.
    """
    candidates = find_html_files(purge_all=purge_all)
    unlinked_count = 0

    print("==============================================================================")
    print("  BERIGHTVGC / COACH PORYGON VGC — HTML ARTIFACT PURGER PRE-HOOK")
    print("==============================================================================")
    print(f"  Scope: {'EVERY .HTML FILE IN REPO (--all)' if purge_all else 'Generated Reports & Output'}")
    print(f"  Dry Run: {dry_run}\n")

    for f in candidates:
        rel_path = f.relative_to(REPO_ROOT)
        is_core = f.name in PROTECTED_CORE_ASSETS

        if not dry_run:
            try:
                f.unlink(missing_ok=True)
                unlinked_count += 1
                tag = " [CORE ASSET]" if is_core else ""
                print(f"  ✔ Removed: {rel_path}{tag}")
            except Exception as exc:
                print(f"  ✖ Failed to remove {rel_path}: {exc}")
        else:
            unlinked_count += 1
            tag = " [CORE ASSET]" if is_core else ""
            print(f"  [DRY RUN] Would remove: {rel_path}{tag}")

    # If purge_all deleted core assets and rebuild is requested, rebuild immediately
    if purge_all and rebuild_ui and not dry_run:
        cc_path = REPO_ROOT / "assets" / "command_center.html"
        if not cc_path.exists():
            print("\n  [REBUILD] Reconstituting canonical command_center.html via update_command_center.py...")
            try:
                subprocess.run(
                    [sys.executable, str(REPO_ROOT / "engine" / "update_command_center.py")],
                    check=True,
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                )
                print("  ✔ Command Center HUD successfully rebuilt and validated.")
            except Exception as exc:
                print(f"  ✖ Rebuild failed: {exc}")

    print("------------------------------------------------------------------------------")
    print(f"  Total HTML files purged: {unlinked_count}")
    print("==============================================================================\n")
    return unlinked_count


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Purge HTML reports and volatile artifacts")
    parser.add_argument("--all", action="store_true", help="Purge literally EVERY .html file across repo")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without deleting files")
    parser.add_argument("--no-rebuild", action="store_true", help="Do not auto-reconstitute command_center.html if purged")
    args = parser.parse_args()

    purge_html_artifacts(
        purge_all=args.all,
        dry_run=args.dry_run,
        rebuild_ui=not args.no_rebuild
    )


if __name__ == "__main__":
    main()
