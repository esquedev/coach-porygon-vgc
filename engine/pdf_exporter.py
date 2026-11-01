#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Deterministic PDF Exporter
Provides headless browser compilation (Chrome / Edge / Chromium) to export
AI-generated HTML esports reports and infographics into print-ready PDF format.
Adheres strictly to System Guardrail Rule 11 (Exclusive Artifact Lock).
"""

import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
_env_artifact = os.environ.get("ANTIGRAVITY_ARTIFACT_DIR")
ARTIFACT_DIR = Path(_env_artifact).resolve() if _env_artifact else None


def find_browser_executable() -> Optional[str]:
    """Dynamically locates Google Chrome, Edge, or Chromium executable across OS environments."""
    for c in ["chrome", "google-chrome", "chromium", "chromium-browser", "msedge"]:
        found = shutil.which(c)
        if found:
            return found
    for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ]:
        if Path(p).exists():
            return str(p)
    return None


def export_pdf(
    html_content: str,
    output_pdf_path: str,
    theme: str = "porygon",
    sync_to_artifact: bool = False
) -> Dict[str, Any]:
    """
    Renders HTML report to disk and exports to PDF using headless Chrome/Chromium/Edge.
    Gracefully falls back to static HTML report if browser executable is unavailable.
    Honors Rule 11 (Exclusive Artifact Lock): does not sync to artifact directory unless explicitly authorized.
    """
    out_pdf = Path(output_pdf_path).resolve()
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    out_html = out_pdf.with_suffix(".html")

    # 1. Write HTML report
    out_html.write_text(html_content, encoding="utf-8")

    # 2. Sync to Antigravity Brain artifact directory ONLY if explicitly permitted
    if sync_to_artifact and ARTIFACT_DIR and ARTIFACT_DIR.exists():
        try:
            shutil.copyfile(out_html, ARTIFACT_DIR / out_html.name)
        except Exception:
            pass

    browser_bin = find_browser_executable()
    if not browser_bin:
        return {
            "success": True,
            "pdf_generated": False,
            "html_path": str(out_html),
            "pdf_path": None,
            "message": "HTML report created successfully. Headless browser not found for automated PDF compilation.",
            "theme": theme
        }

    cmd = [
        browser_bin,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={str(out_pdf)}",
        str(out_html)
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25, check=True)
        pdf_ok = out_pdf.exists() and out_pdf.stat().st_size > 0

        if pdf_ok and sync_to_artifact and ARTIFACT_DIR and ARTIFACT_DIR.exists():
            try:
                shutil.copyfile(out_pdf, ARTIFACT_DIR / out_pdf.name)
            except Exception:
                pass

        return {
            "success": True,
            "pdf_generated": pdf_ok,
            "html_path": str(out_html),
            "pdf_path": str(out_pdf) if pdf_ok else None,
            "size_bytes": out_pdf.stat().st_size if pdf_ok else 0,
            "theme": theme
        }
    except Exception as e:
        return {
            "success": True,
            "pdf_generated": False,
            "html_path": str(out_html),
            "pdf_path": None,
            "message": f"Browser invocation failed: {str(e)}",
            "theme": theme
        }
