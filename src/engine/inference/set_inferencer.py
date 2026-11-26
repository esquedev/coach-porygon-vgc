# -*- coding: utf-8 -*-
"""Zero-AI Open Team Sheet (OTS) 66-SP Mathematical Constraint Solver (Bo1 & Bo3).

Enforces official VGC Open Team Sheet discipline across both single-game (Bo1) and
Best-of-3 (Bo3) series in Pokémon Champions Regulation M-C:
- Requires complete opponent OTS metadata (Species, Item, Ability, Nature, 4 Moves),
  extracted automatically from Showdown `|showteam|` wire logs or supplied as an
  EV-less OTS paste. Raises `MissingOTSError` if OTS metadata is missing.
- Pools all empirical signals across 1..3 games:
    1. Turn-0 simultaneous switch-in ability order & same-priority Speed inequalities
    2. Exact integer HP offensive inversion (`trainer_2` -> `trainer_1`)
    3. Integer-% defensive bulk matrices (`trainer_1` -> `trainer_2`)
    4. Exact HP-SP isolators (Recoil tied to integer `trainer_1` damage, Sitrus Berry,
       Leftovers, Grassy Terrain, Life Orb, Burn, Sandstorm)
- Evaluates all damage & speed sweeps in a single batched call to the vendored offline
  `smogon/damage-calc` Champions bundle (`src/engine/damage_calc/bridge.py`).
- Uses exact 33-HP-slice × 5-stat Dynamic Programming over the Regulation M-C simplex
  (`sum(SP) == 66`, `0 <= SP <= 32`) to compute:
    - Exact projected clamped bounds `[min_sp, max_sp]` per stat (strictly enforced by
      the Replay Coach Clamped Slider GUI — deterministic inferred bounds cannot be
      overridden by the user).
    - Global maximum-likelihood + deterministic VGC role-prior default 66-SP spread.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import math
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from engine.damage_calc import (
    CalcFieldSpec,
    CalcMoveSpec,
    CalcPokemonSpec,
    CalcSideSpec,
    DamageCalcRequest,
    DamageCalcResult,
    SmogonChampionsCalc,
    SpeedCalcRequest,
    get_champions_calc,
)
from engine.db_registry import VGCDataRegistry, get_registry
from engine.parser.models import (
    DamageObservation,
    HpTickObservation,
    ParsedBattle,
    ParsedPokemon,
    SpeedObservation,
    StatSpread,
)
from engine.sp_validator import MAX_SINGLE_STAT_SP, MAX_TOTAL_SP
from engine.state.state_compiler import compute_level_50_stats_from_base

STAT_KEYS: Tuple[str, ...] = ("hp", "atk", "def", "spa", "spd", "spe")
NON_HP_KEYS: Tuple[str, ...] = ("atk", "def", "spa", "spd", "spe")

_PHYS_DEF_OVERRIDE_MOVES: Set[str] = {"Psyshock", "Psystrike", "Secret Sword"}
_USER_DEF_OFFENSE_MOVES: Set[str] = {"Body Press"}
_SKIP_INVERSION_MOVES: Set[str] = {
    "Foul Play",
    "Super Fang",
    "Ruination",
    "Nature's Madness",
    "Endeavor",
    "Night Shade",
    "Seismic Toss",
    "Dragon Rage",
    "Sonic Boom",
    "Final Gambit",
    "Pain Split",
    "Counter",
    "Mirror Coat",
    "Metal Burst",
    "Comeuppance",
    "Bide",
    "Beat Up",
    "Sheer Cold",
    "Fissure",
    "Guillotine",
    "Horn Drill",
}


class MissingOTSError(ValueError):
    """Raised when `trainer_2` lacks required Open Team Sheet metadata (Nature, Ability, or Moves)."""


def _norm_id(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def apply_stat_stage(stat_value: int, stage: int) -> int:
    """Apply standard Pokémon stat stage multiplier (-6..+6) to a Level 50 stat."""
    clamped = max(-6, min(6, int(stage)))
    if clamped >= 0:
        return (stat_value * (2 + clamped)) // 2
    return (stat_value * 2) // (2 - clamped)


def compute_effective_speed(
    base_spe_stat: int,
    spe_stage: int = 0,
    tailwind_active: bool = False,
    status: Optional[str] = None,
    ability: Optional[str] = None,
    item: Optional[str] = None,
    weather: Optional[str] = None,
    terrain: Optional[str] = None,
    unburden_active: bool = False,
) -> int:
    """Compute effective in-battle Speed after stage boosts, Tailwind, items, and abilities."""
    eff = apply_stat_stage(base_spe_stat, spe_stage)

    if not (ability == "Unburden" and unburden_active):
        if item == "Choice Scarf":
            eff = (eff * 3) // 2
        elif item == "Iron Ball":
            eff = eff // 2

    if (
        (ability == "Unburden" and unburden_active)
        or (ability == "Chlorophyll" and weather == "Sun")
        or (ability == "Swift Swim" and weather == "Rain")
        or (ability == "Sand Rush" and weather == "Sand")
        or (ability == "Slush Rush" and weather == "Snow")
        or (ability == "Surge Surfer" and terrain == "Electric")
    ):
        eff *= 2
    elif ability == "Quick Feet" and status:
        eff = (eff * 3) // 2

    if tailwind_active:
        eff *= 2

    if status == "par" and ability != "Quick Feet":
        eff //= 2

    return eff


def _showdown_pct_matches(cur_hp: int, max_hp: int, observed_pct: float) -> bool:
    """Return True if integer `cur_hp / max_hp` can display as `observed_pct` on Showdown."""
    if max_hp <= 0:
        return False
    obs_int = int(round(observed_pct))
    if obs_int <= 0:
        return cur_hp <= 0
    if cur_hp <= 0:
        return False
    # Showdown secret health uses ceil(cur*100/max) in some builds and round(cur*100/max) in others;
    # accepting exact match to either avoids any false exclusion while keeping 1% precision.
    pct_ceil = max(1, min(100, math.ceil((cur_hp * 100.0) / max_hp)))
    pct_round = max(1, min(100, int(round((cur_hp * 100.0) / max_hp))))
    pct_floor = max(1, min(100, (cur_hp * 100) // max_hp))
    return obs_int in (pct_ceil, pct_round, pct_floor)


def _possible_cur_hp_for_pct(max_hp: int, observed_pct: float) -> Tuple[int, int]:
    """Return inclusive `(min_hp, max_hp_val)` integer HP range that displays as `observed_pct`."""
    if observed_pct >= 99.9:
        return (max_hp, max_hp)
    if observed_pct <= 0.0:
        return (0, 0)
    obs_int = int(round(observed_pct))
    lo = max(1, int(math.floor(((obs_int - 1) * max_hp) / 100.0)))
    hi = min(max_hp, int(math.ceil(((obs_int + 1) * max_hp) / 100.0)))
    matched = [h for h in range(lo, hi + 1) if _showdown_pct_matches(h, max_hp, observed_pct)]
    if matched:
        return (matched[0], matched[-1])
    approx = max(1, min(max_hp, int(round((observed_pct * max_hp) / 100.0))))
    return (approx, approx)


@dataclass
class StatBound:
    """Clamped SP feasibility interval and evidence summary for a single stat."""

    stat: str
    min_sp: int = 0
    max_sp: int = MAX_SINGLE_STAT_SP
    default_sp: int = 0
    status: str = "unobserved"  # "pinned" | "bounded" | "unobserved"
    evidence: List[str] = field(default_factory=list)

    @property
    def locked(self) -> bool:
        return self.min_sp == self.max_sp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stat": self.stat,
            "min_sp": self.min_sp,
            "max_sp": self.max_sp,
            "default_sp": self.default_sp,
            "locked": self.locked,
            "status": self.status,
            "evidence": list(self.evidence),
        }


@dataclass
class PokemonSPInference:
    """Solved 66-SP bounds, deterministic default spread, and L50 stats for one opponent Pokémon."""

    species: str
    base_species: str
    item: Optional[str]
    ability: Optional[str]
    nature: str
    moves: List[str]
    base_stats: Dict[str, int]
    bounds: Dict[str, StatBound]
    default_spread: StatSpread
    default_l50_stats: Dict[str, int]
    speed_obs_count: int = 0
    damage_obs_count: int = 0
    hp_tick_obs_count: int = 0
    soft_fallback_used: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "species": self.species,
            "base_species": self.base_species,
            "item": self.item,
            "ability": self.ability,
            "nature": self.nature,
            "moves": list(self.moves),
            "base_stats": dict(self.base_stats),
            "bounds": {k: v.to_dict() for k, v in self.bounds.items()},
            "default_spread": self.default_spread.to_dict(),
            "default_l50_stats": dict(self.default_l50_stats),
            "speed_obs_count": self.speed_obs_count,
            "damage_obs_count": self.damage_obs_count,
            "hp_tick_obs_count": self.hp_tick_obs_count,
            "soft_fallback_used": self.soft_fallback_used,
            "notes": list(self.notes),
        }


@dataclass
class SeriesSPInferenceReport:
    """Complete Bo1 / Bo3 Zero-AI 66-SP inference report for `trainer_2`."""

    trainer_1_name: str
    trainer_2_name: str
    games_pooled: int
    pokemon_inferences: Dict[str, PokemonSPInference]
    primary_sets: Dict[str, ParsedPokemon]
    total_smogon_calcs: int = 0
    elapsed_ms: float = 0.0

    def validate_user_spreads(
        self,
        user_spreads_by_species: Dict[str, Dict[str, int]],
    ) -> Tuple[bool, List[str]]:
        """Strictly validate user slider SP edits against deterministic `[min_sp, max_sp]` clamps
        and Champions Regulation M-C 66-SP budget rules (`0 <= sp <= 32`, `sum == 66`).
        """
        errors: List[str] = []
        for sp_key, inf in self.pokemon_inferences.items():
            cand = (
                user_spreads_by_species.get(sp_key)
                or user_spreads_by_species.get(inf.base_species)
                or user_spreads_by_species.get(_norm_id(inf.base_species))
            )
            if cand is None:
                continue
            total = 0
            for sk in STAT_KEYS:
                raw_v = int(cand.get(sk, cand.get("def_" if sk == "def" else sk, 0)))
                b = inf.bounds[sk]
                if raw_v < 0 or raw_v > MAX_SINGLE_STAT_SP:
                    errors.append(f"{inf.base_species} {sk.upper()}: {raw_v} out of [0, 32].")
                elif raw_v < b.min_sp or raw_v > b.max_sp:
                    errors.append(
                        f"{inf.base_species} {sk.upper()}: {raw_v} SP violates inferred deterministic "
                        f"bounds [{b.min_sp}, {b.max_sp}]."
                    )
                total += raw_v
            if total != MAX_TOTAL_SP:
                errors.append(
                    f"{inf.base_species}: total SP must equal {MAX_TOTAL_SP} (got {total})."
                )
        return (len(errors) == 0, errors)

    def build_paste(
        self,
        override_spreads: Optional[Dict[str, Dict[str, int]]] = None,
    ) -> str:
        """Render the solved (or user-adjusted within clamps) opponent team as a Showdown 66-SP paste."""
        stat_labels = (("hp", "HP"), ("atk", "Atk"), ("def", "Def"), ("spa", "SpA"), ("spd", "SpD"), ("spe", "Spe"))
        blocks: List[str] = []
        for sp_key, inf in self.pokemon_inferences.items():
            sp_dict = inf.default_spread.to_dict()
            if override_spreads:
                cand = (
                    override_spreads.get(sp_key)
                    or override_spreads.get(inf.base_species)
                    or override_spreads.get(_norm_id(inf.base_species))
                )
                if cand:
                    sp_dict = {sk: int(cand.get(sk, sp_dict[sk])) for sk in STAT_KEYS}
            header = f"{inf.base_species} @ {inf.item}" if inf.item else inf.base_species
            lines = [header, f"Ability: {inf.ability or 'None'}", "Level: 50"]
            sp_parts = [f"{sp_dict[sk]} {lbl}" for sk, lbl in stat_labels if sp_dict.get(sk, 0) > 0]
            if sp_parts:
                lines.append("EVs: " + " / ".join(sp_parts))
            lines.append(f"{inf.nature} Nature")
            for mv in inf.moves[:4]:
                lines.append(f"- {mv}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks).strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trainer_1_name": self.trainer_1_name,
            "trainer_2_name": self.trainer_2_name,
            "games_pooled": self.games_pooled,
            "total_smogon_calcs": self.total_smogon_calcs,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "pokemon": [inf.to_dict() for inf in self.pokemon_inferences.values()],
            "paste_text": self.build_paste(),
        }


class OpponentSetInferencer:
    """Zero-AI OTS-enforced 66-SP constraint solver powered by vendored Smogon Champions calc."""

    def __init__(
        self,
        registry: Optional[VGCDataRegistry] = None,
        calc: Optional[SmogonChampionsCalc] = None,
    ) -> None:
        self.registry = registry or get_registry()
        self.calc = calc or get_champions_calc()
        self._move_cat_cache: Dict[str, str] = {}
        self._base_stats_cache: Dict[str, Dict[str, int]] = {}

    # ------------------------------------------------------------------
    # Mechanics Lookups via DuckDB (No tournament_team_slots dependency!)
    # ------------------------------------------------------------------

    def _get_base_stats(self, species: str) -> Dict[str, int]:
        key = species.strip()
        if key in self._base_stats_cache:
            return self._base_stats_cache[key]
        row = self.registry.get_pokemon(key)
        if not row and "-Mega" in key:
            row = self.registry.get_pokemon(key.split("-Mega")[0])
        if row:
            bs = {
                "hp": int(row.get("hp") or 80),
                "atk": int(row.get("atk") or 80),
                "def": int(row.get("def") or 80),
                "spa": int(row.get("spa") or 80),
                "spd": int(row.get("spd") or 80),
                "spe": int(row.get("spe") or 80),
            }
        else:
            bs = {"hp": 80, "atk": 80, "def": 80, "spa": 80, "spd": 80, "spe": 80}
        self._base_stats_cache[key] = bs
        return bs

    def _get_move_category(self, move_name: str) -> str:
        if move_name in self._move_cat_cache:
            return self._move_cat_cache[move_name]
        row = self.registry.get_move(move_name)
        cat = str(row.get("category") or "Status") if row else "Status"
        self._move_cat_cache[move_name] = cat
        return cat

    def _resolve_species_in_dict(
        self, sets: Dict[str, ParsedPokemon], identifier: str
    ) -> Optional[ParsedPokemon]:
        if not identifier:
            return None
        if identifier in sets:
            return sets[identifier]
        norm = _norm_id(identifier)
        base_norm = _norm_id(identifier.split("-Mega")[0])
        for k, mon in sets.items():
            if _norm_id(k) in (norm, base_norm):
                return mon
            if _norm_id(mon.species) in (norm, base_norm):
                return mon
            if mon.base_species and _norm_id(mon.base_species) in (norm, base_norm):
                return mon
            if mon.nickname and _norm_id(mon.nickname) == norm:
                return mon
        return None

    # ------------------------------------------------------------------
    # Public Entry Points (Bo1 & Bo3 Unified)
    # ------------------------------------------------------------------

    def infer_series(
        self,
        trainer_1_sets: Dict[str, ParsedPokemon],
        trainer_2_ots_sets: Dict[str, ParsedPokemon],
        replays: Sequence[Any],
        trainer_1_name: str = "trainer_1",
        trainer_2_name: str = "trainer_2",
    ) -> SeriesSPInferenceReport:
        """Solve exact 66-SP clamped bounds and deterministic defaults across 1..N games.

        Args:
            trainer_1_sets: Full 66-SP sets for `trainer_1` (POV user).
            trainer_2_ots_sets: Open Team Sheet sets for `trainer_2` (EVs optional/ignored;
                Species, Item, Ability, Nature, and Moves required).
            replays: Sequence of 1 (Bo1) to 3 (Bo3) `ParsedReplay` or `ParsedBattle` objects
                providing `speed_observations`, `damage_observations`, and `hp_tick_observations`.
            trainer_1_name: Display name of `trainer_1`.
            trainer_2_name: Display name of `trainer_2`.

        Raises:
            MissingOTSError: If `trainer_2_ots_sets` is empty or any Pokémon lacks Nature/Moves/Ability.
        """
        t_start = time.perf_counter()

        # Deduplicate & validate trainer_2 OTS sets strictly
        t2_ordered: List[Tuple[str, ParsedPokemon]] = []
        seen_norm: Set[str] = set()
        for raw_mon in trainer_2_ots_sets.values():
            base_sp = raw_mon.base_species or raw_mon.species.split("-Mega")[0]
            nk = _norm_id(base_sp)
            if nk in seen_norm:
                continue
            seen_norm.add(nk)
            t2_ordered.append((base_sp, copy.deepcopy(raw_mon)))

        if not t2_ordered:
            raise MissingOTSError(
                "Opponent Open Team Sheet (OTS) is required. Upload a Showdown replay containing "
                "`|showteam|` or paste the opponent's EV-less OTS (Species, Item, Ability, Nature, Moves)."
            )

        missing_details: List[str] = []
        for base_sp, mon in t2_ordered:
            missing_f: List[str] = []
            if not mon.nature:
                missing_f.append("Nature")
            if not mon.ability:
                missing_f.append("Ability")
            if not mon.moves:
                missing_f.append("Moves")
            if missing_f:
                missing_details.append(f"{base_sp} (missing {', '.join(missing_f)})")
        if missing_details:
            raise MissingOTSError(
                "Incomplete opponent OTS — Coach Porygon VGC requires full OTS metadata "
                f"(Nature, Ability, Moves): {'; '.join(missing_details)}"
            )

        # Pool all empirical observations across Games 1..N
        all_speed_obs: List[SpeedObservation] = []
        all_dmg_obs: List[DamageObservation] = []
        all_hp_ticks: List[HpTickObservation] = []
        for rep in replays:
            all_speed_obs.extend(getattr(rep, "speed_observations", []) or [])
            all_dmg_obs.extend(getattr(rep, "damage_observations", []) or [])
            all_hp_ticks.extend(getattr(rep, "hp_tick_observations", []) or [])

        # Detect whether opponent team has Trick Room (used purely as a tie-breaking role prior)
        t2_has_trick_room = any(
            "Trick Room" in (m.moves or []) for _, m in t2_ordered
        )

        # Build canonical lookup map for trainer_2
        t2_by_norm: Dict[str, Tuple[str, ParsedPokemon]] = {
            _norm_id(base_sp): (base_sp, mon) for base_sp, mon in t2_ordered
        }

        # ------------------------------------------------------------------
        # Stage 1: Batch ALL Speed calculations (trainer_1 exact + trainer_2 0..32)
        # ------------------------------------------------------------------
        speed_reqs: List[SpeedCalcRequest] = []
        speed_job_meta: List[Dict[str, Any]] = []

        for obs in all_speed_obs:
            t1_is_faster = obs.faster_trainer == "trainer_1" and obs.slower_trainer == "trainer_2"
            t2_is_faster = obs.faster_trainer == "trainer_2" and obs.slower_trainer == "trainer_1"
            if not (t1_is_faster or t2_is_faster):
                # Fallback resolution by membership if trainer tags were not set
                f1 = self._resolve_species_in_dict(trainer_1_sets, obs.faster_mon)
                s2 = self._resolve_species_in_dict(trainer_2_ots_sets, obs.slower_mon)
                f2 = self._resolve_species_in_dict(trainer_2_ots_sets, obs.faster_mon)
                s1 = self._resolve_species_in_dict(trainer_1_sets, obs.slower_mon)
                if f1 and s2:
                    t1_is_faster = True
                elif f2 and s1:
                    t2_is_faster = True
                else:
                    continue

            t1_sp_obs = obs.faster_mon if t1_is_faster else obs.slower_mon
            t2_sp_obs = obs.slower_mon if t1_is_faster else obs.faster_mon
            t1_mon = self._resolve_species_in_dict(trainer_1_sets, t1_sp_obs)
            t2_entry = t2_by_norm.get(_norm_id(t2_sp_obs.split("-Mega")[0]))
            if t1_mon is None or t2_entry is None:
                continue
            t2_base_sp, t2_mon = t2_entry

            t1_is_mega = obs.faster_is_mega if t1_is_faster else obs.slower_is_mega
            t2_is_mega = obs.slower_is_mega if t1_is_faster else obs.faster_is_mega
            t1_species_calc = t1_sp_obs if (t1_is_mega or "-Mega" in t1_sp_obs) else (t1_mon.base_species or t1_mon.species)
            t2_species_calc = t2_sp_obs if (t2_is_mega or "-Mega" in t2_sp_obs) else t2_base_sp

            t1_spe_stage = obs.faster_spe_stage if t1_is_faster else obs.slower_spe_stage
            t2_spe_stage = obs.slower_spe_stage if t1_is_faster else obs.faster_spe_stage
            t1_unb = obs.faster_unburden if t1_is_faster else obs.slower_unburden
            t2_unb = obs.slower_unburden if t1_is_faster else obs.faster_unburden
            t1_item = (obs.faster_item if t1_is_faster else obs.slower_item)
            t2_item = (obs.slower_item if t1_is_faster else obs.faster_item)
            t1_ab = (obs.faster_ability if t1_is_faster else obs.slower_ability) or t1_mon.ability
            t2_ab = (obs.slower_ability if t1_is_faster else obs.faster_ability) or t2_mon.ability
            t1_st = obs.faster_status if t1_is_faster else obs.slower_status
            t2_st = obs.slower_status if t1_is_faster else obs.faster_status
            t1_tw = obs.tailwind_active_faster if t1_is_faster else obs.tailwind_active_slower
            t2_tw = obs.tailwind_active_slower if t1_is_faster else obs.tailwind_active_faster

            start_idx = len(speed_reqs)
            speed_reqs.append(
                SpeedCalcRequest(
                    pokemon=CalcPokemonSpec(
                        species=t1_species_calc,
                        item=t1_item,
                        ability=t1_ab,
                        ability_on=t1_unb,
                        nature=t1_mon.nature or "Serious",
                        sp=t1_mon.spread.to_dict(),
                        boosts={"spe": t1_spe_stage},
                        status=t1_st,
                    ),
                    field=CalcFieldSpec(
                        game_type="Doubles",
                        weather=obs.weather,
                        terrain=obs.terrain,
                        attacker_side=CalcSideSpec(is_tailwind=t1_tw),
                    ),
                    side="attacker",
                )
            )
            for sp_v in range(MAX_SINGLE_STAT_SP + 1):
                speed_reqs.append(
                    SpeedCalcRequest(
                        pokemon=CalcPokemonSpec(
                            species=t2_species_calc,
                            item=t2_item,
                            ability=t2_ab,
                            ability_on=t2_unb,
                            nature=t2_mon.nature or "Serious",
                            sp={"spe": sp_v},
                            boosts={"spe": t2_spe_stage},
                            status=t2_st,
                        ),
                        field=CalcFieldSpec(
                            game_type="Doubles",
                            weather=obs.weather,
                            terrain=obs.terrain,
                            attacker_side=CalcSideSpec(is_tailwind=t2_tw),
                        ),
                        side="attacker",
                    )
                )
            speed_job_meta.append(
                {
                    "t2_base_sp": t2_base_sp,
                    "t1_species": t1_species_calc,
                    "t2_is_faster": t2_is_faster,
                    "obs": obs,
                    "start_idx": start_idx,
                }
            )

        speed_results = self.calc.calculate_effective_speeds(speed_reqs) if speed_reqs else []

        # ------------------------------------------------------------------
        # Stage 2: Batch ALL Damage calculations (33 calcs per hit across Bo3!)
        # ------------------------------------------------------------------
        dmg_reqs: List[DamageCalcRequest] = []
        dmg_job_meta: List[Dict[str, Any]] = []

        for obs in all_dmg_obs:
            if obs.move in _SKIP_INVERSION_MOVES:
                continue
            m_cat = self._get_move_category(obs.move)
            if m_cat not in ("Physical", "Special"):
                continue

            # Identify direction: offensive (trainer_2 -> trainer_1) vs defensive (trainer_1 -> trainer_2)
            atk_is_t2 = obs.attacker_trainer == "trainer_2" and obs.defender_trainer == "trainer_1"
            atk_is_t1 = obs.attacker_trainer == "trainer_1" and obs.defender_trainer == "trainer_2"
            if not (atk_is_t2 or atk_is_t1):
                if (
                    self._resolve_species_in_dict(trainer_2_ots_sets, obs.attacker)
                    and self._resolve_species_in_dict(trainer_1_sets, obs.defender)
                ):
                    atk_is_t2 = True
                elif (
                    self._resolve_species_in_dict(trainer_1_sets, obs.attacker)
                    and self._resolve_species_in_dict(trainer_2_ots_sets, obs.defender)
                ):
                    atk_is_t1 = True
                else:
                    continue

            if atk_is_t2:
                t2_entry = t2_by_norm.get(_norm_id(obs.attacker.split("-Mega")[0]))
                t1_mon = self._resolve_species_in_dict(trainer_1_sets, obs.defender)
                if t2_entry is None or t1_mon is None:
                    continue
                t2_base_sp, t2_mon = t2_entry
                # Determine which stat on trainer_2 scales this attack's damage
                if obs.move in _USER_DEF_OFFENSE_MOVES:
                    stat_swept = "def"
                elif m_cat == "Physical":
                    stat_swept = "atk"
                else:
                    stat_swept = "spa"

                atk_sp_name = obs.attacker if (obs.attacker_is_mega or "-Mega" in obs.attacker) else t2_base_sp
                def_sp_name = obs.defender if (obs.defender_is_mega or "-Mega" in obs.defender) else (t1_mon.base_species or t1_mon.species)
                is_phys_m = m_cat == "Physical"
                field_spec = CalcFieldSpec(
                    game_type="Doubles",
                    weather=obs.weather,
                    terrain=obs.terrain,
                    attacker_side=CalcSideSpec(is_helping_hand=obs.helping_hand),
                    defender_side=CalcSideSpec(
                        is_reflect=(obs.screen_active and is_phys_m),
                        is_light_screen=(obs.screen_active and not is_phys_m),
                        is_friend_guard=obs.friend_guard,
                    ),
                )
                mv_spec = CalcMoveSpec(
                    name=obs.move,
                    is_crit=obs.is_crit,
                    hits=obs.hits if obs.hits > 1 else None,
                    force_single_target=(not obs.is_spread_multi_target),
                    boosts_already_include_charge_spa=obs.boosts_include_charge_spa,
                )
                def_spec = CalcPokemonSpec(
                    species=def_sp_name,
                    item=obs.defender_item,
                    ability=obs.defender_ability or t1_mon.ability,
                    nature=t1_mon.nature or "Serious",
                    sp=t1_mon.spread.to_dict(),
                    boosts=obs.defender_boosts,
                    cur_hp_pct=obs.hp_pct_before,
                )
                start_idx = len(dmg_reqs)
                for sp_v in range(MAX_SINGLE_STAT_SP + 1):
                    dmg_reqs.append(
                        DamageCalcRequest(
                            attacker=CalcPokemonSpec(
                                species=atk_sp_name,
                                item=obs.attacker_item,
                                ability=obs.attacker_ability or t2_mon.ability,
                                nature=t2_mon.nature or "Serious",
                                sp={stat_swept: sp_v},
                                boosts=obs.attacker_boosts,
                                status="brn" if obs.attacker_burned else None,
                                cur_hp_pct=obs.attacker_hp_pct,
                            ),
                            defender=def_spec,
                            move=mv_spec,
                            field=field_spec,
                        )
                    )
                dmg_job_meta.append(
                    {
                        "kind": "offensive",
                        "t2_base_sp": t2_base_sp,
                        "stat_swept": stat_swept,
                        "obs": obs,
                        "start_idx": start_idx,
                    }
                )

            else:
                # Defensive: trainer_1 hits trainer_2 -> sweep trainer_2's def or spd (0..32)
                t1_mon = self._resolve_species_in_dict(trainer_1_sets, obs.attacker)
                t2_entry = t2_by_norm.get(_norm_id(obs.defender.split("-Mega")[0]))
                if t1_mon is None or t2_entry is None:
                    continue
                t2_base_sp, t2_mon = t2_entry
                if m_cat == "Physical" or obs.move in _PHYS_DEF_OVERRIDE_MOVES:
                    stat_swept = "def"
                else:
                    stat_swept = "spd"

                atk_sp_name = obs.attacker if (obs.attacker_is_mega or "-Mega" in obs.attacker) else (t1_mon.base_species or t1_mon.species)
                def_sp_name = obs.defender if (obs.defender_is_mega or "-Mega" in obs.defender) else t2_base_sp
                is_phys_m = m_cat == "Physical"
                field_spec = CalcFieldSpec(
                    game_type="Doubles",
                    weather=obs.weather,
                    terrain=obs.terrain,
                    attacker_side=CalcSideSpec(is_helping_hand=obs.helping_hand),
                    defender_side=CalcSideSpec(
                        is_reflect=(obs.screen_active and is_phys_m),
                        is_light_screen=(obs.screen_active and not is_phys_m),
                        is_friend_guard=obs.friend_guard,
                    ),
                )
                mv_spec = CalcMoveSpec(
                    name=obs.move,
                    is_crit=obs.is_crit,
                    hits=obs.hits if obs.hits > 1 else None,
                    force_single_target=(not obs.is_spread_multi_target),
                    boosts_already_include_charge_spa=obs.boosts_include_charge_spa,
                )
                atk_spec = CalcPokemonSpec(
                    species=atk_sp_name,
                    item=obs.attacker_item,
                    ability=obs.attacker_ability or t1_mon.ability,
                    nature=t1_mon.nature or "Serious",
                    sp=t1_mon.spread.to_dict(),
                    boosts=obs.attacker_boosts,
                    status="brn" if obs.attacker_burned else None,
                    cur_hp_pct=obs.attacker_hp_pct,
                )
                start_idx = len(dmg_reqs)
                for sp_v in range(MAX_SINGLE_STAT_SP + 1):
                    dmg_reqs.append(
                        DamageCalcRequest(
                            attacker=atk_spec,
                            defender=CalcPokemonSpec(
                                species=def_sp_name,
                                item=obs.defender_item,
                                ability=obs.defender_ability or t2_mon.ability,
                                nature=t2_mon.nature or "Serious",
                                sp={stat_swept: sp_v},
                                boosts=obs.defender_boosts,
                                cur_hp_pct=obs.hp_pct_before,
                            ),
                            move=mv_spec,
                            field=field_spec,
                        )
                    )
                dmg_job_meta.append(
                    {
                        "kind": "defensive",
                        "t2_base_sp": t2_base_sp,
                        "stat_swept": stat_swept,
                        "obs": obs,
                        "start_idx": start_idx,
                    }
                )

        dmg_results = self.calc.calculate_batch(dmg_reqs) if dmg_reqs else []

        # ------------------------------------------------------------------
        # Stage 3: Assemble Per-Pokémon Constraint Systems & Run Exact 66-SP DP
        # ------------------------------------------------------------------
        per_mon_speed_jobs: Dict[str, List[Dict[str, Any]]] = {sp: [] for sp, _ in t2_ordered}
        for job in speed_job_meta:
            per_mon_speed_jobs[job["t2_base_sp"]].append(job)

        per_mon_dmg_jobs: Dict[str, List[Dict[str, Any]]] = {sp: [] for sp, _ in t2_ordered}
        for job in dmg_job_meta:
            per_mon_dmg_jobs[job["t2_base_sp"]].append(job)

        per_mon_ticks: Dict[str, List[HpTickObservation]] = {sp: [] for sp, _ in t2_ordered}
        for tick in all_hp_ticks:
            if tick.trainer == "trainer_2":
                entry = t2_by_norm.get(_norm_id(tick.species.split("-Mega")[0]))
                if entry is not None:
                    per_mon_ticks[entry[0]].append(tick)

        pokemon_inferences: Dict[str, PokemonSPInference] = {}
        primary_sets: Dict[str, ParsedPokemon] = {}

        for base_sp, mon in t2_ordered:
            inf = self._solve_single_pokemon_dp(
                base_sp=base_sp,
                mon=mon,
                speed_jobs=per_mon_speed_jobs[base_sp],
                speed_results=speed_results,
                dmg_jobs=per_mon_dmg_jobs[base_sp],
                dmg_results=dmg_results,
                hp_ticks=per_mon_ticks[base_sp],
                team_has_trick_room=t2_has_trick_room,
            )
            pokemon_inferences[base_sp] = inf
            solved_mon = copy.deepcopy(mon)
            solved_mon.species = base_sp
            solved_mon.base_species = base_sp
            solved_mon.item = mon.initial_item or mon.item
            solved_mon.spread = copy.deepcopy(inf.default_spread)
            primary_sets[base_sp] = solved_mon

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        return SeriesSPInferenceReport(
            trainer_1_name=trainer_1_name,
            trainer_2_name=trainer_2_name,
            games_pooled=max(1, len(replays)),
            pokemon_inferences=pokemon_inferences,
            primary_sets=primary_sets,
            total_smogon_calcs=len(dmg_reqs) + len(speed_reqs),
            elapsed_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------
    # Stage 3 Core: Exact 33-HP-Slice × 5-Stat Dynamic Programming Solver
    # ------------------------------------------------------------------

    def _solve_single_pokemon_dp(
        self,
        base_sp: str,
        mon: ParsedPokemon,
        speed_jobs: List[Dict[str, Any]],
        speed_results: List[Any],
        dmg_jobs: List[Dict[str, Any]],
        dmg_results: List[DamageCalcResult],
        hp_ticks: List[HpTickObservation],
        team_has_trick_room: bool,
    ) -> PokemonSPInference:
        N = MAX_SINGLE_STAT_SP + 1  # 33 values: 0..32
        base_stats = self._get_base_stats(base_sp)
        nature = mon.nature or "Serious"
        item = mon.initial_item or mon.item

        evidence: Dict[str, List[str]] = {sk: [] for sk in STAT_KEYS}
        notes: List[str] = []

        # Per-stat hard compatibility lists & log-likelihood scores (0.0 baseline)
        unary_constraints: Dict[str, List[Tuple[List[bool], str]]] = {sk: [] for sk in STAT_KEYS}
        unary_ll: Dict[str, List[float]] = {sk: [0.0] * N for sk in STAT_KEYS}

        # Pairwise (hp_sp, def_sp) and (hp_sp, spd_sp) bulk constraints + likelihoods
        pair_constraints: Dict[str, List[Tuple[List[List[bool]], str]]] = {"def": [], "spd": []}
        pair_ll: Dict[str, List[List[float]]] = {
            "def": [[0.0] * N for _ in range(N)],
            "spd": [[0.0] * N for _ in range(N)],
        }

        # 1. Process Speed Observations -> unary_constraints["spe"]
        for job in speed_jobs:
            s_idx = job["start_idx"]
            r_t1 = speed_results[s_idx]
            if not r_t1.ok:
                continue
            v1 = r_t1.eff_spe
            obs: SpeedObservation = job["obs"]
            t2_faster = bool(job["t2_is_faster"])
            want_ge = (t2_faster and not obs.trick_room_active) or (
                (not t2_faster) and obs.trick_room_active
            )

            mask = [False] * N
            for sp_v in range(N):
                r_t2 = speed_results[s_idx + 1 + sp_v]
                if not r_t2.ok:
                    continue
                v2 = r_t2.eff_spe
                if (want_ge and v2 >= v1) or ((not want_ge) and v2 <= v1):
                    mask[sp_v] = True
            if any(mask):
                lo_s = next(i for i, ok in enumerate(mask) if ok)
                hi_s = max(i for i, ok in enumerate(mask) if ok)
                tr_tag = " (TR)" if obs.trick_room_active else ""
                rel_txt = f"faster than {job['t1_species']} (>= {v1} Spe)" if want_ge else f"slower than {job['t1_species']} (<= {v1} Spe)"
                src_tag = "Turn-0 ability" if obs.source == "switch_in_ability" else f"T{obs.turn}"
                ev_str = f"G{obs.game_index} {src_tag}{tr_tag}: {rel_txt} -> Spe {lo_s}-{hi_s} SP"
                unary_constraints["spe"].append((mask, ev_str))

        # 2. Process Damage Observations -> unary (offensive) & pairwise (defensive)
        for job in dmg_jobs:
            obs_d: DamageObservation = job["obs"]
            s_idx = job["start_idx"]
            stat_k = job["stat_swept"]

            if job["kind"] == "offensive":
                mask = [False] * N
                ll_add = [0.0] * N
                for sp_v in range(N):
                    res = dmg_results[s_idx + sp_v]
                    if not res.ok:
                        continue
                    rolls = res.rolls_16
                    if obs_d.damage_hp_exact is not None and obs_d.damage_hp_exact > 0:
                        d_ex = obs_d.damage_hp_exact
                        if obs_d.is_ohko or obs_d.focus_sash_or_sturdy:
                            # Lower bound only (hit dealt at least remaining HP)
                            if res.max_damage >= d_ex:
                                mask[sp_v] = True
                                # Mild preference for comfortably reaching the KO roll
                                cnt_ko = sum(1 for rv in rolls if rv >= d_ex)
                                ll_add[sp_v] = math.log(max(0.05, cnt_ko / 16.0)) * 0.4
                        else:
                            if d_ex in rolls:
                                mask[sp_v] = True
                                idxs = [i for i, rv in enumerate(rolls) if rv == d_ex]
                                # Center-roll likelihood: interior rolls (5..10) slightly preferred over 0/15 tails
                                avg_dist = sum(abs(i - 7.5) for i in idxs) / len(idxs)
                                ll_add[sp_v] = math.log(len(idxs) / 16.0) - 0.04 * avg_dist
                    else:
                        # Percentage-only fallback
                        max_hp_def = max(1, res.defender_max_hp)
                        if obs_d.is_ohko or obs_d.focus_sash_or_sturdy:
                            min_needed = max(1, int(math.floor((obs_d.hp_pct_before * max_hp_def) / 100.0)) - 1)
                            if res.max_damage >= min_needed:
                                mask[sp_v] = True
                        else:
                            lo_b, hi_b = _possible_cur_hp_for_pct(max_hp_def, obs_d.hp_pct_before)
                            hit_ok = False
                            for rv in rolls:
                                for cur_b in (lo_b, (lo_b + hi_b) // 2, hi_b):
                                    if _showdown_pct_matches(max(1, cur_b - rv), max_hp_def, obs_d.hp_pct_after):
                                        hit_ok = True
                                        break
                                if hit_ok:
                                    break
                            mask[sp_v] = hit_ok

                if any(mask):
                    lo_s = next(i for i, ok in enumerate(mask) if ok)
                    hi_s = max(i for i, ok in enumerate(mask) if ok)
                    dmg_lbl = (
                        f"{obs_d.damage_hp_exact}/{obs_d.defender_max_hp_exact} HP"
                        if obs_d.damage_hp_exact is not None
                        else f"{obs_d.damage_pct:.0f}%"
                    )
                    ko_lbl = " (KO)" if obs_d.is_ohko else ""
                    ev_str = (
                        f"G{obs_d.game_index} T{obs_d.turn}: {obs_d.move} dealt {dmg_lbl}{ko_lbl} "
                        f"to {obs_d.defender} -> {stat_k.upper()} {lo_s}-{hi_s} SP"
                    )
                    unary_constraints[stat_k].append((mask, ev_str))
                    for sp_v in range(N):
                        unary_ll[stat_k][sp_v] += ll_add[sp_v]

            else:
                # Defensive: trainer_1 hit trainer_2 -> build 33x33 (sp_hp, sp_def) matrix
                mat = [[False] * N for _ in range(N)]
                mat_ll = [[0.0] * N for _ in range(N)]
                any_ok = False
                for d_sp in range(N):
                    res = dmg_results[s_idx + d_sp]
                    if not res.ok:
                        continue
                    rolls = res.rolls_16
                    for h_sp in range(N):
                        max_hp = base_stats["hp"] + h_sp + 75
                        lo_b, hi_b = _possible_cur_hp_for_pct(max_hp, obs_d.hp_pct_before)
                        if obs_d.is_ohko or obs_d.focus_sash_or_sturdy:
                            if res.max_damage >= lo_b:
                                mat[h_sp][d_sp] = True
                                any_ok = True
                                cnt_ko = sum(1 for rv in rolls if rv >= lo_b)
                                mat_ll[h_sp][d_sp] = math.log(max(0.05, cnt_ko / 16.0)) * 0.35
                        else:
                            matched_rolls = 0
                            dist_sum = 0.0
                            for r_i, rv in enumerate(rolls):
                                ok_r = False
                                for cur_b in range(lo_b, hi_b + 1):
                                    cur_a = cur_b - rv
                                    if cur_a >= 1 and _showdown_pct_matches(cur_a, max_hp, obs_d.hp_pct_after):
                                        ok_r = True
                                        break
                                if ok_r:
                                    matched_rolls += 1
                                    dist_sum += abs(r_i - 7.5)
                            if matched_rolls > 0:
                                mat[h_sp][d_sp] = True
                                any_ok = True
                                avg_d = dist_sum / matched_rolls
                                mat_ll[h_sp][d_sp] = math.log(matched_rolls / 16.0) - 0.03 * avg_d

                if any_ok:
                    ko_lbl = " (KO)" if obs_d.is_ohko else ""
                    ev_str = (
                        f"G{obs_d.game_index} T{obs_d.turn}: took {obs_d.attacker}'s {obs_d.move} "
                        f"({obs_d.hp_pct_before:.0f}%->{obs_d.hp_pct_after:.0f}%{ko_lbl})"
                    )
                    pair_constraints[stat_k].append((mat, ev_str))
                    for h_sp in range(N):
                        for d_sp in range(N):
                            pair_ll[stat_k][h_sp][d_sp] += mat_ll[h_sp][d_sp]

        # 3. Process HP Tick Observations (Recoil, Sitrus, Leftovers, Grassy, Life Orb, Burn, Sand)
        for tick in hp_ticks:
            mask = [False] * N
            for h_sp in range(N):
                max_hp = base_stats["hp"] + h_sp + 75
                lo_b, hi_b = _possible_cur_hp_for_pct(max_hp, tick.hp_pct_before)
                if tick.kind == "recoil" and tick.source_damage_hp_exact is not None and tick.source_damage_hp_exact > 0:
                    frac = tick.recoil_fraction or (1.0 / 3.0)
                    rec_c1 = max(1, int(round(tick.source_damage_hp_exact * frac)))
                    rec_c2 = max(1, int(round(tick.source_damage_hp_exact / 3.0))) if abs(frac - 0.33) < 0.02 else rec_c1
                    rec_cands = set(range(max(1, min(rec_c1, rec_c2) - 1), max(rec_c1, rec_c2) + 2))
                    for cur_b in range(lo_b, hi_b + 1):
                        if any(_showdown_pct_matches(max(0, cur_b - rc), max_hp, tick.hp_pct_after) for rc in rec_cands):
                            mask[h_sp] = True
                            break
                elif tick.kind == "sitrus":
                    heal_hp = max(1, max_hp // 4)
                    for cur_b in range(lo_b, hi_b + 1):
                        if cur_b <= max_hp // 2 and _showdown_pct_matches(min(max_hp, cur_b + heal_hp), max_hp, tick.hp_pct_after):
                            mask[h_sp] = True
                            break
                elif tick.kind in ("leftovers", "grassy"):
                    heal_hp = max(1, max_hp // 16)
                    for cur_b in range(lo_b, hi_b + 1):
                        if _showdown_pct_matches(min(max_hp, cur_b + heal_hp), max_hp, tick.hp_pct_after):
                            mask[h_sp] = True
                            break
                elif tick.kind == "life_orb":
                    chip_hp = max(1, max_hp // 10)
                    for cur_b in range(lo_b, hi_b + 1):
                        if _showdown_pct_matches(max(0, cur_b - chip_hp), max_hp, tick.hp_pct_after):
                            mask[h_sp] = True
                            break
                elif tick.kind in ("burn", "sand"):
                    chip_hp = max(1, max_hp // 16)
                    for cur_b in range(lo_b, hi_b + 1):
                        if _showdown_pct_matches(max(0, cur_b - chip_hp), max_hp, tick.hp_pct_after):
                            mask[h_sp] = True
                            break

            if any(mask) and not all(mask):
                lo_s = next(i for i, ok in enumerate(mask) if ok)
                hi_s = max(i for i, ok in enumerate(mask) if ok)
                ev_str = (
                    f"G{tick.game_index} T{tick.turn}: {tick.kind} tick "
                    f"({tick.hp_pct_before:.0f}%->{tick.hp_pct_after:.0f}%) -> HP {lo_s}-{hi_s} SP"
                )
                unary_constraints["hp"].append((mask, ev_str))

        # 4. Intersect Constraints with Soft-Penalty Resilience
        soft_fallback = False
        unary_masks: Dict[str, List[bool]] = {}
        for sk in STAT_KEYS:
            cur_m = [True] * N
            for c_mask, ev_str in unary_constraints[sk]:
                inter = [cur_m[i] and c_mask[i] for i in range(N)]
                if any(inter):
                    cur_m = inter
                    evidence[sk].append(ev_str)
                else:
                    soft_fallback = True
                    notes.append(f"Soft-relaxed conflicting {sk.upper()} constraint: {ev_str}")
            unary_masks[sk] = cur_m

        pair_masks: Dict[str, List[List[bool]]] = {}
        for dk in ("def", "spd"):
            cur_mat = [[True] * N for _ in range(N)]
            for c_mat, ev_str in pair_constraints[dk]:
                inter_mat = [[cur_mat[h][d] and c_mat[h][d] for d in range(N)] for h in range(N)]
                if any(inter_mat[h][d] for h in range(N) for d in range(N)):
                    cur_mat = inter_mat
                    evidence[dk].append(ev_str)
                    evidence["hp"].append(ev_str)
                else:
                    soft_fallback = True
                    notes.append(f"Soft-relaxed conflicting HP/{dk.upper()} bulk constraint: {ev_str}")
            pair_masks[dk] = cur_mat

        # 5. Exact 33-HP-Slice × 5-Stat DP Projection onto `sum(SP) == 66, 0 <= SP <= 32`
        proj = self._project_and_optimize_66sp_dp(
            mon=mon,
            base_stats=base_stats,
            nature=nature,
            item=item,
            team_has_trick_room=team_has_trick_room,
            unary_masks=unary_masks,
            unary_ll=unary_ll,
            pair_masks=pair_masks,
            pair_ll=pair_ll,
        )
        if proj is None:
            # Joint intersection with sum == 66 was empty -> relax pairwise bulk first, then unary
            soft_fallback = True
            notes.append("Joint 66-SP budget projection required soft relaxation of conflicting observations.")
            relaxed_pair = {
                "def": [[True] * N for _ in range(N)],
                "spd": [[True] * N for _ in range(N)],
            }
            proj = self._project_and_optimize_66sp_dp(
                mon=mon,
                base_stats=base_stats,
                nature=nature,
                item=item,
                team_has_trick_room=team_has_trick_room,
                unary_masks=unary_masks,
                unary_ll=unary_ll,
                pair_masks=relaxed_pair,
                pair_ll=pair_ll,
            )
            if proj is None:
                all_open = {sk: [True] * N for sk in STAT_KEYS}
                proj = self._project_and_optimize_66sp_dp(
                    mon=mon,
                    base_stats=base_stats,
                    nature=nature,
                    item=item,
                    team_has_trick_room=team_has_trick_room,
                    unary_masks=all_open,
                    unary_ll=unary_ll,
                    pair_masks=relaxed_pair,
                    pair_ll=pair_ll,
                )

        assert proj is not None
        min_bounds, max_bounds, best_sp_dict = proj

        bounds_out: Dict[str, StatBound] = {}
        for sk in STAT_KEYS:
            lo_v = int(min_bounds[sk])
            hi_v = int(max_bounds[sk])
            def_v = int(best_sp_dict[sk])
            if lo_v == hi_v:
                status = "pinned"
            elif lo_v > 0 or hi_v < MAX_SINGLE_STAT_SP:
                status = "bounded"
            else:
                status = "unobserved"
            # Deduplicate evidence preserving order
            dedup_ev = list(dict.fromkeys(evidence[sk]))
            bounds_out[sk] = StatBound(
                stat=sk,
                min_sp=lo_v,
                max_sp=hi_v,
                default_sp=def_v,
                status=status,
                evidence=dedup_ev,
            )

        default_spread = StatSpread.from_dict(best_sp_dict)
        l50_stats = compute_level_50_stats_from_base(base_stats, default_spread, nature)

        return PokemonSPInference(
            species=base_sp,
            base_species=base_sp,
            item=item,
            ability=mon.ability,
            nature=nature,
            moves=list(mon.moves or []),
            base_stats=base_stats,
            bounds=bounds_out,
            default_spread=default_spread,
            default_l50_stats=l50_stats,
            speed_obs_count=len(speed_jobs),
            damage_obs_count=len(dmg_jobs),
            hp_tick_obs_count=len(hp_ticks),
            soft_fallback_used=soft_fallback,
            notes=notes,
        )

    def _build_vgc_role_priors(
        self,
        mon: ParsedPokemon,
        base_stats: Dict[str, int],
        nature: str,
        item: Optional[str],
        team_has_trick_room: bool,
    ) -> Dict[str, List[float]]:
        """Deterministic, zero-AI Champions VGC builder priors per stat value `0..32`.

        Used strictly as tie-breakers inside empirically feasible intervals and to produce
        competitive defaults for unobserved stats (e.g., bench Pokémon or untested SpD).
        """
        N = MAX_SINGLE_STAT_SP + 1
        phys_cnt = sum(1 for m in (mon.moves or []) if self._get_move_category(m) == "Physical")
        spec_cnt = sum(1 for m in (mon.moves or []) if self._get_move_category(m) == "Special")
        uses_atk = phys_cnt > 0
        uses_spa = spec_cnt > 0
        is_physical = (phys_cnt > spec_cnt) or (phys_cnt == spec_cnt and base_stats["atk"] >= base_stats["spa"])
        off_key = "atk" if is_physical else "spa"
        unused_off = "spa" if is_physical else "atk"
        both_off = uses_atk and uses_spa

        is_tr_nature = nature in ("Brave", "Quiet", "Relaxed", "Sassy")
        is_fast_nature = nature in ("Jolly", "Timid", "Hasty", "Naive")
        is_bulk_nature = nature in ("Bold", "Impish", "Calm", "Careful")
        is_glass_item = item in ("Focus Sash", "Choice Scarf")
        is_bulk_item = item in ("Leftovers", "Sitrus Berry", "Rocky Helmet", "Light Clay")
        is_tr_slow = is_tr_nature or (team_has_trick_room and base_stats["spe"] <= 60 and not is_fast_nature)

        # Target archetype centers (soft Gaussian prior weight so real observations always dominate!)
        targets: Dict[str, Tuple[float, float]] = {}  # stat -> (center, weight)
        if is_glass_item or (is_fast_nature and base_stats["spe"] >= 95):
            targets = {
                "hp": (2.0, 0.08),
                off_key: (32.0, 0.14),
                "spe": (32.0, 0.14),
                "def": (0.0, 0.05),
                "spd": (0.0, 0.05),
                unused_off: (0.0, 0.25 if not both_off else 0.02),
            }
        elif is_tr_slow:
            targets = {
                "hp": (32.0, 0.14),
                off_key: (32.0 if not is_bulk_nature else 6.0, 0.12),
                "spe": (0.0, 0.22),
                "def": (14.0 if is_bulk_nature else 2.0, 0.07),
                "spd": (14.0 if is_bulk_nature else 2.0, 0.07),
                unused_off: (0.0, 0.25 if not both_off else 0.02),
            }
        elif is_bulk_nature or is_bulk_item:
            # Support / bulky pivot: optimize HP + balanced Def/SpD
            def_pref = 20.0 if nature in ("Bold", "Impish") else 14.0
            spd_pref = 20.0 if nature in ("Calm", "Careful") else 14.0
            off_pref = 4.0 if is_bulk_nature else 16.0
            targets = {
                "hp": (32.0, 0.14),
                off_key: (off_pref, 0.06),
                "def": (def_pref, 0.08),
                "spd": (spd_pref, 0.08),
                "spe": (2.0, 0.06),
                unused_off: (0.0, 0.25 if not both_off else 0.02),
            }
        else:
            # Modest / Adamant bulky offensive attacker
            spe_pref = 24.0 if base_stats["spe"] >= 90 else 10.0
            hp_pref = 10.0 if base_stats["spe"] >= 90 else 24.0
            targets = {
                "hp": (hp_pref, 0.08),
                off_key: (32.0, 0.12),
                "spe": (spe_pref, 0.08),
                "def": (2.0, 0.04),
                "spd": (2.0, 0.04),
                unused_off: (0.0, 0.25 if not both_off else 0.02),
            }

        priors: Dict[str, List[float]] = {}
        for sk in STAT_KEYS:
            center, w = targets[sk]
            vals: List[float] = []
            for sp_v in range(N):
                # Never waste SPs on a strictly unused offensive stat (e.g. Atk on a pure Special attacker)
                if sk == unused_off and not both_off:
                    score = -2.5 * float(sp_v)
                else:
                    # Mild concave quadratic penalty around role target (bounded magnitude ~0..0.3)
                    dist = (sp_v - center) / 32.0
                    score = -w * (dist * dist)
                # Subtle Champions HP benchmark bonus (16n / 10n-1 for Leftovers/Life Orb efficiency)
                if sk == "hp" and item == "Life Orb":
                    hp_val = base_stats["hp"] + sp_v + 75
                    if hp_val % 10 == 9:
                        score += 0.015
                elif sk == "hp" and item == "Leftovers":
                    hp_val = base_stats["hp"] + sp_v + 75
                    if hp_val % 16 == 0:
                        score += 0.015
                vals.append(score)
            priors[sk] = vals
        return priors

    def _project_and_optimize_66sp_dp(
        self,
        mon: ParsedPokemon,
        base_stats: Dict[str, int],
        nature: str,
        item: Optional[str],
        team_has_trick_room: bool,
        unary_masks: Dict[str, List[bool]],
        unary_ll: Dict[str, List[float]],
        pair_masks: Dict[str, List[List[bool]]],
        pair_ll: Dict[str, List[List[float]]],
    ) -> Optional[Tuple[Dict[str, int], Dict[str, int], Dict[str, int]]]:
        """Exact 33-HP-slice × 5-stat DP computing:
        1. Tight exact projected bounds `(min_bounds, max_bounds)` across ALL 6 stats under `sum == 66`.
        2. Global highest-scoring legal 66-SP vector `(obs_ll + deterministic_vgc_role_prior)`.
        """
        N = MAX_SINGLE_STAT_SP + 1
        B = MAX_TOTAL_SP  # 66
        priors = self._build_vgc_role_priors(mon, base_stats, nature, item, team_has_trick_room)

        min_b: Dict[str, int] = {sk: MAX_SINGLE_STAT_SP + 1 for sk in STAT_KEYS}
        max_b: Dict[str, int] = {sk: -1 for sk in STAT_KEYS}
        best_total_score = -1e18
        best_vec: Optional[Dict[str, int]] = None

        # Loop over all feasible HP SP values (0..32); for fixed HP, the 5 remaining stats decouple cleanly!
        for h in range(N):
            if not unary_masks["hp"][h]:
                continue
            rem_budget = B - h
            if rem_budget < 0:
                continue

            # Valid domains & scores for the 5 non-HP stats given fixed `h`
            doms: List[List[int]] = []
            scores_per_stat: List[Dict[int, float]] = []
            impossible_h = False
            for sk in NON_HP_KEYS:
                valid_vals: List[int] = []
                sc_map: Dict[int, float] = {}
                for v in range(N):
                    if not unary_masks[sk][v]:
                        continue
                    if sk in ("def", "spd") and not pair_masks[sk][h][v]:
                        continue
                    valid_vals.append(v)
                    sc = unary_ll[sk][v] + priors[sk][v]
                    if sk in ("def", "spd"):
                        sc += pair_ll[sk][h][v]
                    sc_map[v] = sc
                if not valid_vals:
                    impossible_h = True
                    break
                doms.append(valid_vals)
                scores_per_stat.append(sc_map)
            if impossible_h:
                continue

            # Forward reachability DP (prefix[i][s] = True iff stats 0..i-1 can sum to s)
            # and backward reachability DP (suffix[i][s] = True iff stats i..4 can sum to s)
            prefix = [[False] * (rem_budget + 1) for _ in range(6)]
            prefix[0][0] = True
            for i in range(5):
                prev_row = prefix[i]
                cur_row = prefix[i + 1]
                for s in range(rem_budget + 1):
                    if not prev_row[s]:
                        continue
                    for v in doms[i]:
                        ns = s + v
                        if ns <= rem_budget:
                            cur_row[ns] = True

            if not prefix[5][rem_budget]:
                continue

            suffix = [[False] * (rem_budget + 1) for _ in range(6)]
            suffix[5][0] = True
            for i in range(4, -1, -1):
                next_row = suffix[i + 1]
                cur_row = suffix[i]
                for s in range(rem_budget + 1):
                    if not next_row[s]:
                        continue
                    for v in doms[i]:
                        ns = s + v
                        if ns <= rem_budget:
                            cur_row[ns] = True

            # Update exact projected bounds for HP and each of the 5 non-HP stats!
            if h < min_b["hp"]:
                min_b["hp"] = h
            if h > max_b["hp"]:
                max_b["hp"] = h

            for i, sk in enumerate(NON_HP_KEYS):
                pref_i = prefix[i]
                suff_next = suffix[i + 1]
                for v in doms[i]:
                    # Value `v` at stat `i` participates in a legal sum==66 solution iff
                    # exists s_before in 0..rem_budget-v with pref_i[s_before] and suff_next[rem_budget - v - s_before]
                    if v >= min_b[sk] and v <= max_b[sk]:
                        continue
                    target_rem = rem_budget - v
                    for sb in range(target_rem + 1):
                        if pref_i[sb] and suff_next[target_rem - sb]:
                            if v < min_b[sk]:
                                min_b[sk] = v
                            if v > max_b[sk]:
                                max_b[sk] = v
                            break

            # Exact max-score DP over the 5 non-HP stats summing to rem_budget
            NEG_INF = -1e18
            dp_sc = [[NEG_INF] * (rem_budget + 1) for _ in range(6)]
            dp_choice = [[-1] * (rem_budget + 1) for _ in range(6)]
            dp_sc[0][0] = unary_ll["hp"][h] + priors["hp"][h]

            for i in range(5):
                prev_sc = dp_sc[i]
                cur_sc = dp_sc[i + 1]
                cur_ch = dp_choice[i + 1]
                sc_map = scores_per_stat[i]
                for s in range(rem_budget + 1):
                    base_val = prev_sc[s]
                    if base_val <= NEG_INF * 0.5:
                        continue
                    for v in doms[i]:
                        ns = s + v
                        if ns <= rem_budget:
                            cand_sc = base_val + sc_map[v]
                            if cand_sc > cur_sc[ns]:
                                cur_sc[ns] = cand_sc
                                cur_ch[ns] = v

            if dp_sc[5][rem_budget] > best_total_score:
                best_total_score = dp_sc[5][rem_budget]
                sol: Dict[str, int] = {"hp": h}
                rem = rem_budget
                for i in range(4, -1, -1):
                    chosen_v = dp_choice[i + 1][rem]
                    sol[NON_HP_KEYS[i]] = chosen_v
                    rem -= chosen_v
                best_vec = sol

        if best_vec is None:
            return None
        return min_b, max_b, best_vec
