# -*- coding: utf-8 -*-
"""Coach Porygon VGC — Shared Test Constants & Hermetic Fixture Paths."""

from pathlib import Path

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
TEST_DATA_DIR = REPO_ROOT / "tests" / "data"
