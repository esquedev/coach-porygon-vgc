@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================================
REM Coach Porygon VGC — Isolated .venv Windows Installer & Replay Coach Launcher
REM ============================================================================
title Coach Porygon VGC - Replay Coach Studio
cd /d "%~dp0"

REM Strip Windows Mark-of-the-Web (Zone.Identifier) from CoachPorygonStudio.exe if present so SmartScreen does not block it
if exist "CoachPorygonStudio.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Unblock-File -Path '.\CoachPorygonStudio.exe' -ErrorAction SilentlyContinue" >nul 2>&1
)
if exist "dist\CoachPorygonStudio.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Unblock-File -Path '.\dist\CoachPorygonStudio.exe' -ErrorAction SilentlyContinue" >nul 2>&1
)

echo.
echo ============================================================================
echo   Coach Porygon VGC - Replay Coach Studio (Windows Launcher)
echo ============================================================================
echo.

REM 1. Locate Python 3.10+
set "PY_CMD="
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if !ERRORLEVEL!==0 set "PY_CMD=py -3"
)
if not defined PY_CMD (
    where python >nul 2>&1
    if %ERRORLEVEL%==0 (
        python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
        if !ERRORLEVEL!==0 set "PY_CMD=python"
    )
)
if not defined PY_CMD (
    echo [ERROR] Python 3.10 or higher was not found on your PATH.
    echo.
    echo Please install Python 3.10+ from: https://www.python.org/downloads/
    echo IMPORTANT: Check "Add python.exe to PATH" during installation, then re-run this script.
    echo.
    pause
    exit /b 1
)

REM 2. Create virtual environment if missing (never pollutes system Python)
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating isolated Python virtual environment ^(.venv^)...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Isolated virtual environment ^(.venv^) found.
)

REM 3. Explicitly activate the isolated .venv for all subsequent commands
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)
set "VENV_PY=.venv\Scripts\python.exe"
echo [2/4] Activated virtual environment: %CD%\.venv

REM 4. Verify requirements.txt SHA-256 stamp + full core package imports
set "NEED_INSTALL=0"
"%VENV_PY%" -c "import hashlib, pathlib, sys; h=hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(); s=pathlib.Path('.venv/.requirements.sha256'); sys.exit(0 if s.exists() and s.read_text(encoding='utf-8').strip()==h else 1)" >nul 2>&1
if errorlevel 1 set "NEED_INSTALL=1"

if "%NEED_INSTALL%"=="0" (
    "%VENV_PY%" -c "import torch, numpy, scipy, duckdb, py_mini_racer" >nul 2>&1
    if errorlevel 1 set "NEED_INSTALL=1"
)

REM Self-healing CUDA upgrade: if NVIDIA drivers were installed AFTER .venv was created with CPU-only torch,
REM automatically upgrade torch to the CUDA 12.4 wheel!
set "NEED_CUDA_UPGRADE=0"
if "%NEED_INSTALL%"=="0" (
    where nvidia-smi >nul 2>&1
    if !ERRORLEVEL!==0 (
        "%VENV_PY%" -c "import sys, torch; sys.exit(0 if getattr(torch.version, 'cuda', None) else 1)" >nul 2>&1
        if errorlevel 1 set "NEED_CUDA_UPGRADE=1"
    )
)

if "%NEED_CUDA_UPGRADE%"=="1" (
    echo [3/4] NVIDIA GPU driver detected, upgrading CPU-only PyTorch in .venv to CUDA 12.4...
    "%VENV_PY%" -m pip install --upgrade --force-reinstall --no-deps torch --index-url https://download.pytorch.org/whl/cu124
    "%VENV_PY%" -m pip install torch --index-url https://download.pytorch.org/whl/cu124
)

if "%NEED_INSTALL%"=="1" (
    echo [3/4] Syncing runtime dependencies into .venv ^(first-time setup may take a few minutes^)...
    "%VENV_PY%" -m pip install --upgrade pip

    REM Probe for NVIDIA GPU to install CUDA-accelerated PyTorch automatically
    where nvidia-smi >nul 2>&1
    if !ERRORLEVEL!==0 (
        echo       NVIDIA GPU detected - installing CUDA 12.4 PyTorch wheel...
        "%VENV_PY%" -m pip install torch --index-url https://download.pytorch.org/whl/cu124
        if errorlevel 1 (
            echo [WARN] CUDA wheel install failed; falling back to standard CPU PyTorch...
        )
    ) else (
        echo       No NVIDIA GPU detected - installing standard CPU PyTorch...
    )

    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed. Check your internet connection and retry.
        pause
        exit /b 1
    )

    "%VENV_PY%" -c "import hashlib, pathlib; pathlib.Path('.venv/.requirements.sha256').write_text(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(), encoding='utf-8')"
    echo       Dependencies synced and verified inside .venv.
) else (
    echo [3/4] All .venv dependencies verified ^(PyTorch, DuckDB, SciPy, NumPy, MiniRacer^).
)

REM 5. Detect optional --host / --port overrides for browser URL
set "STUDIO_HOST=127.0.0.1"
set "STUDIO_PORT=8765"
set "NEXT_IS="
for %%A in (%*) do (
    if "!NEXT_IS!"=="host" (
        set "STUDIO_HOST=%%~A"
        set "NEXT_IS="
    ) else if "!NEXT_IS!"=="port" (
        set "STUDIO_PORT=%%~A"
        set "NEXT_IS="
    ) else if "%%~A"=="--host" (
        set "NEXT_IS=host"
    ) else if "%%~A"=="--port" (
        set "NEXT_IS=port"
    )
)
set "STUDIO_URL=http://!STUDIO_HOST!:!STUDIO_PORT!/"

REM 6. Boot the Replay Coach Studio HTTP/SSE server and safely open the browser
set "PYTHONPATH=src;."
echo [4/4] Starting Replay Coach Studio at !STUDIO_URL!
echo       Press Ctrl+C in this window to stop the server.
echo.

if not defined COACH_NO_BROWSER (
    start "" /b "%VENV_PY%" -c "import sys, time, urllib.request, webbrowser; u=sys.argv[1]; [time.sleep(0.4) or (urllib.request.urlopen(u+'api/state', timeout=0.5).status==200 and (webbrowser.open(u) or sys.exit(0))) for _ in range(75)]" "!STUDIO_URL!"
)
"%VENV_PY%" -m apps.replay_coach.server %*
if errorlevel 1 (
    echo.
    echo [ERROR] Replay Coach Studio exited unexpectedly.
    pause
    exit /b 1
)

endlocal
