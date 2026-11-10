# -*- coding: utf-8 -*-
"""
Showdown Champions Mod Ingestion, Inheritance, and Pruning Pipeline
File: engine/scripts/ingest_champions_pipeline.py

Fetches canonical base Showdown data + Champions mod overrides, performs
inheritance overlays, filters out illegal/past records, and saves compact
Champions-only JSON snapshots to engine/data/showdown/.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Set

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "src" / "engine" / "data" / "showdown"
RAW_CACHE_DIR = OUTPUT_DIR / "raw_ts"

MOD_URL_BASE = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/mods/champions"
BASE_URL_BASE = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data"


# ==============================================================================
# 1. NETWORK & CACHING
# ==============================================================================

def fetch_ts(url: str, cache_file: Path) -> str:
    """Download a .ts file or read from local cache if already present."""
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    req = urllib.request.Request(url, headers={"User-Agent": "Coach-Porygon-VGC/2.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(content, encoding="utf-8")
            return content
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return ""
        raise


# ==============================================================================
# 2. INDENTATION-AWARE DATA EXTRACTOR
# ==============================================================================

def parse_showdown_table(raw_text: str) -> Dict[str, Any]:
    """
    Parses Showdown tables (moves, abilities, items, conditions, pokedex) by
    extracting 1-tab entry blocks and evaluating static 2-tab properties.
    Completely avoids parsing JS callbacks, regexes, and template literals.
    """
    if not raw_text.strip():
        return {}

    lines = raw_text.splitlines()
    entries: Dict[str, Any] = {}
    current_id: str | None = None
    current_prop_lines: list[str] = []
    in_skipped_block = False
    skip_indent = 0

    entry_start_pattern = re.compile(r"^\t([a-zA-Z0-9_$]+):\s*\{")
    entry_end_pattern = re.compile(r"^\t\},?")
    method_pattern = re.compile(r"^\t\t(?:(?:async|get|set)\s+)?([a-zA-Z0-9_$]+)\s*\(")
    prop_func_pattern = re.compile(r"^\t\t[a-zA-Z0-9_$]+\s*:\s*(?:async\s*)?(?:function\b|\(?[a-zA-Z0-9_$,\s]*\)?\s*=>)")

    def parse_entry_block(raw_id: str, prop_lines: list[str]) -> None:
        if not prop_lines:
            entries[raw_id] = {}
            return

        block_text = "{\n" + "\n".join(prop_lines) + "\n}"
        block_text = re.sub(r"/\*[\s\S]*?\*/", "", block_text)
        block_text = re.sub(r"//.*", "", block_text)
        block_text = re.sub(r"\btrue\b", "True", block_text)
        block_text = re.sub(r"\bfalse\b", "False", block_text)
        block_text = re.sub(r"\bnull\b", "None", block_text)
        block_text = re.sub(r"\bundefined\b", "None", block_text)
        block_text = re.sub(r'([{,\n\r]\s*)([a-zA-Z0-9_$]+)\s*:', r'\1"\2":', block_text)

        try:
            parsed = ast.literal_eval(block_text)
            entries[raw_id] = parsed
        except Exception:
            # Fallback: line-by-line scalar extraction if a nested block has syntax quirks
            scalar_dict: Dict[str, Any] = {}
            for line in prop_lines:
                m_scalar = re.match(r'^\t\t([a-zA-Z0-9_$]+)\s*:\s*([^,]+),?', line)
                if m_scalar:
                    k, v = m_scalar.group(1), m_scalar.group(2).strip().strip('"').strip("'")
                    if v == "true":
                        scalar_dict[k] = True
                    elif v == "false":
                        scalar_dict[k] = False
                    elif v in ("null", "undefined"):
                        scalar_dict[k] = None
                    else:
                        try:
                            scalar_dict[k] = int(v) if v.lstrip("-").isdigit() else float(v)
                        except ValueError:
                            scalar_dict[k] = v
            entries[raw_id] = scalar_dict

    for line in lines:
        # Check for start of an entry at \tlevel (1 tab)
        m_start = entry_start_pattern.match(line)
        if m_start:
            if current_id is not None:
                parse_entry_block(current_id, current_prop_lines)
            current_id = m_start.group(1)
            current_prop_lines = []
            in_skipped_block = False
            continue

        # Check for end of an entry at \tlevel (1 tab)
        if entry_end_pattern.match(line):
            if current_id is not None:
                parse_entry_block(current_id, current_prop_lines)
                current_id = None
                current_prop_lines = []
            in_skipped_block = False
            continue

        if current_id is None:
            continue

        # If currently skipping a nested multi-line callback/condition block
        if in_skipped_block:
            # Check if this line closes the skipped block at the recorded indent
            if line.startswith("\t" * skip_indent + "}") or line.startswith("\t" * skip_indent + "},"):
                in_skipped_block = False
            continue

        # Detect callbacks, functions, or complex condition blocks to skip
        if method_pattern.match(line) or prop_func_pattern.match(line):
            if line.rstrip().endswith("{"):
                in_skipped_block = True
                skip_indent = 2
            continue

        # Skip complex multi-line condition/event dictionaries
        if re.match(r"^\t\t(?:condition|eventMethods)\s*:\s*\{", line):
            in_skipped_block = True
            skip_indent = 2
            continue

        # Keep valid 2-tab data lines
        if line.startswith("\t\t") and not in_skipped_block:
            current_prop_lines.append(line)

    if current_id is not None:
        parse_entry_block(current_id, current_prop_lines)

    return entries


# ==============================================================================
# 3. FAST STATIC PARSER (For Pokedex, Learnsets, Formats-Data)
# ==============================================================================

def fast_parse_static_ts(raw_text: str) -> Dict[str, Any]:
    """Single-pass regex parser for purely static dictionaries."""
    if not raw_text.strip():
        return {}

    text = re.sub(r"/\*[\s\S]*?\*/", "", raw_text)
    text = re.sub(r"//.*", "", text)

    m_root = re.search(r"export\s+const\s+\w+[^=]*=\s*\{", text)
    start_idx = m_root.end() - 1 if m_root else text.find("{")
    if start_idx == -1:
        return {}

    text = text[start_idx:].strip().rstrip(";")
    text = re.sub(r"\btrue\b", "True", text)
    text = re.sub(r"\bfalse\b", "False", text)
    text = re.sub(r"\bnull\b", "None", text)
    text = re.sub(r"\bundefined\b", "None", text)
    text = re.sub(r'([{,\n\r]\s*)([a-zA-Z0-9_$]+)\s*:', r'\1"\2":', text)

    return ast.literal_eval(text)


# ==============================================================================
# 4. MOD INHERITANCE OVERLAY
# ==============================================================================

def apply_mod_overlay(base_dict: Dict[str, Any], mod_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay mod changes onto base definitions using Showdown's inherit semantics."""
    merged: Dict[str, Any] = {}

    for key, base_val in base_dict.items():
        if key in mod_dict:
            mod_val = mod_dict[key]
            if isinstance(mod_val, dict) and mod_val.get("inherit") is True:
                entry = dict(base_val)
                entry.update({k: v for k, v in mod_val.items() if k != "inherit"})
                merged[key] = entry
            else:
                merged[key] = mod_val
        else:
            merged[key] = base_val

    for key, mod_val in mod_dict.items():
        if key not in merged:
            merged[key] = (
                {k: v for k, v in mod_val.items() if k != "inherit"}
                if isinstance(mod_val, dict)
                else mod_val
            )

    return merged


