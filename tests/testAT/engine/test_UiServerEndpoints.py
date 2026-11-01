#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Acceptance Tests for UI Server Flask Endpoints
"""

from pathlib import Path
import unittest
import pyhocon
from pyhocon import ConfigFactory

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
from engine.ui_server import create_app
from tests.test_constants import TEST_DATA_DIR

class TestUiServerEndpoints(unittest.TestCase):
    """Rigorous unit tests for the Flask web application in ui_server.py."""

    @classmethod
    def setUpClass(cls):
        """Create test client from application factory."""
        cls.flask_app = create_app(data_dir=TEST_DATA_DIR)
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
        self.assertIn(resp_shiny.content_type, ["image/png", "image/svg+xml; charset=utf-8"])
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

    def test_flask_gpu_status_and_tactical_endpoints(self):
        """Validate /api/status, /api/audit, /api/gpu-matrix, /api/report/<id>, and /api/benchmark."""
        resp_status = self.client.get("/api/status")
        self.assertEqual(resp_status.status_code, 200)
        status_json = resp_status.get_json()
        self.assertEqual(status_json.get("status"), "ONLINE")
        self.assertIn("cuda_available", status_json)

        resp_audit = self.client.post("/api/audit", json={"persist": False})
        self.assertEqual(resp_audit.status_code, 200)
        audit_json = resp_audit.get_json()
        self.assertIn("payoff_matrix", audit_json)
        self.assertIn("uncertainty_profile", audit_json)
        self.assertIn("all_turns_analysis", audit_json)

        resp_mat = self.client.post("/api/gpu-matrix", json={"turn": 3})
        self.assertEqual(resp_mat.status_code, 200)
        mat_json = resp_mat.get_json()
        self.assertEqual(mat_json.get("turn_number"), 3)
        self.assertEqual(len(mat_json.get("payoff_matrix", [])), 5)

        resp_rep = self.client.get("/api/report/AUD-DEMO")
        self.assertEqual(resp_rep.status_code, 200)
        self.assertIn("text/html", resp_rep.content_type)

        resp_bench = self.client.post("/api/benchmark", json={"batch_size": 4})
        self.assertEqual(resp_bench.status_code, 200)
        bench_json = resp_bench.get_json()
        self.assertEqual(bench_json.get("status"), "OK")
        self.assertIn("gpu_batch_benchmark", bench_json)


if __name__ == "__main__":
    unittest.main()
