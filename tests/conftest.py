# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Pytest Configuration & Global Session Fixtures
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
for _p in (str(REPO_ROOT), str(SRC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
from engine.vgc_tensor_core.schema_and_tables import (
    BilinearLookupTables,
    build_bilinear_lookup_tables,
)


@pytest.fixture(scope="session")
def tables() -> BilinearLookupTables:
    """Provides a cached session-scoped BilinearLookupTables instance on CPU."""
    return build_bilinear_lookup_tables(device="cpu")

