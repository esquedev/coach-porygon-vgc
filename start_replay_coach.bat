@echo off
setlocal EnableExtensions

REM ============================================================================
REM Coach Porygon VGC - Isolated .venv Windows Installer and Replay Coach Launcher
REM Plain-text, human-auditable. Never touches system-wide Python packages.
REM ============================================================================
title Coach Porygon VGC - Replay Coach Studio

cd /d "%~dp0"
if errorlevel 1 (
    echo [ERROR] Could not enter the launcher folder: "%~dp0"
    pause
    exit /b 1
)

REM Force UTF-8 so Studio logs never crash on legacy cp1252 consoles.
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_OPTS=--disable-pip-version-check --retries 5 --timeout 60"
REM Binary-planting defense: never resolve executables from the current directory.
set "NoDefaultCurrentDirectoryInExePath=1"

setlocal EnableDelayedExpansion

echo.
echo ============================================================================
echo   Coach Porygon VGC - Replay Coach Studio (Windows Launcher)
echo ============================================================================
echo.

REM 0. Sanity: must run from the extracted project folder (not from inside a zip preview)
if not exist "requirements.txt" goto :err_extract
if not exist "apps\replay_coach\server.py" goto :err_extract

REM 1. Locate a 64-bit Python 3.10+ (prefers 3.12 / 3.11 which have the widest PyTorch wheel support)
call :find_python
if not defined PY_CMD goto :err_python

REM 2. Create the virtual environment if missing, or recreate it if broken / outdated
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [WARN] The existing .venv is broken or outdated - recreating it...
        rmdir /s /q ".venv"
    )
)
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating isolated Python virtual environment .venv using !PY_CMD! ...
    !PY_CMD! -m venv .venv
    if errorlevel 1 goto :err_venv
    if not exist ".venv\Scripts\python.exe" goto :err_venv
) else (
    echo [1/4] Isolated virtual environment .venv found.
)

REM 3. Explicitly activate the isolated .venv for all subsequent commands
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)
set "VENV_PY=.venv\Scripts\python.exe"
set "PIP_REQUIRE_VIRTUALENV=1"
echo [2/4] Activated virtual environment: .venv

REM 4. Verify requirements.txt SHA-256 stamp + full core package imports
set "NEED_INSTALL=0"
"%VENV_PY%" -c "import hashlib, pathlib, sys; h=hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(); s=pathlib.Path('.venv/.requirements.sha256'); sys.exit(0 if s.exists() and s.read_text(encoding='utf-8').strip()==h else 1)" >nul 2>&1
if errorlevel 1 set "NEED_INSTALL=1"

if "!NEED_INSTALL!"=="0" (
    "%VENV_PY%" -c "import torch, numpy, scipy, duckdb, py_mini_racer" >nul 2>&1
    if errorlevel 1 set "NEED_INSTALL=1"
)

REM Detect a WORKING NVIDIA driver (system paths first, then PATH only - never the current folder)
set "NVSMI="
if exist "%SystemRoot%\System32\nvidia-smi.exe" set "NVSMI=%SystemRoot%\System32\nvidia-smi.exe"
if not defined NVSMI if exist "%ProgramFiles%\NVIDIA Corporation\NVSMI\nvidia-smi.exe" set "NVSMI=%ProgramFiles%\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
if not defined NVSMI for /f "usebackq delims=" %%P in (`where $PATH:nvidia-smi 2^>nul`) do if not defined NVSMI set "NVSMI=%%P"

set "HAS_NVIDIA=0"
set "DRIVER_VER=unknown"
if defined NVSMI (
    "%NVSMI%" -L >nul 2>&1
    if not errorlevel 1 set "HAS_NVIDIA=1"
)
if "!HAS_NVIDIA!"=="1" (
    for /f "usebackq delims=" %%D in (`"%NVSMI%" --query-gpu=driver_version --format=csv,noheader 2^>nul`) do set "DRIVER_VER=%%D"
)

REM Self-healing CUDA upgrade: NVIDIA driver installed AFTER .venv was created with CPU-only torch.
REM A marker stores the driver version already tried so unsupported GPUs never reinstall torch on every launch.
if "!NEED_INSTALL!"=="0" if "!HAS_NVIDIA!"=="1" (
    call :torch_cuda_ok
    if errorlevel 1 (
        set "PREV_MARK="
        if exist ".venv\.cuda_attempt" set /p PREV_MARK=<".venv\.cuda_attempt"
        if not "!PREV_MARK!"=="!DRIVER_VER!" (
            echo [3/4] NVIDIA GPU driver !DRIVER_VER! detected, replacing CPU-only PyTorch in .venv with CUDA PyTorch...
            call :install_cuda_torch
        ) else (
            echo [WARN] NVIDIA GPU found but no compatible CUDA PyTorch wheel for driver !DRIVER_VER! - running on CPU.
        )
    )
)

