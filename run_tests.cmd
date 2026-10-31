@echo off
setlocal
chcp 65001 >nul
call "%~dp0python.cmd" "%~dp0tests\run_all_tests.py" %*
if %ERRORLEVEL% NEQ 0 (
    exit /b %ERRORLEVEL%
)
exit /b 0
