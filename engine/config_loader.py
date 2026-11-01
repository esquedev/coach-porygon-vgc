#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Resilient Configuration Loader
Supports standard JSON, YAML, and optional HOCON (via pyhocon) if available.
"""

import json
from pathlib import Path
from typing import Any, Dict

# Attempt optional pyhocon import
try:
    from pyhocon import ConfigFactory  # type: ignore
    HAS_PYHOCON = True
except ImportError:
    ConfigFactory = None
    HAS_PYHOCON = False


def load_config(file_path: Path) -> Dict[str, Any]:
    """
    Loads configuration from JSON, HOCON (.conf), or YAML.
    Gracefully falls back to standard JSON parsing if pyhocon is unavailable.
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Configuration file not found: {p}")

    ext = p.suffix.lower()

    if ext in (".conf", ".hocon") and HAS_PYHOCON:
        config = ConfigFactory.parse_file(str(p))
        return dict(config)

    # Standard JSON / text fallback
    content = p.read_text(encoding="utf-8")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # If it's a simple key: value structure
        res = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                res[k.strip()] = v.strip().strip('"').strip("'")
        return res
