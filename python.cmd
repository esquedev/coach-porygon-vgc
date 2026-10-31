@echo off
setlocal

REM ==============================================================================
REM Coach Porygon VGC -- Portable Dynamic Python Runtime Launcher
REM Dynamically discovers Python 3.10+ across virtualenvs, PATH, and launchers.
REM ==============================================================================

REM 1. Explicit user override via environment variable
if defined PYTHON_BIN if exist "%PYTHON_BIN%" (
    set "_PY=%PYTHON_BIN%"
    goto :run
)

REM 2. Local workspace virtual environment with installed dependencies (.venv)
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -c "import pycodestyle" >nul 2>&1
    if not errorlevel 1 (
        set "_PY=%~dp0.venv\Scripts\python.exe"
        goto :run
    )
)

REM 3. Local workspace venv/ alternative
if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" -c "import pycodestyle" >nul 2>&1
    if not errorlevel 1 (
        set "_PY=%~dp0venv\Scripts\python.exe"
        goto :run
    )
)

REM 4. Windows Python Launcher (py.exe -3)
py.exe -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "_PY=py.exe -3"
    goto :run
)

REM 5. System python.exe in PATH
python.exe -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "_PY=python.exe"
    goto :run
)

REM 6. Maintainer local workstation fallback (for development continuity on this PC)
if exist "C:\Program Files\Blender Foundation\Blender 4.4\4.4\python\bin\python.exe" (
    set "_PY="C:\Program Files\Blender Foundation\Blender 4.4\4.4\python\bin\python.exe""
    goto :run
)

REM 7. Fallback to workspace .venv if present
if exist "%~dp0.venv\Scripts\python.exe" (
    set "_PY=%~dp0.venv\Scripts\python.exe"
    goto :run
)

echo [ERROR] No suitable Python 3.10+ runtime detected on this machine.
echo To set up the required virtual environment:
echo   1. Install Python 3.10, 3.11, or 3.12 from https://python.org
echo   2. Create virtualenv:    python -m venv .venv
echo   3. Activate:             .venv\Scripts\activate
echo   4. Install dependencies: pip install -r requirements-dev.txt
exit /b 1

:run
endlocal & %_PY% %*
