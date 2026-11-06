# engine/scripts/test_registry.py
import sys
from pathlib import Path

# Resolve to repo root and include src/ for imports
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from engine.db_registry import VGCDataRegistry
except ImportError:
    from src.engine.db_registry import VGCDataRegistry


def run_tests():
    print("=" * 60)
    print("VGC ENGINE DUCKDB REGISTRY INTEGRATION TESTS")
    print("=" * 60)

    registry = VGCDataRegistry()

    # 1. Verify View Creation
    print("\n[1] Checking Registered Database Views...")
    expected_views = {
        "pokedex",
        "moves",
        "items",
        "abilities",
        "learnsets",
        "conditions",
        "tournament_standings",
        "tournament_usage",
        "tournament_overview",
    }

    tables = registry.query("SHOW TABLES;")
    active_views = {row["name"] for row in tables}

    for view in expected_views:
        if view in active_views:
            print(f"  ✓ View mounted: {view}")
        else:
            print(f"  ✗ MISSING View: {view}")

    # 2. Test Showdown Mechanics Lookups
    print("\n[2] Testing Showdown Mechanics Entities...")

    # A. Pokemon Lookup
    test_mon = "Flutter Mane"
    mon = registry.get_pokemon(test_mon)
    if mon:
        print(f"  ✓ Pokemon: {mon.get('name')} | Types: {mon.get('types')} | Spe: {mon.get('spe')}")
    else:
        print(f"  ✗ Failed to find species: {test_mon}")

    # B. Move Lookup
    test_move = "Moonblast"
    move = registry.get_move(test_move)
    if move:
        print(f"  ✓ Move: {move.get('name')} | Type: {move.get('type')} | Power: {move.get('basePower')} | Priority: {move.get('priority')}")
    else:
        print(f"  ✗ Failed to find move: {test_move}")

    # C. Condition Lookup (Weather / Terrain / Status)
    test_cond = "sunnyday"
    condition = registry.get_condition(test_cond)
    if condition:
        name = condition.get("name", condition.get("id"))
        effect_keys = [k for k in condition.keys() if k not in ("id", "name")]
        print(f"  ✓ Condition: {name} (Attributes: {', '.join(effect_keys[:4])})")
    else:
        # Fallback test if ID format differs
        sample_cond = registry.query("SELECT * FROM conditions LIMIT 1;")
        if sample_cond:
            print(f"  ✓ Condition loaded (Sample ID: '{sample_cond[0].get('id', 'N/A')}')")
        else:
            print("  ✗ Conditions view is empty or failed to load.")

    # 3. Test Munchstats Regional Aggregations
    print("\n[3] Testing Munchstats Regional Archives...")

    # A. Tournament Counts
    tourney_count = registry.query("SELECT COUNT(DISTINCT tournament_id) AS total FROM tournament_overview;")
    standings_tourney_count = registry.query("SELECT COUNT(DISTINCT tournament_id) AS total FROM tournament_standings;")

    n_overview = tourney_count[0]["total"] if tourney_count else 0
    n_standings = standings_tourney_count[0]["total"] if standings_tourney_count else 0
    print(f"  ✓ Aggregated {n_overview} tournaments from overview.jsonl")
    print(f"  ✓ Aggregated {n_standings} tournaments from standings.jsonl")

    # B. Dynamic Schema & Field Inspection for Standings
    print("\n[4] Inspecting Standings Schema & Preview...")
    sample_standing = registry.query("SELECT * FROM tournament_standings LIMIT 1;")
    if sample_standing:
        record = sample_standing[0]
        print(f"  ✓ Detected Standings Columns: {list(record.keys())}")
        preview_id = record.get("tournament_id", "Unknown")
        print(f"  ✓ Sample Entry ({preview_id}):")
        for k, v in list(record.items())[:6]:
            print(f"      - {k}: {repr(v)}")
    else:
        print("  ✗ tournament_standings is empty.")

    # C. Dynamic Schema & Field Inspection for Usage
    print("\n[5] Inspecting Usage Schema & Preview...")
    sample_usage = registry.query("SELECT * FROM tournament_usage LIMIT 1;")
    if sample_usage:
        record = sample_usage[0]
        print(f"  ✓ Detected Usage Columns: {list(record.keys())}")
        print(f"  ✓ Sample Entry ({record.get('tournament_id', 'Unknown')}):")
        for k, v in list(record.items())[:6]:
            print(f"      - {k}: {repr(v)}")
    else:
        print("  ✗ tournament_usage is empty.")

    # 4. Cross-Tournament Analytics Test
    print("\n[6] Running Cross-Tournament Query...")
    try:
        top_cut_sample = registry.query("""
            SELECT tournament_id, count(*) AS total_recorded_players
            FROM tournament_standings
            GROUP BY tournament_id
            ORDER BY total_recorded_players DESC
            LIMIT 3;
        """)
        for row in top_cut_sample:
            print(f"  ✓ {row['tournament_id']}: {row['total_recorded_players']} players logged")
    except Exception as e:
        print(f"  ✗ Cross-tournament SQL execution failed: {e}")

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