# ==============================================================================
# 5. PIPELINE ORCHESTRATION
# ==============================================================================

def run_pipeline() -> None:
    print("======================================================================")
    print("=== Coach Porygon: Ingesting & Pruning Champions Mod Dataset ===")
    print("======================================================================")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Pokedex (Static, Base)
    print("[*] Loading pokedex...")
    base_pokedex_raw = fetch_ts(f"{BASE_URL_BASE}/pokedex.ts", RAW_CACHE_DIR / "base_pokedex.ts")
    base_pokedex = fast_parse_static_ts(base_pokedex_raw)
    print(f"    Base: {len(base_pokedex)} entries")

    # 2. Moves (Base + Champions mod overlay via indentation parser)
    print("[*] Loading moves...")
    base_moves_raw = fetch_ts(f"{BASE_URL_BASE}/moves.ts", RAW_CACHE_DIR / "base_moves.ts")
    mod_moves_raw = fetch_ts(f"{MOD_URL_BASE}/moves.ts", RAW_CACHE_DIR / "champ_moves.ts")
    base_moves = parse_showdown_table(base_moves_raw)
    mod_moves = parse_showdown_table(mod_moves_raw)
    moves = apply_mod_overlay(base_moves, mod_moves)
    print(f"    Base: {len(base_moves)} | Mod: {len(mod_moves)} -> Merged: {len(moves)}")

    # 3. Abilities (Base + Champions mod overlay)
    print("[*] Loading abilities...")
    base_ab_raw = fetch_ts(f"{BASE_URL_BASE}/abilities.ts", RAW_CACHE_DIR / "base_abilities.ts")
    mod_ab_raw = fetch_ts(f"{MOD_URL_BASE}/abilities.ts", RAW_CACHE_DIR / "champ_abilities.ts")
    base_abilities = parse_showdown_table(base_ab_raw)
    mod_abilities = parse_showdown_table(mod_ab_raw)
    abilities = apply_mod_overlay(base_abilities, mod_abilities)
    print(f"    Base: {len(base_abilities)} | Mod: {len(mod_abilities)} -> Merged: {len(abilities)}")

    # 4. Items (Base + Champions mod overlay)
    print("[*] Loading items...")
    base_items_raw = fetch_ts(f"{BASE_URL_BASE}/items.ts", RAW_CACHE_DIR / "base_items.ts")
    mod_items_raw = fetch_ts(f"{MOD_URL_BASE}/items.ts", RAW_CACHE_DIR / "champ_items.ts")
    base_items = parse_showdown_table(base_items_raw)
    mod_items = parse_showdown_table(mod_items_raw)
    items = apply_mod_overlay(base_items, mod_items)
    print(f"    Base: {len(base_items)} | Mod: {len(mod_items)} -> Merged: {len(items)}")

    # 5. Conditions (Base + Champions mod overlay)
    print("[*] Loading conditions...")
    base_cond_raw = fetch_ts(f"{BASE_URL_BASE}/conditions.ts", RAW_CACHE_DIR / "base_conditions.ts")
    mod_cond_raw = fetch_ts(f"{MOD_URL_BASE}/conditions.ts", RAW_CACHE_DIR / "champ_conditions.ts")
    base_conditions = parse_showdown_table(base_cond_raw)
    mod_conditions = parse_showdown_table(mod_cond_raw)
    conditions = apply_mod_overlay(base_conditions, mod_conditions)
    print(f"    Base: {len(base_conditions)} | Mod: {len(mod_conditions)} -> Merged: {len(conditions)}")

    # 6. Formats Data (Static: Champions Mod)
    print("[*] Loading formats-data...")
    mod_formats_raw = fetch_ts(f"{MOD_URL_BASE}/formats-data.ts", RAW_CACHE_DIR / "champ_formats-data.ts")
    formats_data = fast_parse_static_ts(mod_formats_raw)
    print(f"    Mod: {len(formats_data)} entries")

    # 7. Learnsets (Static: Champions Mod)
    print("[*] Loading Champions learnsets...")
    mod_learnsets_raw = fetch_ts(f"{MOD_URL_BASE}/learnsets.ts", RAW_CACHE_DIR / "champ_learnsets.ts")
    learnsets = fast_parse_static_ts(mod_learnsets_raw)
    print(f"    Champions Learnsets: {len(learnsets)} legal species movepools loaded.")

