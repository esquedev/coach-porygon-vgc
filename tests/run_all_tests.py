#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Visual ANSI Test Suite Runner
Executes all unit, acceptance, backend, frontend, and asset tests.
Provides colorized output:
- [PASS] in bright green
- [FAIL] in bright red
- [ERROR] in bright red
- [SKIP] in bright yellow
Includes per-test execution duration and comprehensive summary report.
"""

import os
from pathlib import Path
import sys
import time
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "engine"))
sys.path.insert(0, str(REPO_ROOT / "scouts"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Enable ANSI escape codes in Windows Command Prompt and PowerShell
if os.name == "nt":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004)
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass
    os.system("")

# ANSI Color Palette
CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_GREEN = "\033[1;32m"
CLR_RED = "\033[1;31m"
CLR_YELLOW = "\033[1;33m"
CLR_CYAN = "\033[1;36m"
CLR_MAGENTA = "\033[1;35m"
CLR_GRAY = "\033[90m"
CLR_WHITE = "\033[1;37m"


class VisualColoredTestResult(unittest.TestResult):
    """Custom TestResult providing real-time colorized visual feedback."""

    def __init__(self, stream=None, descriptions=None, verbosity=None):
        super().__init__()
        self.stream = stream or sys.stdout
        self.verbosity = verbosity or 2
        self.successes = []
        self._test_start = 0.0

    def startTest(self, test):
        """Record test start timestamp."""
        super().startTest(test)
        self._test_start = time.perf_counter()

    def addSuccess(self, test):
        """Record test success with elapsed execution time in green."""
        super().addSuccess(test)
        duration_ms = (time.perf_counter() - self._test_start) * 1000.0
        self.successes.append((test, duration_ms))
        test_id = test.id().split(".")
        method_name = test_id[-1]
        class_name = ".".join(test_id[-3:-1]) if len(test_id) >= 3 else test_id[0]
        self.stream.write(
            f"  {CLR_GREEN}[PASS]{CLR_RESET}  {CLR_WHITE}{method_name:<52}{CLR_RESET} "
            f"{CLR_GRAY}({class_name}) [{duration_ms:5.1f}ms]{CLR_RESET}\n"
        )
        self.stream.flush()

    def addFailure(self, test, err):
        """Record test failure with red formatted diagnostic output."""
        super().addFailure(test, err)
        duration_ms = (time.perf_counter() - self._test_start) * 1000.0
        test_id = test.id().split(".")
        method_name = test_id[-1]
        class_name = ".".join(test_id[-3:-1]) if len(test_id) >= 3 else test_id[0]
        self.stream.write(
            f"  {CLR_RED}[FAIL]{CLR_RESET}  {CLR_BOLD}{CLR_RED}{method_name:<52}{CLR_RESET} "
            f"{CLR_GRAY}({class_name}) [{duration_ms:5.1f}ms]{CLR_RESET}\n"
        )
        self.stream.flush()

    def addError(self, test, err):
        """Record test error with red formatted diagnostic output."""
        super().addError(test, err)
        duration_ms = (time.perf_counter() - self._test_start) * 1000.0
        test_id = test.id().split(".")
        method_name = test_id[-1]
        class_name = ".".join(test_id[-3:-1]) if len(test_id) >= 3 else test_id[0]
        self.stream.write(
            f"  {CLR_RED}[ERROR]{CLR_RESET} {CLR_BOLD}{CLR_RED}{method_name:<52}{CLR_RESET} "
            f"{CLR_GRAY}({class_name}) [{duration_ms:5.1f}ms]{CLR_RESET}\n"
        )
        self.stream.flush()

    def addSkip(self, test, reason):
        """Record test warning or skip in yellow with explanation reason."""
        super().addSkip(test, reason)
        test_id = test.id().split(".")
        method_name = test_id[-1]
        class_name = ".".join(test_id[-3:-1]) if len(test_id) >= 3 else test_id[0]
        self.stream.write(
            f"  {CLR_YELLOW}[WARN/SKIP]{CLR_RESET} {CLR_WHITE}{method_name:<48}{CLR_RESET} "
            f"{CLR_GRAY}({class_name}){CLR_RESET} {CLR_YELLOW}Reason: {reason}{CLR_RESET}\n"
        )
        self.stream.flush()


def run_tests():
    """Discover and execute full test suite displaying visual ANSI report."""
    start_time = time.perf_counter()

    print(f"\n{CLR_CYAN}{'=' * 78}{CLR_RESET}")
    print(f"{CLR_BOLD}{CLR_CYAN}  COACH PORYGON VGC — REGULATION M-C VERIFICATION & TEST RUNNER{CLR_RESET}")
    print(f"{CLR_CYAN}{'=' * 78}{CLR_RESET}\n")

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(REPO_ROOT / "tests"), pattern="test_*.py")

    result = VisualColoredTestResult()
    suite.run(result)

    total_duration = time.perf_counter() - start_time
    total_tests = result.testsRun
    total_passed = len(result.successes)
    total_failed = len(result.failures)
    total_errors = len(result.errors)
    total_skipped = len(result.skipped)

    # Print Tracebacks if any
    if result.failures:
        print(f"\n{CLR_RED}{'=' * 78}{CLR_RESET}")
        print(f"{CLR_BOLD}{CLR_RED}  DETAILED FAILURE BREAKDOWN ({total_failed}):{CLR_RESET}")
        print(f"{CLR_RED}{'=' * 78}{CLR_RESET}")
        for test, err in result.failures:
            print(f"\n{CLR_BOLD}{CLR_RED}FAIL: {test.id()}{CLR_RESET}")
            print(f"{CLR_RED}{err}{CLR_RESET}")

    if result.errors:
        print(f"\n{CLR_RED}{'=' * 78}{CLR_RESET}")
        print(f"{CLR_BOLD}{CLR_RED}  DETAILED ERROR BREAKDOWN ({total_errors}):{CLR_RESET}")
        print(f"{CLR_RED}{'=' * 78}{CLR_RESET}")
        for test, err in result.errors:
            print(f"\n{CLR_BOLD}{CLR_RED}ERROR: {test.id()}{CLR_RESET}")
            print(f"{CLR_RED}{err}{CLR_RESET}")

    # Summary Card
    print(f"\n{CLR_CYAN}{'-' * 78}{CLR_RESET}")
    print(f"{CLR_BOLD}TEST SUITE EXECUTION SUMMARY:{CLR_RESET}")
    print(f"  Total Executed: {CLR_BOLD}{total_tests}{CLR_RESET} tests")
    print(f"  Passed:         {CLR_GREEN}{total_passed} [OK]{CLR_RESET}")
    if total_failed > 0:
        print(f"  Failed:         {CLR_RED}{total_failed} [FAIL]{CLR_RESET}")
    else:
        print(f"  Failed:         {CLR_GRAY}0{CLR_RESET}")

    if total_errors > 0:
        print(f"  Errors:         {CLR_RED}{total_errors} [ERR]{CLR_RESET}")
    else:
        print(f"  Errors:         {CLR_GRAY}0{CLR_RESET}")

    if total_skipped > 0:
        print(f"  Warnings/Skips: {CLR_YELLOW}{total_skipped} [SKIP]{CLR_RESET}")
    else:
        print(f"  Warnings/Skips: {CLR_GRAY}0{CLR_RESET}")

    print(f"  Execution Time: {CLR_WHITE}{total_duration:.2f}s{CLR_RESET}")
    print(f"{CLR_CYAN}{'=' * 78}{CLR_RESET}")

    if result.wasSuccessful():
        print(f"{CLR_BOLD}{CLR_GREEN}✔ ALL SYSTEMS NOMINAL — 100% OF TESTS PASSED SUCCESSFULLY!{CLR_RESET}")
        print(f"{CLR_CYAN}{'=' * 78}{CLR_RESET}\n")
        return True
    else:
        print(f"{CLR_BOLD}{CLR_RED}✘ TEST SUITE FAILED — PLEASE REVIEW DIAGNOSTICS ABOVE{CLR_RESET}")
        print(f"{CLR_CYAN}{'=' * 78}{CLR_RESET}\n")
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
