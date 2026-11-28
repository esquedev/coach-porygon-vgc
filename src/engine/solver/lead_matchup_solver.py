# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Factored 90×90 Turn-1 Lead & Bring Nash Equilibrium Solver
==============================================================================

Pure-domain Regulation M-C Team-Preview solver operating on the vectorized
`VgcTensorStateMachine` and `LogicalConstraintEngine` (zero HTTP/UI imports).

Given two Regulation M-C teams (`trainer_1` vs `trainer_2`, 4–6 Pokémon each):
1. Pre-compiles every Pokémon's `MonIdx` row (`[MON_DIM]`) and `MoveIdx` matrix
   (`[4, MOVE_DIM]`) **once** upfront via `TurnStateCompiler` + `ShowdownTensorCompiler`,
   enforcing Regulation M-C invariants:
   - Mandatory 31 IVs, `<= 66` total Stat Points (`<= 32` per stat), zero Terastallization.
   - Pre-Mega Base Form at Turn 0 (`IS_MEGA = 0.0`, `CAN_MEGA = 1.0` for Mega Stone holders)
     so Turn-0 speed order and Turn-1 Barrier 2 Mega Evolution (Priority `+5.5`) are exact.
   - `MonIdx.ACTIVE_TURNS == 0.0` on active leads so Turn-1 `Fake Out` / `First Impression`
     remain legal unless blocked by Turn-0 `Psychic Surge` (grounded) or `Armor Tail`.
2. For each of the `C(n1, 2) × C(n2, 2)` (up to `15 × 15 = 225`) lead pairs:
   - Fires `resolve_turn_zero_lead_entry(...)` **once** BEFORE action pruning so
     speed-ordered Weather, Terrain, `Intimidate -> Defiant/Competitive/Mirror Armor/
     Flower Veil/Contrary/White Herb+Unburden`, `Trace`, `Hospitality`, and Terrain Seeds
     resolve cleanly and never double-fire on Turn 1.
   - Factors the Turn-1 action space across all remaining bench Pokémon into 4 compact
     GPU-safe blocks (`Stay×Stay`, `Sw1×Stay2`, `Stay1×Sw2`, `Sw1×Sw2`, `tile_size <= 20`),
     strictly preserving Single-Mega exclusivity (`M[12:24, 12:24] = 0`) and symmetric
     single-switch action unions `S_stay ∪ Sw(b_first) ∪ Sw(b_second)` across all 6 Back-2
     benches (zero Turn-1 double-switch bias).
   - Combines each exact Turn-1 Risk-Adjusted Nash value (`CVaR_0.10`, `lambda = 0.25`)
     with a bounded (`±0.15`) DuckDB-grounded **Post-Turn-1 Bench Matchup Residual**
     computed strictly from each Pokémon's 4 verified paste moves and defender ability
     immunities.
3. Solves the global `90 × 90` (`8,100`-mode) Team-Preview Zero-Sum Nash Equilibrium LP
   and Logit QRE, returning Top Brings Podium, Opponent Counter-Leads, and a complete
   `15 × 15 × (6 × 6)` hierarchical drilldown dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from engine.game_rules import TYPE_CHART
from engine.inference.tournament_db import (
    TournamentUsageRepository,
    get_tournament_repository,
)
from engine.parser.models import ParsedPokemon
from engine.parser.showdown_parser import parse_showdown_paste
from engine.solver.game_theory import (
    decode_joint_action,
    solve_quantal_response,
    solve_zero_sum_nash,
)
from engine.state.models import CompiledPokemonState
from engine.state.state_compiler import TurnStateCompiler
from engine.vgc_tensor_core.compiler import (
    CHOICE_SWITCH_BENCH1,
    CHOICE_SWITCH_BENCH2,
    CompiledBattleState,
    ShowdownTensorCompiler,
)
from engine.vgc_tensor_core.phases_pre_attack import (
    T_ELECTRIC,
    T_GRASSY,
    T_MISTY,
    T_PSYCHIC,
    W_RAIN,
    W_SAND,
    W_SNOW,
    W_SUN,
    resolve_turn_zero_lead_entry,
)
from engine.vgc_tensor_core.schema_and_tables import (
    FIELD_DIM,
    FieldIdx,
    HAS_TORCH,
    MON_DIM,
    MOVE_DIM,
    MOVES_PER_MON,
    MonIdx,
    ROSTER_SLOTS,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_1_BENCH1,
    SLOT_TRAINER_1_BENCH2,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    SLOT_TRAINER_2_BENCH1,
    SLOT_TRAINER_2_BENCH2,
    TERRAIN_TO_IDX,
    WEATHER_TO_IDX,
)
from engine.vgc_tensor_core.state_machine import (
    AnalysisCancelledError,
    VgcTensorStateMachine,
)

if HAS_TORCH:
    import torch
else:
    torch = None  # type: ignore


_BALL_BOMB_MOVES = frozenset(
    {
        "Acid Spray",
        "Aura Sphere",
        "Bullet Seed",
        "Electro Ball",
        "Energy Ball",
        "Focus Blast",
        "Gyro Ball",
        "Ice Ball",
        "Magnet Bomb",
        "Mud Bomb",
        "Octazooka",
        "Pollen Puff",
        "Pyro Ball",
        "Rock Blast",
        "Rock Wrecker",
        "Searing Shot",
        "Seed Bomb",
        "Shadow Ball",
        "Sludge Bomb",
        "Weather Ball",
        "Zap Cannon",
    }
)

_SOUND_MOVES_FALLBACK = frozenset(
    {
        "Alluring Voice",
        "Boomburst",
        "Bug Buzz",
        "Clangorous Soul",
        "Clanging Scales",
        "Disarming Voice",
        "Hyper Voice",
        "Overdrive",
        "Parting Shot",
        "Perish Song",
        "Psychic Noise",
        "Relic Song",
        "Roar",
        "Snarl",
        "Sparkling Aria",
        "Torch Song",
        "Uproar",
    }
)


@dataclass(frozen=True)
class LeadMatchupConfig:
    """Configuration parameters for the Factored `90 × 90` Turn-1 Lead & Bring Lab.

    Attributes:
        preset: Human-readable depth preset (`'fast'`, `'balanced'`, `'tournament'`).
        num_rng_samples: Discrete Spinning-Wheel Monte Carlo threads `K` per Turn-1 cell.
        cap_stay: Maximum prior-ranked stay-in joint actions (`c_a < 24 and c_b < 24`) per side.
        cap_switch_per_mon: Maximum prior-ranked single-switch actions per bench teammate.
        bench_residual_weight: Maximum absolute weight (`±w`) of the DuckDB-grounded
            post-Turn-1 Bench Matchup Residual added to Turn-1 payoff sub-matrices.
        risk_aversion_lambda: Downside CVaR_0.10 weight (default `0.25`).
        rng_seed: Deterministic SplitMix64 base seed.
        tile_size: Maximum GPU tile dimension (`<= 24`) to keep VRAM strictly `< 600 MB`.
        device: Target compute device (`'cuda'`, `'cpu'`, or `None` for auto-detect).
        require_explicit_spreads: When True, rejects bare EV-less OTS pastes where every
            Pokémon has `0` total SP (enforcing Bo3-parity SP rigor).
    """

    preset: str = "balanced"
    num_rng_samples: int = 32
    cap_stay: int = 20
    cap_switch_per_mon: int = 4
    bench_residual_weight: float = 0.15
    risk_aversion_lambda: float = 0.25
    rng_seed: int = 42
    tile_size: int = 20
    device: Optional[str] = None
    compute_mode: str = "auto"
    require_explicit_spreads: bool = True

    @classmethod
    def from_preset(
        cls,
        preset: str = "balanced",
        device: Optional[str] = None,
        require_explicit_spreads: bool = True,
        compute_mode: str = "auto",
    ) -> "LeadMatchupConfig":
        """Construct a hardware-aware configuration from `'fast'`, `'balanced'`, or `'tournament'`."""
        clean = str(preset or "balanced").strip().lower()
        clean_mode = str(compute_mode or "auto").strip().lower()
        if clean_mode not in ("auto", "hybrid", "gpu_only", "cpu_parallel"):
            clean_mode = "auto"
        use_cuda = bool(
            clean_mode != "cpu_parallel"
            and (
                (device is not None and str(device).startswith("cuda"))
                or (device is None and HAS_TORCH and torch.cuda.is_available())
            )
        )
        if clean == "fast":
            return cls(
                preset="fast",
                num_rng_samples=16 if use_cuda else 8,
                cap_stay=16,
                cap_switch_per_mon=3,
                tile_size=16,
                device=device,
                compute_mode=clean_mode,
                require_explicit_spreads=require_explicit_spreads,
            )
        if clean == "tournament":
            return cls(
                preset="tournament",
                num_rng_samples=48 if use_cuda else 16,
                cap_stay=24,
                cap_switch_per_mon=5,
                tile_size=20,
                device=device,
                compute_mode=clean_mode,
                require_explicit_spreads=require_explicit_spreads,
            )
        return cls(
            preset="balanced",
            num_rng_samples=32 if use_cuda else 12,
            cap_stay=20,
            cap_switch_per_mon=4,
            tile_size=20,
            device=device,
            compute_mode=clean_mode,
            require_explicit_spreads=require_explicit_spreads,
        )


@dataclass(frozen=True)
class BringModeSpec:
    """Metadata describing one 4-Pokémon bring mode `(Lead Pair + Back-2 Bench)`."""

    mode_idx: int
    lead_idx: int
    bench_idx: int
    lead_indices: Tuple[int, int]
    bench_indices: Tuple[int, int]
    lead_species: Tuple[str, str]
    bench_species: Tuple[str, str]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this bring mode to a JSON-friendly dictionary."""
        return {
            "mode_idx": self.mode_idx,
            "lead_idx": self.lead_idx,
            "bench_idx": self.bench_idx,
            "lead_indices": list(self.lead_indices),
            "bench_indices": list(self.bench_indices),
            "lead_species": list(self.lead_species),
            "bench_species": list(self.bench_species),
        }


@dataclass(frozen=True)
class CompiledTeamPool:
    """Pre-compiled single-team tensor pool for zero-overhead Turn-1 board slicing."""

    trainer_id: str
    mons: Tuple[CompiledPokemonState, ...]
    display_species: Tuple[str, ...]
    roster_rows: np.ndarray  # [N, MON_DIM]
    move_rows: np.ndarray  # [N, 4, MOVE_DIM]
    move_names: Tuple[Tuple[str, ...], ...]
    leads: Tuple[Tuple[int, int], ...]
    benches_for_lead: Tuple[Tuple[Tuple[int, int], ...], ...]
    modes: Tuple[BringModeSpec, ...]


@dataclass(frozen=True)
class LeadMatchupResult:
    """Complete hierarchical output of the Factored `90 × 90` Turn-1 Lead & Bring Nash Lab."""

    trainer_1_species: List[str]
    trainer_2_species: List[str]
    trainer_1_leads: List[Tuple[str, str]]
    trainer_2_leads: List[Tuple[str, str]]
    modes_t1: List[BringModeSpec]
    modes_t2: List[BringModeSpec]
    payoff_matrix: np.ndarray
    global_game_value: float
    trainer_1_nash_weights: np.ndarray
    trainer_2_nash_weights: np.ndarray
    trainer_1_qre_weights: np.ndarray
    trainer_2_qre_weights: np.ndarray
    trainer_1_top_brings: List[Dict[str, Any]]
    trainer_2_top_brings: List[Dict[str, Any]]
    heatmap_cells: List[List[Dict[str, Any]]]
    device_used: str
    preset: str
    elapsed_s: float
    total_modes_evaluated: int
    hardware_device_name: str = ""
    worker_cell_counts: Dict[str, int] = field(default_factory=dict)
    compute_mode: str = "auto"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the full `90 × 90` Nash result into a JSON-ready payload for Studio UI."""
        return {
            "trainer_1_species": list(self.trainer_1_species),
            "trainer_2_species": list(self.trainer_2_species),
            "trainer_1_leads": [list(p) for p in self.trainer_1_leads],
            "trainer_2_leads": [list(p) for p in self.trainer_2_leads],
            "t1_leads": [list(p) for p in self.trainer_1_leads],
            "t2_leads": [list(p) for p in self.trainer_2_leads],
            "num_t1_modes": len(self.modes_t1),
            "num_t2_modes": len(self.modes_t2),
            "modes_t1": [m.to_dict() for m in self.modes_t1],
            "modes_t2": [m.to_dict() for m in self.modes_t2],
            "global_game_value": round(float(self.global_game_value), 4),
            "trainer_1_top_brings": list(self.trainer_1_top_brings),
            "trainer_2_top_brings": list(self.trainer_2_top_brings),
            "payoff_matrix": np.round(self.payoff_matrix, 3).tolist(),
            "heatmap_cells": self.heatmap_cells,
            "device_used": self.device_used,
            "hardware_device_name": self.hardware_device_name or self.device_used,
            "worker_cell_counts": dict(self.worker_cell_counts),
            "compute_mode": self.compute_mode,
            "preset": self.preset,
            "elapsed_s": round(float(self.elapsed_s), 2),
            "total_modes_evaluated": int(self.total_modes_evaluated),
            "num_t1_leads": len(self.trainer_1_leads),
            "num_t2_leads": len(self.trainer_2_leads),
        }


