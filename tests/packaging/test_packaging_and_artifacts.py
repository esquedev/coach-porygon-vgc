#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Packaging & Build Artifacts Validation Tests
Validates:
1. pyproject.toml PEP 517 / 621 metadata, build-system, dependencies, and package-data rules.
2. Compiled Command Center HTML release asset footprint and integrity.
3. Vector SVG Manifest cryptographic SHA-256 digests consistency.
4. GitHub Actions workflow automation definitions (CI/CD, CodeQL, and Automated Release).
"""

import hashlib
import json
from pathlib import Path
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestPackagingAndArtifacts(unittest.TestCase):
    """Verifies repository build artifacts, packaging metadata, and release automation."""

    def test_pyproject_metadata_and_pep621_compliance(self):
        """Validate pyproject.toml contains valid PEP 621 metadata and build configuration."""
        pyproject_path = REPO_ROOT / "pyproject.toml"
        self.assertTrue(pyproject_path.exists(), "pyproject.toml is missing")

        if tomllib is not None:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
        else:
            # Fallback for Python < 3.11 when neither tomllib nor tomli is present
            raw_text = pyproject_path.read_text(encoding="utf-8")
            data = {
                "build-system": {
                    "build-backend": "setuptools.build_meta" if "build-backend = \"setuptools.build_meta\"" in raw_text else ""
                },
                "project": {
                    "name": "coach-porygon-vgc" if 'name = "coach-porygon-vgc"' in raw_text else "",
                    "version": "1.0.0" if 'version = "1.0.0"' in raw_text else "",
                    "requires-python": ">=3.10" if "requires-python" in raw_text else "",
                    "scripts": {"coach-porygon": "engine.ui_server:main"} if "coach-porygon" in raw_text else {},
                    "optional-dependencies": {
                        "dev": ["build", "twine"] if ("build>=" in raw_text and "twine>=" in raw_text) else []
                    }
                }
            }

        # Build system
        self.assertIn("build-system", data)
        self.assertEqual(data["build-system"]["build-backend"], "setuptools.build_meta")

        # Project metadata
        project = data.get("project", {})
        self.assertEqual(project.get("name"), "coach-porygon-vgc")
        self.assertEqual(project.get("version"), "1.0.0")
        self.assertIn("requires-python", project)
        self.assertIn("scripts", project)
        self.assertIn("coach-porygon", project["scripts"])

        # Dev dependencies include build and twine
        dev_deps = project.get("optional-dependencies", {}).get("dev", [])
        self.assertTrue(any(d.startswith("build") for d in dev_deps), "Missing build in dev dependencies")
        self.assertTrue(any(d.startswith("twine") for d in dev_deps), "Missing twine in dev dependencies")

    def test_command_center_html_asset_integrity(self):
        """Validate compiled standalone Command Center HTML exists, is non-empty, and exceeds 1 MB."""
        html_path = REPO_ROOT / "assets" / "command_center.html"
        self.assertTrue(html_path.exists(), "assets/command_center.html is missing")
        file_size = html_path.stat().st_size
        self.assertGreater(file_size, 1_000_000, f"command_center.html footprint unexpectedly small: {file_size} bytes")

    def test_svg_manifest_cryptographic_digests_sample(self):
        """Validate assets/svg_manifest.json contains accurate SHA-256 digests matching disk files."""
        manifest_path = REPO_ROOT / "assets" / "svg_manifest.json"
        self.assertTrue(manifest_path.exists(), "assets/svg_manifest.json is missing")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        digests = manifest.get("sha256_digests", {})
        self.assertGreaterEqual(len(digests), 539)

        # Sample verification of first 10 items
        for rel_path_str, expected_hash in list(digests.items())[:10]:
            file_path = REPO_ROOT / rel_path_str
            self.assertTrue(file_path.exists(), f"File referenced in manifest not found: {file_path}")
            computed_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            self.assertEqual(computed_hash, expected_hash, f"SHA-256 hash mismatch for {rel_path_str}")

    def test_github_workflows_configuration(self):
        """Validate presence and essential targets of CI, CodeQL, and Release workflows."""
        workflows_dir = REPO_ROOT / ".github" / "workflows"
        self.assertTrue(workflows_dir.exists(), ".github/workflows directory is missing")

        # CI workflow
        ci_yml = (workflows_dir / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("validate-build-artifacts", ci_yml)
        self.assertIn("python -m build", ci_yml)
        self.assertIn("twine check", ci_yml)

        # CodeQL workflow
        codeql_yml = (workflows_dir / "codeql.yml").read_text(encoding="utf-8")
        self.assertIn("CodeQL Analysis", codeql_yml)
        self.assertIn("github/codeql-action/init@v3", codeql_yml)

        # Release workflow
        release_yml = (workflows_dir / "release.yml").read_text(encoding="utf-8")
        self.assertIn("Automated Release", release_yml)
        self.assertIn("softprops/action-gh-release@v2", release_yml)
        self.assertIn("tags:", release_yml)


if __name__ == "__main__":
    unittest.main()