# 8. Legality Pruning
    print("\n[*] Pruning non-legal species, past moves, and items...")
    
    # 8a. Build legal roster from formats-data and pokedex
    legal_species_ids: Set[str] = set()
    
    for s_id, f_data in formats_data.items():
        is_nonstandard = f_data.get("isNonstandard")
        tier = f_data.get("tier", "")
        doubles_tier = f_data.get("doublesTier", "")

        # Exclude nonstandard, cut, and banned entries
        if is_nonstandard in ("Past", "Future", "Unobtainable", "Custom", "Gigantamax"):
            continue
        if tier in ("Illegal", "Unreleased") or doubles_tier in ("Illegal", "Unreleased"):
            continue
            
        legal_species_ids.add(s_id)

    # 8b. Add base species for any legal Megas/Forms (so they have learnsets)
    for s_id in list(legal_species_ids):
        if s_id in base_pokedex:
            base_spec = base_pokedex[s_id].get("baseSpecies")
            if base_spec:
                base_id = re.sub(r"[^a-z0-9]", "", str(base_spec).lower())
                legal_species_ids.add(base_id)

    # 8c. Prune Pokédex
    pruned_pokedex: Dict[str, Any] = {}
    for s_id in legal_species_ids:
        if s_id in base_pokedex:
            pruned_pokedex[s_id] = base_pokedex[s_id]
        else:
            norm_id = re.sub(r"[^a-z0-9]", "", s_id.lower())
            if norm_id in base_pokedex:
                pruned_pokedex[s_id] = base_pokedex[norm_id]

    print(f"    [+] Pokédex: Pruned {len(base_pokedex)} -> {len(pruned_pokedex)} legal Champions species (including Megas/Forms).")

    # 8d. Prune Moves
    pruned_moves = {
        m_id: m_data
        for m_id, m_data in moves.items()
        if m_data.get("isNonstandard") not in ("Past", "Future", "Unobtainable", "Custom")
    }
    print(f"    [+] Moves: Pruned {len(moves)} -> {len(pruned_moves)} legal moves.")

    # 8e. Prune Items
    pruned_items = {
        i_id: i_data
        for i_id, i_data in items.items()
        if i_data.get("isNonstandard") not in ("Past", "Future", "Unobtainable", "Custom")
    }
    print(f"    [+] Items: Pruned {len(items)} -> {len(pruned_items)} legal items.")
    
    # 9. Output Curated Snapshots
    print("\n[*] Writing curated Champions JSON files to engine/data/showdown/...")
    file_map = {
        "pokedex.json": pruned_pokedex,
        "moves.json": pruned_moves,
        "abilities.json": abilities,
        "items.json": pruned_items,
        "conditions.json": conditions,
        "learnsets.json": learnsets,
    }

    for filename, data in file_map.items():
        target_path = OUTPUT_DIR / filename
        target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"    [✓] Saved {filename} ({len(data)} entries)")

    print("\n[✓] Pipeline execution finished. Lightweight Champions dataset ready.")


if __name__ == "__main__":
    run_pipeline()