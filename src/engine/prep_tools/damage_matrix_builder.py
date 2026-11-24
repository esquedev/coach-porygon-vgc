# -*- coding: utf-8 -*-
"""Zero-AI Regulation M-C Damage & KO Matrix Pre-Computation Engine.

Executes batched, cartridge-exact Pokémon Champions Level 50 calculations via
the vendored `SmogonChampionsCalc` (`@smogon/calc` Gen 0 Champions bundle) across:
  - All 6 `trainer_1` Pokémon (+ Mega / Z-Mega forms dynamically from DuckDB)
  - Top-N Regulation M-C regional meta defenders (DuckDB `tournament_team_slots`)
  - All 7 strictly legal Reg M-C defender bulk profiles (`sum(SP) <= 66`, 31 IVs)
  - All 5 Weathers (`none`, `sun`, `rain`, `sand`, `snow`) — including Snow 1.5x Def on Ice
  - All 5 Terrains (`none`, `electric`, `grassy`, `psychic`, `misty`) — including Misty 0.5x Dragon
  - Spread (`0.75x`) vs. Single-Target (`1.0x`) modes for spread moves
  - Terrain Seeds (`Grassy`, `Electric`, `Psychic`, `Misty Seed` +1 Def / +1 SpD)

Deduplicates redundant weather/terrain/bulk lookups into a compact integer-indexed
`rollPool` so the exported standalone Base64 HTML renders in `< 1 ms` on any
mobile browser with zero custom base-damage re-implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from engine.damage_calc.bridge import (
    CalcFieldSpec,
    CalcMoveSpec,
    CalcPokemonSpec,
    DamageCalcRequest,
    get_champions_calc,
)
from engine.db_registry import get_registry
from engine.parser.models import ParsedPokemon
from engine.parser.showdown_parser import parse_showdown_paste
from engine.prep_tools.meta_snapshot import (
    MetaPokemonEntry,
    calc_all_champions_stats,
    get_top_n_meta_snapshot,
    load_sprites_dict,
    query_pokedex_entry,
    resolve_mega_form_for_item,
)
from engine.prep_tools.speed_tiers_builder import TEAM_COLOR_PALETTE, _format_sp_line, _short_display_label

# Official Gen 9 / Champions 18-type effectiveness chart (used strictly for UI 2x/4x badges & resist berry procs)
TYPE_CHART: Dict[str, Dict[str, float]] = {
    "Normal": {"Rock": 0.5, "Ghost": 0.0, "Steel": 0.5},
    "Fire": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 2.0, "Bug": 2.0, "Rock": 0.5, "Dragon": 0.5, "Steel": 2.0},
    "Water": {"Fire": 2.0, "Water": 0.5, "Grass": 0.5, "Ground": 2.0, "Rock": 2.0, "Dragon": 0.5},
    "Electric": {"Water": 2.0, "Electric": 0.5, "Grass": 0.5, "Ground": 0.0, "Flying": 2.0, "Dragon": 0.5},
    "Grass": {"Fire": 0.5, "Water": 2.0, "Grass": 0.5, "Poison": 0.5, "Ground": 2.0, "Flying": 0.5, "Bug": 0.5, "Rock": 2.0, "Dragon": 0.5, "Steel": 0.5},
    "Ice": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 0.5, "Ground": 2.0, "Flying": 2.0, "Dragon": 2.0, "Steel": 0.5},
    "Fighting": {"Normal": 2.0, "Ice": 2.0, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Rock": 2.0, "Ghost": 0.0, "Dark": 2.0, "Steel": 2.0, "Fairy": 0.5},
    "Poison": {"Grass": 2.0, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Ghost": 0.5, "Steel": 0.0, "Fairy": 2.0},
    "Ground": {"Fire": 2.0, "Electric": 2.0, "Grass": 0.5, "Poison": 2.0, "Flying": 0.0, "Bug": 0.5, "Rock": 2.0, "Steel": 2.0},
    "Flying": {"Electric": 0.5, "Grass": 2.0, "Fighting": 2.0, "Bug": 2.0, "Rock": 0.5, "Steel": 0.5},
    "Psychic": {"Fighting": 2.0, "Poison": 2.0, "Psychic": 0.5, "Dark": 0.0, "Steel": 0.5},
    "Bug": {"Fire": 0.5, "Grass": 2.0, "Fighting": 0.5, "Poison": 0.5, "Flying": 0.5, "Psychic": 2.0, "Ghost": 0.5, "Dark": 2.0, "Steel": 0.5, "Fairy": 0.5},
    "Rock": {"Fire": 2.0, "Ice": 2.0, "Fighting": 0.5, "Ground": 0.5, "Flying": 2.0, "Bug": 2.0, "Steel": 0.5},
    "Ghost": {"Normal": 0.0, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5},
    "Dragon": {"Dragon": 2.0, "Steel": 0.5, "Fairy": 0.0},
    "Dark": {"Fighting": 0.5, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5, "Fairy": 0.5},
    "Steel": {"Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2.0, "Rock": 2.0, "Steel": 0.5, "Fairy": 2.0},
    "Fairy": {"Fire": 0.5, "Fighting": 2.0, "Poison": 0.5, "Dragon": 2.0, "Dark": 2.0, "Steel": 0.5},
}

WEATHER_TO_SMOGON: Dict[str, Optional[str]] = {
    "none": None,
    "sun": "Sun",
    "rain": "Rain",
    "sand": "Sand",
    "snow": "Snow",
}

TERRAIN_TO_SMOGON: Dict[str, Optional[str]] = {
    "none": None,
    "electric": "Electric",
    "grassy": "Grassy",
    "psychic": "Psychic",
    "misty": "Misty",
}

HP_DEPENDENT_MOVES: Set[str] = {
    "Super Fang",
    "Nature's Madness",
    "Ruination",
    "Endeavor",
    "Crush Grip",
    "Wring Out",
    "Hard Press",
}

WEATHER_SENSITIVE_MOVES: Set[str] = {
    "Weather Ball",
    "Solar Beam",
    "Solar Blade",
    "Hydro Steam",
}

TERRAIN_SENSITIVE_MOVES: Set[str] = {
    "Expanding Force",
    "Rising Voltage",
    "Terrain Pulse",
    "Misty Explosion",
    "Psyblade",
    "Earthquake",
    "Bulldoze",
    "Magnitude",
    "Steel Roller",
}

SCREEN_BREAKING_MOVES: Set[str] = {"Brick Break", "Psychic Fangs", "Raging Bull"}

# Bulk profile representative mapping when move targets Def vs SpD (all <= 66 SP)
DEF_EQUIVALENCE: Dict[str, str] = {
    "min0": "min0",
    "hp32": "min0",
    "bal": "bal",
    "balDef": "balDef",
    "balSpd": "bal",
    "maxDef": "maxDef",
    "maxSpd": "maxSpd",
}
SPD_EQUIVALENCE: Dict[str, str] = {
    "min0": "min0",
    "hp32": "min0",
    "bal": "bal",
    "balDef": "bal",
    "balSpd": "balSpd",
    "maxDef": "maxDef",
    "maxSpd": "maxSpd",
}


@dataclass(frozen=True)
class DamageMatrixPayload:
    """Structured pre-computed SmogonChampionsCalc payload for mobile HTML rendering."""

    team_name: str
    total_teams: int
    top_n: int
    calc_count: int
    unique_roll_arrays: int
    data: Dict[str, Any]
    sprites: Dict[str, str]


def _is_grounded(types: Sequence[str], ability: Optional[str]) -> bool:
    """Return True if a Pokémon is grounded (eligible for Terrain effects)."""
    if "Flying" in types:
        return False
    if ability == "Levitate":
        return False
    return True


def _query_move_metadata(move_names: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Query DuckDB `moves` table for exact move type, BP, category, target, flags, priority."""
    unique_names = sorted({(m or "").strip() for m in move_names if m and m.strip()})
    if not unique_names:
        return {}
    reg = get_registry()
    placeholders = ",".join("?" for _ in unique_names)
    rows = reg.query(
        f"""
        SELECT name, type, category, basePower, accuracy, priority, target, flags,
               overrideDefensiveStat, overrideOffensiveStat, multihit, willCrit
        FROM moves
        WHERE name IN ({placeholders})
        """,
        unique_names,
    )
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        flags = row.get("flags") or {}
        if not isinstance(flags, dict):
            flags = {}
        acc_raw = row.get("accuracy")
        acc_str = "∞" if acc_raw is True or str(acc_raw).lower() == "true" else f"{acc_raw}%"
        target = str(row.get("target") or "normal")
        out[str(row["name"])] = {
            "name": str(row["name"]),
            "type": str(row["type"]),
            "category": str(row["category"]),
            "bp": int(row["basePower"] or 0),
            "acc": acc_str,
            "priority": int(row["priority"] or 0),
            "target": target,
            "isSpread": target in ("allAdjacentFoes", "allAdjacent"),
            "isBullet": bool(flags.get("bullet")),
            "isContact": bool(flags.get("contact")),
            "isSound": bool(flags.get("sound")),
            "isPulse": bool(flags.get("pulse")),
            "isSlicing": bool(flags.get("slicing")),
            "overrideDefensiveStat": row.get("overrideDefensiveStat"),
            "overrideOffensiveStat": row.get("overrideOffensiveStat"),
            "multihit": row.get("multihit"),
            "willCrit": bool(row.get("willCrit")),
        }
    return out


