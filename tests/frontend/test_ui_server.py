#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit & Acceptance Tests for UI Server & Frontend
Tests live telemetry data loader, crawl dumper, HTML template integrity,
and Flask REST API / dynamic asset endpoints.
"""

from pathlib import Path
import re
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

from engine.ui_generator import load_live_telemetry
from engine.ui_server import (
    create_app,
    execute_prompt_crawl_and_dump,
    resolve_sprite_path,
)


class TestTelemetryGenerator(unittest.TestCase):
    """Unit tests for UI telemetry generator (ui_generator.py)."""

    def test_load_live_telemetry_structure(self):
        """Test for load live telemetry structure."""
        data = load_live_telemetry()
        self.assertIsInstance(data, dict)
        self.assertIn("total_matches", data)
        self.assertIn("total_calcs", data)
        self.assertIn("teams", data)
        self.assertIn("pokedex", data)
        self.assertGreater(data["total_matches"], 0)
        self.assertGreater(data["total_calcs"], 0)
        self.assertGreater(len(data["pokedex"]), 100)

    def test_crawl_prompt_filtering(self):
        """Test for crawl prompt filtering."""
        res = execute_prompt_crawl_and_dump("Nice", export_csv=False)
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("status"), "OK")
        self.assertIn("matched_teams_count", res)
        self.assertGreater(res["matched_teams_count"], 0)


class TestFrontendHtmlIntegrity(unittest.TestCase):
    """Verifies HTML structural integrity, XSS protection, and responsive viewport."""

    def test_command_center_html_exists_and_valid(self):
        """Test for command center html exists and valid."""
        html_file = REPO_ROOT / "assets" / "command_center.html"
        self.assertTrue(html_file.exists())
        text = html_file.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", text)
        self.assertIn("<meta name=\"viewport\"", text)
        self.assertIn("Coach Porygon", text)

    def test_battle_hud_widget_exists(self):
        """Test for battle hud widget exists."""
        hud_file = REPO_ROOT / "assets" / "porygon_battle_hud_widget.html"
        self.assertTrue(hud_file.exists())
        text = hud_file.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", text)

    def test_language_switcher_mexico_usa_flags(self):
        """Verify command center features vector flags for MX and USA without ES/GB emoji text."""
        html_file = REPO_ROOT / "assets" / "command_center.html"
        self.assertTrue(html_file.exists())
        text = html_file.read_text(encoding="utf-8")

        # Must have language toggle buttons
        self.assertIn('id="lang-es-btn"', text)
        self.assertIn('id="lang-en-btn"', text)

        # Must include vector flag definitions for Mexico and USA
        self.assertIn('id="mx-clip"', text)
        self.assertIn('id="us-clip"', text)
        self.assertIn('title="Español (México)"', text)
        self.assertIn('title="English (USA)"', text)

        # Legacy emoji flags (Spain / UK) should not be present
        self.assertNotIn("🇪🇸", text)
        self.assertNotIn("🇬🇧", text)

    def test_i18n_dictionary_completeness(self):
        """Ensure all data-i18n tags in command center are present in both es and en dictionaries."""
        cc_path = REPO_ROOT / "assets" / "command_center.html"
        self.assertTrue(cc_path.exists())
        html = cc_path.read_text(encoding="utf-8")

        html_keys = set(re.findall(r'data-i18n="([^"]+)"', html))
        self.assertGreater(len(html_keys), 50, "Should have comprehensive data-i18n tags")

        es_match = re.search(r'const I18N = \{\s*es: \{([^}]+)\}', html, re.DOTALL)
        en_match = re.search(r'en: \{([^}]+)\}', html, re.DOTALL)
        self.assertIsNotNone(es_match)
        self.assertIsNotNone(en_match)

        es_keys = set(re.findall(r'([a-zA-Z0-9_]+):', es_match.group(1)))
        en_keys = set(re.findall(r'([a-zA-Z0-9_]+):', en_match.group(1)))

        missing_es = html_keys - es_keys
        missing_en = html_keys - en_keys
        self.assertEqual(len(missing_es), 0, f"Keys missing in I18N.es: {missing_es}")
        self.assertEqual(len(missing_en), 0, f"Keys missing in I18N.en: {missing_en}")

    def test_markdown_clean_math_rendering(self):
        """Ensure core markdown documentation does not contain broken math syntax in tables."""
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        contrib = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

        # In README table, $+0$ should be clean +0
        self.assertNotIn("$+0$", readme)
        self.assertNotIn("$+1$", readme)
        self.assertNotIn("$+32$", readme)

        # In CONTRIBUTING, inline LaTeX commands like \text or \left\lfloor should not be raw
        self.assertNotIn(r"$\text{EV}", contrib)
        self.assertNotIn(r"\left\lfloor", contrib)


class TestFlaskEndpoints(unittest.TestCase):
    """Rigorous unit tests for the Flask web application in ui_server.py."""

    @classmethod
    def setUpClass(cls):
        """Create test client from application factory."""
        cls.flask_app = create_app()
        cls.flask_app.config["TESTING"] = True
        cls.client = cls.flask_app.test_client()

    def test_flask_telemetry_endpoint(self):
        """Validate Flask /api/telemetry returns 200 with structured workspace telemetry."""
        resp = self.client.get("/api/telemetry")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, dict)
        self.assertIn("total_matches", data)
        self.assertIn("pokedex", data)

    def test_flask_health_endpoint(self):
        """Validate Flask /api/health reports system UP status."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "UP")

    def test_flask_dynamic_sprite_resolution(self):
        """Validate Flask /api/sprites/<species> dynamically serves PNG or SVG fallback."""
        # 1. Base species
        resp_char = self.client.get("/api/sprites/Charizard")
        self.assertEqual(resp_char.status_code, 200)
        self.assertEqual(resp_char.content_type, "image/png")
        resp_char.close()

        # 2. Mega variant
        resp_mega = self.client.get("/api/sprites/Charizard-Mega-Y")
        self.assertEqual(resp_mega.status_code, 200)
        self.assertEqual(resp_mega.content_type, "image/png")
        resp_mega.close()

        # 3. Shiny variant via query param
        resp_shiny = self.client.get("/api/sprites/Charizard-Mega-Y?shiny=true")
        self.assertEqual(resp_shiny.status_code, 200)
        self.assertEqual(resp_shiny.content_type, "image/png")
        resp_shiny.close()

        # 4. Gender differentiation
        resp_fem = self.client.get("/api/sprites/Indeedee-F")
        self.assertEqual(resp_fem.status_code, 200)
        self.assertEqual(resp_fem.content_type, "image/png")
        resp_fem.close()

        # 5. Uncatalogued species fallback to SVG battle crest
        resp_unknown = self.client.get("/api/sprites/Unknown-Custom-Species")
        self.assertEqual(resp_unknown.status_code, 200)
        self.assertIn("image/svg+xml", resp_unknown.content_type)
        resp_unknown.close()

    def test_flask_security_sensitive_paths_blocked_with_403(self):
        """Validate Flask blocks .git, .github, and trainer_profile.json with HTTP 403."""
        blocked_paths = [
            "/.git/config",
            "/.github/workflows/ci.yml",
            "/.agents/rules/engine_rules.md",
            "/data/trainer_profile.json",
            "/trainer_profile.json",
            "/assets/.git/config",
        ]
        for path in blocked_paths:
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 403, f"Path {path} was not blocked with 403 in Flask")

    def test_flask_cors_origin_policy(self):
        """Validate Flask enforces strict CORS origin filtering."""
        # Allowed: Localhost
        resp_local = self.client.get("/api/telemetry", headers={"Origin": "http://localhost:8000"})
        self.assertEqual(resp_local.headers.get("Access-Control-Allow-Origin"), "http://localhost:8000")

        # Allowed: file:// origin (null)
        resp_file = self.client.get("/api/telemetry", headers={"Origin": "null"})
        self.assertEqual(resp_file.headers.get("Access-Control-Allow-Origin"), "*")

        # Blocked: Malicious external origin
        resp_mal = self.client.get("/api/telemetry", headers={"Origin": "https://malicious-hacker.com"})
        self.assertIsNone(resp_mal.headers.get("Access-Control-Allow-Origin"))


if __name__ == "__main__":
    unittest.main()