def _deduplicate_parsed_team(parsed_dict: Dict[str, ParsedPokemon]) -> List[ParsedPokemon]:
    """Extract unique Pokémon in paste order, filtering duplicate nickname/species alias keys."""
    seen_ids: set[int] = set()
    seen_species: set[str] = set()
    unique: List[ParsedPokemon] = []
    for pkm in parsed_dict.values():
        obj_id = id(pkm)
        if obj_id in seen_ids:
            continue
        seen_ids.add(obj_id)
        canon = str(pkm.base_species or pkm.species).strip().lower()
        if canon in seen_species:
            continue
        seen_species.add(canon)
        unique.append(pkm)
    return unique


def _validate_reg_mc_team_spreads(
    mons: Sequence[ParsedPokemon],
    trainer_id: str,
    require_explicit_spreads: bool,
) -> None:
    """Validate Regulation M-C team size (`4..6`) and 66-SP (`<= 32` per stat) invariants."""
    if len(mons) < 4 or len(mons) > 6:
        raise ValueError(
            f"{trainer_id} must contain between 4 and 6 unique Pokémon (found {len(mons)})."
        )
    total_team_sp = 0
    for pkm in mons:
        sp_dict = pkm.spread.to_dict()
        mon_total = 0
        for stat_key, val in sp_dict.items():
            iv_val = int(val)
            if iv_val < 0 or iv_val > 32:
                raise ValueError(
                    f"{trainer_id} {pkm.species}: {stat_key.upper()} SP={iv_val} violates "
                    "Regulation M-C 0..32 single-stat cap."
                )
            mon_total += iv_val
        if mon_total > 66:
            raise ValueError(
                f"{trainer_id} {pkm.species}: Total SP={mon_total} exceeds Regulation M-C 66-SP budget."
            )
        total_team_sp += mon_total

    if require_explicit_spreads and total_team_sp == 0:
        raise ValueError(
            f"{trainer_id} paste appears to be an EV-less OTS (0 SP across all Pokémon). "
            "Provide a Full 66-SP paste or solve opponent 66-SP from 1–3 Bo3 scouting logs first."
        )


def _describe_turn0_events(
    f_t0: np.ndarray,
    p_before: np.ndarray,
    p_after: np.ndarray,
    slot_species: Sequence[str],
) -> List[str]:
    """Summarize Turn-0 entry weather, terrain, Intimidate, and Seed/White Herb triggers."""
    events: List[str] = []
    weather_names = {
        W_SUN: "Sun",
        W_RAIN: "Rain",
        W_SAND: "Sandstorm",
        W_SNOW: "Snow",
    }
    for w_idx, w_name in weather_names.items():
        if float(f_t0[FieldIdx.WEATHER_START + w_idx]) > 0.5:
            events.append(f"Turn-0 Weather: {w_name}")
            break

    terrain_names = {
        T_ELECTRIC: "Electric Terrain",
        T_GRASSY: "Grassy Terrain",
        T_PSYCHIC: "Psychic Terrain",
        T_MISTY: "Misty Terrain",
    }
    for t_idx, t_name in terrain_names.items():
        if float(f_t0[FieldIdx.TERRAIN_START + t_idx]) > 0.5:
            events.append(f"Turn-0 Terrain: {t_name}")
            break

    for slot in (SLOT_TRAINER_1_A, SLOT_TRAINER_1_B, SLOT_TRAINER_2_A, SLOT_TRAINER_2_B):
        sp = slot_species[slot]
        side_tag = "T1" if slot in (SLOT_TRAINER_1_A, SLOT_TRAINER_1_B) else "T2"
        d_atk = int(round(float(p_after[slot, MonIdx.BOOST_ATK] - p_before[slot, MonIdx.BOOST_ATK])))
        d_spa = int(round(float(p_after[slot, MonIdx.BOOST_SPA] - p_before[slot, MonIdx.BOOST_SPA])))
        d_def = int(round(float(p_after[slot, MonIdx.BOOST_DEF] - p_before[slot, MonIdx.BOOST_DEF])))
        d_spd = int(round(float(p_after[slot, MonIdx.BOOST_SPD] - p_before[slot, MonIdx.BOOST_SPD])))
        unb = float(p_after[slot, MonIdx.UNBURDEN_ACTIVE]) > 0.5 and float(p_before[slot, MonIdx.UNBURDEN_ACTIVE]) < 0.5
        parts: List[str] = []
        if d_atk != 0:
            parts.append(f"{d_atk:+d} Atk")
        if d_spa != 0:
            parts.append(f"{d_spa:+d} SpA")
        if d_def != 0:
            parts.append(f"{d_def:+d} Def")
        if d_spd != 0:
            parts.append(f"{d_spd:+d} SpD")
        if unb:
            parts.append("Unburden 2× Spe")
        if parts:
            events.append(f"{side_tag} {sp}: {', '.join(parts)}")
    return events


def _effective_move_multiplier(
    move_type: str,
    move_name: str,
    move_flags: Dict[str, Any],
    att_ability: str,
    def_types: Sequence[str],
    def_ability: str,
) -> Tuple[float, str]:
    """Compute exact Regulation M-C type multiplier respecting abilities, -ate, and Freeze-Dry."""
    eff_type = move_type
    ab_att = att_ability.strip().lower()
    ab_def = def_ability.strip().lower()

    # Ability move-type conversions
    if eff_type == "Normal":
        if ab_att == "pixilate":
            eff_type = "Fairy"
        elif ab_att == "aerilate":
            eff_type = "Flying"
        elif ab_att == "refrigerate":
            eff_type = "Ice"
    is_sound = bool(move_flags.get("sound")) or (move_name in _SOUND_MOVES_FALLBACK)
    if ab_att == "liquid voice" and is_sound:
        eff_type = "Water"

    # Defender ability immunities (bypassed by Mold Breaker)
    mold_breaker = ab_att in {"mold breaker", "teravolt", "turboblaze"}
    if not mold_breaker:
        if eff_type == "Ground" and ab_def in {"levitate", "earth eater", "eelevate"}:
            return 0.0, eff_type
        if eff_type == "Fire" and ab_def == "flash fire":
            return 0.0, eff_type
        if eff_type == "Water" and ab_def in {"water absorb", "dry skin", "storm drain"}:
            return 0.0, eff_type
        if eff_type == "Electric" and ab_def in {"lightning rod", "volt absorb", "motor drive"}:
            return 0.0, eff_type
        if eff_type == "Grass" and ab_def == "sap sipper":
            return 0.0, eff_type
        if is_sound and ab_def == "soundproof":
            return 0.0, eff_type
        if (bool(move_flags.get("bullet")) or move_name in _BALL_BOMB_MOVES) and ab_def == "bulletproof":
            return 0.0, eff_type

    mult = 1.0
    for d_type in def_types:
        if move_name == "Freeze-Dry" and d_type == "Water":
            mult *= 2.0
        elif ab_att == "scrappy" and d_type == "Ghost" and eff_type in {"Normal", "Fighting"}:
            mult *= 1.0
        else:
            mult *= float(TYPE_CHART.get(eff_type, {}).get(d_type, 1.0))
    return mult, eff_type


def _single_mon_matchup_score(
    att: CompiledPokemonState,
    defender: CompiledPokemonState,
) -> float:
    """Compute a bounded DuckDB-verified offensive/speed pressure score in `[-1.0, +1.0]`."""
    att_types = att.mega_types if (att.can_mega_evolve and att.mega_types) else att.types
    att_ability = (att.mega_ability or att.ability) if att.can_mega_evolve else att.ability
    att_stats = (att.mega_level_50_stats or att.level_50_stats) if att.can_mega_evolve else att.level_50_stats

    def_types = defender.mega_types if (defender.can_mega_evolve and defender.mega_types) else defender.types
    def_ability = (defender.mega_ability or defender.ability) if defender.can_mega_evolve else defender.ability
    def_stats = (
        (defender.mega_level_50_stats or defender.level_50_stats)
        if defender.can_mega_evolve
        else defender.level_50_stats
    )

    best_threat = 0.0
    for mv in att.moves:
        if mv.base_power <= 0 or mv.category == "Status":
            continue
        mult, eff_type = _effective_move_multiplier(
            move_type=mv.type,
            move_name=mv.name,
            move_flags=mv.flags,
            att_ability=att_ability,
            def_types=def_types,
            def_ability=def_ability,
        )
        if mult <= 0.0:
            continue
        stab = 1.0
        if eff_type in att_types:
            stab = 2.0 if att_ability.strip().lower() == "adaptability" else 1.5
        atk_stat = float(att_stats.get("atk" if mv.category == "Physical" else "spa", 100))
        def_stat = max(40.0, float(def_stats.get("def" if mv.category == "Physical" else "spd", 100)))
        eff_bp = float(mv.base_power) * stab * mult * (atk_stat / def_stat)
        best_threat = max(best_threat, eff_bp)

    # Normalize offensive pressure: ~120 = neutral STAB, ~260+ = strong SE threat
    off_norm = float(np.tanh((best_threat - 115.0) / 140.0))

    # Champions Level-50 Speed advantage tie-breaker
    att_spe = float(att_stats.get("spe", 100))
    def_spe = float(def_stats.get("spe", 100))
    if att_spe > def_spe:
        spe_term = 0.14
    elif att_spe < def_spe:
        spe_term = -0.14
    else:
        spe_term = 0.0

    return float(np.clip(0.86 * off_norm + spe_term, -1.0, 1.0))


def _partition_bench_chunks(rem_indices: Sequence[int]) -> List[Tuple[int, int]]:
    """Partition remaining bench Pokémon indices (`2..4` mons) into `1..2` disjoint 2-slot chunks."""
    n = len(rem_indices)
    if n < 2:
        raise ValueError(f"Expected at least 2 remaining bench Pokémon, got {n}.")
    if n == 2:
        return [(int(rem_indices[0]), int(rem_indices[1]))]
    if n == 3:
        return [
            (int(rem_indices[0]), int(rem_indices[1])),
            (int(rem_indices[2]), int(rem_indices[0])),
        ]
    return [
        (int(rem_indices[0]), int(rem_indices[1])),
        (int(rem_indices[2]), int(rem_indices[3])),
    ]