def _effective_move_type(move_type: str, ability: Optional[str]) -> str:
    """Reflect ability-based type conversion (-ate abilities) for weather/terrain relevance."""
    if move_type == "Normal":
        if ability == "Aerilate":
            return "Flying"
        if ability == "Pixilate":
            return "Fairy"
        if ability == "Refrigerate":
            return "Ice"
        if ability == "Galvanize":
            return "Electric"
    if ability == "Liquid Voice":
        return "Water"
    return move_type


def _relevant_weathers(
    move_name: str,
    eff_move_type: str,
    targets_def: bool,
    atk_ability: Optional[str],
    defender: MetaPokemonEntry,
) -> List[str]:
    """Return the minimal list of weathers that can alter damage for `(move, defender)`."""
    weathers: List[str] = ["none"]
    if (
        eff_move_type in ("Fire", "Water")
        or move_name in WEATHER_SENSITIVE_MOVES
        or atk_ability in ("Solar Power", "Orichalcum Pulse")
        or defender.top_ability in ("Dry Skin", "Flower Gift")
    ):
        weathers.append("sun")
    if (
        eff_move_type in ("Fire", "Water")
        or move_name in WEATHER_SENSITIVE_MOVES
        or defender.top_ability == "Dry Skin"
    ):
        weathers.append("rain")
    if (
        ("Rock" in defender.types and not targets_def)
        or move_name in ("Weather Ball", "Solar Beam", "Solar Blade")
        or atk_ability == "Sand Force"
    ):
        weathers.append("sand")
    if (
        ("Ice" in defender.types and targets_def)
        or move_name in ("Weather Ball", "Solar Beam", "Solar Blade")
    ):
        weathers.append("snow")
    return weathers


