# -*- coding: utf-8 -*-
"""Lightweight Stdlib-Only Windows/Cross-Platform Launcher Entry Point.

Designed to compile cleanly via PyInstaller (`--onefile --console`) into a tiny
`~8 MB` `CoachPorygonStudio.exe` wrapper without bundling 3 GB of PyTorch/CUDA
binaries. On launch, it locates the repository root, bootstraps or activates
the isolated project `.venv`, verifies `requirements.txt` via a SHA-256 stamp
and core module probe (auto-selecting CUDA 12.4 vs. CPU PyTorch), boots
`apps.replay_coach.server`, waits for `/api/state`, and opens the user's browser.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import List, Optional, Sequence
import urllib.request
import webbrowser

CORE_IMPORT_CHECK = "import torch, numpy, scipy, duckdb, py_mini_racer"
PYTORCH_CU124_INDEX = "https://download.pytorch.org/whl/cu124"
STAMP_REL_PATH = Path(".venv") / ".requirements.sha256"


def find_repo_root(start_path: Optional[Path] = None) -> Path:
    """Locate the Coach Porygon VGC repository root containing `requirements.txt`."""
    candidates: List[Path] = []
    if start_path is not None:
        candidates.append(Path(start_path).resolve())
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir, exe_dir.parent])
    else:
        here = Path(__file__).resolve()
        candidates.extend([here.parents[2], here.parent, Path.cwd().resolve()])

    seen = set()
    for base in candidates:
        for directory in [base, *base.parents]:
            if directory in seen:
                continue
            seen.add(directory)
            if (
                (directory / "requirements.txt").is_file()
                and (directory / "apps" / "replay_coach" / "server.py").is_file()
            ):
                return directory

    raise FileNotFoundError(
        "Could not locate Coach Porygon VGC repository root (expected requirements.txt "
        "and apps/replay_coach/server.py). Place CoachPorygonStudio.exe inside the "
        "repository folder (or its dist/ subfolder)."
    )


def venv_python_path(repo_root: Path) -> Path:
    """Return the platform-appropriate Python executable inside `.venv`."""
    if os.name == "nt":
        return repo_root / ".venv" / "Scripts" / "python.exe"
    return repo_root / ".venv" / "bin" / "python"


def compute_requirements_hash(requirements_path: Path) -> str:
    """Compute a deterministic SHA-256 hex digest of `requirements.txt`."""
    return hashlib.sha256(requirements_path.read_bytes()).hexdigest()


def find_system_python() -> Optional[List[str]]:
    """Find a system Python 3.10+ interpreter suitable for creating `.venv`."""
    probes: List[List[str]] = (
        [["py", "-3"], ["python"], ["python3"]]
        if os.name == "nt"
        else [["python3"], ["python3.12"], ["python3.11"], ["python3.10"], ["python"]]
    )
    frozen = bool(getattr(sys, "frozen", False))
    current_exe = Path(sys.executable).resolve()

    for cmd in probes:
        exe = shutil.which(cmd[0])
        if not exe:
            continue
        if frozen and Path(exe).resolve() == current_exe:
            continue
        try:
            proc = subprocess.run(
                [*cmd, "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            if proc.returncode == 0:
                return cmd
        except Exception:
            continue
    return None


def has_nvidia_gpu() -> bool:
    """Return True if `nvidia-smi` is available and exits cleanly on Windows/Linux."""
    if sys.platform == "darwin":
        return False
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        proc = subprocess.run(
            ["nvidia-smi"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def needs_dependency_sync(
    venv_py: Path,
    requirements_path: Path,
    stamp_path: Path,
) -> bool:
    """Return True if `.venv` needs a dependency sync based on SHA-256 stamp & imports."""
    if not venv_py.is_file():
        return True
    expected_hash = compute_requirements_hash(requirements_path)
    if not stamp_path.is_file():
        return True
    try:
        recorded_hash = stamp_path.read_text(encoding="utf-8").strip()
    except OSError:
        return True
    if recorded_hash != expected_hash:
        return True
    try:
        proc = subprocess.run(
            [str(venv_py), "-c", CORE_IMPORT_CHECK],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        return proc.returncode != 0
    except Exception:
        return True


def ensure_venv_and_deps(repo_root: Path) -> Path:
    """Ensure `.venv` exists and all `requirements.txt` packages are synced inside it."""
    venv_py = venv_python_path(repo_root)
    req_path = repo_root / "requirements.txt"
    stamp_path = repo_root / STAMP_REL_PATH

    if not venv_py.is_file():
        sys_py = find_system_python()
        if sys_py is None:
            raise RuntimeError(
                "Python 3.10+ was not found on your PATH.\n"
                "Install Python 3.10+ from https://www.python.org/downloads/ "
                "(check 'Add python.exe to PATH' on Windows) and relaunch."
            )
        print(f"[1/4] Creating isolated virtual environment (.venv) using {' '.join(sys_py)}...", flush=True)
        subprocess.run([*sys_py, "-m", "venv", str(repo_root / ".venv")], cwd=str(repo_root), check=True)
    else:
        print("[1/4] Isolated virtual environment (.venv) found.", flush=True)

    print(f"[2/4] Using isolated environment: {repo_root / '.venv'}", flush=True)

    if needs_dependency_sync(venv_py, req_path, stamp_path):
        print("[3/4] Syncing runtime dependencies into .venv (first launch may take a few minutes)...", flush=True)
        subprocess.run([str(venv_py), "-m", "pip", "install", "--upgrade", "pip"], cwd=str(repo_root), check=True)

        if has_nvidia_gpu():
            print("      NVIDIA GPU detected — installing CUDA 12.4 PyTorch wheel...", flush=True)
            cuda_res = subprocess.run(
                [str(venv_py), "-m", "pip", "install", "torch", "--index-url", PYTORCH_CU124_INDEX],
                cwd=str(repo_root),
                check=False,
            )
            if cuda_res.returncode != 0:
                print("[WARN] CUDA wheel install failed; falling back to standard CPU PyTorch...", flush=True)
        else:
            print("      Installing standard PyTorch wheel (CPU / Apple Silicon)...", flush=True)

        subprocess.run(
            [str(venv_py), "-m", "pip", "install", "-r", str(req_path)],
            cwd=str(repo_root),
            check=True,
        )
        stamp_path.parent.mkdir(parents=True, exist_ok=True)
        stamp_path.write_text(compute_requirements_hash(req_path), encoding="utf-8")
        print("      Dependencies synced and verified inside .venv.", flush=True)
    else:
        print("[3/4] All .venv dependencies verified (PyTorch, DuckDB, SciPy, NumPy, MiniRacer).", flush=True)

    return venv_py


def wait_and_open_browser(
    studio_url: str,
    timeout_s: float = 45.0,
    stop_event: Optional[threading.Event] = None,
) -> bool:
    """Poll the Studio `/api/state` endpoint until ready and launch the default browser."""
    probe_url = studio_url.rstrip("/") + "/api/state"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if stop_event is not None and stop_event.is_set():
            return False
        try:
            with urllib.request.urlopen(probe_url, timeout=1.0) as resp:
                if resp.status == 200:
                    webbrowser.open(studio_url)
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the lightweight Replay Coach Studio launcher."""
    parser = argparse.ArgumentParser(
        prog="CoachPorygonStudio",
        description="Coach Porygon VGC — Isolated .venv Replay Coach Studio Launcher",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="Compute backend passed to apps.replay_coach.server",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the server without automatically opening a browser tab",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Bootstrap `.venv`, launch Replay Coach Studio, and open the browser."""
    print("\n============================================================================", flush=True)
    print("  Coach Porygon VGC - Replay Coach Studio Launcher", flush=True)
    print("============================================================================\n", flush=True)

    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        repo_root = find_repo_root()
        venv_py = ensure_venv_and_deps(repo_root)
    except Exception as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr, flush=True)
        if os.name == "nt" and getattr(sys, "frozen", False):
            input("\nPress Enter to close...")
        return 1

    studio_url = f"http://{args.host}:{args.port}/"
    stop_event = threading.Event()
    if not args.no_browser and os.environ.get("COACH_NO_BROWSER") != "1":
        threading.Thread(
            target=wait_and_open_browser,
            args=(studio_url, 45.0, stop_event),
            daemon=True,
        ).start()

    env = dict(os.environ)
    env["PYTHONPATH"] = f"src{os.pathsep}."
    venv_dir = repo_root / ".venv"
    venv_bin = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    env["VIRTUAL_ENV"] = str(venv_dir)
    env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"

    cmd = [
        str(venv_py),
        "-m",
        "apps.replay_coach.server",
        "--host",
        str(args.host),
        "--port",
        str(args.port),
        "--device",
        str(args.device),
    ]
    print(f"[4/4] Starting Replay Coach Studio at {studio_url}", flush=True)
    print("      Press Ctrl+C in this window to stop the server.\n", flush=True)

    proc: Optional[subprocess.Popen[bytes]] = None
    try:
        proc = subprocess.Popen(cmd, cwd=str(repo_root), env=env)
        return int(proc.wait())
    except KeyboardInterrupt:
        print("\n[Coach Porygon VGC] Shutting down Replay Coach Studio...", flush=True)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        return 0
    finally:
        stop_event.set()


if __name__ == "__main__":
    raise SystemExit(main())
