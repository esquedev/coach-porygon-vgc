import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ==============================================================================
# 1. STATIC GAME DATA & COEFFICIENTS (REGULATION M-C)
# ==============================================================================

TYPE_CHART = {
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

NATURE_MODS = {
    "Adamant": {"atk": 1.1, "spa": 0.9}, "Bold":    {"def": 1.1, "atk": 0.9},
    "Brave":   {"atk": 1.1, "spe": 0.9}, "Calm":    {"spd": 1.1, "atk": 0.9},
    "Careful": {"spd": 1.1, "spa": 0.9}, "Modest":  {"spa": 1.1, "atk": 0.9},
    "Quiet":   {"spa": 1.1, "spe": 0.9}, "Timid":   {"spe": 1.1, "atk": 0.9},
    "Jolly":   {"spe": 1.1, "spa": 0.9}, "Impish":  {"def": 1.1, "spa": 0.9},
    "Relaxed": {"def": 1.1, "spe": 0.9}, "Sassy":   {"spd": 1.1, "spe": 0.9},
    "Naive":   {"spe": 1.1, "spd": 0.9}, "Hasty":   {"spe": 1.1, "def": 0.9},
    "Hardy":   {}, "Serious": {}, "Bashful": {}, "Quirky": {}, "Docile": {}
}

BASE_STATS_DB = {
    "Charizard":        {"hp": 78,  "atk": 84,  "def": 78,  "spa": 109, "spd": 85,  "spe": 100, "types": ["Fire", "Flying"]},
    "Charizard-Mega-Y": {"hp": 78,  "atk": 104, "def": 78,  "spa": 159, "spd": 115, "spe": 100, "types": ["Fire", "Flying"]},
    "Milotic":          {"hp": 95,  "atk": 60,  "def": 79,  "spa": 100, "spd": 125, "spe": 81,  "types": ["Water"]},
    "Floette-Mega-Red": {"hp": 74,  "atk": 65,  "def": 67,  "spa": 155, "spd": 128, "spe": 92,  "types": ["Fairy"]},
    "Floette-Eternal":  {"hp": 74,  "atk": 65,  "def": 67,  "spa": 125, "spd": 128, "spe": 92,  "types": ["Fairy"]},
    "Whimsicott":       {"hp": 60,  "atk": 67,  "def": 85,  "spa": 77,  "spd": 75,  "spe": 116, "types": ["Grass", "Fairy"]},
    "Indeedee-F":       {"hp": 70,  "atk": 55,  "def": 65,  "spa": 95,  "spd": 105, "spe": 85,  "types": ["Psychic", "Normal"]},
    "Armarouge":        {"hp": 85,  "atk": 60,  "def": 100, "spa": 125, "spd": 80,  "spe": 75,  "types": ["Fire", "Psychic"]},
    "Kingambit":        {"hp": 100, "atk": 135, "def": 120, "spa": 60,  "spd": 85,  "spe": 50,  "types": ["Dark", "Steel"]},
    "Primarina":        {"hp": 80,  "atk": 74,  "def": 74,  "spa": 126, "spd": 116, "spe": 60,  "types": ["Water", "Fairy"]},
    "Grimmsnarl":       {"hp": 95,  "atk": 120, "def": 65,  "spa": 95,  "spd": 75,  "spe": 60,  "types": ["Dark", "Fairy"]},
    "Garchomp":         {"hp": 108, "atk": 130, "def": 95,  "spa": 80,  "spd": 85,  "spe": 102, "types": ["Dragon", "Ground"]},
    "Sneasler":         {"hp": 80,  "atk": 130, "def": 60,  "spa": 40,  "spd": 80,  "spe": 120, "types": ["Fighting", "Poison"]},
    "Rillaboom":        {"hp": 100, "atk": 125, "def": 90,  "spa": 60,  "spd": 70,  "spe": 85,  "types": ["Grass"]},
    "Gholdengo":        {"hp": 87,  "atk": 60,  "def": 95,  "spa": 133, "spd": 91,  "spe": 84,  "types": ["Steel", "Ghost"]},
    "Pelipper":         {"hp": 60,  "atk": 50,  "def": 100, "spa": 95,  "spd": 70,  "spe": 65,  "types": ["Water", "Flying"]},
    "Archaludon":       {"hp": 90,  "atk": 105, "def": 130, "spa": 125, "spd": 65,  "spe": 85,  "types": ["Steel", "Dragon"]},
    "Venusaur":         {"hp": 80,  "atk": 82,  "def": 83,  "spa": 100, "spd": 100, "spe": 80,  "types": ["Grass", "Poison"]},
    "Farigiraf":        {"hp": 120, "atk": 90,  "def": 70,  "spa": 110, "spd": 70,  "spe": 60,  "types": ["Normal", "Psychic"]},
    "Kommo-o":          {"hp": 75,  "atk": 110, "def": 125, "spa": 100, "spd": 105, "spe": 85,  "types": ["Dragon", "Fighting"]},
    "Incineroar":       {"hp": 95,  "atk": 115, "def": 90,  "spa": 80,  "spd": 90,  "spe": 60,  "types": ["Fire", "Dark"]},
    "Sylveon":          {"hp": 95,  "atk": 65,  "def": 65,  "spa": 110, "spd": 130, "spe": 60,  "types": ["Fairy"]}
}


def _load_mc_available_pokemon() -> None:
    csv_path = Path(__file__).resolve().parent.parent / "data" / "MC_Available_Pokemon.csv"
    if not csv_path.exists():
        return
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("Pokémon") or row.get("Pokemon") or "").strip()
            if not name:
                continue
            types = [t.strip() for t in [row.get("Type 1", ""), row.get("Type 2", "")] if t and t.strip()]
            try:
                entry = {
                    "hp": int(float(row["Base HP"])),
                    "atk": int(float(row["Base Attack"])),
                    "def": int(float(row["Base Defense"])),
                    "spa": int(float(row["Base Sp. Attack"])),
                    "spd": int(float(row["Base Sp. Defense"])),
                    "spe": int(float(row["Speed"])),
                    "types": types,
                }
            except (KeyError, ValueError, TypeError):
                continue
            BASE_STATS_DB[name] = entry
            # Also register Showdown-style alias for Mega forms (e.g. "Mega Charizard Y" <-> "Charizard-Mega-Y")
            if name.startswith("Mega "):
                rest = name[5:].strip()
                parts = rest.split(" ")
                if len(parts) == 2 and parts[1] in ("X", "Y", "Z"):
                    alias = f"{parts[0]}-Mega-{parts[1]}"
                else:
                    alias = f"{rest}-Mega"
                BASE_STATS_DB[alias] = entry