def _assemble_lead_pair_cell_from_payoffs(
    u_full: np.ndarray,
    cv_full: np.ndarray,
    lead_1_idx: int,
    lead_2_idx: int,
    n_stay1: int,
    n_stay2: int,
    r1_global_slice: Dict[int, Tuple[int, int]],
    r2_global_slice: Dict[int, Tuple[int, int]],
    stay1_labels: Sequence[str],
    stay2_labels: Sequence[str],
    sw1_labels_by_mon: Dict[int, Sequence[str]],
    sw2_labels_by_mon: Dict[int, Sequence[str]],
    turn0_events: List[str],
    lead1: Tuple[int, int],
    lead2: Tuple[int, int],
    benches1: Sequence[Tuple[int, int]],
    benches2: Sequence[Tuple[int, int]],
    display_species_1: Sequence[str],
    display_species_2: Sequence[str],
    pressure_12: np.ndarray,
    pressure_21: np.ndarray,
    bench_residual_weight: float,
) -> Dict[str, Any]:
    """Slice a fused `[B1, B2]` cell payoff matrix into all `C(n1-2, 2) × C(n2-2, 2)` bench games and solve their HiGHS Nash LPs."""
    nb1, nb2 = len(benches1), len(benches2)
    sub_scores = np.zeros((nb1, nb2), dtype=np.float64)
    sub_cvar = np.zeros((nb1, nb2), dtype=np.float64)
    sub_t1_openings: List[List[str]] = [["" for _ in range(nb2)] for _ in range(nb1)]
    sub_t2_openings: List[List[str]] = [["" for _ in range(nb2)] for _ in range(nb1)]
    sub_t1_top_plays: List[List[List[List[Any]]]] = [[[] for _ in range(nb2)] for _ in range(nb1)]
    sub_t2_top_plays: List[List[List[List[Any]]]] = [[[] for _ in range(nb2)] for _ in range(nb1)]

    u_ss = u_full[:n_stay1, :n_stay2]
    cvar_ss = cv_full[:n_stay1, :n_stay2]

    for b1_i, (r1a, r1b) in enumerate(benches1):
        a0, a1 = r1_global_slice[r1a]
        b0, b1 = r1_global_slice[r1b]
        t1_labels = (
            list(stay1_labels)
            + list(sw1_labels_by_mon.get(r1a, ()))
            + list(sw1_labels_by_mon.get(r1b, ()))
        )
        u_r1a_s2 = u_full[a0:a1, :n_stay2]
        cv_r1a_s2 = cv_full[a0:a1, :n_stay2]
        u_r1b_s2 = u_full[b0:b1, :n_stay2]
        cv_r1b_s2 = cv_full[b0:b1, :n_stay2]
        squad1 = (lead1[0], lead1[1], r1a, r1b)

        for b2_i, (r2a, r2b) in enumerate(benches2):
            c0, c1 = r2_global_slice[r2a]
            d0, d1 = r2_global_slice[r2b]
            t2_labels = (
                list(stay2_labels)
                + list(sw2_labels_by_mon.get(r2a, ()))
                + list(sw2_labels_by_mon.get(r2b, ()))
            )
            u_s1_r2a = u_full[:n_stay1, c0:c1]
            cv_s1_r2a = cv_full[:n_stay1, c0:c1]
            u_s1_r2b = u_full[:n_stay1, d0:d1]
            cv_s1_r2b = cv_full[:n_stay1, d0:d1]

            u_aa, cv_aa = u_full[a0:a1, c0:c1], cv_full[a0:a1, c0:c1]
            u_ab, cv_ab = u_full[a0:a1, d0:d1], cv_full[a0:a1, d0:d1]
            u_ba, cv_ba = u_full[b0:b1, c0:c1], cv_full[b0:b1, c0:c1]
            u_bb, cv_bb = u_full[b0:b1, d0:d1], cv_full[b0:b1, d0:d1]

            u_mat = np.block(
                [
                    [u_ss, u_s1_r2a, u_s1_r2b],
                    [u_r1a_s2, u_aa, u_ab],
                    [u_r1b_s2, u_ba, u_bb],
                ]
            )
            cv_mat = np.block(
                [
                    [cvar_ss, cv_s1_r2a, cv_s1_r2b],
                    [cv_r1a_s2, cv_aa, cv_ab],
                    [cv_r1b_s2, cv_ba, cv_bb],
                ]
            )

            squad2 = (lead2[0], lead2[1], r2a, r2b)
            t1_bench_adv = float(np.mean([pressure_12[b, o] for b in (r1a, r1b) for o in squad2]))
            t2_bench_adv = float(np.mean([pressure_21[b, o] for b in (r2a, r2b) for o in squad1]))
            residual = float(np.clip(t1_bench_adv - t2_bench_adv, -1.0, 1.0)) * float(
                bench_residual_weight
            )
            u_mat_adj = u_mat + residual

            nash_sub = solve_zero_sum_nash(u_mat_adj)
            p_star = nash_sub.trainer_1_strategy
            q_star = nash_sub.trainer_2_strategy
            top_r = int(np.argmax(p_star)) if len(p_star) > 0 else 0
            top_c = int(np.argmax(q_star)) if len(q_star) > 0 else 0

            sub_scores[b1_i, b2_i] = float(nash_sub.game_value)
            sub_cvar[b1_i, b2_i] = float(p_star @ cv_mat @ q_star)
            sub_t1_openings[b1_i][b2_i] = t1_labels[top_r] if top_r < len(t1_labels) else ""
            sub_t2_openings[b1_i][b2_i] = t2_labels[top_c] if top_c < len(t2_labels) else ""

            ev_t1_rows = u_mat_adj @ q_star if len(q_star) > 0 else np.zeros(len(t1_labels))
            ev_t2_cols = p_star @ u_mat_adj if len(p_star) > 0 else np.zeros(len(t2_labels))
            t1_order = sorted(
                range(min(len(t1_labels), len(p_star))),
                key=lambda idx: (round(float(p_star[idx]), 4), float(ev_t1_rows[idx])),
                reverse=True,
            )[:3]
            t2_order = sorted(
                range(min(len(t2_labels), len(q_star))),
                key=lambda idx: (round(float(q_star[idx]), 4), -float(ev_t2_cols[idx])),
                reverse=True,
            )[:3]
            sub_t1_top_plays[b1_i][b2_i] = [
                [t1_labels[i], round(float(p_star[i] * 100.0), 1), round(float(ev_t1_rows[i]), 3)]
                for i in t1_order
            ]
            sub_t2_top_plays[b1_i][b2_i] = [
                [t2_labels[j], round(float(q_star[j] * 100.0), 1), round(float(ev_t2_cols[j]), 3)]
                for j in t2_order
            ]

    cell_nash = solve_zero_sum_nash(sub_scores)
    best_b1 = int(np.argmax(cell_nash.trainer_1_strategy))
    best_b2 = int(np.argmax(cell_nash.trainer_2_strategy))

    t1_bench_labels = [
        [display_species_1[a], display_species_1[b]] for (a, b) in benches1
    ]
    t2_bench_labels = [
        [display_species_2[a], display_species_2[b]] for (a, b) in benches2
    ]

    return {
        "lead_1_idx": lead_1_idx,
        "lead_2_idx": lead_2_idx,
        "lead_1": [display_species_1[lead1[0]], display_species_1[lead1[1]]],
        "lead_2": [display_species_2[lead2[0]], display_species_2[lead2[1]]],
        "score": round(float(cell_nash.game_value), 4),
        "cvar_10": round(float(sub_cvar[best_b1, best_b2]), 4),
        "best_t1_bench_idx": best_b1,
        "best_t2_bench_idx": best_b2,
        "best_t1_bench": t1_bench_labels[best_b1],
        "best_t2_bench": t2_bench_labels[best_b2],
        "t1_opening": sub_t1_openings[best_b1][best_b2],
        "t2_opening": sub_t2_openings[best_b1][best_b2],
        "t1_bench_labels": t1_bench_labels,
        "t2_bench_labels": t2_bench_labels,
        "sub_matrix_6x6": np.round(sub_scores, 4).tolist(),
        "sub_cvar_6x6": np.round(sub_cvar, 4).tolist(),
        "sub_t1_openings": sub_t1_openings,
        "sub_t2_openings": sub_t2_openings,
        "sub_t1_top_plays": sub_t1_top_plays,
        "sub_t2_top_plays": sub_t2_top_plays,
        "turn0_events": turn0_events,
        "_raw_sub_scores": sub_scores,
    }


_PROC_LEAD_SOLVER: Optional["LeadMatchupSolver"] = None
_PROC_LEAD_POOL_CACHE: Dict[
    Tuple[str, str, bool],
    Tuple[CompiledTeamPool, CompiledTeamPool, np.ndarray, np.ndarray],
] = {}
_LEAD_MP_LOCK = threading.Lock()
_LEAD_MP_EXECUTOR: Any = None
_LEAD_MP_WORKERS: int = 0


def _init_lead_cpu_worker_process(omp_threads: int) -> None:
    """Initialize a persistent Zero-GIL CPU `LeadMatchupSolver` inside a worker subprocess."""
    global _PROC_LEAD_SOLVER, _PROC_LEAD_POOL_CACHE
    if HAS_TORCH:
        try:
            torch.set_num_threads(max(1, int(omp_threads)))
        except Exception:
            pass
    _PROC_LEAD_POOL_CACHE = {}
    _PROC_LEAD_SOLVER = LeadMatchupSolver(device="cpu")


def _eval_lead_cell_in_worker_process(
    t1_paste: str,
    t2_paste: str,
    require_explicit_spreads: bool,
    lead_1_idx: int,
    lead_2_idx: int,
    cfg: LeadMatchupConfig,
) -> Dict[str, Any]:
    """Evaluate one `(lead_1_idx, lead_2_idx)` cell inside an isolated Zero-GIL CPU worker process."""
    global _PROC_LEAD_SOLVER
    if _PROC_LEAD_SOLVER is None:
        _PROC_LEAD_SOLVER = LeadMatchupSolver(device="cpu")
    cache_key = (t1_paste, t2_paste, bool(require_explicit_spreads))
    cached = _PROC_LEAD_POOL_CACHE.get(cache_key)
    if cached is None:
        if len(_PROC_LEAD_POOL_CACHE) >= 2:
            _PROC_LEAD_POOL_CACHE.clear()
        pool_trainer_1 = _PROC_LEAD_SOLVER._precompile_team_pool(
            t1_paste, trainer_id="trainer_1", require_explicit_spreads=require_explicit_spreads
        )
        pool_trainer_2 = _PROC_LEAD_SOLVER._precompile_team_pool(
            t2_paste, trainer_id="trainer_2", require_explicit_spreads=require_explicit_spreads
        )
        pr12, pr21 = _PROC_LEAD_SOLVER._compute_pairwise_pressure(pool_trainer_1, pool_trainer_2)
        cached = (pool_trainer_1, pool_trainer_2, pr12, pr21)
        _PROC_LEAD_POOL_CACHE[cache_key] = cached
    pool_t1, pool_t2, pressure_12, pressure_21 = cached
    return _PROC_LEAD_SOLVER._evaluate_lead_pair_factored(
        pool_t1=pool_t1,
        pool_t2=pool_t2,
        lead_1_idx=lead_1_idx,
        lead_2_idx=lead_2_idx,
        pressure_12=pressure_12,
        pressure_21=pressure_21,
        config=cfg,
        cancel_event=None,
    )


def _get_lead_cpu_process_pool(num_workers: int, omp_threads: int) -> Any:
    """Return a persistent `spawn`-based `ProcessPoolExecutor` for Zero-GIL CPU lead workers."""
    global _LEAD_MP_EXECUTOR, _LEAD_MP_WORKERS
    import atexit
    import concurrent.futures as _cf
    import multiprocessing as _mp

    with _LEAD_MP_LOCK:
        if _LEAD_MP_EXECUTOR is not None and _LEAD_MP_WORKERS == num_workers:
            return _LEAD_MP_EXECUTOR
        if _LEAD_MP_EXECUTOR is not None:
            try:
                _LEAD_MP_EXECUTOR.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            _LEAD_MP_EXECUTOR = None
        try:
            ctx = _mp.get_context("spawn")
            _LEAD_MP_EXECUTOR = _cf.ProcessPoolExecutor(
                max_workers=max(1, int(num_workers)),
                mp_context=ctx,
                initializer=_init_lead_cpu_worker_process,
                initargs=(max(1, int(omp_threads)),),
            )
            _LEAD_MP_WORKERS = int(num_workers)
            atexit.register(lambda ex=_LEAD_MP_EXECUTOR: ex.shutdown(wait=False, cancel_futures=True))
            return _LEAD_MP_EXECUTOR
        except Exception:
            return None


