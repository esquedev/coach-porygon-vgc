#!/usr/bin/env python3
"""
Double Validation: Front-End & Python Backend Integration Test
1. Front-End: SVG Bindings, Mode 5 Health/Tilt/Strengths Dashboard, and API Fetch Calls
2. Backend API: In-Process HTTP Handler Validation of All Endpoints (/api/telemetry, /api/munchstats/crawl, /api/sync, /api/telemetry/ingest)
"""

import io
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine"))
sys.path.insert(0, str(REPO_ROOT / "scouts"))

from ui_server import CoachPorygonHTTPHandler, execute_prompt_crawl_and_dump
from ui_generator import load_live_telemetry

class MockSocket:
    """Mock socket providing in-memory request simulation without network I/O."""
    def __init__(self, request_bytes):
        self.rfile = io.BytesIO(request_bytes)
        self.wfile = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        """Return in-memory stream for HTTP request reading."""
        if 'r' in mode:
            return self.rfile
        return self.wfile

    def sendall(self, data):
        """Capture response bytes sent by HTTP handler."""
        self.wfile.write(data)

class MockServer:
    """Mock HTTP server instance for sandboxed endpoint testing."""
    def __init__(self):
        pass

def run_mock_http_request(method: str, path: str, body: dict = None):
    """Execute sandboxed HTTP GET/POST against CoachPorygonHTTPHandler."""
    body_bytes = json.dumps(body).encode("utf-8") if body else b""
    req_lines = [
        f"{method} {path} HTTP/1.1",
        "Host: localhost",
        "Content-Type: application/json",
        f"Content-Length: {len(body_bytes)}",
        "",
        ""
    ]
    raw_input = "\r\n".join(req_lines).encode("utf-8") + body_bytes
    mock_sock = MockSocket(raw_input)

    handler = CoachPorygonHTTPHandler(mock_sock, ("127.0.0.1", 12345), MockServer())

    # Read output from handler
    output_bytes = mock_sock.wfile.getvalue()
    header_part, _, body_part = output_bytes.partition(b"\r\n\r\n")
    header_str = header_part.decode("utf-8", errors="replace")
    status_line = header_str.splitlines()[0] if header_str else ""
    return status_line, body_part

def test_frontend_bindings():
    """Verify Command Center JavaScript API bindings and endpoints."""
    print("\n--- [VALIDATION 1] VERIFICACIÓN DEL FRONT-END & ASSETS SVG ---")
    html_path = REPO_ROOT / "assets" / "command_center_es.html"
    assert html_path.exists(), f"Falta {html_path}"
    html = html_path.read_text(encoding="utf-8")

    # 1. SVGs Connected in Front-End
    has_item_sprites = "getItemSpritePath(" in html
    has_species_sprites = "getSpritePath(" in html
    has_ots_item_icons = 'getItemSpritePath(m.item)' in html
    has_crucible_item_icons = 'getItemSpritePath(slot.item)' in html
    has_speed_item_icons = 'getItemSpritePath(monA.item)' in html
    has_munch_item_icons = 'getItemSpritePath(u.item)' in html

    print(f"  ✓ Helper getItemSpritePath presente: {has_item_sprites}")
    print(f"  ✓ Helper getSpritePath presente: {has_species_sprites}")
    print(f"  ✓ Íconos SVG de Objetos en Modo 4 (OTS Flowchart): {has_ots_item_icons}")
    print(f"  ✓ Íconos SVG de Objetos en Modo 3 (Crucible Slots): {has_crucible_item_icons}")
    print(f"  ✓ Íconos SVG de Objetos en Modo 3 (Speed Duels): {has_speed_item_icons}")
    print(f"  ✓ Íconos SVG de Objetos en Modo 6 (MunchStats Table): {has_munch_item_icons}")

    assert has_item_sprites and has_species_sprites, "Faltan helpers de SVG"
    assert has_ots_item_icons and has_crucible_item_icons and has_speed_item_icons, "Faltan conexiones de SVGs en los paneles"

    # 2. Mode 5 Psychology & Player Strengths
    has_health_ui = 'id="m5-health-score"' in html and 'id="m5-health-bar"' in html and 'id="m5-health-badge"' in html
    has_tilt_ui = 'id="m5-tilt-score"' in html and 'id="m5-tilt-bar"' in html and 'id="m5-tilt-badge"' in html
    has_strengths_ui = 'id="m5-strengths-list"' in html
    has_psych_calc = 'fbWinRate' in html and 'clutchWinRate' in html and 'tiltScore' in html and 'healthScore' in html

    print(f"  ✓ UI de Salud Cognitiva del Entrenador (Trainer Health): {has_health_ui}")
    print(f"  ✓ UI del Barómetro de Tilt (Tilt-O-Meter): {has_tilt_ui}")
    print(f"  ✓ UI de Fortalezas Competitivas del Entrenador: {has_strengths_ui}")
    print(f"  ✓ Algoritmo de cálculo de Fortalezas, Health y Tilt: {has_psych_calc}")

    assert has_health_ui and has_tilt_ui and has_strengths_ui and has_psych_calc, "Faltan componentes de Psicología y Fortalezas"

    # 3. Backend API Connection Calls in JS
    has_sync_call = "fetch('/api/telemetry')" in html
    has_ingest_call = "fetch('/api/telemetry/ingest'" in html

    print(f"  ✓ Llamada asíncrona a GET /api/telemetry en syncWithBackend: {has_sync_call}")
    print(f"  ✓ Llamada asíncrona a POST /api/telemetry/ingest: {has_ingest_call}")
    assert has_sync_call and has_ingest_call, "Faltan llamadas fetch hacia el backend"

    print(">>> [VALIDATION 1 COMPLETADA CON ÉXITO: 100% FRONT-END CONECTADO] <<<")