def _relevant_terrains(
    move_name: str,
    eff_move_type: str,
    move_priority: int,
    targets_def: bool,
    atk_grounded: bool,
    defender: MetaPokemonEntry,
) -> List[str]:
    """Return the minimal list of terrains that can alter damage for `(move, defender)`."""
    terrains: List[str] = ["none"]
    def_grounded = _is_grounded(defender.types, defender.top_ability)
    seed_t = defender.terrain_seed_terrain
    seed_stat = defender.terrain_seed_stat

    if (
        (eff_move_type == "Electric" and atk_grounded)
        or move_name in ("Rising Voltage", "Terrain Pulse", "Psyblade")
        or (seed_t == "electric" and seed_stat == "def" and targets_def)
    ):
        terrains.append("electric")

    if (
        (eff_move_type == "Grass" and atk_grounded)
        or move_name in ("Earthquake", "Bulldoze", "Magnitude", "Terrain Pulse")
        or (seed_t == "grassy" and seed_stat == "def" and targets_def)
    ):
        terrains.append("grassy")

    if (
        (eff_move_type == "Psychic" and atk_grounded)
        or move_name in ("Expanding Force", "Terrain Pulse")
        or (move_priority > 0 and def_grounded)
        or (seed_t == "psychic" and seed_stat == "spd" and not targets_def)
    ):
        terrains.append("psychic")

    if (
        (eff_move_type == "Dragon" and def_grounded)
        or move_name in ("Misty Explosion", "Terrain Pulse")
        or (seed_t == "misty" and seed_stat == "spd" and not targets_def)
    ):
        terrains.append("misty")

    return terrains


