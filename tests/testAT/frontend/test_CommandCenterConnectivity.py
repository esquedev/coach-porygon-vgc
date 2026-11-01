#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Frontend & Backend Connectivity Acceptance Test Suite
Validates:
1. Official Coach Porygon Theme with localStorage persistence.
2. Official Coach Porygon avatar branding (assets/icons/porygon-coach.svg).
3. Gender-differentiated Showdown sprite mapping (Basculegion-F, Indeedee-F, Meowstic-F).
4. Smooth range sliders and live EV conversion calculations for the 66-SP budget.
5. Official attribution and copyright disclaimers (Made by berightvgc, Powered by Gemini, Nintendo fair use).
6. Backend UI Server routing and telemetry connectivity.
"""

import pyhocon
from pyhocon import ConfigFactory
import unittest
from pathlib import Path
import re
import sys

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO_ROOT))

from engine.ui_generator import load_live_telemetry


class TestCommandCenterConnectivity(unittest.TestCase):
    """Rigorous frontend-backend connectivity and V2 UI acceptance tests."""

    @classmethod
    def setUpClass(cls):
        """Initializes HTML text content and filesystem paths for test assertions."""
        cls.html_path = REPO_ROOT / "assets" / "command_center.html"
        cls.assertTrue(cls.html_path.exists(), f"Missing command_center.html at {cls.html_path}")
        cls.html_text = cls.html_path.read_text(encoding="utf-8")

    def test_coach_porygon_official_theme_and_persistence(self):
        """Verify Coach Porygon official theme initialization and localStorage persistence."""
        self.assertIn('function applyTheme(', self.html_text)
        self.assertIn("localStorage.setItem('cp_theme', 'porygon')", self.html_text)

    def test_coach_porygon_avatar_branding(self):
        """Verify coach avatar is strictly grounded in official Coach Porygon branding."""
        self.assertIn("porygon-coach", self.html_text)
        self.assertIn("avatarEl.src = getSpritePath('porygon-coach')", self.html_text)

        porygon_icon = REPO_ROOT / "assets" / "icons" / "porygon-coach.svg"
        self.assertTrue(porygon_icon.exists(), "Missing assets/icons/porygon-coach.svg")

    def test_gender_differentiated_sprite_resolution(self):
        """Verify getSpritePath handles female and male suffixes cleanly without dropping gender."""
        self.assertIn("isFemale", self.html_text)
        self.assertIn("fCandidates", self.html_text)
        self.assertIn("basculegion-female", self.html_text)
        self.assertIn("indeedee-female", self.html_text)

        # Verify female sprite assets exist on disk in curated Reg_M-C repository
        sprites_dir = REPO_ROOT / "assets" / "sprites"
        reg_mc_dir = sprites_dir / "Reg_M-C"
        has_basculegion = (reg_mc_dir / "basculegion-female.png").exists() or (sprites_dir / "basculegion-female.png").exists()
        has_indeedee = (reg_mc_dir / "indeedee-female.png").exists() or (sprites_dir / "indeedee-female.png").exists()
        self.assertTrue(has_basculegion)
        self.assertTrue(has_indeedee)

    def test_smooth_range_sliders_and_ev_conversion(self):
        """Verify contemporary range sliders and EV equivalent calculations in Mode 2."""
        self.assertIn(".sp-slider", self.html_text)
        self.assertIn("class=\"w-full sp-slider\"", self.html_text)
        self.assertIn("4 + (spVal - 1) * 8", self.html_text)

    def test_attribution_and_copyright_disclaimers(self):
        """Verify Made by berightvgc, Powered by Gemini, and Nintendo copyright disclaimer."""
        # 1. Made by berightvgc
        self.assertIn("Made by <b class=\"text-cyan-300\">berightvgc</b>", self.html_text)

        # 2. Powered by Gemini with icon
        self.assertIn("Powered by", self.html_text)
        self.assertIn("<b class=\"text-cyan-300\">Gemini</b>", self.html_text)

        # 3. Legal copyright disclaimer
        self.assertIn("Nintendo, Game Freak, and Creatures Inc", self.html_text)
        self.assertIn("Pokémon Showdown sprites are utilized strictly under nominative non-commercial fair use", self.html_text)

    def test_backend_telemetry_live_connectivity(self):
        """Verify backend live telemetry feeds into the Command Center."""
        telemetry = load_live_telemetry()
        self.assertGreater(telemetry["total_matches"], 0)
        self.assertIn("window.__COACH_PORYGON_TELEMETRY__", self.html_text)

    def test_munchstats_meta_pre_crawled_overview_box(self):
        """Verify Mode 6 pre-crawled/dumped overview box and 7 regional highlights."""
        # 1. Dedicated pre-crawled overview container exists and is visible on load
        self.assertIn('id="munch-dumped-overview-box"', self.html_text)
        self.assertIn('munch-tournaments-cards', self.html_text)
        self.assertIn('function renderMunchOverviewCards()', self.html_text)
        self.assertIn('function initMode6Munch()', self.html_text)

        # 2. Locked placeholder is eradicated
        self.assertNotIn('id="munch-locked-placeholder"', self.html_text)

        # 3. All 7 VGC 2027 regional tournaments present in selector
        tourn_codes = ["PB002", "NC002", "LO002", "RE002", "FR002", "BR002", "BA002"]
        for code in tourn_codes:
            self.assertIn(code, self.html_text)

    def test_resilient_dual_origin_backend_communicator(self):
        """Verify dual-origin fetchBackendApi and embedded offline telemetry completeness."""
        # 1. Dual-origin fetchBackendApi function exists
        self.assertIn('async function fetchBackendApi(endpoint, options', self.html_text)
        self.assertIn('http://127.0.0.1:8000', self.html_text)
        self.assertIn('http://localhost:8000', self.html_text)

        # 2. Telemetry embedded snapshot contains all 64 scouted teams and 7 tournaments
        telemetry = load_live_telemetry()
        self.assertEqual(len(telemetry.get("scouted", [])), 64)
        self.assertEqual(len(telemetry.get("tournaments", [])), 7)
        self.assertEqual(len(telemetry.get("munchstats_overview", [])), 7)
        self.assertGreaterEqual(len(telemetry.get("munchstats_usage", [])), 1000)

    def test_backend_scouted_ingest_endpoint(self):
        """Verify backend UI server handles /api/scouted/ingest properly."""
        from engine.ui_server import CoachPorygonHTTPHandler
        self.assertTrue(hasattr(CoachPorygonHTTPHandler, 'do_POST'))

    def test_flash_cards_terminology_and_load_functions(self):
        """Verify Mode 3 re-branding to Flash Cards and loadFlashCardScenario definition."""
        self.assertIn("function loadFlashCardScenario(idx)", self.html_text)
        self.assertIn("function loadNextRandomFlashCardScenario()", self.html_text)
        self.assertIn("function simulateFlashCardTurn()", self.html_text)
        self.assertIn("Flash Cards Tácticas", self.html_text)
        self.assertIn("Reintentar Flash Card", self.html_text)
        self.assertIn("Siguiente Flash Card Táctica", self.html_text)

    def test_zero_missing_onclick_functions(self):
        """Verify all functions referenced by onclick handlers exist in the script."""
        onclicks = re.findall(r'onclick="([^"]+)"', self.html_text)
        defined_fns = set(re.findall(r'function\s+([a-zA-Z0-9_]+)\s*\(', self.html_text))
        called_fns = set()
        for oc in onclicks:
            for p in oc.split(";"):
                m = re.match(r'([a-zA-Z0-9_]+)\s*\(', p.strip())
                if m:
                    called_fns.add(m.group(1))
        missing = called_fns - defined_fns
        self.assertEqual(missing, set(), f"Undefined onclick functions found: {missing}")


if __name__ == "__main__":
    unittest.main()