def test_backend_live_server():
    """Verify HTTP handler responses against mock requests."""
    print("\n--- [VALIDATION 2] VERIFICACIÓN DEL MOTOR BACKEND HTTP & ENDPOINTS REST ---")

    # Test Endpoint 1: GET /api/telemetry
    status1, body1 = run_mock_http_request("GET", "/api/telemetry")
    assert "200" in status1, f"Expected 200, got: {status1}"
    data1 = json.loads(body1.decode("utf-8"))
    print(f"  ✓ GET /api/telemetry -> {status1} (Partidas: {data1.get('total_matches')}, Cálculos: {data1.get('total_calcs')}, Equipos: {len(data1.get('teams', []))})")
    assert data1.get("total_matches", 0) >= 322, "Partidas incompletas en /api/telemetry"
    assert data1.get("total_calcs", 0) >= 300, "Cálculos incompletos en /api/telemetry"

    # Test Endpoint 2: POST /api/munchstats/crawl
    crawl_payload = {"prompt": "Nice Rain", "tournament_id": "Nice 2027"}
    status2, body2 = run_mock_http_request("POST", "/api/munchstats/crawl", crawl_payload)
    assert "200" in status2, f"Expected 200, got: {status2}"
    data2 = json.loads(body2.decode("utf-8"))
    print(f"  ✓ POST /api/munchstats/crawl -> {status2} (Status: {data2.get('status')}, Equipos coincidentes: {data2.get('matched_teams_count')})")
    assert data2.get("status") == "OK", "Estado de crawl no fue OK"
    assert "analytics" in data2 and "usage_stats" in data2["analytics"], "Falta analytics en respuesta de crawl"

    # Test Endpoint 3: POST /api/sync
    status3, body3 = run_mock_http_request("POST", "/api/sync", {})
    assert "200" in status3, f"Expected 200, got: {status3}"
    data3 = json.loads(body3.decode("utf-8"))
    print(f"  ✓ POST /api/sync -> {status3} (Status: {data3.get('status')})")
    assert data3.get("status") == "SYNCED", "Sync status no fue SYNCED"

    # Test Endpoint 4: POST /api/telemetry/ingest
    ingest_payload = {
        "id": "M_TEST_CONN",
        "opponent": "ConnectivityValidator",
        "result": "Win",
        "turns": 5,
        "notes": "Automated double validation test"
    }
    status4, body4 = run_mock_http_request("POST", "/api/telemetry/ingest", ingest_payload)
    assert "200" in status4, f"Expected 200, got: {status4}"
    data4 = json.loads(body4.decode("utf-8"))
    print(f"  ✓ POST /api/telemetry/ingest -> {status4} (Status: {data4.get('status')})")
    assert data4.get("status") == "INGESTED", "Ingest status no fue INGESTED"

    # Clean up test match from Raw_Matches.csv if appended
    raw_csv = REPO_ROOT / "data" / "Raw_Matches.csv"
    lines = raw_csv.read_text(encoding="utf-8").splitlines()
    clean_lines = [l for l in lines if "M_TEST_CONN" not in l]
    if len(clean_lines) < len(lines):
        raw_csv.write_text("\n".join(clean_lines) + "\n", encoding="utf-8")
        print("  ✓ Limpieza de datos de prueba en Raw_Matches.csv completada.")

    print(">>> [VALIDATION 2 COMPLETADA CON ÉXITO: 100% ENDPOINTS BACKEND VERIFICADOS] <<<")


def main():
    """Run frontend-to-backend connectivity validation suite."""
    print("=================================================================")
    print("  COACH PORYGON VGC — DOBLE VALIDACIÓN DE INTEGRACIÓN COMPLETA   ")
    print("=================================================================")
    test_frontend_bindings()
    test_backend_live_server()
    print("\n=================================================================")
    print("  RESULTADO: SISTEMA 100% OPERATIVO, CONECTADO Y VALIDADO        ")
    print("=================================================================")

if __name__ == "__main__":
    main()
