@echo off
REM Locate Python interpreter (prefer repository .venv if present)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo [Coach Porygon VGC] Syncing Databases & Compiling Bilingual Command Center...
call "%PY%" "%~dp0engine\update_command_center.py"
echo [Coach Porygon VGC] Starting Python Backend Server at http://localhost:8000 ...
start "" "http://localhost:8000"
call "%PY%" "%~dp0engine\ui_server.py"