_load_mc_available_pokemon()

MOVE_DB = {
    "Solar Beam":     {"type": "Grass",    "cat": "Special",  "power": 120, "accuracy": 100, "priority": 0, "target": "normal"},
    "Scald":          {"type": "Water",    "cat": "Special",  "power": 80,  "accuracy": 100, "priority": 0, "target": "normal"},
    "Dazzling Gleam": {"type": "Fairy",    "cat": "Special",  "power": 80,  "accuracy": 100, "priority": 0, "target": "allAdjacentFoes"},
    "Heat Wave":      {"type": "Fire",     "cat": "Special",  "power": 95,  "accuracy": 90,  "priority": 0, "target": "allAdjacentFoes"},
    "Earthquake":     {"type": "Ground",   "cat": "Physical", "power": 100, "accuracy": 100, "priority": 0, "target": "allAdjacent"},
    "Make It Rain":   {"type": "Steel",    "cat": "Special",  "power": 120, "accuracy": 100, "priority": 0, "target": "allAdjacentFoes"},
    "Expanding Force":{"type": "Psychic",  "cat": "Special",  "power": 80,  "accuracy": 100, "priority": 0, "target": "normal"},
    "Close Combat":   {"type": "Fighting", "cat": "Physical", "power": 120, "accuracy": 100, "priority": 0, "target": "normal"},
    "Kowtow Cleave":  {"type": "Dark",     "cat": "Physical", "power": 85,  "accuracy": 100, "priority": 0, "target": "normal"},
    "Sucker Punch":   {"type": "Dark",     "cat": "Physical", "power": 70,  "accuracy": 100, "priority": 1, "target": "normal"},
    "Grassy Glide":   {"type": "Grass",    "cat": "Physical", "power": 55,  "accuracy": 100, "priority": 1, "target": "normal"},
    "Fake Out":       {"type": "Normal",   "cat": "Physical", "power": 40,  "accuracy": 100, "priority": 3, "target": "normal"},
    "Protect":        {"type": "Normal",   "cat": "Status",   "power": 0,   "accuracy": 100, "priority": 4, "target": "self"},
    "Tailwind":       {"type": "Flying",   "cat": "Status",   "power": 0,   "accuracy": 100, "priority": 0, "target": "allySide"}
}

