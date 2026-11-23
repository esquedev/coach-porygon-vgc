@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================================
REM Coach Porygon VGC — 1-Click Windows Installer & Replay Coach Studio Launcher
REM ============================================================================
title Coach Porygon VGC - Replay Coach Studio
cd /d "%~dp0"

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

REM 2. Create virtual environment if missing
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating local Python virtual environment ^(.venv^)...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [1/3] Virtual environment ^(.venv^) found.
)

set "VENV_PY=.venv\Scripts\python.exe"

REM 3. Install runtime dependencies if any core package is missing
"%VENV_PY%" -c "import torch, numpy, scipy, duckdb" >nul 2>&1
if errorlevel 1 (
    echo [2/3] Installing runtime dependencies ^(first-time setup may take a few minutes^)...
    "%VENV_PY%" -m pip install --upgrade pip

    REM Probe for NVIDIA GPU to install CUDA-accelerated PyTorch automatically
    where nvidia-smi >nul 2>&1
    if !ERRORLEVEL!==0 (
        echo       NVIDIA GPU detected - installing CUDA-enabled PyTorch...
        "%VENV_PY%" -m pip install torch --index-url https://download.pytorch.org/whl/cu124
        if errorlevel 1 (
            echo [WARN] CUDA wheel install failed; falling back to standard PyTorch package...
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
) else (
    echo [2/3] Dependencies already installed ^(PyTorch, DuckDB, SciPy, NumPy^).
)

REM 4. Boot the Replay Coach Studio HTTP/SSE server and open the browser
set "PYTHONPATH=src;."
echo [3/3] Starting Replay Coach Studio at http://127.0.0.1:8765/
echo       Press Ctrl+C in this window to stop the server.
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8765/"
"%VENV_PY%" -m apps.replay_coach.server %*
if errorlevel 1 (
    echo.
    echo [ERROR] Replay Coach Studio exited unexpectedly.
    pause
    exit /b 1
)

endlocal
