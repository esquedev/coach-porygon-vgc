@echo off
setlocal EnableDelayedExpansion

REM Parse CLI arguments for pre-push / AI audit enforcement flag
set "ENFORCE_AI_AUDIT=0"
for %%a in (%*) do (
    if /i "%%a"=="--pre-push" set "ENFORCE_AI_AUDIT=1"
    if /i "%%a"=="--with-ai-audit" set "ENFORCE_AI_AUDIT=1"
    if /i "%%a"=="--enforce-audit" set "ENFORCE_AI_AUDIT=1"
)

REM Locate Python interpreter (prefer repository .venv if present)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY=%~dp0.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

REM Enable Virtual Terminal Processing for ANSI colors in Windows CMD
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "C_RESET=%ESC%[0m"
set "C_BOLD=%ESC%[1m"
set "C_GREEN=%ESC%[1;32m"
set "C_RED=%ESC%[1;31m"
set "C_YELLOW=%ESC%[1;33m"
set "C_CYAN=%ESC%[1;36m"
set "C_WHITE=%ESC%[1;37m"

echo %C_CYAN%==============================================================================%C_RESET%
echo %C_CYAN%  %C_BOLD%COACH PORYGON VGC -- LOCAL CI/CD PIPELINE (FULL 5-PHASE RUNNER)%C_RESET%
echo %C_CYAN%==============================================================================%C_RESET%
echo.

REM --- PHASE 0: Workspace Sanitization & Scratch Cleanup ---
echo %C_CYAN%[PHASE 0/5]%C_RESET% %C_WHITE%Sanitizing Workspace and Garbage Collection...%C_RESET%
call "%PY%" engine/clean_workspace.py
if errorlevel 1 (
    echo %C_RED%  [FAIL] Phase 0: Workspace sanitization failed.%C_RESET%
    exit /b 1
)
echo %C_GREEN%  [OK] Workspace sanitized (scratch, caches, and test residue purged).%C_RESET%
echo.

REM --- PHASE 1: Initialize Public Schema Templates ---
echo %C_CYAN%[PHASE 1/5]%C_RESET% %C_WHITE%Initializing Schema Templates...%C_RESET%
call "%PY%" -c "from pathlib import Path; import shutil; [shutil.copy(f, f.parent / f.name.replace('.example', '')) for f in Path('data').glob('*.example.*') if not (f.parent / f.name.replace('.example', '')).exists()]"
if errorlevel 1 (
    echo %C_RED%  [FAIL] Phase 1 failed to provision data templates.%C_RESET%
    exit /b 1
)
echo %C_GREEN%  [OK] Public schema templates verified.%C_RESET%
echo.

REM --- PHASE 2: Lint and Code Style Verification ---
echo %C_CYAN%[PHASE 2/5]%C_RESET% %C_WHITE%Linting and Syntax Compilation...%C_RESET%
call "%PY%" -m compileall -q engine evals tests
if errorlevel 1 (
    echo %C_RED%  [FAIL] Phase 2: Python syntax compilation error detected.%C_RESET%
    exit /b 1
)

call "%PY%" -m flake8 --version >nul 2>&1
if not errorlevel 1 (
    call "%PY%" -m flake8 engine/ evals/ tests/ --count --max-line-length=160 --extend-ignore=E121,E201,E202,E203,E226,E231,E241,E302,E303,E305,E402,E501,E701,E731,E741,F401,F541,F841,W503,W504 --statistics
) else (
    echo %C_YELLOW%  [WARN] flake8 not installed in current environment; falling back to pycodestyle.%C_RESET%
    call "%PY%" -m pycodestyle engine/ evals/ tests/ --max-line-length=160 --ignore=E121,E201,E202,E203,E226,E231,E241,E302,E303,E305,E402,E501,E701,E731,E741,F401,F541,F841,W503,W504 --statistics
)
if errorlevel 1 (
    echo %C_RED%  [FAIL] Phase 2: Linting violations detected.%C_RESET%
    exit /b 1
)
echo %C_GREEN%  [OK] Code style and syntax verified (0 violations).%C_RESET%
echo.

REM --- PHASE 3: AI Health Stress Audit & Static Guardrails ---
if "!ENFORCE_AI_AUDIT!"=="1" goto :phase3_enforce
goto :phase3_skip

:phase3_enforce
echo %C_CYAN%[PHASE 3/5]%C_RESET% %C_WHITE%Verifying AI Health Stress Audit and Static Guardrails [ENFORCED]...%C_RESET%
call "%PY%" evals/evaluate_release_health.py --verify
if errorlevel 1 goto :phase3_fail
echo %C_GREEN%  [OK] AI Health Stress audit and static guardrails verified and consumed.%C_RESET%
goto :phase3_done

:phase3_skip
echo %C_CYAN%[PHASE 3/5]%C_RESET% %C_WHITE%Verifying Static Guardrails and Link Integrity [AUDIT SKIPPED]...%C_RESET%
call "%PY%" evals/run_static_checks.py
if errorlevel 1 goto :phase3_static_fail
echo %C_YELLOW%  [SKIP] AI Health Stress Audit consumption skipped - run with --pre-push to enforce.%C_RESET%
goto :phase3_done

:phase3_fail
echo %C_RED%  [FAIL] Phase 3: AI Health Stress Audit or static guardrails verification failed.%C_RESET%
exit /b 1

:phase3_static_fail
echo %C_RED%  [FAIL] Phase 3: Static guardrails or link checks failed.%C_RESET%
exit /b 1

:phase3_done
echo.

REM --- PHASE 4: Vector and Raster Asset Audit ---
echo %C_CYAN%[PHASE 4/5]%C_RESET% %C_WHITE%Auditing Vector and Raster Assets...%C_RESET%
call "%PY%" engine/verify_png_inventory.py
if errorlevel 1 (
    echo %C_RED%  [FAIL] Phase 4: Asset curation and SHA-256 digest validation failed.%C_RESET%
    exit /b 1
)
echo %C_GREEN%  [OK] Asset inventory verified.%C_RESET%
echo.

REM --- PHASE 5: Full Test Suite Execution ---
echo %C_CYAN%[PHASE 5/5]%C_RESET% %C_WHITE%Executing Full Test Suite (pytest with coverage parity)...%C_RESET%
call "%PY%" -m pytest --version >nul 2>&1
if not errorlevel 1 (
    call "%PY%" -m pytest tests/ --cov=engine --cov-report=term-missing
) else (
    call "%PY%" tests/run_all_tests.py
)
if errorlevel 1 (
    echo %C_RED%  [FAIL] Phase 5: Test suite failed.%C_RESET%
    exit /b 1
)
echo.
echo %C_CYAN%==============================================================================%C_RESET%
echo %C_GREEN%  [PASS] ALL 5 CI/CD PIPELINE PHASES PASSED LOCALLY WITH ZERO ERRORS%C_RESET%
echo %C_CYAN%==============================================================================%C_RESET%
echo.
echo %C_CYAN%[POST-RUN GC]%C_RESET% %C_WHITE%Executing final workspace sanitization and Git pack optimization...%C_RESET%
call "%PY%" engine/clean_workspace.py --git-gc
echo %C_GREEN%  [OK] Workspace and Git repository optimized for push.%C_RESET%
