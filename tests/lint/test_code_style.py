# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Linting & Code Style Automated Test Suite
Verifies:
1. Syntax validity: All repository Python files parse and compile without errors.
2. Docstring coverage: 100% of public classes and functions have PEP 257 docstrings.
3. PEP 8 compliance: Validated using pycodestyle engine across core modules.
4. Markdown documentation integrity: Core documentation files exist and are well-formed.
"""

import ast
import os
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestCodeStyleAndLinting(unittest.TestCase):
    """Automated linting and style validation suite."""

    def setUp(self):
        """Discover all project Python source files excluding virtualenvs and temporary scratch files."""
        self.dirs = ["engine", "scouts", "evals", "tests"]
        self.py_files = []
        for d in self.dirs:
            p_dir = REPO_ROOT / d
            if p_dir.exists():
                self.py_files.extend(sorted(p_dir.glob("**/*.py")))

    def test_all_python_files_compile_cleanly(self):
        """Ensure all project Python files compile with zero syntax errors."""
        syntax_errors = []
        for py_path in self.py_files:
            try:
                code = py_path.read_text(encoding="utf-8")
                compile(code, str(py_path), "exec")
            except Exception as e:
                syntax_errors.append((str(py_path), str(e)))

        self.assertEqual(syntax_errors, [], f"Syntax compilation errors found: {syntax_errors}")

    def test_complete_docstring_coverage_across_project(self):
        """Ensure 100% of public classes and functions possess PEP 257 docstrings."""
        missing = []
        for py_path in self.py_files:
            try:
                tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
            except Exception as e:
                self.fail(f"Could not parse {py_path}: {e}")

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    # Allow internal dunder methods
                    if node.name.startswith("__") and node.name.endswith("__"):
                        continue
                    doc = ast.get_docstring(node)
                    if not doc or not doc.strip():
                        rel_path = py_path.relative_to(REPO_ROOT)
                        missing.append(f"{rel_path}:{node.lineno} in {node.name}()")

        self.assertEqual(missing, [], f"Functions/classes missing docstrings: {missing}")

    def test_pep8_compliance_via_pycodestyle(self):
        """Ensure core engine modules comply with PEP 8 standards using pycodestyle."""
        try:
            import pycodestyle
        except ImportError:
            self.skipTest("pycodestyle is not installed in the active environment.")

        # Key core modules to enforce strict PEP 8 compliance
        core_files = [
            str(REPO_ROOT / "engine" / "sp_calculator.py"),
            str(REPO_ROOT / "engine" / "config_loader.py"),
            str(REPO_ROOT / "engine" / "repositories.py"),
            str(REPO_ROOT / "scouts" / "pokedex_resolver.py"),
            str(REPO_ROOT / "evals" / "run_static_checks.py"),
            str(REPO_ROOT / "tests" / "run_all_tests.py"),
        ]

        style_guide = pycodestyle.StyleGuide(
            quiet=True,
            ignore=[
                "E501",  # Line length (handled contextually for data tables and regex)
                "W503",  # Line break before binary operator (standard in modern PEP 8 / black)
                "E402",  # Module level import not at top of file (sys.path configuration)
            ],
        )

        report = style_guide.check_files(core_files)
        self.assertEqual(
            report.total_errors,
            0,
            f"PEP 8 violations found across core modules ({report.total_errors} errors).",
        )

    def test_core_markdown_documentation_integrity(self):
        """Ensure all primary Markdown documentation files exist and contain substantive content."""
        required_md_files = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "CONTRIBUTING.md",
            REPO_ROOT / "LEGAL.md",
            REPO_ROOT / "AGENTS.md",
            REPO_ROOT / ".agents" / "rules" / "engine_rules.md",
            REPO_ROOT / ".agents" / "rules" / "mistake_taxonomy.md",
            REPO_ROOT / ".agents" / "rules" / "system_guardrails.md",
        ]

        for md_file in required_md_files:
            self.assertTrue(md_file.exists(), f"Mandatory documentation file missing: {md_file.name}")
            content = md_file.read_text(encoding="utf-8")
            self.assertGreater(len(content.strip()), 200, f"{md_file.name} is unexpectedly short or empty.")


if __name__ == "__main__":
    unittest.main()
