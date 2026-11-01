#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Security Hardening & Penetration Testing Test Suite
Validates:
1. SEC-01 & SEC-02: Strict CORS policy restricting external origin exfiltration.
2. SEC-03: Sensitive path shielding blocking .git, .github, and trainer_profile.json (403 Forbidden).
3. SEC-04: SSRF domain whitelist, HTTPS enforcement, and LFI path traversal guards.
4. SEC-05: SVG vector asset anti-XSS and active script eradication.
5. SEC-06: Unbounded payload buffer DoS protection (413 Payload Too Large).
6. SEC-07: Thread-safe atomic CSV append operations under concurrent contention.
"""

import io
from pathlib import Path
import tempfile
import threading
import pyhocon
from pyhocon import ConfigFactory
import unittest

from engine.ui_server import CoachPorygonHTTPHandler, validate_scraping_target
from engine.verify_png_inventory import DANGEROUS_SVG_PATTERNS

from engine.telemetry import append_csv_row

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())


class MockSocket:
    """In-memory mock socket simulating HTTP client requests without network I/O."""

    def __init__(self, request_bytes: bytes):
        """Initialize mock socket buffers."""
        self.rfile = io.BytesIO(request_bytes)
        self.wfile = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        """Return read or write memory stream for HTTP handler."""
        if "r" in mode:
            return self.rfile
        return self.wfile

    def sendall(self, data: bytes):
        """Capture output bytes sent by HTTP handler."""
        self.wfile.write(data)


class MockServer:
    """Mock HTTP server context for handler initialization."""

    def __init__(self):
        """Initialize empty mock server instance."""
        pass


def execute_mock_request(raw_request: str) -> str:
    """Helper to dispatch simulated raw HTTP request string through CoachPorygonHTTPHandler."""
    sock = MockSocket(raw_request.encode("utf-8"))
    CoachPorygonHTTPHandler(sock, ("127.0.0.1", 12345), MockServer())
    return sock.wfile.getvalue().decode("utf-8", errors="replace")


class TestSecurityHardening(unittest.TestCase):
    """Verifies defensive security controls and vulnerability remediations."""

    def test_cors_rejects_external_origin(self):
        """Validate that external origins do not receive permissive Access-Control-Allow-Origin headers."""
        req = (
            "GET /api/telemetry HTTP/1.1\r\n"
            "Host: localhost:8000\r\n"
            "Origin: https://malicious-attacker.com\r\n"
            "\r\n"
        )
        resp = execute_mock_request(req)
        self.assertNotIn("Access-Control-Allow-Origin: https://malicious-attacker.com", resp)
        self.assertNotIn("Access-Control-Allow-Origin: *", resp)

    def test_cors_allows_localhost_and_file_origins(self):
        """Validate that local development and file:// (null) origins are allowed."""
        # Localhost
        req_local = (
            "GET /api/telemetry HTTP/1.1\r\n"
            "Host: localhost:8000\r\n"
            "Origin: http://localhost:8000\r\n"
            "\r\n"
        )
        resp_local = execute_mock_request(req_local)
        self.assertIn("Access-Control-Allow-Origin: http://localhost:8000", resp_local)

        # Local file:// origin
        req_file = (
            "GET /api/telemetry HTTP/1.1\r\n"
            "Host: localhost:8000\r\n"
            "Origin: null\r\n"
            "\r\n"
        )
        resp_file = execute_mock_request(req_file)
        self.assertIn("Access-Control-Allow-Origin: *", resp_file)

    def test_sensitive_paths_and_dotfiles_blocked_with_403(self):
        """Validate that attempts to read .git, .github, and trainer profile return HTTP 403 Forbidden."""
        blocked_paths = [
            "/.git/config",
            "/.github/workflows/ci.yml",
            "/.agents/rules/engine_rules.md",
            "/data/trainer_profile.json",
            "/trainer_profile.json",
        ]
        for path in blocked_paths:
            req = f"GET {path} HTTP/1.1\r\nHost: localhost:8000\r\n\r\n"
            resp = execute_mock_request(req)
            self.assertIn("403", resp.splitlines()[0], f"Path {path} was not blocked with HTTP 403")

    def test_unbounded_payload_dos_defense(self):
        """Validate that POST requests exceeding 5 MB are rejected with HTTP 413 Payload Too Large."""
        oversized_len = 6 * 1024 * 1024  # 6 MB
        req = (
            "POST /api/telemetry/ingest HTTP/1.1\r\n"
            "Host: localhost:8000\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {oversized_len}\r\n"
            "\r\n"
        )
        resp = execute_mock_request(req)
        self.assertIn("413", resp.splitlines()[0])

    def test_svg_inventory_rejects_active_scripts(self):
        """Validate that all assets on disk contain zero dangerous script or event handler patterns."""
        assets_dir = REPO_ROOT / "assets"
        asset_files = list(assets_dir.rglob("*.png")) + list(assets_dir.rglob("*.svg"))
        self.assertGreaterEqual(len(asset_files), 539)

        svg_files = list(assets_dir.rglob("*.svg"))
        self.assertGreaterEqual(len(svg_files), 1)

        for svg_path in svg_files:
            content_lower = svg_path.read_text(encoding="utf-8", errors="replace").lower()
            for pattern in DANGEROUS_SVG_PATTERNS:
                self.assertNotIn(
                    pattern,
                    content_lower,
                    f"Dangerous active script pattern '{pattern}' discovered in {svg_path.name}"
                )

    def test_ssrf_and_lfi_guardrails(self):
        """Validate SSRF domain whitelist, HTTPS enforcement, and LFI path containment."""
        # 1. Valid whitelisted HTTPS targets
        valid_targets = [
            "https://www.munchstats.com/tournaments/nice-2027",
            "https://bulbapedia.bulbagarden.net/wiki/Pikachu",
            "https://www.wikidex.net/wiki/Pikachu",
            "https://www.pikalytics.com/pokedex",
            "https://victoryroad.pro/teams",
            "https://pokepast.es/sample-team",
        ]
        for url in valid_targets:
            is_url, validated = validate_scraping_target(url)
            self.assertTrue(is_url)
            self.assertEqual(validated, url)

        # 2. Insecure plain HTTP must be rejected
        with self.assertRaises(ValueError) as ctx_http:
            validate_scraping_target("http://www.munchstats.com/tournaments")
        self.assertIn("strictly use HTTPS", str(ctx_http.exception))

        # 3. Untrusted external domain must be rejected
        with self.assertRaises(ValueError) as ctx_domain:
            validate_scraping_target("https://untrusted-external-exploit.com/evil")
        self.assertIn("not in the trusted scraping whitelist", str(ctx_domain.exception))

        # 4. Private IP / cloud metadata must be rejected
        with self.assertRaises(ValueError) as ctx_ip:
            validate_scraping_target("https://169.254.169.254/latest/meta-data/")
        self.assertIn("forbidden", str(ctx_ip.exception))

        # 5. Local file path traversal escape must be rejected
        with self.assertRaises(PermissionError) as ctx_lfi:
            validate_scraping_target("../../Windows/System32/drivers/etc/hosts")
        self.assertIn("Path Traversal Shield", str(ctx_lfi.exception))

        # 6. Valid local file inside REPO_ROOT must succeed
        valid_local = REPO_ROOT / "data" / "Scouted_Teams.csv"
        is_url_local, validated_local = validate_scraping_target(str(valid_local))
        self.assertFalse(is_url_local)
        self.assertEqual(validated_local, valid_local)

    def test_thread_safe_concurrent_csv_writes(self):
        """Validate that concurrent worker threads appending rows do not cause race condition corruption."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_csv = Path(tmp_dir) / "test_concurrency.csv"
            headers = ["Thread_ID", "Sequence_Index", "Payload_Data"]
            num_threads = 10
            rows_per_thread = 5

            def worker_task(thread_idx: int):
                """Simulate worker thread appending telemetry rows concurrently."""
                for seq in range(rows_per_thread):
                    row = {
                        "Thread_ID": f"T-{thread_idx}",
                        "Sequence_Index": seq,
                        "Payload_Data": f"Safe Thread Data {thread_idx}:{seq}"
                    }
                    append_csv_row(test_csv, headers, row)

            threads = []
            for t_id in range(num_threads):
                t = threading.Thread(target=worker_task, args=(t_id,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # Read back and verify exactly num_threads * rows_per_thread rows exist
            lines = test_csv.read_text(encoding="utf-8").splitlines()
            # 1 header line + 50 data lines = 51 lines
            self.assertEqual(len(lines), 1 + (num_threads * rows_per_thread))


if __name__ == "__main__":
    unittest.main()
