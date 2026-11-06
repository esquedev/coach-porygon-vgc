# engine/scripts/normalize_key_data.py
import json
from pathlib import Path

# Dynamically resolves to coach-porygon-vgc/engine/data regardless of execution folder
SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_DIR = SCRIPT_DIR.parent
DATA_DIR = ENGINE_DIR / "data"

SHOWDOWN_DIR = DATA_DIR / "showdown"
MUNCHSTATS_ARCHIVE_DIR = DATA_DIR / "munchstats" / "raw" / "archive"


def convert_dict_or_list_to_jsonl(
    input_path: Path,
    output_path: Path,
    key_field_name: str = "id",
    extra_fields: dict = None,
    delete_source: bool = True,
):
    if not input_path.exists():
        print(f"Skipping {input_path.name} (not found at {input_path})")
        return

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to parse {input_path.name}: {e}. Source file kept.")
        return

    count = 0
    with open(output_path, "w", encoding="utf-8") as out:
        # Case A: Top-level dictionary { "fluttermane": { ... } }
        if isinstance(data, dict):
            for key, val in data.items():
                row = {}
                if isinstance(val, dict):
                    row = val.copy()
                    if key_field_name not in row:
                        row[key_field_name] = key
                else:
                    row = {key_field_name: key, "value": val}

                if extra_fields:
                    row.update(extra_fields)
                out.write(json.dumps(row) + "\n")
                count += 1

        # Case B: Top-level list [ { ... }, { ... } ]
        elif isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    row_copy = row.copy()
                    if extra_fields:
                        row_copy.update(extra_fields)
                    out.write(json.dumps(row_copy) + "\n")
                    count += 1

    print(f" Converted: {input_path.relative_to(DATA_DIR)} -> {output_path.name} ({count} rows)")

    # Only delete the original file once the destination file exists on disk
    if delete_source and output_path.exists():
        input_path.unlink()
        print(f"   🗑️ Deleted original: {input_path.name}")


if __name__ == "__main__":
    print(f"Target Data Directory: {DATA_DIR}\n")

    # 1. Normalize Showdown Reference Files
    showdown_files = [
        "pokedex.json",
        "moves.json",
        "items.json",
        "learnsets.json",
        "abilities.json",
        "conditions.json",
    ]

    print("--- Normalizing Showdown Data ---")
    for fname in showdown_files:
        src = SHOWDOWN_DIR / fname
        dest = SHOWDOWN_DIR / fname.replace(".json", ".jsonl")
        convert_dict_or_list_to_jsonl(src, dest, key_field_name="id", delete_source=True)

    # 2. Normalize Munchstats Tournament Archive
    print("\n--- Normalizing Munchstats Tournament Archives ---")
    if MUNCHSTATS_ARCHIVE_DIR.exists():
        tournament_dirs = [d for d in MUNCHSTATS_ARCHIVE_DIR.iterdir() if d.is_dir()]
        print(f"Found {len(tournament_dirs)} tournament directories.")

        for tourney_dir in tournament_dirs:
            tourney_id = tourney_dir.name
            extra = {"tournament_id": tourney_id}

            for file_type in ["overview.json", "standings.json", "usage.json"]:
                src = tourney_dir / file_type
                dest = tourney_dir / file_type.replace(".json", ".jsonl")
                convert_dict_or_list_to_jsonl(
                    src,
                    dest,
                    key_field_name="species",
                    extra_fields=extra,
                    delete_source=True,
                )
    else:
        print(f"Munchstats archive directory not found at: {MUNCHSTATS_ARCHIVE_DIR}")