# ==============================================================================
# 2. STAT ENGINE & MATHEMATICAL UTILITIES
# ==============================================================================

def calculate_level_50_stats(species: str, sp: dict, nature: str, ivs: Optional[dict] = None) -> Tuple[int, Dict[str, int]]:
    base = BASE_STATS_DB.get(species, {"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 80})
    iv = ivs or {k: 31 for k in ["hp", "atk", "def", "spa", "spd", "spe"]}
    mods = NATURE_MODS.get(nature, {})

    def sp_to_ev(points: int) -> int:
        return 0 if points <= 0 else 4 + 8 * (points - 1)

    hp_ev = sp_to_ev(sp.get("hp", 0))
    max_hp = 1 if base["hp"] == 1 else math.floor((2 * base["hp"] + iv["hp"] + math.floor(hp_ev / 4)) * 50 / 100) + 60

    stats = {}
    for s in ["atk", "def", "spa", "spd", "spe"]:
        ev = sp_to_ev(sp.get(s, 0))
        raw = math.floor((2 * base[s] + iv[s] + math.floor(ev / 4)) * 50 / 100) + 5
        stats[s] = math.floor(raw * mods.get(s, 1.0))

    return max_hp, stats

def get_stage_multiplier(stage: int) -> float:
    stage = max(-6, min(6, stage))
    return (2 + stage) / 2.0 if stage >= 0 else 2.0 / (2 - stage)

def get_type_effectiveness(move_type: str, def_types: List[str]) -> float:
    mult = 1.0
    for dt in def_types:
        mult *= TYPE_CHART.get(move_type, {}).get(dt, 1.0)
    return mult

# ==============================================================================
# 3. CLIENT REPLAY SIMULATOR (HUMAN-READABLE TEXT)
# ==============================================================================

class ClientReplaySimulator:
    def __init__(self, state_dict: dict, choices_dict: dict, pov_player: str = "p1"):
        self.state = json.loads(json.dumps(state_dict))
        self.choices = choices_dict
        self.pov = pov_player
        self.log_blocks: List[List[str]] = []

        for slot_id, slot in self.state["slots"].items():
            if not slot.get("stats") or not slot.get("max_hp"):
                max_hp, stats = calculate_level_50_stats(
                    species=slot["species"],
                    sp=slot.get("sp_spread", {}),
                    nature=slot.get("nature", "Hardy")
                )
                slot["max_hp"] = max_hp
                slot["stats"] = stats
            if "types" not in slot and slot["species"] in BASE_STATS_DB:
                slot["types"] = BASE_STATS_DB[slot["species"]]["types"]

    def format_mon_name(self, slot_id: str) -> str:
        slot = self.state["slots"].get(slot_id)
        if not slot:
            return slot_id
        base_name = slot.get("name") or slot["species"].split("-")[0]
        return base_name if slot_id.startswith(self.pov) else f"The opposing {base_name}"

    def get_effective_speed(self, slot_id: str) -> float:
        slot = self.state["slots"].get(slot_id)
        if not slot or slot["current_hp_pct"] <= 0:
            return -1.0
        spe = slot["stats"]["spe"] * get_stage_multiplier(slot["boosts"].get("spe", 0))
        side = self.state["p1"] if slot_id.startswith("p1") else self.state["p2"]
        if side.get("tailwind_turns", 0) > 0:
            spe *= 2.0
        if slot.get("status") == "par":
            spe *= 0.5
        return spe

    def resolve_action_order(self) -> List[Tuple[str, dict]]:
        queue = []
        for slot_id, action in self.choices.items():
            slot = self.state["slots"].get(slot_id)
            if not slot or slot["current_hp_pct"] <= 0:
                continue
            move = MOVE_DB.get(action.get("move_name", ""), {})
            priority = move.get("priority", 0)
            spe = self.get_effective_speed(slot_id)
            queue.append((priority, spe, random.random(), slot_id, action))
        queue.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        return [(item[3], item[4]) for item in queue]

    def calculate_damage(self, attacker: dict, defender: dict, move_data: dict, is_spread: bool, roll: float) -> Tuple[float, float]:
        cat = move_data["cat"]
        pwr = move_data["power"]
        atk_stat = "atk" if cat == "Physical" else "spa"
        def_stat = "def" if cat == "Physical" else "spd"

        a = attacker["stats"][atk_stat] * get_stage_multiplier(attacker["boosts"].get(atk_stat, 0))
        d = max(1.0, defender["stats"][def_stat] * get_stage_multiplier(defender["boosts"].get(def_stat, 0)))
        base = math.floor(math.floor((22 * pwr * a) / d) / 50) + 2

        d_val = base
        if is_spread:
            d_val = math.floor(d_val * 3072 / 4096)

        m_type = move_data["type"]
        weather = self.state["field"].get("weather")
        if weather == "sun":
            if m_type == "Fire": d_val = math.floor(d_val * 1.5)
            elif m_type == "Water": d_val = math.floor(d_val * 0.5)
        elif weather == "rain":
            if m_type == "Water": d_val = math.floor(d_val * 1.5)
            elif m_type == "Fire": d_val = math.floor(d_val * 0.5)

        if m_type == "Fairy" and any(s.get("ability") == "Fairy Aura" for s in self.state["slots"].values() if s["current_hp_pct"] > 0):
            d_val = math.floor(d_val * 5461 / 4096)

        d_val = math.floor(d_val * roll)
        if m_type in attacker.get("types", []):
            d_val = math.floor(d_val * 1.5)

        eff = get_type_effectiveness(m_type, defender.get("types", []))
        d_val = math.floor(d_val * eff)

        def_side = self.state["p1"] if defender["slot_id"].startswith("p1") else self.state["p2"]
        if cat == "Special" and def_side.get("light_screen_turns", 0) > 0:
            d_val = math.floor(d_val * 2732 / 4096)
        elif cat == "Physical" and def_side.get("reflect_turns", 0) > 0:
            d_val = math.floor(d_val * 2732 / 4096)

        max_hp = max(1, int(defender.get("max_hp", 1)))
        dmg_pct = round((d_val / max_hp) * 100.0, 1)
        return dmg_pct, eff

    def run_turn(self, roll_mode: str = "random", fixed_roll: float = 0.925) -> Tuple[dict, str]:
        self.log_blocks.append([f"Turn {self.state['turn']}"])
        order = self.resolve_action_order()

        for slot_id, action in order:
            user = self.state["slots"].get(slot_id)
            if not user or user["current_hp_pct"] <= 0:
                continue

            move_name = action.get("move_name")
            move_data = MOVE_DB.get(move_name)
            if not move_data:
                continue

            action_lines = [f"{self.format_mon_name(slot_id)} used {move_name}!"]

            if move_data["target"] == "allySide" and move_name == "Tailwind":
                side = self.state["p1"] if slot_id.startswith("p1") else self.state["p2"]
                side["tailwind_turns"] = 4
                side_str = "Your team" if slot_id.startswith(self.pov) else "The opposing team"
                action_lines.append(f"The Tailwind blew from behind {side_str.lower()}!")
                self.log_blocks.append(action_lines)
                continue

            targets = []
            if move_data["target"] == "normal":
                tgt_id = action.get("target_slot")
                if tgt_id and self.state["slots"].get(tgt_id) and self.state["slots"][tgt_id]["current_hp_pct"] > 0:
                    targets.append(self.state["slots"][tgt_id])
            elif move_data["target"] == "allAdjacentFoes":
                opp = "p2" if slot_id.startswith("p1") else "p1"
                targets = [s for s in self.state["slots"].values() if s["slot_id"].startswith(opp) and s["current_hp_pct"] > 0]

            is_spread = len(targets) > 1
            roll = (random.randint(85, 100) / 100.0) if roll_mode == "random" else fixed_roll

            faint_lines = []
            for tgt in targets:
                dmg_pct, eff = self.calculate_damage(user, tgt, move_data, is_spread, roll)
                tgt["current_hp_pct"] = max(0.0, round(tgt["current_hp_pct"] - dmg_pct, 1))
                tgt_name = self.format_mon_name(tgt["slot_id"])

                if eff > 1.0:
                    action_lines.append(f"It's super effective on {tgt_name}!")
                elif 0.0 < eff < 1.0:
                    action_lines.append(f"It's not very effective on {tgt_name}.")

                action_lines.append(f"({tgt_name} lost {dmg_pct}% of its health!)")

                if tgt["current_hp_pct"] == 0:
                    faint_lines.append(f"{tgt_name} fainted!")

            action_lines.extend(faint_lines)
            self.log_blocks.append(action_lines)

        eot_lines = []
        f = self.state["field"]
        if f.get("weather_turns", 0) > 0:
            f["weather_turns"] -= 1
            if f["weather"] == "sun":
                eot_lines.append("(The sunlight is strong.)")
            elif f["weather"] == "rain":
                eot_lines.append("(Rain continues to fall.)")

        for s in [self.state["p1"], self.state["p2"]]:
            if s.get("tailwind_turns", 0) > 0:
                s["tailwind_turns"] -= 1
                if s["tailwind_turns"] == 0:
                    side_str = "Your team's" if s["player"].startswith(self.pov) else "The opposing team's"
                    eot_lines.append(f"{side_str} Tailwind petered out!")

            if s.get("light_screen_turns", 0) > 0:
                s["light_screen_turns"] -= 1
                if s["light_screen_turns"] == 0:
                    side_str = "Your team's" if s["player"].startswith(self.pov) else "The opposing team's"
                    eot_lines.append(f"{side_str} Light Screen wore off!")

        if eot_lines:
            self.log_blocks.append(eot_lines)

        self.state["turn"] += 1
        formatted_replay = "\n\n".join(["\n".join(block) for block in self.log_blocks])
        return self.state, formatted_replay


# ==============================================================================
# 4. CLI & SAMPLE TURN 6 DOUBLES TEST HARNESS
# ==============================================================================

SAMPLE_TURN_6_STATE = {
    "turn": 6,
    "field": {"weather": "sun", "weather_turns": 2},
    "p1": {"player": "p1", "tailwind_turns": 0, "light_screen_turns": 1, "reflect_turns": 0},
    "p2": {"player": "p2", "tailwind_turns": 1, "light_screen_turns": 0, "reflect_turns": 0},
    "slots": {
        "p1a": {
            "slot_id": "p1a",
            "species": "Charizard-Mega-Y",
            "name": "Charizard",
            "types": ["Fire", "Flying"],
            "ability": "Drought",
            "nature": "Modest",
            "sp_spread": {"hp": 18, "atk": 0, "def": 1, "spa": 32, "spd": 1, "spe": 14},
            "current_hp_pct": 76.0,
            "boosts": {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            "status": None
        },
        "p1b": {
            "slot_id": "p1b",
            "species": "Milotic",
            "name": "Milotic",
            "types": ["Water"],
            "ability": "Competitive",
            "nature": "Calm",
            "sp_spread": {"hp": 32, "atk": 0, "def": 18, "spa": 4, "spd": 10, "spe": 2},
            "current_hp_pct": 64.0,
            "boosts": {"atk": 0, "def": 0, "spa": 2, "spd": 0, "spe": 0},
            "status": None
        },
        "p2a": {
            "slot_id": "p2a",
            "species": "Floette-Mega-Red",
            "name": "Floette",
            "types": ["Fairy"],
            "ability": "Fairy Aura",
            "nature": "Timid",
            "sp_spread": {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32},
            "current_hp_pct": 88.0,
            "boosts": {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            "status": None
        },
        "p2b": {
            "slot_id": "p2b",
            "species": "Whimsicott",
            "name": "Whimsicott",
            "types": ["Grass", "Fairy"],
            "ability": "Prankster",
            "nature": "Timid",
            "sp_spread": {"hp": 32, "atk": 0, "def": 2, "spa": 0, "spd": 0, "spe": 32},
            "current_hp_pct": 42.0,
            "boosts": {"atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            "status": None
        }
    }
}

SAMPLE_TURN_6_CHOICES = {
    "p1a": {"move_name": "Heat Wave", "target_slot": "allAdjacentFoes"},
    "p1b": {"move_name": "Scald", "target_slot": "p2a"},
    "p2a": {"move_name": "Dazzling Gleam", "target_slot": "allAdjacentFoes"},
    "p2b": {"move_name": "Solar Beam", "target_slot": "p1b"}
}


def main():
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
        state = SAMPLE_TURN_6_STATE
        choices = SAMPLE_TURN_6_CHOICES

    sim = ClientReplaySimulator(state, choices)
    next_state, replay_text = sim.run_turn(roll_mode=args.roll_mode, fixed_roll=args.fixed_roll)
    print(replay_text)


if __name__ == "__main__":
    main()