def _extract_unique_team(paste_text: str) -> List[ParsedPokemon]:
    """Parse Showdown paste into up to 6 unique Pokémon."""
    parsed = parse_showdown_paste(paste_text)
    unique: List[ParsedPokemon] = []
    seen: Set[int] = set()
    for mon in parsed.values():
        if id(mon) not in seen:
            seen.add(id(mon))
            unique.append(mon)
    if not unique:
        raise ValueError("Showdown paste did not contain any valid Pokémon sets.")
    return unique[:6]


def build_damage_matrix_payload(
    paste_text: str,
    team_name: str = "My Reg M-C Team",
    top_n: int = 50,
) -> DamageMatrixPayload:
    """Pre-compute exact 16-roll Champions damage tables for any 6-Pokémon Reg M-C team."""
    team_mons = _extract_unique_team(paste_text)
    snapshot = get_top_n_meta_snapshot(top_n=max(top_n, 50))
    defenders = snapshot.entries[: max(1, min(int(top_n), len(snapshot.entries)))]

    all_move_names: List[str] = []
    for mon in team_mons:
        all_move_names.extend(mon.moves[:4])
    move_catalog = _query_move_metadata(all_move_names)

    attackers_out: List[Dict[str, Any]] = []
    all_moves_out: List[Dict[str, Any]] = []
    sprite_keys_needed: List[str] = []

    # Execution descriptors for batched SmogonChampionsCalc
    # Each task records: (form_move_key, def_idx, prof_key, weather, terrain, single_flag, seed_flag)
    batch_requests: List[DamageCalcRequest] = []
    batch_meta: List[Tuple[str, int, str, str, str, int, int]] = []

    for idx, mon in enumerate(team_mons):
        base_dex = query_pokedex_entry(mon.species)
        if base_dex is None:
            raise ValueError(f"Unknown Regulation M-C species in DuckDB pokedex: '{mon.species}'")
        mega_dex = resolve_mega_form_for_item(base_dex["name"], mon.item)

        nature = (mon.nature or "Serious").replace("Naïve", "Naive").strip()
        sp_map = {
            "hp": max(0, min(32, int(mon.spread.hp))),
            "atk": max(0, min(32, int(mon.spread.atk))),
            "def": max(0, min(32, int(mon.spread.def_))),
            "spa": max(0, min(32, int(mon.spread.spa))),
            "spd": max(0, min(32, int(mon.spread.spd))),
            "spe": max(0, min(32, int(mon.spread.spe))),
        }

        base_ab = mon.ability or (base_dex["abilities"][0] if base_dex["abilities"] else "None")
        base_stats_l50 = calc_all_champions_stats(base_dex["baseStats"], sp_map, nature)
        sprite_keys_needed.append(base_dex["name"])

        mega_form_dict: Optional[Dict[str, Any]] = None
        if mega_dex is not None:
            mega_ab = mega_dex["abilities"][0] if mega_dex["abilities"] else base_ab
            mega_stats_l50 = calc_all_champions_stats(mega_dex["baseStats"], sp_map, nature)
            mega_form_dict = {
                "name": mega_dex["name"],
                "types": list(mega_dex["types"]),
                "ability": mega_ab,
                "stats": mega_stats_l50,
                "spriteKey": mega_dex["name"],
            }
            sprite_keys_needed.append(mega_dex["name"])

        atk_id = f"{''.join(ch for ch in base_dex['name'].lower() if ch.isalnum())}_{idx}"
        label = _short_display_label(mon, mega_dex["name"] if mega_dex else None)

        mon_moves_out: List[Dict[str, Any]] = []
        move_exec_specs: List[Tuple[str, str, Dict[str, Any], Dict[str, Any]]] = []

        for m_name in mon.moves[:4]:
            m_info = move_catalog.get(m_name)
            if not m_info or m_info["category"] == "Status":
                continue
            uid_slug = "".join(ch for ch in m_name.lower() if ch.isalnum())
            move_uid = f"{atk_id}_{uid_slug}"
            targets_def = (
                m_info["overrideDefensiveStat"] == "def"
                if m_info.get("overrideDefensiveStat")
                else (m_info["category"] == "Physical")
            )
            mv_entry = {
                "uid": move_uid,
                "attackerId": atk_id,
                "attackerLabel": label,
                "name": m_name,
                "smogonName": m_name,
                "type": m_info["type"],
                "category": m_info["category"],
                "targetsDef": targets_def,
                "bp": m_info["bp"],
                "acc": m_info["acc"],
                "priority": m_info["priority"],
                "isSpread": m_info["isSpread"],
                "isBullet": m_info["isBullet"],
                "isContact": m_info["isContact"],
                "isSound": m_info["isSound"],
                "willCrit": m_info["willCrit"],
                "breaksScreens": m_name in SCREEN_BREAKING_MOVES,
                "chargeSpABoost": m_name in ("Electro Shot", "Meteor Beam"),
                "isFacade": m_name == "Facade",
                "usesHpDependent": m_name in HP_DEPENDENT_MOVES,
            }
            mon_moves_out.append(mv_entry)
            all_moves_out.append(mv_entry)
            move_exec_specs.append((move_uid, m_name, mv_entry, {}))

            # Convenience 2x variant for Stomping Tantrum
            if m_name == "Stomping Tantrum":
                mv_2x_uid = f"{atk_id}_stompingtantrum2x"
                mv_2x = dict(mv_entry)
                mv_2x["uid"] = mv_2x_uid
                mv_2x["name"] = "Stomping Tantrum (2×)"
                mv_2x["bp"] = 150
                mon_moves_out.append(mv_2x)
                all_moves_out.append(mv_2x)
                move_exec_specs.append((mv_2x_uid, m_name, mv_2x, {"basePower": 150}))

        attackers_out.append(
            {
                "id": atk_id,
                "species": base_dex["name"],
                "label": label,
                "item": mon.item or "None",
                "nature": nature,
                "evLine": _format_sp_line(mon),
                "color": TEAM_COLOR_PALETTE[idx % len(TEAM_COLOR_PALETTE)],
                "base": {
                    "name": base_dex["name"],
                    "types": list(base_dex["types"]),
                    "ability": base_ab,
                    "stats": base_stats_l50,
                    "spriteKey": base_dex["name"],
                },
                "mega": mega_form_dict,
                "moves": mon_moves_out,
            }
        )

        # Build deduplicated SmogonChampionsCalc batch for base (and mega if present)
        forms_to_eval: List[Tuple[str, Dict[str, Any]]] = [("base", attackers_out[-1]["base"])]
        if mega_form_dict is not None:
            forms_to_eval.append(("mega", mega_form_dict))

        for form_tag, form_obj in forms_to_eval:
            atk_spec = CalcPokemonSpec(
                species=form_obj["name"],
                item=mon.item if mon.item and mon.item.lower() != "none" else None,
                ability=form_obj["ability"],
                nature=nature,
                level=50,
                sp=sp_map,
            )
            atk_grounded = _is_grounded(form_obj["types"], form_obj["ability"])

            for move_uid, smogon_name, mv_meta, move_overrides in move_exec_specs:
                fm_key = f"{form_tag}:{move_uid}"
                eff_type = _effective_move_type(mv_meta["type"], form_obj["ability"])
                targets_def = bool(mv_meta["targetsDef"])
                uses_hp_dep = bool(mv_meta["usesHpDependent"])

                # Unique bulk profile representatives to evaluate
                if uses_hp_dep:
                    unique_prof_keys = ("min0", "hp32", "bal", "balDef", "balSpd", "maxDef", "maxSpd")
                elif targets_def:
                    unique_prof_keys = ("min0", "bal", "balDef", "maxDef", "maxSpd")
                else:
                    unique_prof_keys = ("min0", "bal", "balSpd", "maxDef", "maxSpd")

                spread_flags = (0, 1) if mv_meta["isSpread"] else (0,)

                for def_idx, defender in enumerate(defenders):
                    rel_weathers = _relevant_weathers(
                        move_name=smogon_name,
                        eff_move_type=eff_type,
                        targets_def=targets_def,
                        atk_ability=form_obj["ability"],
                        defender=defender,
                    )
                    rel_terrains = _relevant_terrains(
                        move_name=smogon_name,
                        eff_move_type=eff_type,
                        move_priority=int(mv_meta["priority"]),
                        targets_def=targets_def,
                        atk_grounded=atk_grounded,
                        defender=defender,
                    )

                    # Evaluate relevant (weather, terrain) pairs (Cartesian product of small lists)
                    for w_key in rel_weathers:
                        for t_key in rel_terrains:
                            seed_matches = (
                                defender.terrain_seed is not None
                                and defender.terrain_seed_terrain == t_key
                                and (
                                    (defender.terrain_seed_stat == "def" and targets_def)
                                    or (defender.terrain_seed_stat == "spd" and not targets_def)
                                )
                            )
                            seed_variants = (0, 1) if seed_matches else (0,)

                            for seed_flag in seed_variants:
                                def_boosts: Dict[str, int] = {}
                                if seed_flag == 1 and defender.terrain_seed_stat:
                                    def_boosts[defender.terrain_seed_stat] = 1

                                # Avoid baking Multiscale into base rolls so Hit 2 in Partner Double-Up can break it cleanly!
                                def_ability_for_calc = (
                                    None
                                    if defender.top_ability in ("Multiscale", "Shadow Shield")
                                    else defender.top_ability
                                )

                                eff_spread_flags = (
                                    (0, 1)
                                    if (
                                        mv_meta["isSpread"]
                                        or (smogon_name == "Expanding Force" and t_key == "psychic" and atk_grounded)
                                    )
                                    else (0,)
                                )
                                for s_flag in eff_spread_flags:
                                    use_singles_for_ef = (
                                        smogon_name == "Expanding Force"
                                        and t_key == "psychic"
                                        and s_flag == 1
                                    )
                                    mv_spec = CalcMoveSpec(
                                        name=smogon_name,
                                        is_crit=bool(mv_meta["willCrit"]),
                                        force_single_target=(s_flag == 1),
                                        overrides=move_overrides,
                                    )
                                    field_spec = CalcFieldSpec(
                                        game_type="Singles" if use_singles_for_ef else "Doubles",
                                        weather=WEATHER_TO_SMOGON[w_key],
                                        terrain=TERRAIN_TO_SMOGON[t_key],
                                    )
                                    for p_key in unique_prof_keys:
                                        prof = defender.profiles[p_key]
                                        def_spec = CalcPokemonSpec(
                                            species=defender.species,
                                            item=None,  # Defensive items (Sash/Sitrus/Resist Berry/Seed) handled cleanly via simItems toggle!
                                            ability=def_ability_for_calc,
                                            nature=prof.nature,
                                            level=50,
                                            sp={
                                                "hp": prof.hp_sp,
                                                "atk": 0,
                                                "def": prof.def_sp,
                                                "spa": 0,
                                                "spd": prof.spd_sp,
                                                "spe": 0,
                                            },
                                            boosts=def_boosts,
                                        )
                                        batch_requests.append(
                                            DamageCalcRequest(
                                                attacker=atk_spec,
                                                defender=def_spec,
                                                move=mv_spec,
                                                field=field_spec,
                                            )
                                        )
                                        batch_meta.append(
                                            (fm_key, def_idx, p_key, w_key, t_key, s_flag, seed_flag)
                                        )

    # Execute all calculations in chunked batched V8 calls (keeps single IPC payload compact)
    calc = get_champions_calc()
    chunk_size = 4000
    all_results = []
    for start in range(0, len(batch_requests), chunk_size):
        all_results.extend(calc.calculate_batch(batch_requests[start : start + chunk_size]))

    # Deduplicate 16-roll arrays into a compact integer-indexed pool (`rollPool[0] == [0]*16`)
    zero_rolls = (0,) * 16
    roll_to_id: Dict[Tuple[int, ...], int] = {zero_rolls: 0}
    roll_pool: List[List[int]] = [[0] * 16]

    # Hierarchical compact lookup:
    # calcLut[fm_key][def_idx_str][p_key] = { "w|t|s|seed": roll_pool_id }
    # Only entries differing from default ("none|none|0|0") are stored!
    raw_store: Dict[str, Dict[int, Dict[str, Dict[str, int]]]] = {}
    for meta_row, res in zip(batch_meta, all_results):
        fm_key, def_idx, p_key, w_key, t_key, s_flag, seed_flag = meta_row
        rolls_tup = res.rolls_16 if (res.ok and len(res.rolls_16) == 16) else zero_rolls
        rid = roll_to_id.get(rolls_tup)
        if rid is None:
            rid = len(roll_pool)
            roll_to_id[rolls_tup] = rid
            roll_pool.append(list(rolls_tup))
        env_key = f"{w_key}|{t_key}|{s_flag}|{seed_flag}"
        raw_store.setdefault(fm_key, {}).setdefault(def_idx, {}).setdefault(p_key, {})[env_key] = rid

    # Prune entries whose roll_id equals the canonical default ("none|none|0|0")
    calc_lut: Dict[str, List[Dict[str, Any]]] = {}
    for fm_key, by_def in raw_store.items():
        def_arr: List[Dict[str, Any]] = []
        for def_idx in range(len(defenders)):
            prof_map = by_def.get(def_idx, {})
            compact_prof: Dict[str, Any] = {}
            for p_key, env_map in prof_map.items():
                base_rid = env_map.get("none|none|0|0", 0)
                overrides = {
                    ek: rid
                    for ek, rid in env_map.items()
                    if ek != "none|none|0|0" and rid != base_rid
                }
                if overrides:
                    overrides["_"] = base_rid
                    compact_prof[p_key] = overrides
                else:
                    compact_prof[p_key] = base_rid
            def_arr.append(compact_prof)
        calc_lut[fm_key] = def_arr

    defenders_out: List[Dict[str, Any]] = []
    for entry in defenders:
        sprite_keys_needed.append(entry.sprite_key)
        defenders_out.append(
            {
                "rank": entry.rank,
                "species": entry.species,
                "usagePct": entry.usage_pct,
                "top32Count": entry.top32_count,
                "types": list(entry.types),
                "baseStats": dict(entry.base_stats),
                "spriteKey": entry.sprite_key,
                "ability": entry.top_ability,
                "abilityPct": entry.top_ability_pct,
                "hasBulletproofAlt": entry.has_bulletproof_alt,
                "bulletproofPct": entry.bulletproof_pct,
                "topItem": entry.top_item,
                "topItemPct": entry.top_item_pct,
                "defaultItem": entry.default_item,
                "sitrusPct": entry.sitrus_pct,
                "sashPct": entry.sash_pct,
                "resistBerry": entry.resist_berry,
                "resistBerryType": entry.resist_berry_type,
                "resistBerryPct": entry.resist_berry_pct,
                "terrainSeed": entry.terrain_seed,
                "terrainSeedTerrain": entry.terrain_seed_terrain,
                "terrainSeedStat": entry.terrain_seed_stat,
                "terrainSeedPct": entry.terrain_seed_pct,
                "topNatures": list(entry.top_natures[:3]),
                "topItems": list(entry.top_items[:3]),
                "metaKey": entry.meta_bulk_key,
                "profiles": {k: v.to_dict() for k, v in entry.profiles.items()},
            }
        )

    sprites = load_sprites_dict(sprite_keys_needed)
    default_move_uid = all_moves_out[0]["uid"] if all_moves_out else ""
    default_mega_state = {
        a["id"]: bool(a["mega"] is not None) for a in attackers_out
    }

    payload_data: Dict[str, Any] = {
        "teamName": team_name,
        "totalTeams": snapshot.total_teams,
        "defaultTopN": int(top_n),
        "defaultMoveUid": default_move_uid,
        "defaultMegaForm": default_mega_state,
        "attackers": attackers_out,
        "allMoves": all_moves_out,
        "defenders": defenders_out,
        "typeChart": TYPE_CHART,
        "defEquiv": DEF_EQUIVALENCE,
        "spdEquiv": SPD_EQUIVALENCE,
        "rollPool": roll_pool,
        "calcLut": calc_lut,
        "calcCount": len(batch_requests),
    }
    return DamageMatrixPayload(
        team_name=team_name,
        total_teams=snapshot.total_teams,
        top_n=int(top_n),
        calc_count=len(batch_requests),
        unique_roll_arrays=len(roll_pool),
        data=payload_data,
        sprites=sprites,
    )
