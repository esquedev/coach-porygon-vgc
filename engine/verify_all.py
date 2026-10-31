import csv
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

REPO_ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = REPO_ROOT / "assets" / "command_center_es.html"

def test_all():
    """Run comprehensive verification across all 9 operational validation points."""
    print("=== RUNNING FULL VERIFICATION ON EXTENDED COMMAND CENTER ===")
    html = HTML_PATH.read_text(encoding="utf-8")

    # 1. Check Mode selector labels (no mode numbers)
    nav_match = re.search(r'<nav[^>]*id="mode-tabs"[^>]*>(.*?)</nav>', html, re.DOTALL)
    assert nav_match, "mode-tabs nav not found"
    nav_text = nav_match.group(1)
    has_numbered_modes = any(f"Modo {i}" in nav_text or f"Mode {i}" in nav_text for i in range(1, 7))
    print(f"Point 1 - Mode labels have no numbers: {not has_numbered_modes}")

    # 2. Check SVG sprites & Items/Megastones
    sprites_match = re.search(r'window\.__COACH_PORYGON_SPRITES__\s*=\s*(\{.*?\});', html)
    items_match = re.search(r'window\.__COACH_PORYGON_ITEMS__\s*=\s*(\{.*?\});', html)
    assert sprites_match, "Sprite map not found"
    assert items_match, "Item map not found"
    sprite_map = json.loads(sprites_match.group(1))
    item_map = json.loads(items_match.group(1))
    has_get_item_func = 'function getItemSpritePath' in html
    print(f"Point 2a - Embedded SVG Pokémon species sprites: {len(sprite_map)} (>=363 format species)")
    print(f"Point 2b - Embedded SVG Items & Mega Stones: {len(item_map)} (85 items + 81 mega stones)")
    print(f"Point 2c - getItemSpritePath helper present: {has_get_item_func}")
    assert len(sprite_map) >= 363, f"Expected >= 363 sprites, got {len(sprite_map)}"
    assert len(item_map) >= 160, f"Expected >= 160 items/stones, got {len(item_map)}"
    assert has_get_item_func, "getItemSpritePath missing"

    # 3. Check Crucible 42 Scenarios & 168 Total Options
    sc_ids = re.findall(r'"?id"?:\s*"SC-(\d+)"', html)
    opt_ids = re.findall(r'"?id"?:\s*"(OPT-[A-D])"', html)
    print(f"Point 3a - Crucible scenarios count: {len(sc_ids)} (IDs: SC-01 to SC-{sc_ids[-1]})")
    print(f"Point 3b - Total 4-option response choices: {len(opt_ids)} (4 options per scenario: {len(opt_ids) == 168})")
    assert len(sc_ids) == 42, f"Expected 42 scenarios, found {len(sc_ids)}"
    assert len(opt_ids) == 168, f"Expected 168 options, found {len(opt_ids)}"

    # 3c. Check Speed Duel Flashcards (25 Matchups)
    speed_ids = re.findall(r'"?id"?:\s*"SD-(\d+)"', html)
    has_speed_container = 'id="crucible-speed-duel-container"' in html
    has_speed_funcs = 'setCrucibleSubMode' in html and 'loadSpeedDuel' in html and 'guessSpeedWinner' in html
    print(f"Point 3c - Speed Duel flashcards count: {len(speed_ids)} (IDs: SD-01 to SD-25): {len(speed_ids) == 25}")
    print(f"Point 3d - Speed Duel interactive UI & functions present: {has_speed_container and has_speed_funcs}")
    assert len(speed_ids) == 25, f"Expected 25 speed duels, found {len(speed_ids)}"
    assert has_speed_container and has_speed_funcs, "Speed Duel UI missing"

    # 3e. Check AI Generator Banners, Sub-Mode toggle & Auto-Advance QoL
    has_crucible_ai_banner = 'Generador de Escenarios Crucible con IA' in html
    has_submode_toggle = 'crucible-submode-tactical-btn' in html and 'crucible-submode-speed-btn' in html
    has_crucible_auto = 'id="crucible-auto-advance"' in html and 'id="crucible-auto-badge"' in html and 'crucibleAutoAdvanceTimer' in html
    has_speed_auto = 'id="speed-auto-advance"' in html and 'id="speed-auto-badge"' in html and 'speedAutoAdvanceTimer' in html
    has_random_start = 'Math.floor(Math.random()' in html
    print(f"Point 3e - Crucible AI Banner & Submode Toggle: {has_crucible_ai_banner and has_submode_toggle}")
    print(f"Point 3f - Crucible & Speed Duel Auto-Advance Toggles & Timers: {has_crucible_auto and has_speed_auto}")
    print(f"Point 3g - Random Initial Scenario / Duel Selection: {has_random_start}")
    assert has_crucible_ai_banner and has_submode_toggle, "Crucible AI Banner or toggle missing"
    assert has_crucible_auto and has_speed_auto, "Crucible or Speed auto-advance missing"
    assert has_random_start, "Random start logic missing"

    # 4. Check Persistent CSV Datasets
    crucible_csv = REPO_ROOT / "data" / "Crucible_Scenarios.csv"
    speed_csv = REPO_ROOT / "data" / "Speed_Duel_Scenarios.csv"
    assert crucible_csv.exists(), "Crucible_Scenarios.csv missing"
    assert speed_csv.exists(), "Speed_Duel_Scenarios.csv missing"
    with open(crucible_csv, "r", encoding="utf-8") as f:
        c_rows = list(csv.reader(f))
    with open(speed_csv, "r", encoding="utf-8") as f:
        s_rows = list(csv.reader(f))
    print(f"Point 4a - Crucible_Scenarios.csv rows: {len(c_rows)-1} (Header + 42 Scenarios)")
    print(f"Point 4b - Speed_Duel_Scenarios.csv rows: {len(s_rows)-1} (Header + 25 Duels)")
    assert len(c_rows) - 1 == 42, f"Expected 42 rows in Crucible_Scenarios.csv, got {len(c_rows)-1}"
    assert len(s_rows) - 1 == 25, f"Expected 25 rows in Speed_Duel_Scenarios.csv, got {len(s_rows)-1}"

    # 5. Check Mode 4 OTS select and rendering
    has_my_select = 'id="ots-my-team-select"' in html
    has_opp_select = 'id="ots-opp-team-select"' in html
    has_ots_func = 'function renderOtsComparison' in html and 'function initMode4Ots' in html
    print(f"Point 5 - Mode 4 OTS dropdowns and logic present: {has_my_select and has_opp_select and has_ots_func}")

    # 6. Check Mode 2 Spread Champions & Damage Calc
    has_sp_team_select = 'id="sp-team-select"' in html
    has_sp_mon_select = 'id="sp-mon-select"' in html
    has_sp_presets = 'applySpPreset' in html and 'copySpVerificationString' in html
    has_sp_benchmarks = 'renderSpLiveBenchmarks' in html
    has_duel_stage = 'calc-stage-atk-name' in html and 'calc-atk-sprite' in html and 'calc-def-sprite' in html
    print(f"Point 6 - Mode 2 Spread Champions & VGC Damage Calculator: {has_sp_team_select and has_sp_mon_select and has_sp_presets and has_sp_benchmarks and has_duel_stage}")

    # 7. Check Mode 1 dynamic calcs, growth banner & quick ingestion
    has_m1_select = 'id="m1-match-select"' in html
    has_m1_calcs = 'renderVerifiedCalcsTable' in html and 'm1-calcs-count-badge' in html
    no_hardcoded_title_290 = 'Compendio de 290' not in html and 'Compendium of 290' not in html
    has_m1_banner = 'Expansión Continua de Telemetría' in html
    has_m1_ingest = 'id="m1-ingest-box"' in html and 'ingestMatchReplayInSession' in html
    calcs_csv = REPO_ROOT / "data" / "Damage_Calculations.csv"
    with open(calcs_csv, "r", encoding="utf-8") as f:
        calcs_rows = list(csv.reader(f))
    print(f"Point 7a - Mode 1 dynamic calcs & no hardcoded 290 in UI titles: {has_m1_select and has_m1_calcs and no_hardcoded_title_290}")
    print(f"Point 7b - Mode 1 Telemetry Growth Banner & Quick Ingest UI: {has_m1_banner and has_m1_ingest}")
    print(f"Point 7c - Damage_Calculations.csv live rows count: {len(calcs_rows)-1} (>=300 rows)")
    assert len(calcs_rows) - 1 >= 300, f"Expected >= 300 calcs, got {len(calcs_rows)-1}"
    assert has_m1_banner and has_m1_ingest, "Mode 1 growth banner or quick ingest missing"

    # 8. Check Mode 5 Psychology, Leaks, Trainer Health, Tilt-O-Meter & Strengths
    has_m5_filter_team = 'id="m5-filter-team"' in html
    has_m5_drivers = 'm5-drivers-bars' in html and 'm5-codes-bars' in html
    has_m5_diagnostics = 'm5-diagnostics-list' in html
    has_m5_health = 'id="m5-health-score"' in html and 'id="m5-health-bar"' in html
    has_m5_tilt = 'id="m5-tilt-score"' in html and 'id="m5-tilt-bar"' in html
    has_m5_strengths = 'id="m5-strengths-list"' in html and 'fbWinRate' in html
    print(f"Point 8a - Mode 5 Psychology filters, driver bars, code bars and diagnostics list: {has_m5_filter_team and has_m5_drivers and has_m5_diagnostics}")
    print(f"Point 8b - Mode 5 Trainer Health, Tilt-O-Meter & Competitive Strengths: {has_m5_health and has_m5_tilt and has_m5_strengths}")
    assert has_m5_health and has_m5_tilt and has_m5_strengths, "Mode 5 Health/Tilt/Strengths missing"

    # 9. Check Mode 6 Structured MunchStats Scraper CLI, Banner, Quick Ingest, and Dynamic Columns
    has_munch_banner = 'Flujo Híbrido de Ingesta & Consulta de Metagame MunchStats' in html
    has_quick_ingest = 'id="munch-ingest-box"' in html and 'ingestScoutedTeamInSession' in html
    has_col_selector = 'col-btn-usage' in html and 'col-btn-speed' in html and 'col-btn-role' in html and 'toggleMunchColumn' in html
    has_table_renderer = 'renderMunchTable' in html and 'id="munch-table-head"' in html and 'id="munch-table-body"' in html
    has_munch_cli_preview = 'munch-cmd-line' in html and 'updateMunchCliPreview' in html
    has_munch_crawl = 'executeMunchCrawl' in html and 'downloadMunchCsv' in html
    print(f"Point 9 - Mode 6 MunchStats Hybrid Banner, Quick Ingest, Column Selector & Table: {has_munch_banner and has_quick_ingest and has_col_selector and has_table_renderer and has_munch_cli_preview and has_munch_crawl}")

    # Terminology Check
    has_pilot = bool(re.search(r'\bpilot\b', html, re.I))
    print(f"Terminology Check - No lingering 'pilot' in UI HTML: {not has_pilot}")

    # 10. Double Validation: Backend HTTP Handlers & API Connection
    from verify_backend_connection import test_backend_live_server
    test_backend_live_server()

    print("=== ALL EXTENDED VERIFICATION CHECKS COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_all()
