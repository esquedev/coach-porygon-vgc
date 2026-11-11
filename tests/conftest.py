# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Pytest Configuration & Global Session Fixtures
"""

from __future__ import annotations

import pytest
from engine.vgc_tensor_core.schema_and_tables import (
    BilinearLookupTables,
    build_bilinear_lookup_tables,
)


@pytest.fixture(scope="session")
def tables() -> BilinearLookupTables:
    """Provides a cached session-scoped BilinearLookupTables instance on CPU."""
    return build_bilinear_lookup_tables(device="cpu")

