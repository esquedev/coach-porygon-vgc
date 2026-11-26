# -*- coding: utf-8 -*-
"""Ethical-hacking & AppSec regression suite for Coach Porygon VGC.

Actively tests the local HTTP server, replay XSS escaping, path traversal containment,
DNS-rebinding & localhost CSRF defenses, payload size caps, Windows launcher host/CWD
hardening, and GitHub Actions least-privilege / SLSA provenance invariants.
"""
from __future__ import annotations

import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import threading

import pytest

from apps.replay_coach.launcher_entry import (
    find_system_python,
    validate_bind_host_port,
)
from apps.replay_coach.protocol_parser import parse_showdown_replay
from apps.replay_coach.server import (
    MAX_JSON_BODY_BYTES,
    ReplayCoachAppState,
    make_handler,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def local_studio_server(tmp_path_factory):
    """Spin up an isolated ephemeral `CoachHTTPHandler` on `127.0.0.1:0`."""
    db_file = tmp_path_factory.mktemp("sec_db") / "ots_test.duckdb"
    state = ReplayCoachAppState(device="cpu", db_path=db_file)
    handler = make_handler(state)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, state
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_security_headers_and_legitimate_loopback(local_studio_server) -> None:
    """Legitimate loopback requests succeed and include full browser hardening headers."""
    port, _ = local_studio_server
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/api/state", headers={"Host": f"127.0.0.1:{port}"})
    resp = conn.getresponse()
    _ = resp.read()
    assert resp.status == 200
    assert resp.getheader("X-Content-Type-Options") == "nosniff"
    assert resp.getheader("X-Frame-Options") == "SAMEORIGIN"
    assert resp.getheader("Referrer-Policy") == "no-referrer"
    assert "camera=()" in (resp.getheader("Permissions-Policy") or "")
    conn.close()


def test_dns_rebinding_host_header_blocked(local_studio_server) -> None:
    """Requests carrying a non-loopback Host header (DNS rebinding) must be rejected (403)."""
    port, _ = local_studio_server
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/api/rosters", headers={"Host": "evil.attacker.example:8765"})
    resp = conn.getresponse()
    _ = resp.read()
    assert resp.status == 403
    conn.close()


def test_cross_origin_csrf_post_blocked(local_studio_server) -> None:
    """Cross-origin POST requests from external web pages must be rejected with 403."""
    port, _ = local_studio_server
    for bad_headers in (
        {"Host": f"127.0.0.1:{port}", "Origin": "https://evil.example", "Content-Type": "application/json"},
        {"Host": f"127.0.0.1:{port}", "Sec-Fetch-Site": "cross-site", "Content-Type": "application/json"},
        {"Host": f"127.0.0.1:{port}", "Referer": "https://phishing.example/trap", "Content-Type": "application/json"},
    ):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/api/lead-lab/cancel", body=b"{}", headers=bad_headers)
        resp = conn.getresponse()
        _ = resp.read()
        assert resp.status == 403, f"Expected 403 for headers={bad_headers}, got {resp.status}"
        conn.close()


def test_path_traversal_vectors_blocked(local_studio_server) -> None:
    """Static and asset endpoints must block `../`, URL-encoded `%2e%2e`, backslashes, and NUL bytes."""
    port, _ = local_studio_server
    vectors = (
        "/static/../../pyproject.toml",
        "/static/%2e%2e/%2e%2e/pyproject.toml",
        "/assets/..%2f..%2fLICENSE",
        "/assets/..\\..\\LICENSE",
        "/static/index.html%00.png",
    )
    for vec in vectors:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", vec, headers={"Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        _ = resp.read()
        assert resp.status == 404, f"Path traversal vector was not blocked: {vec} -> {resp.status}"
        conn.close()


def test_oversized_post_body_rejected_with_413(local_studio_server) -> None:
    """Declared Content-Length above MAX_JSON_BODY_BYTES must return 413 without allocating."""
    port, _ = local_studio_server
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", "/api/lead-lab/cancel")
    conn.putheader("Host", f"127.0.0.1:{port}")
    conn.putheader("Origin", f"http://127.0.0.1:{port}")
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(MAX_JSON_BODY_BYTES + 1024))
    conn.endheaders()
    resp = conn.getresponse()
    _ = resp.read()
    assert resp.status == 413
    conn.close()


def test_showdown_player_escapes_case_insensitive_script_breakout(tmp_path: Path) -> None:
    """Malicious `</SCRIPT>` or `</ScRiPt>` in a replay log must never break out of `<script type=text/plain>`."""
    evil_log = (
        "|player|p1|Alice|1|\n"
        "|player|p2|Bob|2|\n"
        "|c|p2|</SCRIPT><script>alert('xss')</script><!--\n"
        "|turn|1\n"
    )
    state = ReplayCoachAppState(device="cpu", db_path=tmp_path / "xss_test.duckdb")
    state.replay = parse_showdown_replay(evil_log)
    rendered = state.render_official_showdown_player_html()
    m = re.search(
        r'<script type="text/plain" class="battle-log-data">(.*?)</script>',
        rendered,
        re.DOTALL,
    )
    assert m is not None
    inner = m.group(1)
    assert "</script" not in inner.lower()
    assert "alert('xss')" not in rendered.split('class="battle-log-data">')[1].split("</script>")[1]


def test_launcher_host_port_validation_and_cwd_plant_defense(tmp_path: Path, monkeypatch) -> None:
    """Launcher rejects shell-injection hosts/invalid ports and ignores planted python in repo root."""
    assert validate_bind_host_port("127.0.0.1", 8765) == ("127.0.0.1", 8765)
    for bad_host in ("127.0.0.1 & calc.exe", "127.0.0.1';import os;#", "http://evil", ""):
        with pytest.raises(ValueError):
            validate_bind_host_port(bad_host, 8765)
    for bad_port in (0, -1, 70000):
        with pytest.raises(ValueError):
            validate_bind_host_port("127.0.0.1", bad_port)

    # Planted python binary inside fake repo_root must never be selected
    planted = tmp_path / "python3"
    planted.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    planted.chmod(0o755)
    monkeypatch.setattr("apps.replay_coach.launcher_entry.shutil.which", lambda _name: str(planted))
    assert find_system_python(repo_root=tmp_path) is None


def test_github_actions_supply_chain_hardening() -> None:
    """Verify least-privilege permissions, pinned PyInstaller, SHA256SUMS, SLSA attestation & zero tag injection."""
    ci_txt = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    exe_txt = (REPO_ROOT / ".github" / "workflows" / "build-windows-launcher.yml").read_text(encoding="utf-8")

    assert re.search(r"^permissions:\s*\n\s+contents:\s*read", ci_txt, re.MULTILINE)
    assert re.search(r"^permissions:\s*\n\s+contents:\s*read", exe_txt, re.MULTILINE)
    assert "pyinstaller==" in exe_txt
    assert "SHA256SUMS.txt" in exe_txt
    assert "actions/attest-build-provenance@" in exe_txt
    # Ensure github.ref_name is NEVER interpolated directly inside shell/pwsh scripts (only via env:)
    assert '$tag = "${{ github.ref_name }}"' not in exe_txt
    assert "RELEASE_TAG: ${{ github.ref_name }}" in exe_txt
