#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build Script for the Lightweight Windows `CoachPorygonStudio.exe` Launcher.

Generates a multi-resolution Great Ball Coach Porygon `.ico` icon using pure
Python stdlib (zero Pillow dependency required!) and invokes PyInstaller to
package `apps/replay_coach/launcher_entry.py` into a compact `~8 MB` standalone
Windows `.exe` wrapper that bootstraps `.venv` with the user's exact GPU.

Usage:
    python scripts/build_windows_launcher.py --check   # Dry-run & generate .ico (Linux/macOS/Windows)
    python scripts/build_windows_launcher.py           # Compile dist/CoachPorygonStudio.exe (Windows)
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from typing import List, Sequence, Tuple
import zlib

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY_SCRIPT = REPO_ROOT / "apps" / "replay_coach" / "launcher_entry.py"
ICON_PATH = REPO_ROOT / "assets" / "coach_porygon.ico"
DIST_DIR = REPO_ROOT / "dist"


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Wrap a raw PNG chunk with length prefix and IEEE CRC-32 checksum."""
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def _render_greatball_rgba(size: int) -> bytes:
    """Render an anti-aliased Great Ball Coach Porygon emblem as RGBA PNG bytes."""
    rows: List[bytes] = []
    half = (size - 1) / 2.0
    radius = size * 0.45

    for y in range(size):
        row = bytearray([0])  # PNG filter type 0 (None)
        dy = (y - half) / radius
        for x in range(size):
            dx = (x - half) / radius
            dist = math.hypot(dx, dy)

            if dist > 1.03:
                row.extend((0, 0, 0, 0))
                continue

            # Outer silhouette anti-aliasing
            alpha = 255
            if dist > 0.96:
                alpha = max(0, min(255, int(round(255 * (1.03 - dist) / 0.07))))

            # Outer dark rim
            if dist >= 0.89:
                r, g, b = 11, 16, 27
            # Center Great Ball button
            elif dist <= 0.14:
                r, g, b = 37, 99, 235  # Great Ball royal blue core
            elif dist <= 0.24:
                r, g, b = 248, 250, 252  # White inner ring
            elif dist <= 0.34:
                r, g, b = 11, 16, 27  # Dark collar
            # Equatorial black band
            elif abs(dy) <= 0.09:
                r, g, b = 11, 16, 27
            # Lower white hemisphere
            elif dy > 0:
                shade = max(0.86, 1.0 - 0.12 * dist)
                r, g, b = int(248 * shade), int(250 * shade), int(252 * shade)
            # Upper blue hemisphere with twin crimson Great Ball stripes
            else:
                # Diagonal crimson stripes on upper-left and upper-right
                stripe_val = abs(dx) * 0.82 - (-dy) * 0.52
                in_stripe = (
                    0.26 <= abs(dx) <= 0.82
                    and 0.12 <= (-dy) <= 0.72
                    and 0.06 <= stripe_val <= 0.30
                )
                if in_stripe:
                    r, g, b = 225, 29, 72  # Crimson red accent
                else:
                    # Subtle top highlight
                    hl = max(0.0, 1.0 - math.hypot(dx + 0.25, dy + 0.42) * 1.15)
                    r = min(255, int(37 + 42 * hl))
                    g = min(255, int(99 + 52 * hl))
                    b = min(255, int(235 + 18 * hl))

            row.extend((r, g, b, alpha))
        rows.append(bytes(row))

    raw_scanlines = b"".join(rows)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat = zlib.compress(raw_scanlines, level=9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def generate_coach_icon(
    output_path: Path = ICON_PATH,
    sizes: Sequence[int] = (16, 32, 48, 256),
) -> Path:
    """Write a multi-resolution Windows `.ico` file using embedded PNG frames."""
    frames: List[Tuple[int, bytes]] = [(sz, _render_greatball_rgba(sz)) for sz in sizes]
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries: List[bytes] = []
    blobs: List[bytes] = []

    for sz, png_bytes in frames:
        dim_byte = 0 if sz >= 256 else sz
        entry = struct.pack(
            "<BBBBHHII",
            dim_byte,
            dim_byte,
            0,
            0,
            1,
            32,
            len(png_bytes),
            offset,
        )
        entries.append(entry)
        blobs.append(png_bytes)
        offset += len(png_bytes)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(header + b"".join(entries) + b"".join(blobs))
    return output_path


def build_pyinstaller_command(
    icon_path: Path = ICON_PATH,
    entry_script: Path = ENTRY_SCRIPT,
    dist_dir: Path = DIST_DIR,
) -> List[str]:
    """Construct the canonical PyInstaller command for the lightweight launcher `.exe`."""
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",
        "--clean",
        "--noconfirm",
        "--name",
        "CoachPorygonStudio",
        "--icon",
        str(icon_path),
        "--distpath",
        str(dist_dir),
        str(entry_script),
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the icon asset and compile (or dry-run validate) `CoachPorygonStudio.exe`."""
    parser = argparse.ArgumentParser(description="Build lightweight Windows CoachPorygonStudio.exe")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Generate assets/coach_porygon.ico and validate PyInstaller invocation without compiling",
    )
    parser.add_argument(
        "--icon-only",
        action="store_true",
        help="Only regenerate assets/coach_porygon.ico",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not ENTRY_SCRIPT.is_file():
        print(f"[ERROR] Missing launcher entry point: {ENTRY_SCRIPT}", file=sys.stderr)
        return 1

    icon = generate_coach_icon(ICON_PATH)
    print(f"[OK] Generated icon asset: {icon} ({icon.stat().st_size:,} bytes)")
    if args.icon_only:
        return 0

    cmd = build_pyinstaller_command(icon_path=icon)
    if args.check:
        print("[CHECK] Entry script verified:", ENTRY_SCRIPT)
        print("[CHECK] Planned PyInstaller command:")
        print("        " + " ".join(cmd))
        return 0

    if sys.platform != "win32":
        print(
            "[ERROR] Compiling a native Windows .exe requires running PyInstaller on Windows.\n"
            "        Use `--check` on Linux/macOS or trigger `.github/workflows/build-windows-launcher.yml`.",
            file=sys.stderr,
        )
        return 2

    if shutil.which("pyinstaller") is None:
        # Check `python -m PyInstaller`
        probe = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if probe.returncode != 0:
            print("[ERROR] PyInstaller is not installed. Run: pip install pyinstaller", file=sys.stderr)
            return 1

    print("[BUILD] Running PyInstaller for CoachPorygonStudio.exe...")
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)
    exe_path = DIST_DIR / "CoachPorygonStudio.exe"
    if not exe_path.is_file():
        print(f"[ERROR] Expected output binary not found at {exe_path}", file=sys.stderr)
        return 1
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"[OK] Built {exe_path} ({size_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
