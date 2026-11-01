# -*- coding: utf-8 -*-
"""Coach Porygon VGC — Unit Tests for Workspace Garbage Collector.

Validates:
1. sanitize_scratch_directory: Removes non-gitkeep scratch files while preserving .gitkeep.
2. sanitize_coverage_and_test_artifacts: Cleans .coverage databases and .temp items.
3. sanitize_build_artifacts: Removes build, dist, and egg-info directories.
4. run_git_maintenance: Dry-run execution returns True without executing git.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine.clean_workspace import (
    run_git_maintenance,
    sanitize_build_artifacts,
    sanitize_coverage_and_test_artifacts,
    sanitize_pycache_directories,
    sanitize_scratch_directory,
    sanitize_temp_files,
)


class TestCleanWorkspace(unittest.TestCase):
    """Unit tests for the workspace sanitization and garbage collection engine."""

    def setUp(self):
        """Create a temporary sandbox directory for file creation tests."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sandbox = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up the temporary sandbox."""
        self.temp_dir.cleanup()

    def test_sanitize_scratch_preserves_gitkeep(self):
        """Ensure scratch sanitization preserves .gitkeep while removing other files."""
        scratch = self.sandbox / "scratch"
        scratch.mkdir()
        gitkeep = scratch / ".gitkeep"
        gitkeep.touch()
        temp_file = scratch / "temp_calc.py"
        temp_file.write_text("print('test')", encoding="utf-8")

        with patch("engine.clean_workspace.REPO_ROOT", self.sandbox):
            removed = sanitize_scratch_directory(dry_run=False)

        self.assertEqual(removed, 1)
        self.assertTrue(gitkeep.exists())
        self.assertFalse(temp_file.exists())

    def test_sanitize_dry_run_does_not_delete(self):
        """Ensure dry-run counts items without unlinking."""
        scratch = self.sandbox / "scratch"
        scratch.mkdir()
        dummy = scratch / "dummy.json"
        dummy.write_text("{}", encoding="utf-8")

        with patch("engine.clean_workspace.REPO_ROOT", self.sandbox):
            removed = sanitize_scratch_directory(dry_run=True)

        self.assertEqual(removed, 1)
        self.assertTrue(dummy.exists())

    def test_sanitize_coverage_and_temp(self):
        """Ensure .coverage files and .temp contents are wiped."""
        cov = self.sandbox / ".coverage"
        cov.touch()
        temp_p = self.sandbox / ".temp"
        temp_p.mkdir()
        temp_keep = temp_p / ".gitkeep"
        temp_keep.touch()
        temp_f = temp_p / "cached_eval.json"
        temp_f.touch()

        with patch("engine.clean_workspace.REPO_ROOT", self.sandbox):
            removed = sanitize_coverage_and_test_artifacts(dry_run=False)

        self.assertGreaterEqual(removed, 2)
        self.assertFalse(cov.exists())
        self.assertTrue(temp_keep.exists())
        self.assertFalse(temp_f.exists())

    def test_sanitize_build_artifacts(self):
        """Ensure build, dist, and egg-info directories are removed."""
        build_d = self.sandbox / "build"
        build_d.mkdir()
        dist_d = self.sandbox / "dist"
        dist_d.mkdir()
        egg_d = self.sandbox / "sample.egg-info"
        egg_d.mkdir()

        with patch("engine.clean_workspace.REPO_ROOT", self.sandbox):
            removed = sanitize_build_artifacts(dry_run=False)

        self.assertEqual(removed, 3)
        self.assertFalse(build_d.exists())
        self.assertFalse(dist_d.exists())
        self.assertFalse(egg_d.exists())

    def test_run_git_maintenance_dry_run(self):
        """Ensure git maintenance dry-run returns True."""
        result = run_git_maintenance(dry_run=True)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
