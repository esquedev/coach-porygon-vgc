import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ==============================================================================
# 1. STATIC GAME DATA & COEFFICIENTS (REGULATION M-C / SHOWDOWN SIM)
# ==============================================================================

TYPE_CHART: Dict[str, Dict[str, float]] = {
    "Normal":   {"Rock": 0.5, "Ghost": 0.0, "Steel": 0.5},
    "Fire":     {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 2.0, "Bug": 2.0, "Rock": 0.5, "Dragon": 0.5, "Steel": 2.0},
    "Water":    {"Fire": 2.0, "Water": 0.5, "Grass": 0.5, "Ground": 2.0, "Rock": 2.0, "Dragon": 0.5},
    "Grass":    {"Fire": 0.5, "Water": 2.0, "Grass": 0.5, "Poison": 0.5, "Ground": 2.0, "Flying": 0.5, "Bug": 0.5, "Rock": 2.0, "Dragon": 0.5, "Steel": 0.5},
    "Electric": {"Water": 2.0, "Electric": 0.5, "Grass": 0.5, "Ground": 0.0, "Flying": 2.0, "Dragon": 0.5},
    "Ice":      {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 0.5, "Ground": 2.0, "Flying": 2.0, "Dragon": 2.0, "Steel": 0.5},
    "Fighting": {"Normal": 2.0, "Ice": 2.0, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Rock": 2.0, "Ghost": 0.0, "Dark": 2.0, "Steel": 2.0, "Fairy": 0.5},
    "Poison":   {"Grass": 2.0, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Ghost": 0.5, "Steel": 0.0, "Fairy": 2.0},
    "Ground":   {"Fire": 2.0, "Electric": 2.0, "Grass": 0.5, "Poison": 2.0, "Flying": 0.0, "Bug": 0.5, "Rock": 2.0, "Steel": 2.0},
    "Flying":   {"Electric": 0.5, "Grass": 2.0, "Fighting": 2.0, "Bug": 2.0, "Rock": 0.5, "Steel": 0.5},
    "Psychic":  {"Fighting": 2.0, "Poison": 2.0, "Psychic": 0.5, "Dark": 0.0, "Steel": 0.5},
    "Bug":      {"Fire": 0.5, "Grass": 2.0, "Fighting": 0.5, "Poison": 0.5, "Flying": 0.5, "Psychic": 2.0, "Ghost": 0.5, "Dark": 2.0, "Steel": 0.5, "Fairy": 0.5},
    "Rock":     {"Fire": 2.0, "Ice": 2.0, "Fighting": 0.5, "Ground": 0.5, "Flying": 2.0, "Bug": 2.0, "Steel": 0.5},
    "Ghost":    {"Normal": 0.0, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5},
    "Dragon":   {"Dragon": 2.0, "Steel": 0.5, "Fairy": 0.0},
    "Dark":     {"Fighting": 0.5, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5, "Fairy": 0.5},
    "Steel":    {"Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2.0, "Rock": 2.0, "Steel": 0.5, "Fairy": 2.0},
    "Fairy":    {"Fire": 0.5, "Fighting": 2.0, "Poison": 0.5, "Dragon": 2.0, "Dark": 2.0, "Steel": 0.5}
}

NATURE_MODS: Dict[str, Dict[str, float]] = {
    "Adamant": {"atk": 1.1, "spa": 0.9}, "Bold":    {"def": 1.1, "atk": 0.9},
    "Brave":   {"atk": 1.1, "spe": 0.9}, "Calm":    {"spd": 1.1, "atk": 0.9},
    "Careful": {"spd": 1.1, "spa": 0.9}, "Modest":  {"spa": 1.1, "atk": 0.9},
    "Quiet":   {"spa": 1.1, "spe": 0.9}, "Timid":   {"spe": 1.1, "atk": 0.9},
    "Jolly":   {"spe": 1.1, "spa": 0.9}, "Impish":  {"def": 1.1, "spa": 0.9},
    "Relaxed": {"def": 1.1, "spe": 0.9}, "Sassy":   {"spd": 1.1, "spe": 0.9},
    "Naive":   {"spe": 1.1, "spd": 0.9}, "Hasty":   {"spe": 1.1, "def": 0.9},
    "Lonely":  {"atk": 1.1, "def": 0.9}, "Mild":    {"spa": 1.1, "def": 0.9},
    "Gentle":  {"spd": 1.1, "def": 0.9}, "Rash":    {"spa": 1.1, "spd": 0.9},
    "Naughty": {"atk": 1.1, "spd": 0.9}, "Lax":     {"def": 1.1, "spd": 0.9},
    "Hardy":   {}, "Serious": {}, "Bashful": {}, "Quirky": {}, "Docile": {}
}

TYPE_BOOST_ITEMS: Dict[str, str] = {
    "Charcoal": "Fire", "Mystic Water": "Water", "Miracle Seed": "Grass",
    "Magnet": "Electric", "Never-Melt Ice": "Ice", "Black Belt": "Fighting",
    "Poison Barb": "Poison", "Soft Sand": "Ground", "Sharp Beak": "Flying",
    "Twisted Spoon": "Psychic", "Silver Powder": "Bug", "Hard Stone": "Rock",
    "Spell Tag": "Ghost", "Dragon Fang": "Dragon", "Black Glasses": "Dark",
    "Metal Coat": "Steel", "Fairy Feather": "Fairy", "Silk Scarf": "Normal",
}

RESIST_BERRIES: Dict[str, str] = {
    "Occa Berry": "Fire", "Passho Berry": "Water", "Wacan Berry": "Electric",
    "Rindo Berry": "Grass", "Yache Berry": "Ice", "Chople Berry": "Fighting",
    "Kebia Berry": "Poison", "Shuca Berry": "Ground", "Coba Berry": "Flying",
    "Payapa Berry": "Psychic", "Tanga Berry": "Bug", "Charti Berry": "Rock",
    "Kasib Berry": "Ghost", "Haban Berry": "Dragon", "Colbur Berry": "Dark",
    "Babiri Berry": "Steel", "Roseli Berry": "Fairy", "Chilan Berry": "Normal",
}

PROTECT_MOVES = {
    "Protect", "Detect", "Spiky Shield", "Baneful Bunker",
    "King's Shield", "Silk Trap", "Burning Bulwark", "Obstruct"
}

STAT_LABELS = {
    "atk": "Attack", "def": "Defense", "spa": "Sp. Atk",
    "spd": "Sp. Def", "spe": "Speed", "accuracy": "accuracy", "evasion": "evasion"
}

BASE_STATS_DB: Dict[str, Dict[str, Any]] = {}
MOVE_DB: Dict[str, Dict[str, Any]] = {}


def _load_databases() -> None:
    """Load base stats, typings, items, and moves from cache and CSV files."""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    cache_path = data_dir / "pokedex_cache.json"

    if cache_path.exists():
        try:
            cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
            for sp_name, sp_info in cache_data.get("species", {}).items():
                entry = {
                    "hp": int(sp_info["hp"]),
                    "atk": int(sp_info["atk"]),
                    "def": int(sp_info["def"]),
                    "spa": int(sp_info["spa"]),
                    "spd": int(sp_info["spd"]),
                    "spe": int(sp_info["spe"]),
                    "types": sp_info.get("types", []),
                    "abilities": sp_info.get("abilities", {}),
                    "requiredItem": sp_info.get("requiredItem"),
                    "weightkg": float(sp_info.get("weightkg", 10.0)),
                    "learnset": sp_info.get("learnset", []),
                }
                BASE_STATS_DB[sp_name] = entry
                for alias in sp_info.get("aliases", []):
                    BASE_STATS_DB[alias] = entry

            for mv_name, mv_info in cache_data.get("moves", {}).items():
                entry = dict(mv_info)
                entry["name"] = mv_name
                entry["type"] = mv_info.get("type", "Normal")
                entry["cat"] = mv_info.get("cat", "Status")
                entry["power"] = int(mv_info.get("power", 0))
                entry["accuracy"] = mv_info.get("accuracy", 100)
                entry["priority"] = int(mv_info.get("priority", 0))
                entry["target"] = mv_info.get("target", "normal")
                entry["pp"] = int(mv_info.get("pp", 5))
                entry["flags"] = mv_info.get("flags", [])
                MOVE_DB[mv_name] = entry
        except Exception:
            pass

    csv_path = data_dir / "MC_Available_Pokemon.csv"
    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("Pokémon") or row.get("Pokemon") or "").strip()
                if not name:
                    continue
                types = [t.strip() for t in [row.get("Type 1", ""), row.get("Type 2", "")] if t and t.strip()]
                try:
                    existing = BASE_STATS_DB.get(name, {})
                    entry = {
                        "hp": int(float(row["Base HP"])),
                        "atk": int(float(row["Base Attack"])),
                        "def": int(float(row["Base Defense"])),
                        "spa": int(float(row["Base Sp. Attack"])),
                        "spd": int(float(row["Base Sp. Defense"])),
                        "spe": int(float(row["Speed"])),
                        "types": types,
                        "abilities": existing.get("abilities", {}),
                        "requiredItem": (row.get("Required Item") or "").strip() or existing.get("requiredItem"),
                        "weightkg": existing.get("weightkg", 10.0),
                        "learnset": existing.get("learnset", []),
                    }
                    BASE_STATS_DB[name] = entry
                    if name.startswith("Mega "):
                        rest = name[5:].strip()
                        parts = rest.split(" ")
                        if len(parts) == 2 and parts[1] in ("X", "Y", "Z"):
                            alias = f"{parts[0]}-Mega-{parts[1]}"
                        else:
                            alias = f"{rest}-Mega"
                        BASE_STATS_DB[alias] = entry
                except (KeyError, ValueError, TypeError):
                    continue


_load_databases()

# ==============================================================================
# 2. SHOWDOWN FIXED-POINT ARITHMETIC & STAT ENGINE
# ==============================================================================

def trunc(n: float, bits: int = 0) -> int:
    """Truncate float to integer with optional bit masking."""
    res = int(n)
    if bits:
        res = res & ((1 << bits) - 1)
    return res


def sd_modify(value: int, numerator: float, denominator: float = 1.0) -> int:
    """Exact port of Showdown Battle#modify (battle.ts:2348)."""
    modifier = trunc(numerator * 4096 / denominator)
    return trunc((trunc(value * modifier) + 2048 - 1) / 4096)


def sd_chain_mod(prev_mod_4096: int, numerator: float, denominator: float = 1.0) -> int:
    """Exact port of Showdown Battle#chainModify (battle.ts:2337)."""
    next_mod = trunc(numerator * 4096 / denominator)
    return (prev_mod_4096 * next_mod + 2048) >> 12


def apply_mod_4096(value: int, mod_4096: int) -> int:
    """Apply 4096 fixed-point modifier to integer value with official rounding."""
    return trunc((trunc(value * mod_4096) + 2048 - 1) / 4096)


def calculate_level_50_stats(species: str, sp: dict, nature: str, ivs: Optional[dict] = None) -> Tuple[int, Dict[str, int]]:
    """Exact port of Showdown Champions Scripts#statModify (data/mods/champions/scripts.ts:10)."""
    base = BASE_STATS_DB.get(species, {"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 80})
    mods = NATURE_MODS.get(nature, {})

    hp_sp = int(sp.get("hp", 0))
    max_hp = 1 if base["hp"] == 1 else int(base["hp"]) + hp_sp + 75

    stats = {}
    for s in ["atk", "def", "spa", "spd", "spe"]:
        s_sp = int(sp.get(s, 0))
        raw = int(base[s]) + s_sp + 20
        mod = mods.get(s, 1.0)
        if mod > 1.0:
            stats[s] = trunc(trunc(raw * 110, 16) / 100)
        elif mod < 1.0:
            stats[s] = trunc(trunc(raw * 90, 16) / 100)
        else:
            stats[s] = raw

    return max_hp, stats


def get_stage_multiplier(stage: int) -> float:
    """Compute stat stage multiplier (-6 to +6)."""
    stage = max(-6, min(6, stage))
    return (2 + stage) / 2.0 if stage >= 0 else 2.0 / (2 - stage)


def apply_stat_boost(stat: int, boost: int) -> int:
    """Exact port of Showdown Pokemon#calculateStat / getStat boost table (pokemon.ts:604)."""
    boost = max(-6, min(6, int(boost)))
    if boost >= 0:
        return trunc(stat * (2 + boost) / 2)
    return trunc(stat * 2 / (2 - boost))


def get_type_effectiveness(move_type: str, def_types: List[str], move_name: str = "", scrappy: bool = False) -> float:
    """Calculate elemental type matchup multiplier against dual-type defender."""
    mult = 1.0
    for dt in def_types:
        if move_name == "Freeze-Dry" and dt == "Water":
            mult *= 2.0
            continue
        if scrappy and dt == "Ghost" and move_type in ("Normal", "Fighting"):
            continue
        mult *= TYPE_CHART.get(move_type, {}).get(dt, 1.0)
    return mult


def is_airborne(slot: dict, field: Optional[dict] = None) -> bool:
    """Exact port of Showdown Pokemon#isGrounded (pokemon.ts:2169)."""
    if field and field.get("gravity_turns", 0) > 0:
        return False
    volatiles = slot.get("volatiles", {})
    if "smackdown" in volatiles or "ingrain" in volatiles:
        return False
    if slot.get("item") == "Iron Ball":
        return False
    types = slot.get("types", [])
    if "Flying" in types and "roost" not in volatiles:
        return True
    if slot.get("ability") in ("Levitate", "Eelevate"):
        return True
    if slot.get("item") == "Air Balloon":
        return True
    if "magnetrise" in volatiles or "telekinesis" in volatiles:
        return True
    return False


# ==============================================================================
# 3. SHOWDOWN-ACCURATE DOUBLES TURN MICRO-SIMULATOR
# ==============================================================================

class ClientReplaySimulator:
    """Showdown-accurate doubles turn micro-simulator with VP tracking."""
    def __init__(self, state_dict: dict, choices_dict: dict, pov_player: str = "p1"):
        self.state = json.loads(json.dumps(state_dict))
        self.choices = choices_dict
        self.pov = pov_player
        self.log_blocks: List[List[str]] = []
        self.redirect_target: Dict[str, str] = {}  # side ("p1" / "p2") -> slot_id
        self.wide_guard_sides: Set[str] = set()
        self.quick_guard_sides: Set[str] = set()
        self.crafty_shield_sides: Set[str] = set()

        # Normalize choices dict to support both move_name/move and choice/type keys
        for slot_id, action in self.choices.items():
            if isinstance(action, dict):
                if "move_name" not in action and "move" in action:
                    action["move_name"] = action["move"]
                if "choice" not in action and "type" in action:
                    action["choice"] = action["type"]

        self.state.setdefault("field", {"weather": None, "terrain": None})
        self.state.setdefault("p1", {"player": "p1", "tailwind_turns": 0})
        self.state.setdefault("p2", {"player": "p2", "tailwind_turns": 0})

        for slot_id, slot in self.state["slots"].items():
            slot["slot_id"] = slot_id
            if not slot.get("stats") or not slot.get("max_hp"):
                max_hp, stats = calculate_level_50_stats(
                    species=slot["species"],
                    sp=slot.get("sp_spread", {}),
                    nature=slot.get("nature", "Hardy")
                )
                slot["max_hp"] = max_hp
                slot["stats"] = stats
            if "types" not in slot and slot["species"] in BASE_STATS_DB:
                slot["types"] = list(BASE_STATS_DB[slot["species"]]["types"])
            slot.setdefault("boosts", {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0})
            slot.setdefault("volatiles", {})
            slot.setdefault("active_turns", 1)
            slot["protected"] = False
            slot["protect_type"] = None
            slot["flinched"] = False
            slot["moved_this_turn"] = False
            slot["helping_hand_mult"] = 1.0
            # Synchronize exact integer HP with current_hp_pct
            max_hp = max(1, int(slot.get("max_hp", 1)))
            if "current_hp_pct" in slot:
                pct = float(slot["current_hp_pct"])
                slot["current_hp_pct"] = max(0.0, min(100.0, pct))
                if "hp" not in slot:
                    slot["hp"] = 0 if pct <= 0 else max(1, round(max_hp * pct / 100.0))
                else:
                    slot["hp"] = max(0, min(max_hp, int(slot["hp"])))
            elif "hp" in slot:
                hp = max(0, min(max_hp, int(slot["hp"])))
                slot["hp"] = hp
                slot["current_hp_pct"] = 0.0 if hp <= 0 else round((hp / max_hp) * 100.0, 1)
            else:
                slot["hp"] = max_hp
                slot["current_hp_pct"] = 100.0

    def format_mon_name(self, slot_id: str) -> str:
        """Format species and side name for battle spectator display."""
        slot = self.state["slots"].get(slot_id)
        if not slot:
            return slot_id
        base_name = slot.get("name") or slot["species"]
        return base_name if slot_id.startswith(self.pov) else f"The opposing {base_name}"

    def sync_hp_pct(self, slot: dict) -> None:
        """Synchronize current HP percentage based on exact current and max HP values."""
        max_hp = max(1, int(slot.get("max_hp", 1)))
        hp = max(0, min(max_hp, int(slot.get("hp", 0))))
        slot["hp"] = hp
        slot["current_hp_pct"] = 0.0 if hp <= 0 else round((hp / max_hp) * 100.0, 1)

    def deal_hp_damage(self, slot: dict, dmg_hp: int, lines: List[str], check_sash: bool = False) -> int:
        """Apply damage to slot updating HP, fainting states, and battle logs."""
        max_hp = max(1, int(slot.get("max_hp", 1)))
        old_hp = int(slot.get("hp", 0))
        if old_hp <= 0 or dmg_hp <= 0:
            return 0

        t_name = self.format_mon_name(slot["slot_id"])
        # Focus Sash / Sturdy check when at full HP
        if check_sash and old_hp == max_hp and dmg_hp >= old_hp:
            if slot.get("ability") == "Sturdy":
                dmg_hp = old_hp - 1
                lines.append(f"{t_name} endured the hit with Sturdy!")
            elif slot.get("item") == "Focus Sash":
                dmg_hp = old_hp - 1
                slot["item"] = ""
                slot["unburden_active"] = slot.get("ability") == "Unburden"
                lines.append(f"{t_name} hung on using its Focus Sash!")

        actual = min(old_hp, max(1, dmg_hp))
        slot["hp"] = old_hp - actual
        old_pct = slot["current_hp_pct"]
        self.sync_hp_pct(slot)
        lost_pct = round(old_pct - slot["current_hp_pct"], 1)
        lines.append(f"({t_name} lost {lost_pct}% of its health!)")

        # Air Balloon pop
        if slot.get("item") == "Air Balloon" and actual > 0:
            slot["item"] = ""
            slot["unburden_active"] = slot.get("ability") == "Unburden"
            lines.append(f"{t_name}'s Air Balloon popped!")

        # Sitrus Berry check
        if 0 < slot["hp"] <= max_hp // 2 and slot.get("item") == "Sitrus Berry":
            slot["item"] = ""
            slot["unburden_active"] = slot.get("ability") == "Unburden"
            heal_amt = max(1, max_hp // 4)
            slot["hp"] = min(max_hp, slot["hp"] + heal_amt)
            self.sync_hp_pct(slot)
            lines.append(f"{t_name} restored its health using its Sitrus Berry!")

        # Berserk / Anger Shell check
        if 0 < slot["hp"] <= max_hp // 2 and old_hp > max_hp // 2:
            if slot.get("ability") == "Berserk":
                self.apply_boost(slot, {"spa": 1}, lines, source_self=True, ability_source="Berserk")
            elif slot.get("ability") == "Anger Shell":
                self.apply_boost(slot, {"atk": 1, "spa": 1, "spe": 1, "def": -1, "spd": -1}, lines, source_self=True, ability_source="Anger Shell")

        return actual

    def heal_hp(self, slot: dict, heal_hp_amt: int, lines: List[str], msg: Optional[str] = None) -> int:
        """Restore slot HP capping at maximum HP."""
        max_hp = max(1, int(slot.get("max_hp", 1)))
        old_hp = int(slot.get("hp", 0))
        if old_hp <= 0 or old_hp >= max_hp or heal_hp_amt <= 0:
            return 0
        slot["hp"] = min(max_hp, old_hp + max(1, heal_hp_amt))
        self.sync_hp_pct(slot)
        if msg:
            lines.append(msg)
        return slot["hp"] - old_hp

    def apply_boost(self, slot: dict, boosts: Dict[str, int], lines: List[str], source_self: bool = False, ability_source: Optional[str] = None) -> bool:
        """Exact port of Showdown Battle#boost (battle.ts:2037) with Clear Body, Contrary, Defiant, Competitive, White Herb."""
        if slot["current_hp_pct"] <= 0:
            return False
        t_name = self.format_mon_name(slot["slot_id"])
        ab = slot.get("ability", "")
        changed = False
        had_negative = False

        for stat, delta in boosts.items():
            if stat not in slot["boosts"]:
                slot["boosts"][stat] = 0
            if ab == "Contrary":
                delta = -delta
            elif ab == "Simple":
                delta *= 2

            if delta < 0 and not source_self:
                if ab in ("Clear Body", "White Smoke", "Full Metal Body") or (ab == "Hyper Cutter" and stat == "atk") or (ab == "Keen Eye" and stat == "accuracy"):
                    lines.append(f"{t_name}'s {ab} prevents stat loss!")
                    continue
                if slot.get("item") == "Clear Amulet":
                    lines.append(f"{t_name}'s Clear Amulet prevents its stats from being lowered!")
                    continue

            old_val = slot["boosts"][stat]
            new_val = max(-6, min(6, old_val + delta))
            actual = new_val - old_val
            slot["boosts"][stat] = new_val
            s_label = STAT_LABELS.get(stat, stat)
            prefix = f"[{t_name}'s {ability_source}] " if ability_source else ""

            if actual > 0:
                changed = True
                adv = "sharply " if actual == 2 else ("drastically " if actual >= 3 else "")
                lines.append(f"{prefix}{t_name}'s {s_label} {adv}rose!")
            elif actual < 0:
                changed = True
                had_negative = True
                adv = "harshly " if actual == -2 else ("severely " if actual <= -3 else "")
                lines.append(f"{prefix}{t_name}'s {s_label} {adv}fell!")

        if had_negative and not source_self:
            if ab == "Competitive":
                self.apply_boost(slot, {"spa": 2}, lines, source_self=True, ability_source="Competitive")
            elif ab == "Defiant":
                self.apply_boost(slot, {"atk": 2}, lines, source_self=True, ability_source="Defiant")

        # White Herb check
        if slot.get("item") == "White Herb" and any(v < 0 for v in slot["boosts"].values()):
            for k in list(slot["boosts"].keys()):
                if slot["boosts"][k] < 0:
                    slot["boosts"][k] = 0
            slot["item"] = ""
            slot["unburden_active"] = slot.get("ability") == "Unburden"
            lines.append(f"{t_name} restored its status using its White Herb!")

        return changed

    def try_set_status(self, slot: dict, status: str, lines: List[str], source_slot: Optional[dict] = None) -> bool:
        """Exact port of Showdown Pokemon#trySetStatus (pokemon.ts:1690) & Champions Conditions."""
        if slot["current_hp_pct"] <= 0 or slot.get("status"):
            return False
        types = slot.get("types", [])
        ab = slot.get("ability", "")
        f = self.state["field"]
        side = self.state["p1"] if slot["slot_id"].startswith("p1") else self.state["p2"]

        if side.get("safeguard_turns", 0) > 0 and (not source_slot or source_slot.get("ability") != "Infiltrator"):
            return False
        if f.get("terrain") == "misty" and not is_airborne(slot, f):
            return False
        if status == "slp" and f.get("terrain") == "electric" and not is_airborne(slot, f):
            return False
        if ab in ("Purifying Salt", "Comatose") or (ab == "Leaf Guard" and f.get("weather") == "sun"):
            return False

        # Natural type & ability immunities
        if status == "brn" and ("Fire" in types or ab in ("Water Veil", "Water Bubble", "Thermal Exchange")):
            return False
        if status == "par" and ("Electric" in types or ab == "Limber"):
            return False
        if status in ("psn", "tox") and ("Poison" in types or "Steel" in types or ab in ("Immunity", "Pastel Veil")):
            if not (source_slot and source_slot.get("ability") == "Corrosion"):
                return False
        if status == "slp" and ab in ("Insomnia", "Vital Spirit", "Sweet Veil"):
            return False
        if status == "frz" and ("Ice" in types or ab == "Magma Armor" or f.get("weather") == "sun"):
            return False

        slot["status"] = status
        t_name = self.format_mon_name(slot["slot_id"])
        status_msgs = {
            "brn": f"{t_name} was burned!",
            "par": f"{t_name} is paralyzed! It may be unable to move!",
            "slp": f"{t_name} fell asleep!",
            "frz": f"{t_name} was frozen solid!",
            "psn": f"{t_name} was poisoned!",
            "tox": f"{t_name} was badly poisoned!",
        }
        lines.append(status_msgs.get(status, f"{t_name} was inflicted with {status}!"))
        if status == "slp":
            slot["sleep_turns"] = 2
        elif status == "frz":
            slot["freeze_turns"] = 3
        elif status == "tox":
            slot["toxic_counter"] = 1

        # Lum Berry / Chesto Berry check
        if slot.get("item") == "Lum Berry" or (slot.get("item") == "Chesto Berry" and status == "slp"):
            berry = slot["item"]
            slot["item"] = ""
            slot["status"] = None
            slot["unburden_active"] = slot.get("ability") == "Unburden"
            lines.append(f"{t_name}'s {berry} cured its {status} status!")

        return True

    def trigger_entry_ability(self, slot_id: str, ability: str) -> None:
        """Execute switch-in abilities (Intimidate, Drizzle, Drought, Terrains)."""
        slot = self.state["slots"].get(slot_id)
        if not slot or slot["current_hp_pct"] <= 0 or not ability:
            return
        lines: List[str] = []
        name = self.format_mon_name(slot_id)
        f = self.state["field"]
        item = slot.get("item", "")

        if ability == "Drought":
            f["weather"] = "sun"
            f["weather_turns"] = 8 if item == "Heat Rock" else 5
            lines.append(f"[{name}'s Drought intensified the sun's rays!]")
        elif ability == "Drizzle":
            f["weather"] = "rain"
            f["weather_turns"] = 8 if item == "Damp Rock" else 5
            lines.append(f"[{name}'s Drizzle made it rain!]")
        elif ability == "Snow Warning":
            f["weather"] = "snow"
            f["weather_turns"] = 8 if item == "Icy Rock" else 5
            lines.append(f"[{name}'s Snow Warning whipped up a snowstorm!]")
        elif ability == "Sand Stream":
            f["weather"] = "sand"
            f["weather_turns"] = 8 if item == "Smooth Rock" else 5
            lines.append(f"[{name}'s Sand Stream whipped up a sandstorm!]")
        elif ability == "Grassy Surge":
            f["terrain"] = "grassy"
            f["terrain_turns"] = 8 if item == "Terrain Extender" else 5
            lines.append("[Grass grew to cover the battlefield!]")
        elif ability == "Electric Surge":
            f["terrain"] = "electric"
            f["terrain_turns"] = 8 if item == "Terrain Extender" else 5
            lines.append("[An electric current ran across the battlefield!]")
        elif ability == "Psychic Surge":
            f["terrain"] = "psychic"
            f["terrain_turns"] = 8 if item == "Terrain Extender" else 5
            lines.append("[The battlefield got weird!]")
        elif ability == "Misty Surge":
            f["terrain"] = "misty"
            f["terrain_turns"] = 8 if item == "Terrain Extender" else 5
            lines.append("[Mist swirled around the battlefield!]")
        elif ability == "Intimidate":
            opp = "p2" if slot_id.startswith("p1") else "p1"
            lines.append(f"[{name}'s Intimidate]")
            for sid, s in self.state["slots"].items():
                if sid.startswith(opp) and s["current_hp_pct"] > 0:
                    t_name = self.format_mon_name(sid)
                    if s.get("ability") in ("Inner Focus", "Oblivious", "Own Tempo", "Scrappy"):
                        lines.append(f"{t_name}'s {s.get('ability')} prevents Intimidate!")
                    elif s.get("ability") == "Guard Dog":
                        self.apply_boost(s, {"atk": 1}, lines, source_self=True, ability_source="Guard Dog")
                    elif s.get("ability") == "Rattled":
                        self.apply_boost(s, {"atk": -1}, lines, source_self=False)
                        self.apply_boost(s, {"spe": 1}, lines, source_self=True, ability_source="Rattled")
                    else:
                        self.apply_boost(s, {"atk": -1}, lines, source_self=False)
        elif ability in ("Sword of Ruin", "Beads of Ruin", "Tablets of Ruin", "Vessel of Ruin"):
            lines.append(f"[{name}'s {ability} weakened the stats of all surrounding Pokémon!]")
        elif ability == "Download":
            opp = "p2" if slot_id.startswith("p1") else "p1"
            tot_def = sum(self.get_modified_stat(s, "def") for sid, s in self.state["slots"].items() if sid.startswith(opp) and s["current_hp_pct"] > 0)
            tot_spd = sum(self.get_modified_stat(s, "spd") for sid, s in self.state["slots"].items() if sid.startswith(opp) and s["current_hp_pct"] > 0)
            boost_stat = "atk" if tot_def < tot_spd else "spa"
            self.apply_boost(slot, {boost_stat: 1}, lines, source_self=True, ability_source="Download")

        if lines:
            self.log_blocks.append(lines)

    def perform_switch_in(self, slot_id: str, action: dict) -> None:
        """Execute Pokémon switch-in resetting volatiles and applying entry hazards."""
        slot = self.state["slots"].get(slot_id)
        if not slot:
            return
        new_sp = action.get("switch_to")
        if not new_sp:
            return
        old_name = self.format_mon_name(slot_id)
        # Natural Cure / Regenerator on switch out
        if slot["current_hp_pct"] > 0:
            if slot.get("ability") == "Natural Cure" and slot.get("status"):
                slot["status"] = None
            elif slot.get("ability") == "Regenerator":
                slot["current_hp_pct"] = min(100.0, round(slot["current_hp_pct"] + 33.3, 1))

        self.log_blocks.append([f"{old_name} was withdrawn!", f"{new_sp} was sent out!"])
        slot["species"] = new_sp
        slot["name"] = new_sp
        slot["current_hp_pct"] = float(action.get("incoming_hp_pct", 100.0))
        max_hp, stats = calculate_level_50_stats(new_sp, action.get("sp_spread", {}), action.get("nature", "Hardy"))
        slot["max_hp"] = max_hp
        slot["stats"] = stats
        slot["hp"] = max(1, round(max_hp * slot["current_hp_pct"] / 100.0))
        self.sync_hp_pct(slot)
        slot["boosts"] = {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
        slot["volatiles"] = {}
        slot["active_turns"] = 1
        slot["protected"] = False
        slot["flinched"] = False
        slot["moved_this_turn"] = False
        slot["unburden_active"] = False
        if new_sp in BASE_STATS_DB:
            slot["types"] = list(BASE_STATS_DB[new_sp]["types"])
            default_ab = BASE_STATS_DB[new_sp].get("abilities", {}).get("0", "")
        else:
            default_ab = ""
        slot["ability"] = action.get("ability") or default_ab
        slot["item"] = action.get("item", "")
        slot["status"] = action.get("status", None)
        self.trigger_entry_ability(slot_id, slot["ability"])

    def perform_mega_evo(self, slot_id: str) -> None:
        """Execute instantaneous Mega Evolution updating base stats and speed."""
        slot = self.state["slots"].get(slot_id)
        if not slot or slot["current_hp_pct"] <= 0:
            return
        base_sp = slot["species"]
        item = slot.get("item") or slot.get("mega_stone", "")
        item_norm = item.lower().replace("-", " ").strip()
        mega_name = None
        for candidate in [
            f"Mega {base_sp}", f"Mega {base_sp} Y", f"Mega {base_sp} X", f"Mega {base_sp} Z",
            f"{base_sp}-Mega-Y", f"{base_sp}-Mega-X", f"{base_sp}-Mega-Z", f"{base_sp}-Mega"
        ]:
            if candidate in BASE_STATS_DB:
                req = BASE_STATS_DB[candidate].get("requiredItem")
                if not req or (req.lower().replace("-", " ").strip() == item_norm):
                    mega_name = candidate
                    break
        if not mega_name:
            mega_name = f"Mega {base_sp}" if f"Mega {base_sp}" in BASE_STATS_DB else f"{base_sp}-Mega"
        if mega_name not in BASE_STATS_DB:
            return

        old_name = self.format_mon_name(slot_id)
        slot["species"] = mega_name
        slot["name"] = mega_name
        slot["types"] = list(BASE_STATS_DB[mega_name]["types"])
        mega_ab = BASE_STATS_DB[mega_name].get("abilities", {}).get("0")
        if mega_ab:
            slot["ability"] = mega_ab
        _, stats = calculate_level_50_stats(mega_name, slot.get("sp_spread", {}), slot.get("nature", "Hardy"))
        slot["stats"] = stats
        self.log_blocks.append([f"{old_name} has Mega Evolved into {self.format_mon_name(slot_id)}!"])
        self.trigger_entry_ability(slot_id, slot.get("ability", ""))

    def execute_activation_phase(self) -> None:
        """Exact port of Showdown BattleQueue order 103 (switch) and 104 (megaEvo) sorted by speed."""
        # 1. Switches (Order 103) sorted by current action speed
        switch_queue = []
        for slot_id, action in self.choices.items():
            slot = self.state["slots"].get(slot_id)
            if not slot or slot["current_hp_pct"] <= 0:
                continue
            if action.get("choice") == "switch" or (action.get("switch_to") and not action.get("move_name")):
                switch_queue.append((self.get_action_speed(slot_id), random.random(), slot_id, action))
        switch_queue.sort(key=lambda x: (x[0], x[1]), reverse=True)
        for _, _, slot_id, action in switch_queue:
            self.perform_switch_in(slot_id, action)

        # 2. Mega Evolutions (Order 104) sorted by current action speed
        mega_queue = []
        for slot_id, action in self.choices.items():
            slot = self.state["slots"].get(slot_id)
            if not slot or slot["current_hp_pct"] <= 0:
                continue
            if action.get("mega") and action.get("choice") != "switch":
                mega_queue.append((self.get_action_speed(slot_id), random.random(), slot_id))
        mega_queue.sort(key=lambda x: (x[0], x[1]), reverse=True)
        for _, _, slot_id in mega_queue:
            self.perform_mega_evo(slot_id)

    def get_modified_stat(self, slot: dict, stat_name: str, ignore_negative: bool = False, ignore_positive: bool = False) -> int:
        """Exact port of Showdown Pokemon#calculateStat & ModifyStat events (pokemon.ts:595)."""
        raw_stat = int(slot["stats"].get(stat_name, 80))
        boost = int(slot["boosts"].get(stat_name, 0))
        if ignore_negative and boost < 0:
            boost = 0
        if ignore_positive and boost > 0:
            boost = 0
        stat = apply_stat_boost(raw_stat, boost)

        ab = slot.get("ability", "")
        item = slot.get("item", "")
        status = slot.get("status")
        f = self.state["field"]
        weather = "sun" if ab == "Mega Sol" else f.get("weather")
        terrain = f.get("terrain")
        mod_4096 = 4096

        if stat_name == "atk":
            if ab in ("Huge Power", "Pure Power"):
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            if ab == "Guts" and status:
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            if ab == "Hustle":
                stat = sd_modify(stat, 1.5)
            if ab == "Gorilla Tactics":
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            if ab == "Defeatist" and slot["current_hp_pct"] <= 50.0:
                mod_4096 = sd_chain_mod(mod_4096, 0.5)
            if ab == "Flower Gift" and weather == "sun":
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            if item == "Choice Band":
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            elif item == "Thick Club" and "Marowak" in slot["species"]:
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            elif item == "Light Ball" and "Pikachu" in slot["species"]:
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            # Tablets of Ruin on field
            if ab != "Tablets of Ruin" and any(s.get("ability") == "Tablets of Ruin" and s["current_hp_pct"] > 0 for s in self.state["slots"].values()):
                mod_4096 = sd_chain_mod(mod_4096, 0.75)

        elif stat_name == "def":
            if weather == "snow" and "Ice" in slot.get("types", []):
                stat = sd_modify(stat, 1.5)
            if ab == "Fur Coat":
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            if ab == "Marvel Scale" and status:
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            if ab == "Grass Pelt" and terrain == "grassy":
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            if item == "Eviolite":
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            if ab != "Sword of Ruin" and any(s.get("ability") == "Sword of Ruin" and s["current_hp_pct"] > 0 for s in self.state["slots"].values()):
                mod_4096 = sd_chain_mod(mod_4096, 0.75)

        elif stat_name == "spa":
            if ab == "Solar Power" and weather == "sun":
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            if ab == "Defeatist" and slot["current_hp_pct"] <= 50.0:
                mod_4096 = sd_chain_mod(mod_4096, 0.5)
            if item == "Choice Specs":
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            elif item == "Light Ball" and "Pikachu" in slot["species"]:
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            if ab != "Vessel of Ruin" and any(s.get("ability") == "Vessel of Ruin" and s["current_hp_pct"] > 0 for s in self.state["slots"].values()):
                mod_4096 = sd_chain_mod(mod_4096, 0.75)

        elif stat_name == "spd":
            if weather == "sand" and "Rock" in slot.get("types", []):
                stat = sd_modify(stat, 1.5)
            if ab == "Flower Gift" and weather == "sun":
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            if item == "Assault Vest":
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            elif item == "Eviolite":
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            if ab != "Beads of Ruin" and any(s.get("ability") == "Beads of Ruin" and s["current_hp_pct"] > 0 for s in self.state["slots"].values()):
                mod_4096 = sd_chain_mod(mod_4096, 0.75)

        elif stat_name == "spe":
            side = self.state["p1"] if slot["slot_id"].startswith("p1") else self.state["p2"]
            if side.get("tailwind_turns", 0) > 0:
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            if ab == "Swift Swim" and weather == "rain" and item != "Utility Umbrella":
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            elif ab == "Chlorophyll" and weather == "sun" and item != "Utility Umbrella":
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            elif ab == "Sand Rush" and weather == "sand":
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            elif ab == "Slush Rush" and weather == "snow":
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            elif ab == "Surge Surfer" and terrain == "electric":
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            elif ab == "Unburden" and (slot.get("unburden_active") or not item):
                mod_4096 = sd_chain_mod(mod_4096, 2.0)
            elif ab == "Quick Feet" and status:
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            if item == "Choice Scarf":
                mod_4096 = sd_chain_mod(mod_4096, 1.5)
            elif item == "Iron Ball":
                mod_4096 = sd_chain_mod(mod_4096, 0.5)
            if status == "par" and ab != "Quick Feet":
                mod_4096 = sd_chain_mod(mod_4096, 0.5)

        return max(1, apply_mod_4096(stat, mod_4096))

    def get_effective_speed(self, slot_id: str) -> float:
        """Calculate dynamic speed considering stage boosts, Tailwind, and items."""
        slot = self.state["slots"].get(slot_id)
        if not slot or slot["current_hp_pct"] <= 0:
            return -999999.0
        return float(self.get_modified_stat(slot, "spe"))

    def get_action_speed(self, slot_id: str) -> float:
        """Exact port of Showdown Champions Pokemon#getActionSpeed (champions/scripts.ts:46)."""
        spe = self.get_effective_speed(slot_id)
        if self.state["field"].get("trick_room_turns", 0) > 0:
            return -spe
        return spe

    def get_move_priority(self, slot: dict, move_name: str, move_data: dict) -> float:
        """Exact port of Showdown Battle#getActionSpeed priority modifiers (battle.ts:2696)."""
        priority = float(move_data.get("priority", 0))
        ab = slot.get("ability", "")
        cat = move_data.get("cat", "Status")
        m_type = move_data.get("type", "Normal")
        f = self.state["field"]

        if ab == "Prankster" and cat == "Status":
            priority += 1.0
        elif ab == "Gale Wings" and m_type == "Flying" and slot["current_hp_pct"] >= 99.9:
            priority += 1.0
        elif ab == "Triage" and ("heal" in move_data.get("flags", []) or move_data.get("drain") or move_data.get("heal")):
            priority += 3.0

        if move_name == "Grassy Glide" and f.get("terrain") == "grassy" and not is_airborne(slot, f):
            priority += 1.0

        return priority

    def resolve_action_order(self) -> List[Tuple[str, dict]]:
        """Initial sort of move queue; mid-turn dynamic sorting happens inside run_turn."""
        queue = []
        for slot_id, action in self.choices.items():
            slot = self.state["slots"].get(slot_id)
            if not slot or slot["current_hp_pct"] <= 0:
                continue
            if action.get("choice") == "switch" or (action.get("switch_to") and not action.get("move_name")):
                continue
            move_name = action.get("move_name", "")
            move = MOVE_DB.get(move_name, {})
            priority = self.get_move_priority(slot, move_name, move)
            spe = self.get_action_speed(slot_id)
            queue.append((priority, spe, random.random(), slot_id, action))

        queue.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        return [(item[3], item[4]) for item in queue]

    def compute_dynamic_base_power(self, attacker: dict, defender: dict, move_data: dict) -> Tuple[int, str]:
        """Handles Showdown basePowerCallback and ModifyType (Pixilate, Weather Ball, Knock Off, etc.)."""
        move_name = move_data.get("name", "")
        cat = move_data.get("cat", "Status")
        pwr = int(move_data.get("power", 0))
        m_type = move_data.get("type", "Normal")
        flags = move_data.get("flags", [])
        atk_ability = attacker.get("ability", "")
        f = self.state["field"]
        weather = "sun" if atk_ability == "Mega Sol" else f.get("weather")
        terrain = f.get("terrain")

        # 1. Variable BP / Type Callbacks
        if move_name == "Weather Ball":
            if weather == "sun" and attacker.get("item") != "Utility Umbrella":
                m_type, pwr = "Fire", 100
            elif weather == "rain" and attacker.get("item") != "Utility Umbrella":
                m_type, pwr = "Water", 100
            elif weather == "sand":
                m_type, pwr = "Rock", 100
            elif weather == "snow":
                m_type, pwr = "Ice", 100
        elif move_name == "Terrain Pulse" and not is_airborne(attacker, f) and terrain:
            pwr = 100
            m_type = {"electric": "Electric", "grassy": "Grass", "psychic": "Psychic", "misty": "Fairy"}.get(terrain, "Normal")
        elif move_name == "Expanding Force" and terrain == "psychic" and not is_airborne(attacker, f):
            pwr = 120
        elif move_name == "Rising Voltage" and terrain == "electric" and not is_airborne(defender, f):
            pwr = 140
        elif move_name == "Misty Explosion" and terrain == "misty" and not is_airborne(attacker, f):
            pwr = 150
        elif move_name in ("Eruption", "Water Spout", "Dragon Energy"):
            max_hp = max(1, int(attacker.get("max_hp", 1)))
            cur_hp = int(attacker.get("hp", max_hp))
            pwr = max(1, trunc(150 * cur_hp / max_hp))
        elif move_name == "Acrobatics" and not attacker.get("item"):
            pwr = 110
        elif move_name == "Facade" and attacker.get("status") in ("brn", "par", "psn", "tox"):
            pwr = 140
        elif move_name in ("Hex", "Infernal Parade") and defender.get("status"):
            pwr *= 2
        elif move_name in ("Venoshock", "Barb Barrage") and defender.get("status") in ("psn", "tox"):
            pwr *= 2
        elif move_name == "Knock Off":
            def_item = defender.get("item", "")
            req_item = BASE_STATS_DB.get(defender["species"], {}).get("requiredItem")
            if def_item and not req_item and not def_item.endswith("ite") and not def_item.endswith("ite X") and not def_item.endswith("ite Y") and not def_item.endswith("ite Z"):
                pwr = sd_modify(pwr, 6144, 4096)
        elif move_name in ("Heavy Slam", "Heat Crash"):
            aw = float(BASE_STATS_DB.get(attacker["species"], {}).get("weightkg", 50.0))
            dw = max(0.1, float(BASE_STATS_DB.get(defender["species"], {}).get("weightkg", 50.0)))
            ratio = aw / dw
            pwr = 120 if ratio >= 5 else (100 if ratio >= 4 else (80 if ratio >= 3 else (60 if ratio >= 2 else 40)))
        elif move_name in ("Low Kick", "Grass Knot"):
            dw = float(BASE_STATS_DB.get(defender["species"], {}).get("weightkg", 50.0))
            pwr = 120 if dw >= 200 else (100 if dw >= 100 else (80 if dw >= 50 else (60 if dw >= 25 else (40 if dw >= 10 else 20))))

        # 2. Type-changing abilities
        type_changed_boost = False
        if m_type == "Normal" and cat != "Status":
            if atk_ability == "Pixilate":
                m_type, type_changed_boost = "Fairy", True
            elif atk_ability == "Aerilate":
                m_type, type_changed_boost = "Flying", True
            elif atk_ability == "Refrigerate":
                m_type, type_changed_boost = "Ice", True
            elif atk_ability == "Galvanize":
                m_type, type_changed_boost = "Electric", True
            elif atk_ability == "Dragonize":
                m_type, type_changed_boost = "Dragon", True
        elif atk_ability == "Liquid Voice" and "sound" in flags:
            m_type = "Water"

        # 3. Chain Base Power Modifiers (Showdown onBasePower 4096 chain)
        bp_mod = 4096
        if type_changed_boost:
            bp_mod = sd_chain_mod(bp_mod, 4915, 4096)
        if atk_ability == "Technician" and pwr <= 60:
            bp_mod = sd_chain_mod(bp_mod, 6144, 4096)
        if atk_ability == "Iron Fist" and "punch" in flags:
            bp_mod = sd_chain_mod(bp_mod, 4915, 4096)
        if atk_ability == "Strong Jaw" and "bite" in flags:
            bp_mod = sd_chain_mod(bp_mod, 6144, 4096)
        if atk_ability == "Mega Launcher" and "pulse" in flags:
            bp_mod = sd_chain_mod(bp_mod, 6144, 4096)
        if atk_ability == "Tough Claws" and "contact" in flags:
            bp_mod = sd_chain_mod(bp_mod, 5325, 4096)
        if atk_ability == "Sharpness" and "slicing" in flags:
            bp_mod = sd_chain_mod(bp_mod, 6144, 4096)
        if atk_ability == "Sheer Force" and (move_data.get("secondary") or move_data.get("secondaries")):
            bp_mod = sd_chain_mod(bp_mod, 5325, 4096)
        if atk_ability == "Reckless" and move_data.get("recoil"):
            bp_mod = sd_chain_mod(bp_mod, 4915, 4096)
        if atk_ability in ("Blaze", "Overgrow", "Torrent", "Swarm") and attacker["current_hp_pct"] <= 33.3:
            blaze_type = {"Blaze": "Fire", "Overgrow": "Grass", "Torrent": "Water", "Swarm": "Bug"}[atk_ability]
            if m_type == blaze_type:
                bp_mod = sd_chain_mod(bp_mod, 6144, 4096)
        if atk_ability == "Sand Force" and weather == "sand" and m_type in ("Rock", "Ground", "Steel"):
            bp_mod = sd_chain_mod(bp_mod, 5325, 4096)

        # Helping Hand
        if attacker.get("helping_hand_mult", 1.0) > 1.0:
            bp_mod = sd_chain_mod(bp_mod, 6144, 4096)

        # Charge volatile on Electric moves
        if m_type == "Electric" and attacker.get("volatiles", {}).get("charge"):
            bp_mod = sd_chain_mod(bp_mod, 8192, 4096)

        # Ally Steely Spirit / Battery / Power Spot
        ally_prefix = attacker["slot_id"][:2]
        for sid, s in self.state["slots"].items():
            if sid.startswith(ally_prefix) and s["current_hp_pct"] > 0:
                if s.get("ability") == "Steely Spirit" and m_type == "Steel":
                    bp_mod = sd_chain_mod(bp_mod, 6144, 4096)
                elif sid != attacker["slot_id"] and s.get("ability") == "Battery" and cat == "Special":
                    bp_mod = sd_chain_mod(bp_mod, 5325, 4096)
                elif sid != attacker["slot_id"] and s.get("ability") == "Power Spot":
                    bp_mod = sd_chain_mod(bp_mod, 5325, 4096)

        # Terrain Base Power Modifiers
        if not is_airborne(attacker, f):
            if terrain == "electric" and m_type == "Electric":
                bp_mod = sd_chain_mod(bp_mod, 5325, 4096)
            elif terrain == "grassy" and m_type == "Grass":
                bp_mod = sd_chain_mod(bp_mod, 5325, 4096)
            elif terrain == "psychic" and m_type == "Psychic":
                bp_mod = sd_chain_mod(bp_mod, 5325, 4096)
        if not is_airborne(defender, f):
            if terrain == "misty" and m_type == "Dragon":
                bp_mod = sd_chain_mod(bp_mod, 2048, 4096)
            elif terrain == "grassy" and move_name in ("Earthquake", "Bulldoze", "Magnitude"):
                bp_mod = sd_chain_mod(bp_mod, 2048, 4096)

        # Fairy Aura / Dark Aura
        aura_break = any(s.get("ability") == "Aura Break" and s["current_hp_pct"] > 0 for s in self.state["slots"].values())
        if m_type == "Fairy" and any(s.get("ability") == "Fairy Aura" and s["current_hp_pct"] > 0 for s in self.state["slots"].values()):
            bp_mod = sd_chain_mod(bp_mod, 3072 if aura_break else 5448, 4096)
        elif m_type == "Dark" and any(s.get("ability") == "Dark Aura" and s["current_hp_pct"] > 0 for s in self.state["slots"].values()):
            bp_mod = sd_chain_mod(bp_mod, 3072 if aura_break else 5448, 4096)

        # Type-boosting items & Muscle Band / Wise Glasses
        atk_item = attacker.get("item", "")
        if TYPE_BOOST_ITEMS.get(atk_item) == m_type:
            bp_mod = sd_chain_mod(bp_mod, 4915, 4096)
        elif atk_item == "Muscle Band" and cat == "Physical":
            bp_mod = sd_chain_mod(bp_mod, 4505, 4096)
        elif atk_item == "Wise Glasses" and cat == "Special":
            bp_mod = sd_chain_mod(bp_mod, 4505, 4096)

        final_bp = max(1, apply_mod_4096(pwr, bp_mod))
        return final_bp, m_type

    def calculate_damage_full(
        self, attacker: dict, defender: dict, move_data: dict, is_spread: bool, roll: float, hit_num: int = 1
    ) -> Tuple[int, float, float, bool]:
        """
        Exact port of Showdown BattleActions#getDamage & Champions Scripts#modifyDamage
        (battle-actions.ts:1639 & data/mods/champions/scripts.ts:196).
        Returns (damage_hp, damage_pct, type_effectiveness, is_crit).
        """
        move_name = move_data.get("name", "")
        cat = move_data.get("cat", "Status")
        flags = move_data.get("flags", [])
        atk_ability = attacker.get("ability", "")
        def_ability = defender.get("ability", "")
        mold_breaker = atk_ability in ("Mold Breaker", "Teravolt", "Turboblaze")

        # Fixed / Level / Super Fang / Ruination damage callbacks
        max_hp = max(1, int(defender.get("max_hp", 1)))
        cur_hp = max(1, int(defender.get("hp", max_hp)))
        if move_name in ("Super Fang", "Nature's Madness", "Ruination"):
            d_val = max(1, cur_hp // 2)
            return d_val, round((d_val / max_hp) * 100.0, 1), 1.0, False
        elif move_name == "Final Gambit":
            d_val = max(1, int(attacker.get("hp", 1)))
            return d_val, round((d_val / max_hp) * 100.0, 1), 1.0, False
        elif move_name in ("Night Shade", "Seismic Toss"):
            d_val = 50
            return d_val, round((d_val / max_hp) * 100.0, 1), 1.0, False

        base_power, m_type = self.compute_dynamic_base_power(attacker, defender, move_data)
        scrappy = atk_ability in ("Scrappy", "Mind's Eye")
        eff = get_type_effectiveness(m_type, defender.get("types", []), move_name=move_name, scrappy=scrappy)
        if eff == 0.0:
            return 0, 0.0, 0.0, False

        # Critical Hit check
        is_crit = bool(move_data.get("willCrit", False))
        if (not mold_breaker and def_ability in ("Battle Armor", "Shell Armor")):
            is_crit = False

        # Offensive & Defensive stat selection (Body Press, Foul Play, Psyshock, Sacred Sword, Unaware)
        off_source = defender if move_data.get("overrideOffensivePokemon") == "target" else attacker
        atk_stat_name = move_data.get("overrideOffensiveStat") or ("atk" if cat == "Physical" else "spa")
        def_stat_name = move_data.get("overrideDefensiveStat") or ("def" if cat == "Physical" else "spd")

        ignore_neg_off = is_crit or bool(move_data.get("ignoreNegativeOffensive")) or (not mold_breaker and def_ability == "Unaware" and off_source is attacker)
        ignore_pos_def = is_crit or bool(move_data.get("ignoreDefensive")) or (atk_ability == "Unaware")

        a = self.get_modified_stat(off_source, atk_stat_name, ignore_negative=ignore_neg_off, ignore_positive=(not mold_breaker and def_ability == "Unaware" and off_source is attacker))
        if atk_ability == "Fire Mane" and m_type == "Fire":
            a = sd_modify(a, 1.5)
        elif not mold_breaker and def_ability == "Thick Fat" and m_type in ("Fire", "Ice"):
            a = sd_modify(a, 0.5)
        elif not mold_breaker and def_ability == "Purifying Salt" and m_type == "Ghost":
            a = sd_modify(a, 0.5)
        elif not mold_breaker and def_ability == "Heatproof" and m_type == "Fire":
            a = sd_modify(a, 0.5)

        d = self.get_modified_stat(defender, def_stat_name, ignore_negative=(atk_ability == "Unaware"), ignore_positive=ignore_pos_def)

        # Showdown baseDamage = tr(tr(tr(tr(2 * L / 5 + 2) * basePower * attack) / defense) / 50)
        base_damage = trunc(trunc(trunc(22 * base_power * a) / d) / 50)

        # --- Champions Scripts#modifyDamage (champions/scripts.ts:196) ---
        base_damage += 2

        # 1. Spread / Parental Bond modifier
        if is_spread:
            base_damage = sd_modify(base_damage, 0.75)
        elif atk_ability == "Parental Bond" and hit_num > 1:
            base_damage = sd_modify(base_damage, 0.25)

        # 2. Weather modifier
        f = self.state["field"]
        weather = "sun" if atk_ability == "Mega Sol" else f.get("weather")
        if defender.get("item") == "Utility Umbrella" and weather in ("sun", "rain"):
            weather = None
        if weather == "sun":
            if m_type == "Fire" or move_name == "Hydro Steam":
                base_damage = sd_modify(base_damage, 1.5)
            elif m_type == "Water":
                base_damage = sd_modify(base_damage, 0.5)
        elif weather == "rain":
            if m_type == "Water":
                base_damage = sd_modify(base_damage, 1.5)
            elif m_type == "Fire":
                base_damage = sd_modify(base_damage, 0.5)

        # 3. Critical hit (1.5x)
        if is_crit:
            base_damage = trunc(base_damage * 1.5)

        # 4. Randomizer: tr(tr(baseDamage * (100 - random(16))) / 100)
        roll_int = int(round(roll * 100))
        base_damage = trunc(trunc(base_damage * roll_int) / 100)

        # 5. STAB
        if m_type in attacker.get("types", []):
            stab = 2.0 if atk_ability == "Adaptability" else 1.5
            base_damage = sd_modify(base_damage, stab)

        # 6. Type Effectiveness (integer shifts per stage, champions/scripts.ts:266)
        type_mod = int(round(math.log2(eff)))
        if type_mod > 0:
            for _ in range(type_mod):
                base_damage *= 2
        elif type_mod < 0:
            for _ in range(-type_mod):
                base_damage = trunc(base_damage / 2)

        # 7. Burn penalty
        if attacker.get("status") == "brn" and cat == "Physical" and atk_ability != "Guts" and move_name != "Facade":
            base_damage = sd_modify(base_damage, 0.5)

        # 8. Final ModifyDamage chain
        final_mod = 4096
        def_side = self.state["p1"] if defender["slot_id"].startswith("p1") else self.state["p2"]
        if not is_crit and atk_ability != "Infiltrator" and move_name not in ("Brick Break", "Psychic Fangs", "Raging Bull"):
            if cat == "Special" and (def_side.get("light_screen_turns", 0) > 0 or def_side.get("aurora_veil_turns", 0) > 0):
                final_mod = sd_chain_mod(final_mod, 2732, 4096)
            elif cat == "Physical" and (def_side.get("reflect_turns", 0) > 0 or def_side.get("aurora_veil_turns", 0) > 0):
                final_mod = sd_chain_mod(final_mod, 2732, 4096)

        if not mold_breaker:
            if def_ability in ("Multiscale", "Shadow Shield") and defender["current_hp_pct"] >= 99.9:
                final_mod = sd_chain_mod(final_mod, 0.5)
            if def_ability == "Aura Guard" and "contact" in flags:
                final_mod = sd_chain_mod(final_mod, 0.5)
            if def_ability == "Fluffy":
                if "contact" in flags:
                    final_mod = sd_chain_mod(final_mod, 0.5)
                if m_type == "Fire":
                    final_mod = sd_chain_mod(final_mod, 2.0)
            if def_ability == "Ice Scales" and cat == "Special":
                final_mod = sd_chain_mod(final_mod, 0.5)
            if def_ability in ("Filter", "Solid Rock") and eff > 1.0:
                final_mod = sd_chain_mod(final_mod, 0.75)
        if def_ability == "Prism Armor" and eff > 1.0:
            final_mod = sd_chain_mod(final_mod, 0.75)

        # Ally Friend Guard
        def_prefix = defender["slot_id"][:2]
        if not mold_breaker and any(
            sid.startswith(def_prefix) and sid != defender["slot_id"] and s["current_hp_pct"] > 0 and s.get("ability") == "Friend Guard"
            for sid, s in self.state["slots"].items()
        ):
            final_mod = sd_chain_mod(final_mod, 0.75)

        if atk_ability == "Tinted Lens" and eff < 1.0:
            final_mod = sd_chain_mod(final_mod, 2.0)
        if atk_ability == "Sniper" and is_crit:
            final_mod = sd_chain_mod(final_mod, 1.5)
        if atk_ability == "Neuroforce" and eff > 1.0:
            final_mod = sd_chain_mod(final_mod, 1.25)

        atk_item = attacker.get("item", "")
        if atk_item == "Expert Belt" and eff > 1.0:
            final_mod = sd_chain_mod(final_mod, 4915, 4096)
        elif atk_item == "Life Orb":
            final_mod = sd_chain_mod(final_mod, 5324, 4096)

        base_damage = apply_mod_4096(base_damage, final_mod)

        # 9. Bypass Protect 0.25x modifier (champions/scripts.ts:298)
        if defender.get("protected"):
            base_damage = sd_modify(base_damage, 0.25)

        # 10. Minimum 1 damage & 16-bit truncation
        final_hp_dmg = max(1, trunc(base_damage, 16))
        dmg_pct = round((final_hp_dmg / max_hp) * 100.0, 1)
        return final_hp_dmg, dmg_pct, eff, is_crit

    def calculate_damage(self, attacker: dict, defender: dict, move_data: dict, is_spread: bool, roll: float) -> Tuple[float, float]:
        """Backward-compatible wrapper returning (dmg_pct, eff)."""
        _, dmg_pct, eff, _ = self.calculate_damage_full(attacker, defender, move_data, is_spread, roll)
        return dmg_pct, eff

    def check_target_immunity_and_absorption(self, user: dict, tgt: dict, move_name: str, move_data: dict, m_type: str, action_lines: List[str]) -> bool:
        """Returns True if the target is immune/absorbs the move (and logs the effect)."""
        tgt_name = self.format_mon_name(tgt["slot_id"])
        def_ab = tgt.get("ability", "")
        mold_breaker = user.get("ability") in ("Mold Breaker", "Teravolt", "Turboblaze")
        flags = move_data.get("flags", [])
        cat = move_data.get("cat", "Status")
        f = self.state["field"]

        # Prankster vs Dark-type immunity
        if user.get("ability") == "Prankster" and cat == "Status" and "Dark" in tgt.get("types", []) and not tgt["slot_id"].startswith(user["slot_id"][:2]):
            action_lines.append(f"It doesn't affect {tgt_name}...")
            return True

        # Good as Gold
        if not mold_breaker and def_ab == "Good as Gold" and cat == "Status" and tgt["slot_id"] != user["slot_id"]:
            action_lines.append(f"{tgt_name}'s Good as Gold blocks {move_name}!")
            return True

        # Powder move immunity (Grass-type, Overcoat, Safety Goggles)
        if "powder" in flags and tgt["slot_id"] != user["slot_id"]:
            if "Grass" in tgt.get("types", []) or (not mold_breaker and def_ab == "Overcoat") or tgt.get("item") == "Safety Goggles":
                action_lines.append(f"It doesn't affect {tgt_name}...")
                return True

        # Soundproof / Bulletproof / Wind Rider
        if not mold_breaker and tgt["slot_id"] != user["slot_id"]:
            if def_ab == "Soundproof" and "sound" in flags:
                action_lines.append(f"{tgt_name}'s Soundproof blocks {move_name}!")
                return True
            if def_ab == "Bulletproof" and "bullet" in flags:
                action_lines.append(f"{tgt_name}'s Bulletproof blocks {move_name}!")
                return True
            if def_ab == "Wind Rider" and "wind" in flags:
                self.apply_boost(tgt, {"atk": 1}, action_lines, source_self=True, ability_source="Wind Rider")
                return True

        # Ground immunity (Flying, Levitate, Eelevate, Air Balloon)
        if m_type == "Ground" and cat != "Status" and move_name != "Thousand Arrows":
            if is_airborne(tgt, f):
                if not (mold_breaker and def_ab in ("Levitate", "Eelevate") and "Flying" not in tgt.get("types", []) and tgt.get("item") != "Air Balloon"):
                    action_lines.append(f"It doesn't affect {tgt_name}...")
                    return True

        # Elemental absorption abilities
        if not mold_breaker and tgt["slot_id"] != user["slot_id"]:
            if m_type == "Water" and def_ab in ("Water Absorb", "Dry Skin"):
                self.heal_hp(tgt, max(1, tgt["max_hp"] // 4), action_lines, f"{tgt_name}'s {def_ab} restored its HP!")
                return True
            if m_type == "Water" and def_ab == "Storm Drain":
                self.apply_boost(tgt, {"spa": 1}, action_lines, source_self=True, ability_source="Storm Drain")
                return True
            if m_type == "Electric" and def_ab == "Volt Absorb":
                self.heal_hp(tgt, max(1, tgt["max_hp"] // 4), action_lines, f"{tgt_name}'s Volt Absorb restored its HP!")
                return True
            if m_type == "Electric" and def_ab == "Lightning Rod":
                self.apply_boost(tgt, {"spa": 1}, action_lines, source_self=True, ability_source="Lightning Rod")
                return True
            if m_type == "Electric" and def_ab == "Motor Drive":
                self.apply_boost(tgt, {"spe": 1}, action_lines, source_self=True, ability_source="Motor Drive")
                return True
            if m_type == "Fire" and def_ab == "Flash Fire":
                action_lines.append(f"{tgt_name}'s Flash Fire boosted its Fire-type moves!")
                return True
            if m_type == "Fire" and def_ab == "Well-Baked Body":
                self.apply_boost(tgt, {"def": 2}, action_lines, source_self=True, ability_source="Well-Baked Body")
                return True
            if m_type == "Grass" and def_ab == "Sap Sipper":
                self.apply_boost(tgt, {"atk": 1}, action_lines, source_self=True, ability_source="Sap Sipper")
                return True
            if m_type == "Ground" and def_ab == "Earth Eater":
                self.heal_hp(tgt, max(1, tgt["max_hp"] // 4), action_lines, f"{tgt_name}'s Earth Eater restored its HP!")
                return True

        # Standard type chart 0x immunity
        scrappy = user.get("ability") in ("Scrappy", "Mind's Eye")
        if cat != "Status" and get_type_effectiveness(m_type, tgt.get("types", []), move_name=move_name, scrappy=scrappy) == 0.0:
            action_lines.append(f"It doesn't affect {tgt_name}...")
            return True

        return False

    def execute_single_action(self, slot_id: str, action: dict, roll_mode: str, fixed_roll: float) -> None:
        """Execute single offensive, status, or protect action within turn."""
        user = self.state["slots"].get(slot_id)
        if not user or user["current_hp_pct"] <= 0:
            return

        user_name = self.format_mon_name(slot_id)
        move_name = action.get("move_name", "")
        move_data = MOVE_DB.get(move_name)
        if not move_data:
            return

        # 1. BeforeMove checks (Flinch, Sleep, Freeze, Paralysis, Taunt, Disable)
        if user.get("flinched"):
            user["flinched"] = False
            self.log_blocks.append([f"{user_name} flinched and couldn't move!"])
            return

        status = user.get("status")
        if status == "slp":
            turns = int(user.get("sleep_turns", 1)) - 1
            user["sleep_turns"] = turns
            if turns <= 0:
                user["status"] = None
                self.log_blocks.append([f"{user_name} woke up!"])
            elif move_name not in ("Sleep Talk", "Snore"):
                self.log_blocks.append([f"{user_name} is fast asleep."])
                return

        if status == "frz":
            flags = move_data.get("flags", [])
            turns = int(user.get("freeze_turns", 1)) - 1
            user["freeze_turns"] = turns
            thaw = ("defrost" in flags) or (turns <= 0) or (roll_mode == "random" and random.randint(1, 4) == 1)
            if thaw:
                user["status"] = None
                self.log_blocks.append([f"{user_name} thawed out!"])
            else:
                self.log_blocks.append([f"{user_name} is frozen solid!"])
                return

        if status == "par" and roll_mode == "random" and random.randint(1, 8) == 1:
            self.log_blocks.append([f"{user_name} is paralyzed! It can't move!"])
            return

        if user.get("volatiles", {}).get("taunt", 0) > 0 and move_data.get("cat") == "Status":
            self.log_blocks.append([f"{user_name} can't use {move_name} after the taunt!"])
            return

        action_lines = [f"{user_name} used {move_name}!"]
        user["moved_this_turn"] = True
        f = self.state["field"]
        cat = move_data.get("cat", "Status")
        flags = move_data.get("flags", [])

        # Throat Spray on sound moves
        if "sound" in flags and user.get("item") == "Throat Spray":
            user["item"] = ""
            user["unburden_active"] = user.get("ability") == "Unburden"
            self.apply_boost(user, {"spa": 1}, action_lines, source_self=True)

        # Fake Out / First Impression turn 1 check
        if move_name in ("Fake Out", "First Impression") and int(user.get("active_turns", 1)) > 1:
            action_lines.append("But it failed!")
            self.log_blocks.append(action_lines)
            return

        # 2. Protect / Wide Guard / Quick Guard / Redirection / Field / Side Condition Moves
        if move_name in PROTECT_MOVES:
            user["protected"] = True
            user["protect_type"] = move_name
            action_lines.append(f"{user_name} protected itself!")
            self.log_blocks.append(action_lines)
            return
        elif move_name == "Wide Guard":
            side_key = "p1" if slot_id.startswith("p1") else "p2"
            self.wide_guard_sides.add(side_key)
            action_lines.append(f"Wide Guard protected {user_name}'s team!")
            self.log_blocks.append(action_lines)
            return
        elif move_name == "Quick Guard":
            side_key = "p1" if slot_id.startswith("p1") else "p2"
            self.quick_guard_sides.add(side_key)
            action_lines.append(f"Quick Guard protected {user_name}'s team!")
            self.log_blocks.append(action_lines)
            return
        elif move_name in ("Follow Me", "Rage Powder"):
            side_key = "p1" if slot_id.startswith("p1") else "p2"
            self.redirect_target[side_key] = slot_id
            user["volatiles"]["ragepowder" if move_name == "Rage Powder" else "followme"] = True
            action_lines.append(f"{user_name} became the center of attention!")
            self.log_blocks.append(action_lines)
            return
        elif move_name == "Helping Hand":
            ally_prefix = slot_id[:2]
            for sid, s in self.state["slots"].items():
                if sid.startswith(ally_prefix) and sid != slot_id and s["current_hp_pct"] > 0:
                    s["helping_hand_mult"] = 1.5
                    action_lines.append(f"{user_name} is ready to help {self.format_mon_name(sid)}!")
            self.log_blocks.append(action_lines)
            return
        elif move_name == "Tailwind":
            side = self.state["p1"] if slot_id.startswith("p1") else self.state["p2"]
            side["tailwind_turns"] = 4
            side_str = "Your team" if slot_id.startswith(self.pov) else "The opposing team"
            action_lines.append(f"The Tailwind blew from behind {side_str.lower()}!")
            # Check Wind Rider on allies
            for sid, s in self.state["slots"].items():
                if sid.startswith(slot_id[:2]) and s["current_hp_pct"] > 0 and s.get("ability") == "Wind Rider":
                    self.apply_boost(s, {"atk": 1}, action_lines, source_self=True, ability_source="Wind Rider")
            self.log_blocks.append(action_lines)
            return
        elif move_name == "Trick Room":
            if f.get("trick_room_turns", 0) > 0:
                f["trick_room_turns"] = 0
                action_lines.append(f"{user_name} twisted the dimensions back to normal!")
            else:
                f["trick_room_turns"] = 5
                action_lines.append(f"{user_name} twisted the dimensions!")
            self.log_blocks.append(action_lines)
            return
        elif move_name in ("Reflect", "Light Screen", "Aurora Veil"):
            side = self.state["p1"] if slot_id.startswith("p1") else self.state["p2"]
            if move_name == "Aurora Veil" and f.get("weather") != "snow":
                action_lines.append("But it failed!")
                self.log_blocks.append(action_lines)
                return
            dur = 8 if user.get("item") == "Light Clay" else 5
            key = {"Reflect": "reflect_turns", "Light Screen": "light_screen_turns", "Aurora Veil": "aurora_veil_turns"}[move_name]
            side[key] = dur
            side_str = "your team" if slot_id.startswith(self.pov) else "the opposing team"
            action_lines.append(f"{move_name} made {side_str} stronger against attacks!")
            self.log_blocks.append(action_lines)
            return
        elif move_data.get("weather"):
            w_map = {"SunnyDay": "sun", "RainDance": "rain", "Sandstorm": "sand", "Snow": "snow", "Hail": "snow"}
            w_val = w_map.get(move_data["weather"])
            if w_val:
                f["weather"] = w_val
                f["weather_turns"] = 5
                action_lines.append(f"The weather changed to {w_val}!")
                self.log_blocks.append(action_lines)
                return
        elif move_data.get("terrain"):
            t_map = {"electricterrain": "electric", "grassyterrain": "grassy", "psychicterrain": "psychic", "mistyterrain": "misty"}
            t_val = t_map.get(move_data["terrain"].lower())
            if t_val:
                f["terrain"] = t_val
                f["terrain_turns"] = 8 if user.get("item") == "Terrain Extender" else 5
                action_lines.append(f"The battlefield became {t_val} terrain!")
                self.log_blocks.append(action_lines)
                return

        # 3. Electro Shot / Solar Beam / Meteor Beam two-turn charge handling
        weather = "sun" if user.get("ability") == "Mega Sol" else f.get("weather")
        if move_name == "Electro Shot":
            self.apply_boost(user, {"spa": 1}, action_lines, source_self=True)
            if weather != "rain":
                action_lines.append(f"{user_name} absorbed electricity!")
                self.log_blocks.append(action_lines)
                return
        elif move_name in ("Solar Beam", "Solar Blade") and weather != "sun":
            action_lines.append(f"{user_name} absorbed light!")
            self.log_blocks.append(action_lines)
            return
        elif move_name == "Meteor Beam":
            self.apply_boost(user, {"spa": 1}, action_lines, source_self=True)
            action_lines.append(f"{user_name} is overflowing with space power!")
            self.log_blocks.append(action_lines)
            return

        # 4. Self-targeting Heal & Boost Status moves (Recover, Nasty Plot, Dragon Dance, Calm Mind, Swords Dance, etc.)
        if move_data.get("target") in ("self", "allies", "adjacentAllyOrSelf") and cat == "Status":
            tgt_slot = user
            if move_data.get("target") == "adjacentAllyOrSelf" and action.get("target_slot") in self.state["slots"]:
                cand = self.state["slots"][action["target_slot"]]
                if cand["current_hp_pct"] > 0:
                    tgt_slot = cand
            if move_data.get("heal"):
                num, den = move_data["heal"]
                heal_amt = max(1, trunc(tgt_slot["max_hp"] * num / den))
                self.heal_hp(tgt_slot, heal_amt, action_lines, f"{self.format_mon_name(tgt_slot['slot_id'])} regained health!")
            elif move_name in ("Morning Sun", "Synthesis", "Moonlight"):
                mult = 0.667 if weather == "sun" else (0.25 if weather in ("rain", "sand", "snow") else 0.5)
                self.heal_hp(tgt_slot, max(1, trunc(tgt_slot["max_hp"] * mult)), action_lines, f"{user_name} regained health!")
            if move_data.get("boosts"):
                if move_name == "Clangorous Soul":
                    if user["hp"] <= user["max_hp"] // 3:
                        action_lines.append("But it failed!")
                        self.log_blocks.append(action_lines)
                        return
                    self.deal_hp_damage(user, user["max_hp"] // 3, action_lines)
                self.apply_boost(tgt_slot, move_data["boosts"], action_lines, source_self=True)
            elif move_name == "Belly Drum":
                if user["hp"] <= user["max_hp"] // 2 or user["boosts"].get("atk", 0) >= 6:
                    action_lines.append("But it failed!")
                else:
                    self.deal_hp_damage(user, user["max_hp"] // 2, action_lines)
                    user["boosts"]["atk"] = 6
                    action_lines.append(f"{user_name} cut its own HP and maximized its Attack!")
            elif move_name == "Curse" and "Ghost" not in user.get("types", []):
                self.apply_boost(user, {"atk": 1, "def": 1, "spe": -1}, action_lines, source_self=True)
            self.log_blocks.append(action_lines)
            return

        # 5. Target Resolution & Redirection (Showdown Pokemon#getMoveTargets, pokemon.ts:812)
        targets: List[dict] = []
        is_spread = False
        opp = "p2" if slot_id.startswith("p1") else "p1"
        target_type = move_data.get("target", "normal")
        if move_name == "Expanding Force" and f.get("terrain") == "psychic" and not is_airborne(user, f):
            target_type = "allAdjacentFoes"

        if target_type in ("normal", "any", "adjacentFoe", "randomNormal"):
            tgt_id = action.get("target_slot")
            # Redirection check (Follow Me / Rage Powder / Lightning Rod / Storm Drain)
            tracks_target = bool(move_data.get("tracksTarget")) or user.get("ability") in ("Stalwart", "Propeller Tail")
            if not tracks_target and (not tgt_id or not tgt_id.startswith(slot_id[:2])):
                # Check Follow Me / Rage Powder on opposing side
                red_id = self.redirect_target.get(opp)
                if red_id and self.state["slots"].get(red_id) and self.state["slots"][red_id]["current_hp_pct"] > 0:
                    red_slot = self.state["slots"][red_id]
                    is_rage_powder = bool(red_slot.get("volatiles", {}).get("ragepowder"))
                    ignore_powder = is_rage_powder and (
                        "Grass" in user.get("types", []) or user.get("ability") == "Overcoat" or user.get("item") == "Safety Goggles"
                    )
                    if not ignore_powder:
                        tgt_id = red_id
                # Check Lightning Rod / Storm Drain redirection
                eff_type = move_data.get("type", "Normal")
                for sid, s in self.state["slots"].items():
                    if sid != slot_id and s["current_hp_pct"] > 0:
                        if eff_type == "Electric" and s.get("ability") == "Lightning Rod":
                            tgt_id = sid
                            break
                        if eff_type == "Water" and s.get("ability") == "Storm Drain":
                            tgt_id = sid
                            break

            # Smart retargeting if selected foe slot already fainted this turn
            if (not tgt_id or not self.state["slots"].get(tgt_id) or self.state["slots"][tgt_id]["current_hp_pct"] <= 0):
                living_foes = [s for s in self.state["slots"].values() if s["slot_id"].startswith(opp) and s["current_hp_pct"] > 0]
                if living_foes:
                    tgt_id = living_foes[0]["slot_id"]

            if tgt_id and self.state["slots"].get(tgt_id) and self.state["slots"][tgt_id]["current_hp_pct"] > 0:
                targets.append(self.state["slots"][tgt_id])

        elif target_type == "adjacentAlly":
            ally_prefix = slot_id[:2]
            for sid, s in self.state["slots"].items():
                if sid.startswith(ally_prefix) and sid != slot_id and s["current_hp_pct"] > 0:
                    targets.append(s)

        elif target_type == "allAdjacentFoes":
            targets = [s for s in self.state["slots"].values() if s["slot_id"].startswith(opp) and s["current_hp_pct"] > 0]
            is_spread = len(targets) > 1

        elif target_type == "allAdjacent":
            targets = [s for s in self.state["slots"].values() if s["slot_id"] != slot_id and s["current_hp_pct"] > 0]
            is_spread = len(targets) > 1

        if not targets:
            action_lines.append("But there was no target...")
            self.log_blocks.append(action_lines)
            return

        # 6. Priority Blocking (Psychic Terrain, Armor Tail, Dazzling, Queenly Majesty, Quick Guard)
        prio = self.get_move_priority(user, move_name, move_data)
        if prio > 0:
            # Armor Tail / Dazzling / Queenly Majesty on opposing board
            mold_breaker = user.get("ability") in ("Mold Breaker", "Teravolt", "Turboblaze")
            if not mold_breaker:
                for sid, s in self.state["slots"].items():
                    if sid.startswith(opp) and s["current_hp_pct"] > 0 and s.get("ability") in ("Armor Tail", "Dazzling", "Queenly Majesty"):
                        if any(t["slot_id"].startswith(opp) for t in targets):
                            action_lines.append(f"{self.format_mon_name(sid)}'s {s['ability']} prevents priority moves!")
                            self.log_blocks.append(action_lines)
                            return

            # Psychic Terrain Priority Collision Check (MEC-01)
            if f.get("terrain") == "psychic":
                filtered = []
                for t in targets:
                    if not t["slot_id"].startswith(slot_id[:2]) and not is_airborne(t, f):
                        action_lines.append(f"{self.format_mon_name(t['slot_id'])} is protected by the Psychic Terrain!")
                    else:
                        filtered.append(t)
                targets = filtered
                if not targets:
                    self.log_blocks.append(action_lines)
                    return

            # Quick Guard check
            filtered_qg = []
            for t in targets:
                t_side = "p1" if t["slot_id"].startswith("p1") else "p2"
                if t_side in self.quick_guard_sides and t_side != slot_id[:2]:
                    action_lines.append(f"Quick Guard protected {self.format_mon_name(t['slot_id'])}!")
                else:
                    filtered_qg.append(t)
            targets = filtered_qg
            if not targets:
                self.log_blocks.append(action_lines)
                return

        # 7. Wide Guard Check
        if target_type in ("allAdjacentFoes", "allAdjacent"):
            filtered_wg = []
            for t in targets:
                t_side = "p1" if t["slot_id"].startswith("p1") else "p2"
                if t_side in self.wide_guard_sides:
                    action_lines.append(f"Wide Guard protected {self.format_mon_name(t['slot_id'])}!")
                else:
                    filtered_wg.append(t)
            targets = filtered_wg
            if not targets:
                self.log_blocks.append(action_lines)
                return

        # 8. Sucker Punch / Upper Hand conditional checks
        if move_name == "Sucker Punch":
            tgt = targets[0]
            tgt_act = self.choices.get(tgt["slot_id"], {})
            tgt_mv = MOVE_DB.get(tgt_act.get("move_name", ""), {})
            if tgt.get("moved_this_turn") or tgt_act.get("choice") == "switch" or tgt_mv.get("cat") == "Status":
                action_lines.append("But it failed!")
                self.log_blocks.append(action_lines)
                return
        elif move_name == "Upper Hand":
            tgt = targets[0]
            tgt_act = self.choices.get(tgt["slot_id"], {})
            tgt_mv_name = tgt_act.get("move_name", "")
            tgt_mv = MOVE_DB.get(tgt_mv_name, {})
            tgt_prio = self.get_move_priority(tgt, tgt_mv_name, tgt_mv) if tgt_mv else 0
            if tgt.get("moved_this_turn") or tgt_mv.get("cat") == "Status" or not (1 <= tgt_prio <= 3):
                action_lines.append("But it failed!")
                self.log_blocks.append(action_lines)
                return

        # 9. Pollen Puff on Ally (heals 50% instead of attacking)
        if move_name == "Pollen Puff" and len(targets) == 1 and targets[0]["slot_id"].startswith(slot_id[:2]):
            ally = targets[0]
            self.heal_hp(ally, max(1, ally["max_hp"] // 2), action_lines, f"{self.format_mon_name(ally['slot_id'])} restored its HP!")
            self.log_blocks.append(action_lines)
            return

        # 10. Status Moves Targeting Foes/Allies (Will-O-Wisp, Thunder Wave, Spore, Taunt, Icy Wind/Parting Shot, Coaching, Decorate)
        if cat == "Status":
            for tgt in targets:
                tgt_name = self.format_mon_name(tgt["slot_id"])
                if tgt.get("protected") and "protect" in flags:
                    action_lines.append(f"{tgt_name} protected itself!")
                    continue
                if self.check_target_immunity_and_absorption(user, tgt, move_name, move_data, move_data.get("type", "Normal"), action_lines):
                    continue
                if move_data.get("status"):
                    if not self.try_set_status(tgt, move_data["status"], action_lines, source_slot=user):
                        action_lines.append(f"It doesn't affect {tgt_name}...")
                if move_data.get("boosts"):
                    self.apply_boost(tgt, move_data["boosts"], action_lines, source_self=tgt["slot_id"].startswith(slot_id[:2]))
                if move_data.get("volatileStatus") == "taunt":
                    if tgt.get("ability") == "Oblivious":
                        action_lines.append(f"{tgt_name}'s Oblivious prevents Taunt!")
                    else:
                        tgt["volatiles"]["taunt"] = 3
                        action_lines.append(f"{tgt_name} fell for the taunt!")
                        if tgt.get("item") == "Mental Herb":
                            tgt["item"] = ""
                            tgt["volatiles"].pop("taunt", None)
                            tgt["unburden_active"] = tgt.get("ability") == "Unburden"
                            action_lines.append(f"{tgt_name} shook off the taunt using its Mental Herb!")
                elif move_name == "Coaching":
                    self.apply_boost(tgt, {"atk": 1, "def": 1}, action_lines, source_self=True)
                elif move_name == "Decorate":
                    self.apply_boost(tgt, {"atk": 2, "spa": 2}, action_lines, source_self=True)
                elif move_name in ("Life Dew", "Floral Healing"):
                    self.heal_hp(tgt, max(1, tgt["max_hp"] // (2 if move_name == "Floral Healing" else 4)), action_lines, f"{tgt_name} regained health!")
            if move_data.get("selfSwitch") and action.get("switch_to"):
                self.log_blocks.append(action_lines)
                self.perform_switch_in(slot_id, action)
                return
            self.log_blocks.append(action_lines)
            return

        # 11. Damaging Move Execution Loop (Supports Multihit & Parental Bond)
        multihit = move_data.get("multihit", 1)
        if isinstance(multihit, list):
            num_hits = 3 if roll_mode == "fixed" else random.choice([2, 2, 2, 3, 3, 3, 4, 5])
        else:
            num_hits = int(multihit)
        if num_hits == 1 and user.get("ability") == "Parental Bond" and not is_spread:
            num_hits = 2

        total_damage_dealt = 0
        any_target_hit = False
        faint_lines: List[str] = []
        _, eff_m_type = self.compute_dynamic_base_power(user, targets[0], move_data)

        for tgt in targets:
            tgt_name = self.format_mon_name(tgt["slot_id"])
            if self.check_target_immunity_and_absorption(user, tgt, move_name, move_data, eff_m_type, action_lines):
                continue

            # Protection Check
            if tgt.get("protected") and "protect" in flags:
                breaks_prot = bool(move_data.get("breaksProtect"))
                pierce = breaks_prot or (user.get("ability") in ("Piercing Drill", "Unseen Fist") and "contact" in flags)
                p_type = tgt.get("protect_type", "Protect")

                if not pierce:
                    action_lines.append(f"{tgt_name} protected itself!")
                    if "contact" in flags:
                        if p_type == "Spiky Shield":
                            self.deal_hp_damage(user, max(1, user["max_hp"] // 8), action_lines)
                        elif p_type == "Baneful Bunker":
                            self.try_set_status(user, "psn", action_lines, source_slot=tgt)
                        elif p_type == "King's Shield":
                            self.apply_boost(user, {"atk": -1}, action_lines, source_self=False)
                        elif p_type == "Obstruct":
                            self.apply_boost(user, {"def": -2}, action_lines, source_self=False)
                        elif p_type == "Burning Bulwark":
                            self.try_set_status(user, "brn", action_lines, source_slot=tgt)
                    continue
                elif breaks_prot:
                    tgt["protected"] = False
                    action_lines.append(f"{user_name} broke through {tgt_name}'s protection!")
                else:
                    action_lines.append(f"{user_name}'s {user.get('ability')} pierced the protection!")

            # Multi-hit loop on this target
            hits_landed = 0
            for h in range(1, num_hits + 1):
                if tgt["current_hp_pct"] <= 0 or user["current_hp_pct"] <= 0:
                    break
                roll = (random.randint(85, 100) / 100.0) if roll_mode == "random" else fixed_roll
                dmg_hp, _, eff, is_crit = self.calculate_damage_full(user, tgt, move_data, is_spread, roll, hit_num=h)

                # Type-resist Berry check on first hit
                def_item = tgt.get("item", "")
                if def_item in RESIST_BERRIES and RESIST_BERRIES[def_item] == eff_m_type and (eff > 1.0 or def_item == "Chilan Berry"):
                    tgt["item"] = ""
                    tgt["unburden_active"] = tgt.get("ability") == "Unburden"
                    dmg_hp = max(1, sd_modify(dmg_hp, 0.5))
                    action_lines.append(f"{tgt_name}'s {def_item} weakened the damage!")

                if h == 1:
                    if eff > 1.0:
                        action_lines.append(f"It's super effective on {tgt_name}!")
                    elif 0.0 < eff < 1.0:
                        action_lines.append(f"It's not very effective on {tgt_name}.")
                if is_crit:
                    action_lines.append(f"A critical hit on {tgt_name}!")

                dealt = self.deal_hp_damage(tgt, dmg_hp, action_lines, check_sash=True)
                total_damage_dealt += dealt
                any_target_hit = True
                hits_landed += 1

                # Drain healing
                if move_data.get("drain") and dealt > 0:
                    d_num, d_den = move_data["drain"]
                    heal_amt = max(1, round(dealt * d_num / d_den))
                    self.heal_hp(user, heal_amt, action_lines, f"{tgt_name} had its energy drained!")

                # Weakness Policy on super-effective hit
                if eff > 1.0 and tgt["current_hp_pct"] > 0 and tgt.get("item") == "Weakness Policy":
                    tgt["item"] = ""
                    tgt["unburden_active"] = tgt.get("ability") == "Unburden"
                    self.apply_boost(tgt, {"atk": 2, "spa": 2}, action_lines, source_self=True)

                # Stamina / Weak Armor / Justified / Thermal Exchange / Electromorphosis / Seed Sower / Rocky Helmet / Rough Skin
                if tgt["current_hp_pct"] > 0:
                    t_ab = tgt.get("ability", "")
                    if t_ab == "Stamina":
                        self.apply_boost(tgt, {"def": 1}, action_lines, source_self=True, ability_source="Stamina")
                    elif t_ab == "Weak Armor" and cat == "Physical":
                        self.apply_boost(tgt, {"def": -1, "spe": 2}, action_lines, source_self=True, ability_source="Weak Armor")
                    elif t_ab == "Justified" and eff_m_type == "Dark":
                        self.apply_boost(tgt, {"atk": 1}, action_lines, source_self=True, ability_source="Justified")
                    elif t_ab == "Thermal Exchange" and eff_m_type == "Fire":
                        self.apply_boost(tgt, {"atk": 1}, action_lines, source_self=True, ability_source="Thermal Exchange")
                    elif t_ab == "Electromorphosis":
                        tgt["volatiles"]["charge"] = True
                        action_lines.append(f"Being hit by {move_name} charged {tgt_name} with power!")
                    elif t_ab == "Seed Sower":
                        f["terrain"] = "grassy"
                        f["terrain_turns"] = 5
                        action_lines.append("[Grass grew to cover the battlefield!]")

                if "contact" in flags and user["current_hp_pct"] > 0:
                    if tgt.get("ability") in ("Rough Skin", "Iron Barbs"):
                        self.deal_hp_damage(user, max(1, user["max_hp"] // 8), action_lines)
                    if tgt.get("item") == "Rocky Helmet":
                        self.deal_hp_damage(user, max(1, user["max_hp"] // 6), action_lines)

            if num_hits > 1 and hits_landed > 0:
                action_lines.append(f"Hit {hits_landed} time(s)!")

            # Knock Off item removal
            if move_name == "Knock Off" and tgt["current_hp_pct"] > 0 and tgt.get("item"):
                def_item = tgt["item"]
                req_item = BASE_STATS_DB.get(tgt["species"], {}).get("requiredItem")
                if not req_item and not def_item.endswith("ite") and not def_item.endswith("ite X") and not def_item.endswith("ite Y") and not def_item.endswith("ite Z"):
                    tgt["item"] = ""
                    tgt["unburden_active"] = tgt.get("ability") == "Unburden"
                    action_lines.append(f"{user_name} knocked off {tgt_name}'s {def_item}!")

            # Secondary Effects on target (Icy Wind, Snarl, Fake Out, Incineroar Flare Blitz, etc.)
            if tgt["current_hp_pct"] > 0 and user.get("ability") != "Sheer Force":
                shielded = tgt.get("ability") == "Shield Dust" or tgt.get("item") == "Covert Cloak"
                secs = []
                if move_data.get("secondary"):
                    secs.append(move_data["secondary"])
                if move_data.get("secondaries"):
                    secs.extend(move_data["secondaries"])
                if move_name == "Upper Hand":
                    secs.append({"chance": 100, "volatileStatus": "flinch"})

                for sec in secs:
                    chance = int(sec.get("chance", 100))
                    if user.get("ability") == "Serene Grace":
                        chance = min(100, chance * 2)
                    # Deterministic rule: in 'fixed' roll_mode, trigger 100% secondaries (e.g. Icy Wind, Snarl, Fake Out, Acid Spray);
                    # in 'random' roll_mode, roll exact probability
                    triggers = (chance >= 100) if roll_mode == "fixed" else (random.randint(1, 100) <= chance)
                    if not triggers:
                        continue
                    if sec.get("self_boosts"):
                        self.apply_boost(user, sec["self_boosts"], action_lines, source_self=True)
                    if shielded:
                        continue
                    if sec.get("boosts"):
                        self.apply_boost(tgt, sec["boosts"], action_lines, source_self=False)
                    if sec.get("status"):
                        self.try_set_status(tgt, sec["status"], action_lines, source_slot=user)
                    if sec.get("volatileStatus") == "flinch":
                        if tgt.get("ability") != "Inner Focus":
                            tgt["flinched"] = True

            if tgt["current_hp_pct"] <= 0:
                faint_lines.append(f"{tgt_name} fainted!")
                if user["current_hp_pct"] > 0 and user.get("ability") in ("Moxie", "Chilling Neigh"):
                    self.apply_boost(user, {"atk": 1}, faint_lines, source_self=True, ability_source=user["ability"])
                elif user["current_hp_pct"] > 0 and user.get("ability") in ("Grim Neigh", "Soul-Heart"):
                    self.apply_boost(user, {"spa": 1}, faint_lines, source_self=True, ability_source=user["ability"])

        # 12. Attacker Post-Move Effects (Self Drops, Recoil, Life Orb, Self-Switch)
        if any_target_hit and user["current_hp_pct"] > 0:
            if eff_m_type == "Electric" and user.get("volatiles", {}).get("charge"):
                user["volatiles"].pop("charge", None)

            if move_data.get("self_boosts"):
                self.apply_boost(user, move_data["self_boosts"], action_lines, source_self=True)

            if move_data.get("recoil") and total_damage_dealt > 0 and user.get("ability") not in ("Rock Head", "Magic Guard"):
                r_num, r_den = move_data["recoil"]
                recoil_hp = max(1, round(total_damage_dealt * r_num / r_den))
                action_lines.append(f"{user_name} was damaged by the recoil!")
                self.deal_hp_damage(user, recoil_hp, action_lines)

            if user.get("item") == "Life Orb" and user["current_hp_pct"] > 0 and user.get("ability") != "Magic Guard":
                if not (user.get("ability") == "Sheer Force" and (move_data.get("secondary") or move_data.get("secondaries"))):
                    self.deal_hp_damage(user, max(1, user["max_hp"] // 10), action_lines)

            if user["current_hp_pct"] <= 0:
                faint_lines.append(f"{user_name} fainted!")

        action_lines.extend(faint_lines)
        self.log_blocks.append(action_lines)

        if any_target_hit and user["current_hp_pct"] > 0 and move_data.get("selfSwitch") and action.get("switch_to"):
            self.perform_switch_in(slot_id, action)

    def run_turn(self, roll_mode: str = "random", fixed_roll: float = 0.925) -> Tuple[dict, str]:
        """Execute full doubles turn order sorting actions by speed and priority."""
        self.log_blocks.append([f"Turn {self.state['turn']}"])

        # 1. Activation Phase (Order 103 Priority +6 Switches & Order 104 Instantaneous Mega Evolution)
        self.execute_activation_phase()

        # 2. Pre-Queue Moves with Dynamic Mid-Turn Speed Recalculation (Showdown Gen 8/9 Battle#runAction, battle.ts:2978)
        pending_slots: List[Tuple[str, dict, float]] = []
        for slot_id, action in self.choices.items():
            slot = self.state["slots"].get(slot_id)
            if not slot or slot["current_hp_pct"] <= 0:
                continue
            if action.get("choice") == "switch" or (action.get("switch_to") and not action.get("move_name")):
                continue
            pending_slots.append((slot_id, action, random.random()))

        while pending_slots:
            # Dynamically recalculate priority and action speed before each move pops
            pending_slots.sort(
                key=lambda item: (
                    self.get_move_priority(
                        self.state["slots"][item[0]],
                        item[1].get("move_name", ""),
                        MOVE_DB.get(item[1].get("move_name", ""), {})
                    ),
                    self.get_action_speed(item[0]),
                    item[2],
                ),
                reverse=True,
            )
            slot_id, action, _ = pending_slots.pop(0)
            self.execute_single_action(slot_id, action, roll_mode=roll_mode, fixed_roll=fixed_roll)

        # 3. End of Turn (Residual) Phase (Showdown Battle#fieldEvent('Residual'))
        eot_lines: List[str] = []
        f = self.state["field"]

        # Weather timer & residual effects
        if f.get("weather_turns", 0) > 0:
            f["weather_turns"] -= 1
            if f["weather_turns"] == 0:
                f["weather"] = None
                eot_lines.append("(The weather cleared.)")
            elif f.get("weather") == "sun":
                eot_lines.append("(The sunlight is strong.)")
            elif f.get("weather") == "rain":
                eot_lines.append("(Rain continues to fall.)")
            elif f.get("weather") == "sand":
                eot_lines.append("(The sandstorm is raging.)")
                for s in self.state["slots"].values():
                    if s["current_hp_pct"] > 0 and s.get("item") != "Safety Goggles" and s.get("ability") not in ("Overcoat", "Sand Force", "Sand Rush", "Sand Veil", "Magic Guard"):
                        if not any(t in s.get("types", []) for t in ("Rock", "Ground", "Steel")):
                            self.deal_hp_damage(s, max(1, s["max_hp"] // 16), eot_lines)
            elif f.get("weather") == "snow":
                eot_lines.append("(The snow is falling.)")

        # Terrain timer & Grassy Terrain healing
        if f.get("terrain") == "grassy":
            for s in self.state["slots"].values():
                if s["current_hp_pct"] > 0 and not is_airborne(s, f) and s["current_hp_pct"] < 100.0:
                    self.heal_hp(s, max(1, s["max_hp"] // 16), eot_lines, f"{self.format_mon_name(s['slot_id'])} was healed by the Grassy Terrain!")

        if f.get("terrain_turns", 0) > 0:
            f["terrain_turns"] -= 1
            if f["terrain_turns"] == 0:
                old_t = f.get("terrain")
                f["terrain"] = None
                eot_lines.append(f"(The {old_t} terrain faded.)")

        if f.get("trick_room_turns", 0) > 0:
            f["trick_room_turns"] -= 1
            if f["trick_room_turns"] == 0:
                eot_lines.append("The twisted dimensions returned to normal!")

        # Leftovers, Black Sludge, Status Residuals (Burn, Poison, Toxic), Speed Boost
        active_sorted = sorted(
            [s for s in self.state["slots"].values() if s["current_hp_pct"] > 0],
            key=lambda s: self.get_action_speed(s["slot_id"]),
            reverse=True,
        )
        for s in active_sorted:
            if s["current_hp_pct"] <= 0:
                continue
            s_name = self.format_mon_name(s["slot_id"])
            if s.get("item") == "Leftovers" and s["current_hp_pct"] < 100.0:
                self.heal_hp(s, max(1, s["max_hp"] // 16), eot_lines, f"{s_name} restored a little HP using its Leftovers!")
            elif s.get("item") == "Black Sludge":
                if "Poison" in s.get("types", []):
                    self.heal_hp(s, max(1, s["max_hp"] // 16), eot_lines, f"{s_name} restored a little HP using its Black Sludge!")
                else:
                    self.deal_hp_damage(s, max(1, s["max_hp"] // 8), eot_lines)

            if s.get("ability") != "Magic Guard" and s["current_hp_pct"] > 0:
                st = s.get("status")
                if st == "brn":
                    div = 32 if s.get("ability") == "Heatproof" else 16
                    eot_lines.append(f"{s_name} was hurt by its burn!")
                    self.deal_hp_damage(s, max(1, s["max_hp"] // div), eot_lines)
                elif st == "psn":
                    eot_lines.append(f"{s_name} was hurt by poison!")
                    self.deal_hp_damage(s, max(1, s["max_hp"] // 8), eot_lines)
                elif st == "tox":
                    cnt = int(s.get("toxic_counter", 1))
                    s["toxic_counter"] = cnt + 1
                    eot_lines.append(f"{s_name} was hurt by poison!")
                    self.deal_hp_damage(s, max(1, trunc(s["max_hp"] * cnt / 16)), eot_lines)

            if s["current_hp_pct"] > 0 and s.get("ability") == "Speed Boost":
                self.apply_boost(s, {"spe": 1}, eot_lines, source_self=True, ability_source="Speed Boost")

            if s["current_hp_pct"] <= 0:
                eot_lines.append(f"{s_name} fainted!")
            else:
                s["active_turns"] = int(s.get("active_turns", 1)) + 1
                if s.get("volatiles", {}).get("taunt", 0) > 0:
                    s["volatiles"]["taunt"] -= 1
                    if s["volatiles"]["taunt"] <= 0:
                        s["volatiles"].pop("taunt", None)
                        eot_lines.append(f"{s_name}'s taunt wore off!")

        # Side Condition Timers (Tailwind, Reflect, Light Screen, Aurora Veil)
        for s in [self.state["p1"], self.state["p2"]]:
            side_str = "Your team's" if s.get("player", "").startswith(self.pov) else "The opposing team's"
            if s.get("tailwind_turns", 0) > 0:
                s["tailwind_turns"] -= 1
                if s["tailwind_turns"] == 0:
                    eot_lines.append(f"{side_str} Tailwind petered out!")
            if s.get("light_screen_turns", 0) > 0:
                s["light_screen_turns"] -= 1
                if s["light_screen_turns"] == 0:
                    eot_lines.append(f"{side_str} Light Screen wore off!")
            if s.get("reflect_turns", 0) > 0:
                s["reflect_turns"] -= 1
                if s["reflect_turns"] == 0:
                    eot_lines.append(f"{side_str} Reflect wore off!")
            if s.get("aurora_veil_turns", 0) > 0:
                s["aurora_veil_turns"] -= 1
                if s["aurora_veil_turns"] == 0:
                    eot_lines.append(f"{side_str} Aurora Veil wore off!")

        if eot_lines:
            self.log_blocks.append(eot_lines)

        self.state["turn"] += 1
        formatted_replay = "\n\n".join(["\n".join(block) for block in self.log_blocks])
        return self.state, formatted_replay


def main():
    """CLI runner for deterministic turn simulation."""
    parser = argparse.ArgumentParser(description="Regulation M-C Doubles Turn Micro-Simulator")
    parser.add_argument("--state", type=str, help="Path to JSON board_state file")
    parser.add_argument("--choices", type=str, help="Path to JSON choices file")
    parser.add_argument("--roll-mode", choices=["random", "fixed"], default="fixed")
    parser.add_argument("--fixed-roll", type=float, default=0.925)
    args = parser.parse_args()

    if args.state and args.choices:
        state_path = Path(args.state).resolve()
        choices_path = Path(args.choices).resolve()
        if state_path.stat().st_size > 1_048_576 or choices_path.stat().st_size > 1_048_576:
            raise ValueError("Input JSON files must not exceed 1 MB.")
        with open(state_path, "r", encoding="utf-8") as sf:
            state = json.load(sf)
        with open(choices_path, "r", encoding="utf-8") as cf:
            choices = json.load(cf)
    else:
        state = {
            "turn": 1,
            "field": {"weather": None, "terrain": None},
            "p1": {"player": "p1", "tailwind_turns": 0},
            "p2": {"player": "p2", "tailwind_turns": 0},
            "slots": {}
        }
        choices = {}

    sim = ClientReplaySimulator(state, choices)
    _next_state, replay_text = sim.run_turn(roll_mode=args.roll_mode, fixed_roll=args.fixed_roll)
    print(replay_text)


if __name__ == "__main__":
    main()
