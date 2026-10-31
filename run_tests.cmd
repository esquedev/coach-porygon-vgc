@echo off
setlocal

echo ==============================================================================
echo   COACH PORYGON VGC -- LOCAL CI/CD PIPELINE (FULL 5-PHASE RUNNER)
echo ==============================================================================
echo.

REM --- PHASE 1: Initialize Public Schema Templates ---
echo [PHASE 1/5] Initializing Schema Templates...
call "%~dp0python.cmd" -c "from pathlib import Path; import shutil; [shutil.copy(f, f.parent / f.name.replace('.example', '')) for f in Path('data').glob('*.example.*') if not (f.parent / f.name.replace('.example', '')).exists()]"
if errorlevel 1 (
    echo [FAIL] Phase 1 failed to provision data templates.
    exit /b 1
)
echo   [OK] Public schema templates verified.
echo.

REM --- PHASE 2: Lint and Code Style Verification ---
echo [PHASE 2/5] Linting and Syntax Compilation...
call "%~dp0python.cmd" -m compileall -q engine evals scouts tests
if errorlevel 1 (
    echo [FAIL] Phase 2: Python syntax compilation error detected.
    exit /b 1
)

call "%~dp0python.cmd" -m flake8 --version >nul 2>&1
if not errorlevel 1 (
    call "%~dp0python.cmd" -m flake8 engine/ evals/ scouts/ tests/ --count --max-line-length=120 --extend-ignore=E121,E201,E202,E203,E226,E231,E241,E302,E303,E305,E402,E501,E701,E731,E741,F401,F541,F841,W503,W504 --statistics
) else (
    call "%~dp0python.cmd" -m pycodestyle engine/ evals/ scouts/ tests/ --max-line-length=120 --ignore=E121,E201,E202,E203,E226,E231,E241,E302,E303,E305,E402,E501,E701,E731,E741,F401,F541,F841,W503,W504 --statistics
)
if errorlevel 1 (
    echo [FAIL] Phase 2: Linting violations detected.
    exit /b 1
)
echo   [OK] Code style and syntax verified (0 violations).
echo.

REM --- PHASE 3: Static Guardrails and Prompt Health (Mode 7) ---
echo [PHASE 3/5] Running Static Guardrails and Path Reference Audit...
call "%~dp0python.cmd" "%~dp0evals\run_static_checks.py"
if errorlevel 1 (
    echo [FAIL] Phase 3: Static path or prompt rule check failed.
    exit /b 1
)
echo.

REM --- PHASE 4: Digital Asset and SVG/PNG Integrity Audit ---
echo [PHASE 4/5] Auditing Vector and Raster Assets...
call "%~dp0python.cmd" "%~dp0engine\verify_svg_inventory.py"
if errorlevel 1 (
    echo [FAIL] Phase 4: Asset manifest or XML check failed.
    exit /b 1
)
echo.

REM --- PHASE 5: Full Test Suite Execution ---
echo [PHASE 5/5] Executing Full Test Suite (117 Tests)...
call "%~dp0python.cmd" "%~dp0tests\run_all_tests.py" %*
if errorlevel 1 (
    echo [FAIL] Phase 5: Test suite failed.
    exit /b 1
)

echo.
echo ==============================================================================
echo   [PASS] ALL 5 CI/CD PIPELINE PHASES PASSED LOCALLY WITH ZERO ERRORS
echo ==============================================================================
exit /b 0