if "!NEED_INSTALL!"=="1" (
    echo [3/4] Syncing runtime dependencies into .venv - first-time setup may take a few minutes...
    "%VENV_PY%" -m pip install %PIP_OPTS% --upgrade pip
    if "!HAS_NVIDIA!"=="1" (
        echo       NVIDIA GPU detected - installing CUDA PyTorch wheel...
        call :install_cuda_torch
    ) else (
        echo       No working NVIDIA GPU detected - installing standard CPU PyTorch...
    )

    "%VENV_PY%" -m pip install %PIP_OPTS% -r requirements.txt
    if errorlevel 1 goto :err_deps

    REM Guard against requirements.txt replacing CUDA torch with a CPU wheel
    if "!HAS_NVIDIA!"=="1" (
        call :torch_cuda_ok
        if errorlevel 1 call :install_cuda_torch
    )

    "%VENV_PY%" -c "import torch, numpy, scipy, duckdb, py_mini_racer" >nul 2>&1
    if errorlevel 1 goto :err_deps
    "%VENV_PY%" -c "import hashlib, pathlib; pathlib.Path('.venv/.requirements.sha256').write_text(hashlib.sha256(pathlib.Path('requirements.txt').read_bytes()).hexdigest(), encoding='utf-8')"
    echo       Dependencies synced and verified inside .venv.
) else (
    echo [3/4] All .venv dependencies verified - PyTorch, DuckDB, SciPy, NumPy, MiniRacer.
)

REM 5. Parse optional --host / --port / --no-browser (--no-browser is launcher-only, never forwarded)
set "STUDIO_HOST=127.0.0.1"
set "STUDIO_PORT=8765"
set "NEXT_IS="
set "SERVER_ARGS="
set "NO_BROWSER="
if defined COACH_NO_BROWSER set "NO_BROWSER=1"
for %%A in (%*) do (
    if "%%~A"=="--no-browser" (
        set "NO_BROWSER=1"
    ) else (
        set "SERVER_ARGS=!SERVER_ARGS! %%~A"
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
)
set "URL_HOST=!STUDIO_HOST!"
if "!URL_HOST!"=="0.0.0.0" set "URL_HOST=127.0.0.1"
set "STUDIO_URL=http://!URL_HOST!:!STUDIO_PORT!/"

REM 6. Boot the Replay Coach Studio HTTP/SSE server and safely open the browser
set "PYTHONPATH=src;."
echo [4/4] Starting Replay Coach Studio at !STUDIO_URL!
echo       Press Ctrl+C in this window to stop the server.
echo.

if not defined NO_BROWSER (
    start "" /b "%VENV_PY%" -c "import sys, time, urllib.request, webbrowser; u=sys.argv[1]; [time.sleep(0.4) or (urllib.request.urlopen(u+'api/state', timeout=0.5).status==200 and (webbrowser.open(u) or sys.exit(0))) for _ in range(75)]" "!STUDIO_URL!"
)
"%VENV_PY%" -m apps.replay_coach.server !SERVER_ARGS!
set "RC=!ERRORLEVEL!"
if "!RC!"=="0" exit /b 0
if "!RC!"=="-1073741510" exit /b 0
if "!RC!"=="130" exit /b 0
echo.
echo [ERROR] Replay Coach Studio exited unexpectedly - code !RC!.
echo         If the port is busy, retry with another one: start_replay_coach.bat --port 9000
pause
exit /b !RC!

REM ----------------------------------------------------------------------------
REM Subroutines
REM ----------------------------------------------------------------------------
:find_python
set "PY_CMD="
for %%V in (3.12 3.11 3.13 3.10) do (
    if not defined PY_CMD (
        py -%%V -c "import sys; sys.exit(0 if (sys.version_info >= (3, 10) and sys.maxsize > 2**32) else 1)" >nul 2>&1
        if not errorlevel 1 set "PY_CMD=py -%%V"
    )
)
if not defined PY_CMD (
    python -c "import sys; sys.exit(0 if (sys.version_info >= (3, 10) and sys.maxsize > 2**32) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY_CMD=python"
)
exit /b 0

:torch_cuda_ok
"%VENV_PY%" -c "import sys, torch; sys.exit(0 if (getattr(torch.version, 'cuda', None) and torch.cuda.is_available()) else 1)" >nul 2>&1
exit /b %ERRORLEVEL%

:install_cuda_torch
REM NEVER uninstall first: pip downloads before it replaces, so an offline/failed attempt keeps the working torch.
for %%U in (cu128 cu126 cu124 cu121) do (
    call :torch_cuda_ok
    if errorlevel 1 (
        echo       Trying official PyTorch CUDA wheel index %%U ...
        "%VENV_PY%" -m pip install %PIP_OPTS% --upgrade --force-reinstall --no-cache-dir torch --index-url https://download.pytorch.org/whl/%%U
    )
)
call :torch_cuda_ok
if errorlevel 1 (
    echo [WARN] No compatible CUDA PyTorch wheel could be installed - keeping the CPU PyTorch build.
    "%VENV_PY%" -c "import torch" >nul 2>&1
    if errorlevel 1 "%VENV_PY%" -m pip install %PIP_OPTS% torch
)
>".venv\.cuda_attempt" echo !DRIVER_VER!
exit /b 0

REM ----------------------------------------------------------------------------
REM Error exits (always pause so a double-clicked window never vanishes)
REM ----------------------------------------------------------------------------
:err_extract
echo [ERROR] requirements.txt / apps\replay_coach was not found next to this script.
echo         Extract the FULL release zip first - do not run the .bat from inside the zip preview.
echo.
pause
exit /b 1

:err_python
echo [ERROR] A 64-bit Python 3.10 or higher was not found.
echo.
echo         Install Python 3.12 from https://www.python.org/downloads/
echo         IMPORTANT: tick "Add python.exe to PATH" during installation, then re-run this script.
echo.
pause
exit /b 1

:err_venv
echo [ERROR] Failed to create the .venv virtual environment.
echo         Close any other Studio window using this folder, delete the .venv folder, and retry.
echo.
pause
exit /b 1

:err_deps
echo.
echo [ERROR] Dependency installation failed. Check your internet connection and retry.
echo         If the problem persists, delete the .venv folder and run this script again.
echo.
pause
exit /b 1