class LeadMatchupSolver:
    """Factored `90 × 90` (`8,100`-Mode) Regulation M-C Turn-1 Lead & Bring Nash Solver.

    Pre-compiles both 6-Pokémon teams once and factors Turn-1 stay-in actions across all
    6 Back-2 benches per lead pair so every `15 × 15 × (6 × 6)` team-preview matchup is
    solved accurately within `< 600 MB` VRAM.
    """

    def __init__(
        self,
        repo: Optional[TournamentUsageRepository] = None,
        device: Optional[str] = None,
    ) -> None:
        self.repo: TournamentUsageRepository = repo or get_tournament_repository()
        self.turn_compiler: TurnStateCompiler = TurnStateCompiler(repo=self.repo)
        if device is None:
            self.device_str: str = "cuda" if (HAS_TORCH and torch.cuda.is_available()) else "cpu"
        else:
            self.device_str = device
        self.backend: str = "torch" if HAS_TORCH else "numpy"
        self.sm: VgcTensorStateMachine = VgcTensorStateMachine(
            backend=self.backend,
            device=self.device_str if HAS_TORCH else "cpu",
            risk_aversion_lambda=0.25,
        )
        if HAS_TORCH and hasattr(self.sm, "device"):
            self.device_str = str(self.sm.device)
        self.tensor_compiler: ShowdownTensorCompiler = ShowdownTensorCompiler(
            registry=self.repo.registry,
            backend=self.backend,
            device=self.device_str,
        )
        self._cpu_pool_lock = threading.Lock()
        self._cpu_worker_solvers: Dict[int, "LeadMatchupSolver"] = {}

    def _get_cpu_worker_solver(self, worker_idx: int) -> "LeadMatchupSolver":
        """Return a cached thread-local CPU `LeadMatchupSolver` for `worker_idx` (zero cold-init overhead)."""
        if self.device_str == "cpu" and worker_idx == 0:
            return self
        with self._cpu_pool_lock:
            ws = self._cpu_worker_solvers.get(worker_idx)
            if ws is None:
                ws = LeadMatchupSolver(repo=self.repo, device="cpu")
                self._cpu_worker_solvers[worker_idx] = ws
            return ws

    def _precompile_team_pool(
        self,
        paste_text: str,
        trainer_id: str,
        require_explicit_spreads: bool = True,
    ) -> CompiledTeamPool:
        """Parse, validate, and compile all Pokémon in a Showdown paste once upfront."""
        parsed_dict = parse_showdown_paste(paste_text)
        unique_parsed = _deduplicate_parsed_team(parsed_dict)
        _validate_reg_mc_team_spreads(
            unique_parsed,
            trainer_id=trainer_id,
            require_explicit_spreads=require_explicit_spreads,
        )

        compiled_mons: List[CompiledPokemonState] = []
        display_species: List[str] = []
        roster_list: List[np.ndarray] = []
        move_list: List[np.ndarray] = []
        move_names_list: List[Tuple[str, ...]] = []

        for raw_pkm in unique_parsed:
            # Strictly enforce Turn-0 Pre-Mega fresh entry state (100% HP, is_mega=False, active_turns=1)
            turn0_pkm = ParsedPokemon(
                species=raw_pkm.species,
                base_species=raw_pkm.base_species,
                nickname=raw_pkm.nickname,
                item=raw_pkm.item,
                ability=raw_pkm.ability,
                nature=raw_pkm.nature,
                spread=raw_pkm.spread,
                moves=list(raw_pkm.moves),
                current_hp_pct=100.0,
                fainted=False,
                is_mega=False,
                mega_stone=raw_pkm.mega_stone,
                revealed_in_battle=True,
                active_turns=1,
            )
            cm = self.turn_compiler.compile_pokemon(turn0_pkm, trainer_mega_used=False)
            p_vec, m_mat, _sp, mv_names = self.tensor_compiler.compile_pokemon_from_state(cm)

            # Anti Reg M-C Hallucination Invariant #4: ACTIVE_TURNS == 0.0 represents Turn 1 on field
            p_vec[MonIdx.ACTIVE_TURNS] = 0.0
            p_vec[MonIdx.IS_MEGA] = 0.0
            p_vec[MonIdx.PROTECT_COUNTER] = 0.0
            p_vec[MonIdx.CHOICE_LOCKED_MOVE] = -1.0
            p_vec[MonIdx.LAST_MOVE_IDX] = -1.0

            compiled_mons.append(cm)
            # Clean display label: preserve Mega target identity when stone is held, else base species
            disp_name = cm.mega_target_species if (cm.can_mega_evolve and cm.mega_target_species) else cm.base_species
            display_species.append(str(disp_name))
            roster_list.append(p_vec)
            move_list.append(m_mat)
            move_names_list.append(tuple(mv_names))

        n = len(compiled_mons)
        leads = tuple(combinations(range(n), 2))
        benches_for_lead: List[Tuple[Tuple[int, int], ...]] = []
        modes: List[BringModeSpec] = []
        mode_cursor = 0
        for l_idx, (la, lb) in enumerate(leads):
            rem = [idx for idx in range(n) if idx not in (la, lb)]
            bench_pairs = tuple(combinations(rem, 2))
            benches_for_lead.append(bench_pairs)
            for b_idx, (ba, bb) in enumerate(bench_pairs):
                modes.append(
                    BringModeSpec(
                        mode_idx=mode_cursor,
                        lead_idx=l_idx,
                        bench_idx=b_idx,
                        lead_indices=(la, lb),
                        bench_indices=(ba, bb),
                        lead_species=(display_species[la], display_species[lb]),
                        bench_species=(display_species[ba], display_species[bb]),
                    )
                )
                mode_cursor += 1

        return CompiledTeamPool(
            trainer_id=trainer_id,
            mons=tuple(compiled_mons),
            display_species=tuple(display_species),
            roster_rows=np.stack(roster_list, axis=0).astype(np.float32),
            move_rows=np.stack(move_list, axis=0).astype(np.float32),
            move_names=tuple(move_names_list),
            leads=leads,
            benches_for_lead=tuple(benches_for_lead),
            modes=tuple(modes),
        )

    def _compute_pairwise_pressure(
        self,
        pool_t1: CompiledTeamPool,
        pool_t2: CompiledTeamPool,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Pre-compute `[N1, N2]` and `[N2, N1]` DuckDB-verified matchup pressure matrices."""
        n1, n2 = len(pool_t1.mons), len(pool_t2.mons)
        p_12 = np.zeros((n1, n2), dtype=np.float64)
        p_21 = np.zeros((n2, n1), dtype=np.float64)
        for i in range(n1):
            for j in range(n2):
                p_12[i, j] = _single_mon_matchup_score(pool_t1.mons[i], pool_t2.mons[j])
                p_21[j, i] = _single_mon_matchup_score(pool_t2.mons[j], pool_t1.mons[i])
        return p_12, p_21

    def _build_board_state(
        self,
        f_vec_np: np.ndarray,
        p_leads_np: np.ndarray,
        pool_t1: CompiledTeamPool,
        pool_t2: CompiledTeamPool,
        lead1: Tuple[int, int],
        bench1: Tuple[int, int],
        lead2: Tuple[int, int],
        bench2: Tuple[int, int],
    ) -> CompiledBattleState:
        """Assemble an 8-slot `CompiledBattleState` in `< 0.05 ms` by slicing pre-compiled rows."""
        p_np = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        m_np = np.zeros((ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)

        # Active leads inherit Turn-0 post-entry states (`p_leads_np[0, 1, 4, 5]`)
        p_np[SLOT_TRAINER_1_A] = p_leads_np[SLOT_TRAINER_1_A]
        p_np[SLOT_TRAINER_1_B] = p_leads_np[SLOT_TRAINER_1_B]
        p_np[SLOT_TRAINER_2_A] = p_leads_np[SLOT_TRAINER_2_A]
        p_np[SLOT_TRAINER_2_B] = p_leads_np[SLOT_TRAINER_2_B]

        # Bench slots slice directly from pre-compiled fresh rows
        p_np[SLOT_TRAINER_1_BENCH1] = pool_t1.roster_rows[bench1[0]]
        p_np[SLOT_TRAINER_1_BENCH2] = pool_t1.roster_rows[bench1[1]]
        p_np[SLOT_TRAINER_2_BENCH1] = pool_t2.roster_rows[bench2[0]]
        p_np[SLOT_TRAINER_2_BENCH2] = pool_t2.roster_rows[bench2[1]]

        m_np[SLOT_TRAINER_1_A] = pool_t1.move_rows[lead1[0]]
        m_np[SLOT_TRAINER_1_B] = pool_t1.move_rows[lead1[1]]
        m_np[SLOT_TRAINER_1_BENCH1] = pool_t1.move_rows[bench1[0]]
        m_np[SLOT_TRAINER_1_BENCH2] = pool_t1.move_rows[bench1[1]]
        m_np[SLOT_TRAINER_2_A] = pool_t2.move_rows[lead2[0]]
        m_np[SLOT_TRAINER_2_B] = pool_t2.move_rows[lead2[1]]
        m_np[SLOT_TRAINER_2_BENCH1] = pool_t2.move_rows[bench2[0]]
        m_np[SLOT_TRAINER_2_BENCH2] = pool_t2.move_rows[bench2[1]]

        slot_species = (
            pool_t1.display_species[lead1[0]],
            pool_t1.display_species[lead1[1]],
            pool_t1.display_species[bench1[0]],
            pool_t1.display_species[bench1[1]],
            pool_t2.display_species[lead2[0]],
            pool_t2.display_species[lead2[1]],
            pool_t2.display_species[bench2[0]],
            pool_t2.display_species[bench2[1]],
        )
        slot_move_names = (
            pool_t1.move_names[lead1[0]],
            pool_t1.move_names[lead1[1]],
            pool_t1.move_names[bench1[0]],
            pool_t1.move_names[bench1[1]],
            pool_t2.move_names[lead2[0]],
            pool_t2.move_names[lead2[1]],
            pool_t2.move_names[bench2[0]],
            pool_t2.move_names[bench2[1]],
        )

        if self.backend == "torch" and HAS_TORCH:
            return CompiledBattleState(
                field_tensor=torch.from_numpy(f_vec_np.copy()).to(self.device_str),
                roster_tensor=torch.from_numpy(p_np).to(self.device_str),
                moves_tensor=torch.from_numpy(m_np).to(self.device_str),
                backend="torch",
                device=self.device_str,
                slot_species=slot_species,
                slot_move_names=slot_move_names,
            )

        return CompiledBattleState(
            field_tensor=f_vec_np.copy(),
            roster_tensor=p_np,
            moves_tensor=m_np,
            backend="numpy",
            device="cpu",
            slot_species=slot_species,
            slot_move_names=slot_move_names,
        )

    def _extract_stay_and_switch_actions(
        self,
        board: CompiledBattleState,
        trainer_id: str,
        cap_stay: int,
        cap_switch_per_mon: int,
        bench_pair: Tuple[int, int],
        extract_stay: bool,
        needed_bench_mons: Sequence[int],
    ) -> Tuple[np.ndarray, List[str], Dict[int, Tuple[np.ndarray, List[str]]]]:
        """Extract top stay-in choices and symmetric single-switch choices for specific bench mons."""
        mask_res = self.sm.logic_engine.prune_side_26x26_tensor_actions(
            board, trainer_id=trainer_id, min_prior_threshold=0.0
        )
        coords = mask_res.pruned_choices
        priors = mask_res.prior_matrix_26x26
        if HAS_TORCH and isinstance(coords, torch.Tensor):
            c_np = coords.detach().cpu().numpy().astype(np.int64)
            p_np = priors.detach().cpu().numpy().astype(np.float32)
        else:
            c_np = np.asarray(coords, dtype=np.int64)
            p_np = np.asarray(priors, dtype=np.float32)

        stay_choices = np.zeros((0, 2), dtype=np.int64)
        stay_labels: List[str] = []
        if extract_stay:
            stay_mask = (c_np[:, 0] < CHOICE_SWITCH_BENCH1) & (c_np[:, 1] < CHOICE_SWITCH_BENCH1)
            stay_all = c_np[stay_mask]
            if len(stay_all) == 0:
                stay_all = c_np[:1] if len(c_np) > 0 else np.array([[0, 0]], dtype=np.int64)
            scores = np.array([float(p_np[int(r[0]), int(r[1])]) for r in stay_all], dtype=np.float32)
            order = np.argsort(-scores)[: max(1, cap_stay)]
            stay_choices = stay_all[order]
            stay_labels = [
                decode_joint_action(board, trainer_id, (int(r[0]), int(r[1])))
                for r in stay_choices
            ]

        sw_by_mon: Dict[int, Tuple[np.ndarray, List[str]]] = {}
        for slot_pos, mon_idx in enumerate(bench_pair):
            if mon_idx not in needed_bench_mons or mon_idx in sw_by_mon:
                continue
            sw_code = CHOICE_SWITCH_BENCH1 if slot_pos == 0 else CHOICE_SWITCH_BENCH2
            # Symmetric single-switch ONLY (exactly one lead switches to mon_idx, partner stays in)
            a_sw = c_np[(c_np[:, 0] == sw_code) & (c_np[:, 1] < CHOICE_SWITCH_BENCH1)]
            b_sw = c_np[(c_np[:, 1] == sw_code) & (c_np[:, 0] < CHOICE_SWITCH_BENCH1)]

            def _top_k(arr: np.ndarray, k: int) -> np.ndarray:
                if len(arr) <= k:
                    return arr
                sc = np.array([float(p_np[int(r[0]), int(r[1])]) for r in arr], dtype=np.float32)
                return arr[np.argsort(-sc)[:k]]

            half_a = max(1, (cap_switch_per_mon + 1) // 2)
            half_b = max(1, cap_switch_per_mon - half_a)
            picked_a = _top_k(a_sw, half_a)
            picked_b = _top_k(b_sw, half_b)
            # Backfill if one side had fewer actions
            if len(picked_a) + len(picked_b) < cap_switch_per_mon:
                rem_k = cap_switch_per_mon - (len(picked_a) + len(picked_b))
                if len(a_sw) > len(picked_a):
                    picked_a = _top_k(a_sw, len(picked_a) + rem_k)
                elif len(b_sw) > len(picked_b):
                    picked_b = _top_k(b_sw, len(picked_b) + rem_k)

            if len(picked_a) > 0 and len(picked_b) > 0:
                sw_arr = np.concatenate([picked_a, picked_b], axis=0)[:cap_switch_per_mon]
            elif len(picked_a) > 0:
                sw_arr = picked_a[:cap_switch_per_mon]
            elif len(picked_b) > 0:
                sw_arr = picked_b[:cap_switch_per_mon]
            else:
                sw_arr = np.zeros((0, 2), dtype=np.int64)

            sw_labels = [
                decode_joint_action(board, trainer_id, (int(r[0]), int(r[1])))
                for r in sw_arr
            ]
            sw_by_mon[mon_idx] = (sw_arr, sw_labels)

        return stay_choices, stay_labels, sw_by_mon

    def _run_block(
        self,
        board: CompiledBattleState,
        c1_np: np.ndarray,
        c2_np: np.ndarray,
        config: LeadMatchupConfig,
        seed_offset: int,
        cancel_event: Optional[threading.Event],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Run a single factored Turn-1 tensor block returning `(U_risk, CVaR_10)` as float64 arrays."""
        if len(c1_np) == 0 or len(c2_np) == 0:
            return (
                np.zeros((len(c1_np), len(c2_np)), dtype=np.float64),
                np.zeros((len(c1_np), len(c2_np)), dtype=np.float64),
            )
        if self.backend == "torch" and HAS_TORCH:
            c1_t: Any = torch.tensor(c1_np, dtype=torch.long, device=self.device_str)
            c2_t: Any = torch.tensor(c2_np, dtype=torch.long, device=self.device_str)
        else:
            c1_t = c1_np
            c2_t = c2_np

        step_res = self.sm.step(
            F=board.field_tensor,
            P=board.roster_tensor,
            M_moves=board.moves_tensor,
            trainer_1_choices=c1_t,
            trainer_2_choices=c2_t,
            num_mc_samples=config.num_rng_samples,
            rng_seed=config.rng_seed + seed_offset,
            risk_aversion_lambda=config.risk_aversion_lambda,
            resolve_lead_entry_abilities=False,  # Turn-0 entry already resolved once before pruning!
            tile_size=min(24, max(8, int(config.tile_size))),
            cancel_event=cancel_event,
        )
        u_raw = step_res.stats.risk_adjusted_utility
        cvar_raw = step_res.stats.cvar_10_utility
        if HAS_TORCH and isinstance(u_raw, torch.Tensor):
            return (
                u_raw.detach().cpu().numpy().astype(np.float64),
                cvar_raw.detach().cpu().numpy().astype(np.float64),
            )
        return (
            np.asarray(u_raw, dtype=np.float64),
            np.asarray(cvar_raw, dtype=np.float64),
        )

    def _prepare_lead_pair_fused_tensors(
        self,
        pool_t1: CompiledTeamPool,
        pool_t2: CompiledTeamPool,
        lead_1_idx: int,
        lead_2_idx: int,
        config: LeadMatchupConfig,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
        """Compile Turn-0 lead entry & fuse all 4 bench-chunk boards into one `[B1, B2]` tensor block."""
        prep_solver = self if self.device_str == "cpu" else self._get_cpu_worker_solver(0)
        lead1 = pool_t1.leads[lead_1_idx]
        lead2 = pool_t2.leads[lead_2_idx]
        rem1 = [i for i in range(len(pool_t1.mons)) if i not in lead1]
        rem2 = [i for i in range(len(pool_t2.mons)) if i not in lead2]

        chunks1 = _partition_bench_chunks(rem1)
        chunks2 = _partition_bench_chunks(rem2)

        # 1. Clean Turn-0 Field & Lead Entry Pass (ONCE per lead pair, BEFORE action pruning!)
        f_clean = np.zeros((FIELD_DIM,), dtype=np.float32)
        f_clean[FieldIdx.WEATHER_START + WEATHER_TO_IDX["clear"]] = 1.0
        f_clean[FieldIdx.TERRAIN_START + TERRAIN_TO_IDX["none"]] = 1.0

        p_base = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        p_base[SLOT_TRAINER_1_A] = pool_t1.roster_rows[lead1[0]]
        p_base[SLOT_TRAINER_1_B] = pool_t1.roster_rows[lead1[1]]
        p_base[SLOT_TRAINER_1_BENCH1] = pool_t1.roster_rows[chunks1[0][0]]
        p_base[SLOT_TRAINER_1_BENCH2] = pool_t1.roster_rows[chunks1[0][1]]
        p_base[SLOT_TRAINER_2_A] = pool_t2.roster_rows[lead2[0]]
        p_base[SLOT_TRAINER_2_B] = pool_t2.roster_rows[lead2[1]]
        p_base[SLOT_TRAINER_2_BENCH1] = pool_t2.roster_rows[chunks2[0][0]]
        p_base[SLOT_TRAINER_2_BENCH2] = pool_t2.roster_rows[chunks2[0][1]]

        f_t0, p_t0 = resolve_turn_zero_lead_entry(f_clean, p_base, tables=prep_solver.sm.tables)
        f_t0_np = (
            f_t0.detach().cpu().numpy()
            if (HAS_TORCH and isinstance(f_t0, torch.Tensor))
            else np.asarray(f_t0)
        )
        p_t0_np = (
            p_t0.detach().cpu().numpy()
            if (HAS_TORCH and isinstance(p_t0, torch.Tensor))
            else np.asarray(p_t0)
        )

        lead_slot_species = (
            pool_t1.display_species[lead1[0]],
            pool_t1.display_species[lead1[1]],
            pool_t1.display_species[chunks1[0][0]],
            pool_t1.display_species[chunks1[0][1]],
            pool_t2.display_species[lead2[0]],
            pool_t2.display_species[lead2[1]],
            pool_t2.display_species[chunks2[0][0]],
            pool_t2.display_species[chunks2[0][1]],
        )
        turn0_events = _describe_turn0_events(f_t0_np, p_base, p_t0_np, lead_slot_species)

        # 2. Build chunk boards on CPU & prune Stay-In (once) + Symmetric Single-Switches per bench mon
        boards: Dict[Tuple[int, int], CompiledBattleState] = {}
        for c1_i, ch1 in enumerate(chunks1):
            for c2_i, ch2 in enumerate(chunks2):
                boards[(c1_i, c2_i)] = prep_solver._build_board_state(
                    f_t0_np, p_t0_np, pool_t1, pool_t2, lead1, ch1, lead2, ch2
                )

        stay1_choices = np.zeros((0, 2), dtype=np.int64)
        stay1_labels: List[str] = []
        sw1_by_mon: Dict[int, Tuple[np.ndarray, List[str]]] = {}
        seen_r1: set[int] = set()
        for c1_i, ch1 in enumerate(chunks1):
            needed = [m for m in ch1 if m not in seen_r1]
            s1_c, s1_l, sw_map = prep_solver._extract_stay_and_switch_actions(
                boards[(c1_i, 0)],
                trainer_id="trainer_1",
                cap_stay=config.cap_stay,
                cap_switch_per_mon=config.cap_switch_per_mon,
                bench_pair=ch1,
                extract_stay=(c1_i == 0),
                needed_bench_mons=needed,
            )
            if c1_i == 0:
                stay1_choices, stay1_labels = s1_c, s1_l
            for m_id, val in sw_map.items():
                sw1_by_mon[m_id] = val
                seen_r1.add(m_id)

        stay2_choices = np.zeros((0, 2), dtype=np.int64)
        stay2_labels: List[str] = []
        sw2_by_mon: Dict[int, Tuple[np.ndarray, List[str]]] = {}
        seen_r2: set[int] = set()
        for c2_i, ch2 in enumerate(chunks2):
            needed = [m for m in ch2 if m not in seen_r2]
            s2_c, s2_l, sw_map = prep_solver._extract_stay_and_switch_actions(
                boards[(0, c2_i)],
                trainer_id="trainer_2",
                cap_stay=config.cap_stay,
                cap_switch_per_mon=config.cap_switch_per_mon,
                bench_pair=ch2,
                extract_stay=(c2_i == 0),
                needed_bench_mons=needed,
            )
            if c2_i == 0:
                stay2_choices, stay2_labels = s2_c, s2_l
            for m_id, val in sw_map.items():
                sw2_by_mon[m_id] = val
                seen_r2.add(m_id)

        # 3. Fuse all trainer_1 rows [Stay1, Sw1_chunk0, Sw1_chunk1, ...] and trainer_2 cols into one [B1, B2] grid
        t1_parts = [stay1_choices]
        t1_chunk_owners = [0] * len(stay1_choices)
        r1_global_slice: Dict[int, Tuple[int, int]] = {}
        cur_r = len(stay1_choices)
        assigned_r1: set[int] = set()
        for c1_i, ch1 in enumerate(chunks1):
            for m_id in ch1:
                if m_id in assigned_r1:
                    continue
                arr = sw1_by_mon.get(m_id, (np.zeros((0, 2), dtype=np.int64), []))[0]
                r1_global_slice[m_id] = (cur_r, cur_r + len(arr))
                cur_r += len(arr)
                if len(arr) > 0:
                    t1_parts.append(arr)
                    t1_chunk_owners.extend([c1_i] * len(arr))
                assigned_r1.add(m_id)
        all_c1 = np.concatenate(t1_parts, axis=0) if t1_parts else np.zeros((1, 2), dtype=np.int64)

        t2_parts = [stay2_choices]
        t2_chunk_owners = [0] * len(stay2_choices)
        r2_global_slice: Dict[int, Tuple[int, int]] = {}
        cur_c = len(stay2_choices)
        assigned_r2: set[int] = set()
        for c2_i, ch2 in enumerate(chunks2):
            for m_id in ch2:
                if m_id in assigned_r2:
                    continue
                arr2 = sw2_by_mon.get(m_id, (np.zeros((0, 2), dtype=np.int64), []))[0]
                r2_global_slice[m_id] = (cur_c, cur_c + len(arr2))
                cur_c += len(arr2)
                if len(arr2) > 0:
                    t2_parts.append(arr2)
                    t2_chunk_owners.extend([c2_i] * len(arr2))
                assigned_r2.add(m_id)
        all_c2 = np.concatenate(t2_parts, axis=0) if t2_parts else np.zeros((1, 2), dtype=np.int64)

        B1, B2 = len(all_c1), len(all_c2)
        p_t1_by_c = []
        m_t1_by_c = []
        for ch1 in chunks1:
            p_t1_by_c.append(
                np.stack(
                    [
                        p_t0_np[SLOT_TRAINER_1_A],
                        p_t0_np[SLOT_TRAINER_1_B],
                        pool_t1.roster_rows[ch1[0]],
                        pool_t1.roster_rows[ch1[1]],
                    ],
                    axis=0,
                )
            )
            m_t1_by_c.append(
                np.stack(
                    [
                        pool_t1.move_rows[lead1[0]],
                        pool_t1.move_rows[lead1[1]],
                        pool_t1.move_rows[ch1[0]],
                        pool_t1.move_rows[ch1[1]],
                    ],
                    axis=0,
                )
            )

        p_t2_by_c = []
        m_t2_by_c = []
        for ch2 in chunks2:
            p_t2_by_c.append(
                np.stack(
                    [
                        p_t0_np[SLOT_TRAINER_2_A],
                        p_t0_np[SLOT_TRAINER_2_B],
                        pool_t2.roster_rows[ch2[0]],
                        pool_t2.roster_rows[ch2[1]],
                    ],
                    axis=0,
                )
            )
            m_t2_by_c.append(
                np.stack(
                    [
                        pool_t2.move_rows[lead2[0]],
                        pool_t2.move_rows[lead2[1]],
                        pool_t2.move_rows[ch2[0]],
                        pool_t2.move_rows[ch2[1]],
                    ],
                    axis=0,
                )
            )

        own1 = np.asarray(t1_chunk_owners, dtype=np.int64)
        own2 = np.asarray(t2_chunk_owners, dtype=np.int64)
        P_cell = np.empty((B1, B2, ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        M_cell = np.empty((B1, B2, ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)
        P_cell[:, :, :4, :] = np.asarray(p_t1_by_c)[own1][:, None, :, :]
        P_cell[:, :, 4:, :] = np.asarray(p_t2_by_c)[own2][None, :, :, :]
        M_cell[:, :, :4, :, :] = np.asarray(m_t1_by_c)[own1][:, None, :, :, :]
        M_cell[:, :, 4:, :, :] = np.asarray(m_t2_by_c)[own2][None, :, :, :, :]
        F_cell = np.broadcast_to(f_t0_np[None, None, :], (B1, B2, FIELD_DIM)).copy()
        C1_cell = np.broadcast_to(all_c1[:, None, :], (B1, B2, 2)).copy()
        C2_cell = np.broadcast_to(all_c2[None, :, :], (B1, B2, 2)).copy()

        cell_meta: Dict[str, Any] = {
            "lead_1_idx": lead_1_idx,
            "lead_2_idx": lead_2_idx,
            "n_stay1": len(stay1_choices),
            "n_stay2": len(stay2_choices),
            "r1_global_slice": r1_global_slice,
            "r2_global_slice": r2_global_slice,
            "stay1_labels": stay1_labels,
            "stay2_labels": stay2_labels,
            "sw1_labels_by_mon": {m_id: val[1] for m_id, val in sw1_by_mon.items()},
            "sw2_labels_by_mon": {m_id: val[1] for m_id, val in sw2_by_mon.items()},
            "turn0_events": turn0_events,
        }
        return F_cell, P_cell, M_cell, C1_cell, C2_cell, cell_meta

    def _evaluate_lead_pair_factored(
        self,
        pool_t1: CompiledTeamPool,
        pool_t2: CompiledTeamPool,
        lead_1_idx: int,
        lead_2_idx: int,
        pressure_12: np.ndarray,
        pressure_21: np.ndarray,
        config: LeadMatchupConfig,
        cancel_event: Optional[threading.Event],
    ) -> Dict[str, Any]:
        """Evaluate all `C(n1-2, 2) × C(n2-2, 2)` (up to `6 × 6 = 36`) bench matchups for one lead pair in 1 fused pass."""
        F_cell, P_cell, M_cell, C1_cell, C2_cell, meta = self._prepare_lead_pair_fused_tensors(
            pool_t1=pool_t1,
            pool_t2=pool_t2,
            lead_1_idx=lead_1_idx,
            lead_2_idx=lead_2_idx,
            config=config,
        )
        pair_seed = (lead_1_idx * 31 + lead_2_idx) * 101
        ctx = torch.inference_mode() if (self.backend == "torch" and HAS_TORCH) else _NullContext()
        with ctx:
            if self.backend == "torch" and HAS_TORCH:
                f_in: Any = torch.from_numpy(F_cell).to(self.device_str)
                p_in: Any = torch.from_numpy(P_cell).to(self.device_str)
                m_in: Any = torch.from_numpy(M_cell).to(self.device_str)
                c1_in: Any = torch.from_numpy(C1_cell).to(self.device_str)
                c2_in: Any = torch.from_numpy(C2_cell).to(self.device_str)
            else:
                f_in, p_in, m_in, c1_in, c2_in = F_cell, P_cell, M_cell, C1_cell, C2_cell

            step_res = self.sm.step(
                F=f_in,
                P=p_in,
                M_moves=m_in,
                trainer_1_choices=c1_in,
                trainer_2_choices=c2_in,
                num_mc_samples=config.num_rng_samples,
                rng_seed=config.rng_seed + pair_seed + 1,
                risk_aversion_lambda=config.risk_aversion_lambda,
                resolve_lead_entry_abilities=False,
                max_sim_chunk_size=max(64, int(config.num_rng_samples)),
                cancel_event=cancel_event,
            )
            u_raw = step_res.stats.risk_adjusted_utility
            cvar_raw = step_res.stats.cvar_10_utility
            if HAS_TORCH and isinstance(u_raw, torch.Tensor):
                u_full = u_raw.detach().cpu().numpy().astype(np.float64)
                cv_full = cvar_raw.detach().cpu().numpy().astype(np.float64)
            else:
                u_full = np.asarray(u_raw, dtype=np.float64)
                cv_full = np.asarray(cvar_raw, dtype=np.float64)
            del step_res

        return _assemble_lead_pair_cell_from_payoffs(
            u_full=u_full,
            cv_full=cv_full,
            lead_1_idx=lead_1_idx,
            lead_2_idx=lead_2_idx,
            n_stay1=meta["n_stay1"],
            n_stay2=meta["n_stay2"],
            r1_global_slice=meta["r1_global_slice"],
            r2_global_slice=meta["r2_global_slice"],
            stay1_labels=meta["stay1_labels"],
            stay2_labels=meta["stay2_labels"],
            sw1_labels_by_mon=meta["sw1_labels_by_mon"],
            sw2_labels_by_mon=meta["sw2_labels_by_mon"],
            turn0_events=meta["turn0_events"],
            lead1=pool_t1.leads[lead_1_idx],
            lead2=pool_t2.leads[lead_2_idx],
            benches1=pool_t1.benches_for_lead[lead_1_idx],
            benches2=pool_t2.benches_for_lead[lead_2_idx],
            display_species_1=pool_t1.display_species,
            display_species_2=pool_t2.display_species,
            pressure_12=pressure_12,
            pressure_21=pressure_21,
            bench_residual_weight=config.bench_residual_weight,
        )

    def solve_90x90_matchup(
        self,
        trainer_1_paste: str,
        trainer_2_paste: str,
        config: Optional[LeadMatchupConfig] = None,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> LeadMatchupResult:
        """Execute the full Factored `90 × 90` (`8,100`-Mode) Team-Preview Nash Equilibrium sweep.

        Args:
            trainer_1_paste: Full Regulation M-C 66-SP Showdown paste for `trainer_1`.
            trainer_2_paste: Full Regulation M-C 66-SP Showdown paste for `trainer_2`
                (either directly provided or materialized from inferred clamped 66-SP sliders).
            config: Optional `LeadMatchupConfig` depth/hardware settings.
            progress_cb: Optional callback invoked after every `(lead_1, lead_2)` cell completes,
                emitting live heatmap tile payloads for Studio SSE streaming.
            cancel_event: Optional `threading.Event` checked between lead pairs and GPU tiles.

        Returns:
            `LeadMatchupResult` containing global Nash brings, counter-leads, and `15 × 15 × (6 × 6)` data.
        """
        t_start = time.perf_counter()
        cfg = config or LeadMatchupConfig.from_preset("balanced", device=self.device_str)

        pool_t1 = self._precompile_team_pool(
            trainer_1_paste,
            trainer_id="trainer_1",
            require_explicit_spreads=cfg.require_explicit_spreads,
        )
        pool_t2 = self._precompile_team_pool(
            trainer_2_paste,
            trainer_id="trainer_2",
            require_explicit_spreads=cfg.require_explicit_spreads,
        )

        pressure_12, pressure_21 = self._compute_pairwise_pressure(pool_t1, pool_t2)

        num_l1 = len(pool_t1.leads)
        num_l2 = len(pool_t2.leads)
        num_b1 = len(pool_t1.benches_for_lead[0])
        num_b2 = len(pool_t2.benches_for_lead[0])
        num_m1 = len(pool_t1.modes)
        num_m2 = len(pool_t2.modes)
        total_lead_pairs = num_l1 * num_l2

        payoff_matrix = np.zeros((num_m1, num_m2), dtype=np.float64)
        heatmap_cells: List[List[Dict[str, Any]]] = [
            [{} for _ in range(num_l2)] for _ in range(num_l1)
        ]

        completed = 0
        worker_cell_counts: Dict[str, int] = {}
        has_cuda = bool(
            HAS_TORCH and str(self.device_str).startswith("cuda") and torch.cuda.is_available()
        )
        gpu_hw_name = (
            torch.cuda.get_device_name(self.device_str) if has_cuda else "CPU (PyTorch)"
        )
        cpu_hw_name = "CPU (PyTorch)"

        from collections import deque as _deque
        import concurrent.futures as _cf
        import os as _os
        from engine.solver.hybrid_scheduler import (
            resolve_gpu_superbatch_bounds,
            resolve_worker_topology,
        )

        cpu_cores = max(1, int(_os.cpu_count() or 4))
        topo = resolve_worker_topology(
            mode=getattr(cfg, "compute_mode", "auto"),
            has_cuda=has_cuda,
            cpu_count=cpu_cores,
            total_turns=total_lead_pairs,
        )
        eff_mode = str(topo["mode"])
        use_gpu = bool(topo["use_gpu"])
        num_gpu_workers = int(topo.get("gpu_workers", 1 if use_gpu else 0)) if use_gpu else 0
        num_cpu_workers = int(topo["cpu_workers"])
        threads_per_cpu = int(topo.get("threads_per_cpu_worker") or 2)
        sb_bounds = (
            resolve_gpu_superbatch_bounds(
                num_mc_samples=cfg.num_rng_samples,
                device=getattr(self.sm, "device", None),
            )
            if use_gpu
            else {"gpu_superbatch_cells": 1, "gpu_thread_budget": 65536}
        )
        m_batch = max(1, int(sb_bounds["gpu_superbatch_cells"]))

        gpu_stream_tag = f"{gpu_hw_name} ({num_gpu_workers}S)" if num_gpu_workers > 1 else gpu_hw_name
        hw_name = (
            f"{gpu_stream_tag} + CPU ({num_cpu_workers}W)"
            if (use_gpu and num_cpu_workers > 0)
            else (gpu_stream_tag if use_gpu else f"{cpu_hw_name} ({num_cpu_workers}W)")
        )

        # Dual-End Hybrid Fused GPU Super-Batch Producer + Zero-GIL Multi-CPU LP & Work-Stealing Pool:
        # - GPU Super-Batch Producer pops `M_batch` lead pairs at a time from the LEFT: (0,0) -> (14,14),
        #   simulates them in one fused CUDA launch, and offloads the 37 HiGHS Nash LPs per cell asynchronously to CPU workers.
        # - In Hybrid mode, each CPU worker (`CPU-W1..WN`) steals 1 initial right-end cell (14,14) -> ... at t=0
        #   while the GPU runs its first super-batch, then dedicates 100% of CPU cores to solving the GPU's offloaded HiGHS LPs.
        if use_gpu or num_cpu_workers >= 1:
            use_mp_cpu = bool(
                num_cpu_workers >= 1
                and total_lead_pairs >= 16
                and (int(cfg.num_rng_samples) >= 16 or _os.environ.get("PORYGON_LEAD_MP_POOL") == "1")
            )
            mp_pool = (
                _get_lead_cpu_process_pool(num_cpu_workers, threads_per_cpu)
                if use_mp_cpu
                else None
            )
            if mp_pool is None:
                for wi in range(max(1, num_cpu_workers)):
                    self._get_cpu_worker_solver(wi)

            prev_threads = int(torch.get_num_threads()) if HAS_TORCH else None
            if HAS_TORCH and num_cpu_workers >= 1 and mp_pool is None:
                try:
                    torch.set_num_threads(threads_per_cpu)
                except Exception:
                    pass

            pair_q = _deque((l1_i, l2_i) for l1_i in range(num_l1) for l2_i in range(num_l2))
            claimed_pairs: set[Tuple[int, int]] = set()
            q_lock = threading.Lock()
            out_lock = threading.Lock()
            worker_errors: List[Exception] = []

            # Pre-claim the initial lead pairs for GPU lanes in deterministic order
            # so Lane 0 ("GPU") strictly evaluates (0, 0) and Lane 1 ("GPU-S2") evaluates (0, 1).
            initial_gpu_pairs: List[Tuple[int, int]] = []
            initial_cpu_pairs: Dict[int, Optional[Tuple[int, int]]] = {}
            if use_gpu:
                for _gi in range(max(1, num_gpu_workers)):
                    while pair_q:
                        cand = pair_q.popleft()
                        if cand not in claimed_pairs:
                            claimed_pairs.add(cand)
                            initial_gpu_pairs.append(cand)
                            break
                # Pre-claim 1 right-end cell per CPU worker at t=0 so CPU workers never create a late tail stall
                for wi in range(num_cpu_workers):
                    if len(pair_q) <= max(4, m_batch * 2):
                        break
                    cand_r = pair_q.pop()
                    if cand_r not in claimed_pairs:
                        claimed_pairs.add(cand_r)
                        initial_cpu_pairs[wi] = cand_r

            def _record_completed_cell(
                l1_i: int,
                l2_i: int,
                cell: Dict[str, Any],
                w_label: str,
                w_hw: str,
            ) -> None:
                nonlocal completed
                raw_sub = cell.pop("_raw_sub_scores")
                cell["compute_worker"] = w_label
                cell["hardware_device"] = w_hw
                r0 = l1_i * num_b1
                c0 = l2_i * num_b2
                with out_lock:
                    payoff_matrix[r0 : r0 + num_b1, c0 : c0 + num_b2] = raw_sub
                    heatmap_cells[l1_i][l2_i] = cell
                    worker_cell_counts[w_label] = worker_cell_counts.get(w_label, 0) + 1
                    completed += 1
                    cur_completed = completed
                    counts_snap = dict(worker_cell_counts)
                if progress_cb is not None:
                    elapsed_now = time.perf_counter() - t_start
                    rate = elapsed_now / max(1, cur_completed)
                    eta_s = max(0.0, rate * (total_lead_pairs - cur_completed))
                    progress_cb(
                        {
                            "lead_1_idx": l1_i,
                            "lead_2_idx": l2_i,
                            "completed": cur_completed,
                            "total": total_lead_pairs,
                            "compute_worker": w_label,
                            "hardware_device": w_hw,
                            "worker_cell_counts": counts_snap,
                            "score": cell["score"],
                            "cvar_10": cell["cvar_10"],
                            "best_t1_bench": cell["best_t1_bench"],
                            "best_t2_bench": cell["best_t2_bench"],
                            "t1_opening": cell["t1_opening"],
                            "elapsed_s": round(elapsed_now, 1),
                            "eta_s": round(eta_s, 1),
                        }
                    )

            def _gpu_superbatch_producer() -> None:
                own_lp_pool = mp_pool is None
                lp_pool: Any = (
                    _cf.ThreadPoolExecutor(max_workers=max(2, num_cpu_workers or 2))
                    if own_lp_pool
                    else mp_pool
                )
                pending_lp_futs: Any = _deque()
                pre_q: Any = _deque(initial_gpu_pairs)
                gpu_cell_counter = 0
                cur_m_batch = m_batch

                def _drain_lps(block_all: bool = False) -> None:
                    while pending_lp_futs:
                        if not block_all and not pending_lp_futs[0][0].done():
                            break
                        fut_item, f_l1, f_l2, f_lbl = pending_lp_futs.popleft()
                        cell_out = fut_item.result()
                        if cancel_event is not None and cancel_event.is_set():
                            return
                        _record_completed_cell(f_l1, f_l2, cell_out, f_lbl, gpu_hw_name)

                try:
                    while True:
                        if cancel_event is not None and cancel_event.is_set():
                            return
                        batch_items: List[Tuple[int, int, str]] = []
                        with q_lock:
                            while len(batch_items) < cur_m_batch:
                                cand_pair: Optional[Tuple[int, int]] = None
                                if pre_q:
                                    cand_pair = pre_q.popleft()
                                else:
                                    while pair_q:
                                        c_p = pair_q.popleft()
                                        if c_p not in claimed_pairs:
                                            claimed_pairs.add(c_p)
                                            cand_pair = c_p
                                            break
                                if cand_pair is None:
                                    break
                                lane_idx = gpu_cell_counter % max(1, num_gpu_workers)
                                w_lbl = "GPU" if lane_idx == 0 else f"GPU-S{lane_idx + 1}"
                                gpu_cell_counter += 1
                                batch_items.append((cand_pair[0], cand_pair[1], w_lbl))

                        if not batch_items:
                            break

                        try:
                            prepped = [
                                (
                                    l1_i,
                                    l2_i,
                                    w_lbl,
                                    self._prepare_lead_pair_fused_tensors(
                                        pool_t1, pool_t2, l1_i, l2_i, cfg
                                    ),
                                )
                                for (l1_i, l2_i, w_lbl) in batch_items
                            ]

                            def _run_superbatch(
                                sub_prepped: Sequence[Tuple[int, int, str, Any]],
                                seed_shift: int,
                            ) -> List[Tuple[int, int, str, np.ndarray, np.ndarray, Dict[str, Any]]]:
                                max_b1 = max(item[3][0].shape[0] for item in sub_prepped)
                                max_b2 = max(item[3][0].shape[1] for item in sub_prepped)
                                n_b = len(sub_prepped)
                                F_sup = np.zeros((n_b * max_b1, max_b2, FIELD_DIM), dtype=np.float32)
                                P_sup = np.zeros((n_b * max_b1, max_b2, ROSTER_SLOTS, MON_DIM), dtype=np.float32)
                                M_sup = np.zeros((n_b * max_b1, max_b2, ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)
                                C1_sup = np.zeros((n_b * max_b1, max_b2, 2), dtype=np.int64)
                                C2_sup = np.zeros((n_b * max_b1, max_b2, 2), dtype=np.int64)
                                slices_info = []
                                for bi, (l1_i, l2_i, w_lbl, (fc, pc, mc, c1c, c2c, meta)) in enumerate(sub_prepped):
                                    b1, b2 = fc.shape[0], fc.shape[1]
                                    r0 = bi * max_b1
                                    F_sup[r0 : r0 + b1, :b2] = fc
                                    P_sup[r0 : r0 + b1, :b2] = pc
                                    M_sup[r0 : r0 + b1, :b2] = mc
                                    C1_sup[r0 : r0 + b1, :b2] = c1c
                                    C2_sup[r0 : r0 + b1, :b2] = c2c
                                    slices_info.append((l1_i, l2_i, w_lbl, r0, b1, b2, meta))

                                ctx = torch.inference_mode() if (self.backend == "torch" and HAS_TORCH) else _NullContext()
                                with ctx:
                                    step_res = self.sm.step(
                                        F=torch.from_numpy(F_sup).to(self.device_str),
                                        P=torch.from_numpy(P_sup).to(self.device_str),
                                        M_moves=torch.from_numpy(M_sup).to(self.device_str),
                                        trainer_1_choices=torch.from_numpy(C1_sup).to(self.device_str),
                                        trainer_2_choices=torch.from_numpy(C2_sup).to(self.device_str),
                                        num_mc_samples=cfg.num_rng_samples,
                                        rng_seed=cfg.rng_seed + seed_shift,
                                        risk_aversion_lambda=cfg.risk_aversion_lambda,
                                        resolve_lead_entry_abilities=False,
                                        max_sim_chunk_size=max(64, int(cfg.num_rng_samples)),
                                        cancel_event=cancel_event,
                                    )
                                    u_sup = step_res.stats.risk_adjusted_utility.detach().cpu().numpy().astype(np.float64)
                                    cv_sup = step_res.stats.cvar_10_utility.detach().cpu().numpy().astype(np.float64)
                                    del step_res

                                out_slices = []
                                for (l1_i, l2_i, w_lbl, r0, b1, b2, meta) in slices_info:
                                    out_slices.append(
                                        (
                                            l1_i,
                                            l2_i,
                                            w_lbl,
                                            u_sup[r0 : r0 + b1, :b2].copy(),
                                            cv_sup[r0 : r0 + b1, :b2].copy(),
                                            meta,
                                        )
                                    )
                                return out_slices

                            base_seed_shift = (batch_items[0][0] * 31 + batch_items[0][1]) * 101 + 1
                            try:
                                sim_outputs = _run_superbatch(prepped, base_seed_shift)
                            except RuntimeError as oom_exc:
                                if "out of memory" not in str(oom_exc).lower():
                                    raise
                                if HAS_TORCH and torch.cuda.is_available():
                                    torch.cuda.empty_cache()
                                cur_m_batch = 1
                                sim_outputs = []
                                for single_item in prepped:
                                    s_shift = (single_item[0] * 31 + single_item[1]) * 101 + 1
                                    sim_outputs.extend(_run_superbatch([single_item], s_shift))

                            for (l1_i, l2_i, w_lbl, u_cell, cv_cell, meta) in sim_outputs:
                                fut = lp_pool.submit(
                                    _assemble_lead_pair_cell_from_payoffs,
                                    u_cell,
                                    cv_cell,
                                    l1_i,
                                    l2_i,
                                    meta["n_stay1"],
                                    meta["n_stay2"],
                                    meta["r1_global_slice"],
                                    meta["r2_global_slice"],
                                    meta["stay1_labels"],
                                    meta["stay2_labels"],
                                    meta["sw1_labels_by_mon"],
                                    meta["sw2_labels_by_mon"],
                                    meta["turn0_events"],
                                    pool_t1.leads[l1_i],
                                    pool_t2.leads[l2_i],
                                    pool_t1.benches_for_lead[l1_i],
                                    pool_t2.benches_for_lead[l2_i],
                                    pool_t1.display_species,
                                    pool_t2.display_species,
                                    pressure_12,
                                    pressure_21,
                                    cfg.bench_residual_weight,
                                )
                                pending_lp_futs.append((fut, l1_i, l2_i, w_lbl))

                            _drain_lps(block_all=False)
                        except AnalysisCancelledError:
                            return
                        except Exception as exc:
                            with out_lock:
                                worker_errors.append(exc)
                            return

                    _drain_lps(block_all=True)
                except AnalysisCancelledError:
                    return
                except Exception as exc:
                    with out_lock:
                        worker_errors.append(exc)
                finally:
                    if own_lp_pool:
                        try:
                            lp_pool.shutdown(wait=False, cancel_futures=True)
                        except Exception:
                            pass

            def _cpu_lead_worker(worker_idx: int) -> None:
                w_label = f"CPU-W{worker_idx + 1}"
                w_solver = None if mp_pool is not None else self._get_cpu_worker_solver(worker_idx)
                next_cpu_pair: Optional[Tuple[int, int]] = initial_cpu_pairs.get(worker_idx)
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    pair_item: Optional[Tuple[int, int]] = next_cpu_pair
                    next_cpu_pair = None
                    if pair_item is None:
                        if use_gpu:
                            # In Hybrid mode, after finishing its 1 pre-claimed right-end cell at t=0,
                            # this CPU worker immediately frees the CPU pool to solve the GPU Producer's HiGHS LPs!
                            return
                        with q_lock:
                            while pair_q:
                                cand = pair_q.popleft()
                                if cand not in claimed_pairs:
                                    claimed_pairs.add(cand)
                                    pair_item = cand
                                    break
                    if pair_item is None:
                        return
                    l1_i, l2_i = pair_item
                    try:
                        if mp_pool is not None:
                            fut = mp_pool.submit(
                                _eval_lead_cell_in_worker_process,
                                trainer_1_paste,
                                trainer_2_paste,
                                bool(cfg.require_explicit_spreads),
                                l1_i,
                                l2_i,
                                cfg,
                            )
                            cell = fut.result()
                        else:
                            assert w_solver is not None
                            cell = w_solver._evaluate_lead_pair_factored(
                                pool_t1=pool_t1,
                                pool_t2=pool_t2,
                                lead_1_idx=l1_i,
                                lead_2_idx=l2_i,
                                pressure_12=pressure_12,
                                pressure_21=pressure_21,
                                config=cfg,
                                cancel_event=cancel_event,
                            )
                    except AnalysisCancelledError:
                        return
                    except Exception as exc:
                        with out_lock:
                            worker_errors.append(exc)
                        return
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    _record_completed_cell(l1_i, l2_i, cell, w_label, cpu_hw_name)

            try:
                workers: List[threading.Thread] = []
                if use_gpu:
                    workers.append(
                        threading.Thread(
                            target=_gpu_superbatch_producer,
                            name="porygon-lead-gpu-superbatch",
                            daemon=True,
                        )
                    )
                for wi in range(num_cpu_workers):
                    workers.append(
                        threading.Thread(
                            target=_cpu_lead_worker,
                            args=(wi,),
                            name=f"porygon-lead-cpu-{wi + 1}",
                            daemon=True,
                        )
                    )
                for th in workers:
                    th.start()
                for th in workers:
                    th.join()
            finally:
                if prev_threads is not None and HAS_TORCH:
                    try:
                        torch.set_num_threads(prev_threads)
                    except Exception:
                        pass
            if cancel_event is not None and cancel_event.is_set():
                raise AnalysisCancelledError("90×90 Lead Lab sweep cancelled by user.")
            if worker_errors:
                raise worker_errors[0]

        # Solve Global 90×90 Zero-Sum Nash Equilibrium LP + Logit QRE
        global_nash = solve_zero_sum_nash(payoff_matrix)
        global_qre = solve_quantal_response(payoff_matrix, rationality_beta=4.0)

        p_nash = np.asarray(global_nash.trainer_1_strategy, dtype=np.float64)
        q_nash = np.asarray(global_nash.trainer_2_strategy, dtype=np.float64)
        p_qre = np.asarray(global_qre.trainer_1_strategy, dtype=np.float64)
        q_qre = np.asarray(global_qre.trainer_2_strategy, dtype=np.float64)

        # Rank trainer_1's optimal 4-mon brings
        ev_vs_opp_nash = payoff_matrix @ q_nash
        minimax_floor = np.min(payoff_matrix, axis=1)
        mean_vs_all = np.mean(payoff_matrix, axis=1)

        t1_rank_order = sorted(
            range(num_m1),
            key=lambda idx: (
                round(float(p_nash[idx]), 4),
                float(ev_vs_opp_nash[idx]),
                float(minimax_floor[idx]),
            ),
            reverse=True,
        )
        t1_top_brings: List[Dict[str, Any]] = []
        for rank_i, m_idx in enumerate(t1_rank_order[:12], start=1):
            spec = pool_t1.modes[m_idx]
            # Find opponent's toughest answer to this bring
            worst_opp_idx = int(np.argmin(payoff_matrix[m_idx]))
            worst_opp = pool_t2.modes[worst_opp_idx]
            t1_top_brings.append(
                {
                    "rank": rank_i,
                    "mode_idx": m_idx,
                    "lead_idx": spec.lead_idx,
                    "bench_idx": spec.bench_idx,
                    "lead_species": list(spec.lead_species),
                    "bench_species": list(spec.bench_species),
                    "nash_weight": round(float(p_nash[m_idx]), 4),
                    "qre_weight": round(float(p_qre[m_idx]), 4),
                    "ev_vs_opp_nash": round(float(ev_vs_opp_nash[m_idx]), 4),
                    "worst_case_floor": round(float(minimax_floor[m_idx]), 4),
                    "mean_vs_all": round(float(mean_vs_all[m_idx]), 4),
                    "toughest_opp_lead": list(worst_opp.lead_species),
                    "toughest_opp_bench": list(worst_opp.bench_species),
                }
            )

        # Rank trainer_2's most dangerous brings & trainer_1's best counter-bring
        opp_ev_vs_t1_nash = p_nash @ payoff_matrix  # Lower = stronger for trainer_2
        t2_rank_order = sorted(
            range(num_m2),
            key=lambda idx: (
                round(float(q_nash[idx]), 4),
                -float(opp_ev_vs_t1_nash[idx]),
            ),
            reverse=True,
        )
        t2_top_brings: List[Dict[str, Any]] = []
        for rank_j, m2_idx in enumerate(t2_rank_order[:8], start=1):
            spec2 = pool_t2.modes[m2_idx]
            best_counter_idx = int(np.argmax(payoff_matrix[:, m2_idx]))
            counter_spec = pool_t1.modes[best_counter_idx]
            cell_ref = heatmap_cells[counter_spec.lead_idx][spec2.lead_idx]
            opening_str = cell_ref["sub_t1_openings"][counter_spec.bench_idx][spec2.bench_idx]
            t2_top_brings.append(
                {
                    "rank": rank_j,
                    "mode_idx": m2_idx,
                    "lead_idx": spec2.lead_idx,
                    "bench_idx": spec2.bench_idx,
                    "lead_species": list(spec2.lead_species),
                    "bench_species": list(spec2.bench_species),
                    "opp_nash_weight": round(float(q_nash[m2_idx]), 4),
                    "opp_qre_weight": round(float(q_qre[m2_idx]), 4),
                    "ev_for_t1": round(float(opp_ev_vs_t1_nash[m2_idx]), 4),
                    "best_counter_mode_idx": best_counter_idx,
                    "best_counter_lead": list(counter_spec.lead_species),
                    "best_counter_bench": list(counter_spec.bench_species),
                    "best_counter_score": round(float(payoff_matrix[best_counter_idx, m2_idx]), 4),
                    "best_counter_opening": opening_str,
                }
            )

        elapsed_total = time.perf_counter() - t_start
        return LeadMatchupResult(
            trainer_1_species=list(pool_t1.display_species),
            trainer_2_species=list(pool_t2.display_species),
            trainer_1_leads=[
                (pool_t1.display_species[a], pool_t1.display_species[b]) for (a, b) in pool_t1.leads
            ],
            trainer_2_leads=[
                (pool_t2.display_species[a], pool_t2.display_species[b]) for (a, b) in pool_t2.leads
            ],
            modes_t1=list(pool_t1.modes),
            modes_t2=list(pool_t2.modes),
            payoff_matrix=payoff_matrix,
            global_game_value=float(global_nash.game_value),
            trainer_1_nash_weights=p_nash,
            trainer_2_nash_weights=q_nash,
            trainer_1_qre_weights=p_qre,
            trainer_2_qre_weights=q_qre,
            trainer_1_top_brings=t1_top_brings,
            trainer_2_top_brings=t2_top_brings,
            heatmap_cells=heatmap_cells,
            device_used=self.device_str,
            preset=cfg.preset,
            elapsed_s=elapsed_total,
            total_modes_evaluated=num_m1 * num_m2,
            hardware_device_name=hw_name,
            worker_cell_counts=worker_cell_counts,
            compute_mode=eff_mode,
        )

    def build_turn1_battle_state(
        self,
        trainer_1_paste: str,
        trainer_2_paste: str,
        mode_1_idx: int,
        mode_2_idx: int,
    ) -> Tuple[CompiledBattleState, BringModeSpec, BringModeSpec, List[str]]:
        """Build an exact Turn-1 post-entry `CompiledBattleState` for a specific `(mode_1, mode_2)` pair.

        Used by Studio's 1-click Deep Unpruned Turn-1 Audit (`K=128`) so Turn-0 entry abilities
        resolve identically to the `90 × 90` sweep before running full unpruned IEDS + Nash + QRE.
        """
        pool_t1 = self._precompile_team_pool(
            trainer_1_paste, trainer_id="trainer_1", require_explicit_spreads=False
        )
        pool_t2 = self._precompile_team_pool(
            trainer_2_paste, trainer_id="trainer_2", require_explicit_spreads=False
        )
        m1 = pool_t1.modes[int(mode_1_idx)]
        m2 = pool_t2.modes[int(mode_2_idx)]

        f_clean = np.zeros((FIELD_DIM,), dtype=np.float32)
        f_clean[FieldIdx.WEATHER_START + WEATHER_TO_IDX["clear"]] = 1.0
        f_clean[FieldIdx.TERRAIN_START + TERRAIN_TO_IDX["none"]] = 1.0

        p_init = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        p_init[SLOT_TRAINER_1_A] = pool_t1.roster_rows[m1.lead_indices[0]]
        p_init[SLOT_TRAINER_1_B] = pool_t1.roster_rows[m1.lead_indices[1]]
        p_init[SLOT_TRAINER_1_BENCH1] = pool_t1.roster_rows[m1.bench_indices[0]]
        p_init[SLOT_TRAINER_1_BENCH2] = pool_t1.roster_rows[m1.bench_indices[1]]
        p_init[SLOT_TRAINER_2_A] = pool_t2.roster_rows[m2.lead_indices[0]]
        p_init[SLOT_TRAINER_2_B] = pool_t2.roster_rows[m2.lead_indices[1]]
        p_init[SLOT_TRAINER_2_BENCH1] = pool_t2.roster_rows[m2.bench_indices[0]]
        p_init[SLOT_TRAINER_2_BENCH2] = pool_t2.roster_rows[m2.bench_indices[1]]

        f_t0, p_t0 = resolve_turn_zero_lead_entry(f_clean, p_init, tables=self.sm.tables)
        f_t0_np = f_t0.detach().cpu().numpy() if (HAS_TORCH and isinstance(f_t0, torch.Tensor)) else np.asarray(f_t0)
        p_t0_np = p_t0.detach().cpu().numpy() if (HAS_TORCH and isinstance(p_t0, torch.Tensor)) else np.asarray(p_t0)

        board = self._build_board_state(
            f_t0_np,
            p_t0_np,
            pool_t1,
            pool_t2,
            m1.lead_indices,
            m1.bench_indices,
            m2.lead_indices,
            m2.bench_indices,
        )
        events = _describe_turn0_events(f_t0_np, p_init, p_t0_np, board.slot_species)
        return board, m1, m2, events


class _NullContext:
    """No-op context manager used when running in pure-NumPy fallback mode."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: Any) -> None:
        return None
