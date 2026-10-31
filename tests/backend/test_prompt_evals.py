#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit Tests for Prompt Health & Adversarial Suite (evals/run_static_checks.py)
"""

import unittest

from evals.run_static_checks import (
    verify_referenced_paths,
    verify_species_blacklist,
    verify_stress_cases_schema,
    verify_taxonomy_codes,
)


class TestPromptHealthEvals(unittest.TestCase):
    """Verifies that all prompt health and static guardrail checks pass."""

    def test_stress_cases_count_and_schema(self):
        """Test for stress cases count and schema."""
        count = verify_stress_cases_schema()
        self.assertGreaterEqual(count, 25)

    def test_all_referenced_paths_exist(self):
        """Test for all referenced paths exist."""
        count = verify_referenced_paths()
        self.assertGreater(count, 50)

    def test_species_blacklist_grounding(self):
        """Test for species blacklist grounding."""
        count = verify_species_blacklist()
        self.assertGreaterEqual(count, 20)

    def test_taxonomy_codes_and_drivers(self):
        """Test for taxonomy codes and drivers."""
        count = verify_taxonomy_codes()
        self.assertGreaterEqual(count, 14)


if __name__ == "__main__":
    unittest.main()
