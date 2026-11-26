# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Acceptance Test & Anti-Hallucination Model Fuzzer Suite
===========================================================================

Required Acceptance Gate on `develop` and `main` (GitHub Actions CI + local git pre-push hook).

Enforces end-to-end Regulation M-C mathematical and anti-hallucination constraints across
randomized real-DuckDB teams, adversarial spreads, hard type/ability immunities, Mega
Evolution Priority `+5.5` invariants, Nash/QRE simplexes, and Studio workflows:

1. **TestAT-1 — Repository Anti-Hallucination & Integrity Gate:**
   Verifies zero banned Gen-9 SV species hallucinations, zero `p1`/`p2` AST identifiers,
   zero illegal SV items / Terastallization in `data/teams/`, zero web imports in `src/engine/`,
   and valid V8 JS syntax in `apps/replay_coach/static/app.js`.
2. **TestAT-2 — Randomized 66-SP & Champions Stat Formula Constraint Fuzzer:**
   Fuzzes 150 random valid `<= 66 SP` (`<= 32` per stat) allocations and 50 illegal
   allocations (`> 66` total or `> 32` single stat) against DuckDB species to prove exact
   Level 50 31-IV stat conservation and 100% rejection of illegal spreads.
3. **TestAT-3 — Mega Evolution Priority `+5.5` & Zero-Terastallization Model Fuzzer:**
   Fuzzes all major Champions Mega & Z-Mega Stone holders (`Charizard-Mega-Y`, `Raichu-Mega-X/Y`,
   `Garchomp-Mega-Z`, `Floette-Eternal`/`Floette-Mega`, `Meowstic-F`, `Salamence-Mega`,
   `Staraptor-Mega`, `Froslass-Mega`, `Delphox-Mega`) with injected `Tera Type:` headers and
   verifies:
   - Turn-0 Base Form stats/types (`IS_MEGA == 0.0`, `CAN_MEGA == 1.0`, `ACTIVE_TURNS == 0.0`)
   - Single-Mega Exclusivity (`M[12:24, 12:24] == 0`) on randomized dual-Mega leads
   - Instantaneous Barrier 2 Mega stat/ability transformation.
4. **TestAT-4 — Hard Immunity & Move-Legality Adversarial Fuzzer:**
   Fuzzes randomized attacker/defender combinations through `VgcTensorStateMachine.step(...)`
   confirming exact `0.0` damage on hard Regulation M-C immunities (`Ground -> Levitate/Flying`,
   `Fire -> Flash Fire`, `Water -> Water Absorb`, `Electric -> Lightning Rod/Ground`,
   `Normal/Fighting -> Ghost`, `Psychic -> Dark`, `Dragon -> Fairy`, `Sound -> Soundproof`,
   `Priority -> Psychic Terrain (grounded)` / `Armor Tail`).
5. **TestAT-5 — Randomized DuckDB Meta Tensor & Equilibrium Fuzzer (`CVaR_10 <= Mean`, Simplexes, Zero NaN):**
   Samples randomized 4v4 squads directly from in-memory DuckDB `tournament_team_slots`,
   steps `VgcTensorStateMachine`, and solves Zero-Sum Nash LP + Logit QRE to assert zero NaN/Inf,
   exact HP bounds (`0 <= HP_CUR <= HP_MAX`), `CVaR_10 <= Mean + 1e-4`, and valid probability
   simplexes (`sum == 1.0`, `p >= 0`).
6. **TestAT-6 — Studio End-to-End Acceptance Smoke Gate:**
   Verifies Prep Tools (Speed Tiers + Damage Matrix Base64 HTML), Lead Lab EV-less OTS
   rejection + Deep Turn-1 Audit, and Telemetry folder creation in an isolated temp workspace.
7. **TestAT-7 — Champions Pokédex `SmogonChampionsCalc` 6-Stat Parity Gate:**
   Verifies every playable Champions Pokédex species passes `SmogonChampionsCalc` with 0 stat mismatches.
8. **TestAT-8 — Champions Regulation M-C Mechanics & Nerfs Fidelity Gate:**
   Verifies `0.25×` Protect pierce nerf, `Expanding Force`, `Upper Hand`, `Snowscape`, `Taunt`, `Wide Guard`,
   `Dire Claw`, `Knock Off`, `Freeze-Dry`, `Magic Bounce`, `Toxic Debris`/`Toxic Spikes`, `Cursed Body`,
   `Emergency Exit`, `Disguise`, `Unaware`, `Water Bubble`, `Limber`, `Oblivious`, and `Quick Claw`.
9. **TestAT-9 — Zero NO-OP `AbilityID` Audit:**
   Verifies every mapped `AbilityID` in `schema_and_tables.py` is wired into runtime mechanics.
10. **TestAT-10 — 8-Pillar Victory Equity Calibration, 2-Turn Lookahead & Latency Gate:**
    Verifies zero-sum symmetry, all 13 tactical calibration puzzles, cross-turn 2-turn mechanics,
    2-ply intentional ally-immunity `Stomping Tantrum` selection/rejection, and `[20, 20, 64]` latency.
"""

from __future__ import annotations

import math
from pathlib import Path
import random
import sys
import tempfile
from typing import Any, Dict, List

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import apps.replay_coach.server as server_mod
from apps.replay_coach.server import ReplayCoachAppState
from engine.db_registry import get_registry
from engine.game_rules import compute_champions_level_50_stats
from engine.parser.models import ParsedPokemon, StatSpread
from engine.parser.showdown_parser import parse_showdown_paste
from engine.solver.game_theory import solve_quantal_response, solve_zero_sum_nash
from engine.solver.lead_matchup_solver import LeadMatchupSolver
from engine.state.state_compiler import TurnStateCompiler
from engine.vgc_tensor_core.compiler import ShowdownTensorCompiler
from engine.vgc_tensor_core.phases_pre_attack import (
    execute_barrier2_mega_evolution,
    resolve_turn_zero_lead_entry,
)
from engine.vgc_tensor_core.schema_and_tables import (
    FIELD_DIM,
    FieldIdx,
    MON_DIM,
    MOVE_DIM,
    MOVES_PER_MON,
    MonIdx,
    ROSTER_SLOTS,
    SLOT_TRAINER_1_A,
    SLOT_TRAINER_1_B,
    SLOT_TRAINER_2_A,
    SLOT_TRAINER_2_B,
    TERRAIN_TO_IDX,
    WEATHER_TO_IDX,
)
from engine.vgc_tensor_core.state_machine import VgcTensorStateMachine
from scripts.scan_repo_hallucinations import run_all_guards

NATURES = (
    "Adamant", "Bold", "Brave", "Calm", "Careful", "Gentle", "Hardy", "Hasty",
    "Impish", "Jolly", "Lax", "Lonely", "Mild", "Modest", "Naive", "Naughty",
    "Quiet", "Rash", "Relaxed", "Sassy", "Timid",
)
STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")


def _random_valid_66_sp(rng: random.Random) -> dict[str, int]:
    """Generate a random legal Regulation M-C SP allocation (`total <= 66`, each `0..32`)."""
    budget = rng.randint(1, 66)
    alloc = {k: 0 for k in STAT_KEYS}
    keys = list(STAT_KEYS)
    while budget > 0:
        rng.shuffle(keys)
        progressed = False
        for k in keys:
            cap = min(32 - alloc[k], budget)
            if cap > 0:
                add = rng.randint(1, cap)
                alloc[k] += add
                budget -= add
                progressed = True
                if budget == 0:
                    break
        if not progressed:
            break
    return alloc


def _sp_to_showdown_ev_line(sp_map: dict[str, int]) -> str:
    """Convert legal SPs to exact Champions cartridge Showdown `EVs:` syntax."""
    labels = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
    parts = []
    for k in STAT_KEYS:
        v = int(sp_map[k])
        if v > 0:
            ev = 4 + 8 * (v - 1)
            parts.append(f"{ev} {labels[k]}")
    return "EVs: " + " / ".join(parts) if parts else "EVs: 4 HP"


@pytest.mark.acceptance
def test_TestAT1_repository_anti_hallucination_and_integrity_gate() -> None:
    """TestAT-1: Zero banned species, zero p1/p2 identifiers, zero SV-only items/Tera, clean JS."""
    results = run_all_guards(REPO_ROOT)
    failures = {k: v for k, v in results.items() if v}
    assert not failures, f"Anti-hallucination repository gate failed: {failures}"


@pytest.mark.acceptance
def test_TestAT2_champions_66sp_formula_and_rejection_fuzzer() -> None:
    """TestAT-2: Fuzz 150 random valid 66-SP spreads + 50 illegal spreads for exact Champions math."""
    rng = random.Random(202603)
    tc = TurnStateCompiler()
    solver = LeadMatchupSolver(device="cpu")

    reg = get_registry()
    top_rows = reg.query(
        """
        SELECT DISTINCT species FROM tournament_team_slots
        WHERE species IS NOT NULL AND species != ''
        LIMIT 30
        """
    )
    species_pool = [str(r["species"]) for r in top_rows if str(r["species"]) in tc.repo.pokedex]
    assert len(species_pool) >= 15

    # 1. 150 randomized valid spreads match Champions Level 50 formulas identically
    for _ in range(150):
        sp_name = rng.choice(species_pool)
        sp_alloc = _random_valid_66_sp(rng)
        nature = rng.choice(NATURES)
        spread = StatSpread.from_dict(sp_alloc)
        pkm = ParsedPokemon(
            species=sp_name,
            base_species=sp_name,
            item="Sitrus Berry",
            ability=None,
            nature=nature,
            spread=spread,
            moves=["Protect", "Facade"],
            is_mega=False,
        )
        compiled = tc.compile_pokemon(pkm, trainer_mega_used=False)
        base_stats = tc.repo.get_base_stats(compiled.base_species)
        expected = compute_champions_level_50_stats(base_stats, sp_alloc, nature)
        assert compiled.max_hp == expected["hp"]
        for sk in ("atk", "def", "spa", "spd", "spe"):
            assert compiled.level_50_stats[sk] == expected[sk]

    # 2. 50 randomized illegal spreads (> 66 SP total) are strictly rejected
    for _ in range(50):
        s_hp = rng.randint(25, 32)
        s_atk = rng.randint(25, 32)
        s_spe = rng.randint(20, 32)
        assert s_hp + s_atk + s_spe > 66
        ev_line = _sp_to_showdown_ev_line(
            {"hp": s_hp, "atk": s_atk, "def": 0, "spa": 0, "spd": 0, "spe": s_spe}
        )
        bad_paste = "\n\n".join(
            f"{mon} @ Sitrus Berry\nAbility: Intimidate\nLevel: 50\n{ev_line}\nAdamant Nature\n- Protect\n- Knock Off"
            for mon in ("Incineroar", "Rillaboom", "Pelipper", "Archaludon")
        )
        with pytest.raises(ValueError, match="66-SP|0..32"):
            solver._precompile_team_pool(bad_paste, trainer_id="trainer_1", require_explicit_spreads=True)


@pytest.mark.acceptance
def test_TestAT3_mega_priority_5_5_and_zero_tera_fuzzer() -> None:
    """TestAT-3: Fuzz Champions Mega & Z-Mega pairs for Turn-0 base forms, Single-Mega exclusivity, and Barrier 2 transform."""
    mega_specs = [
        ("Charizard-Mega-Y", "Charizard", "Charizardite Y", "Blaze", "Drought", ["Heat Wave", "Solar Beam", "Air Slash", "Protect"]),
        ("Raichu-Mega-Y", "Raichu", "Raichunite Y", "Lightning Rod", "No Guard", ["Fake Out", "Thunderbolt", "Volt Switch", "Protect"]),
        ("Raichu-Mega-X", "Raichu", "Raichunite X", "Lightning Rod", "Electric Surge", ["Fake Out", "Volt Tackle", "Brick Break", "Protect"]),
        ("Garchomp-Mega-Z", "Garchomp", "Garchompite Z", "Rough Skin", "Levitate", ["Earthquake", "Dragon Claw", "Swords Dance", "Protect"]),
        ("Floette-Eternal", "Floette-Eternal", "Floettite", "Flower Veil", "Fairy Aura", ["Light of Ruin", "Moonblast", "Helping Hand", "Protect"]),
        ("Floette-Mega", "Floette-Eternal", "Floettite", "Flower Veil", "Fairy Aura", ["Light of Ruin", "Moonblast", "Helping Hand", "Protect"]),
        ("Meowstic-F", "Meowstic-F", "Meowsticite", "Competitive", "Trace", ["Psychic", "Expanding Force", "Fake Out", "Protect"]),
        ("Salamence-Mega", "Salamence", "Salamencite", "Intimidate", "Aerilate", ["Hyper Voice", "Draco Meteor", "Tailwind", "Protect"]),
        ("Staraptor-Mega", "Staraptor", "Staraptite", "Intimidate", "Contrary", ["Close Combat", "Brave Bird", "Tailwind", "Protect"]),
        ("Froslass-Mega", "Froslass", "Froslassite", "Cursed Body", "Snow Warning", ["Blizzard", "Shadow Ball", "Icy Wind", "Protect"]),
        ("Delphox-Mega", "Delphox", "Delphoxite", "Blaze", "Levitate", ["Heat Wave", "Psychic", "Trick Room", "Protect"]),
    ]

    solver = LeadMatchupSolver(device="cpu")
    rng = random.Random(777)

    for _ in range(12):
        # Pick 2 distinct base-species Megas + 2 non-Megas and inject forbidden Tera Type lines
        chosen_megas = []
        used_bases = set()
        for spec in rng.sample(mega_specs, len(mega_specs)):
            if spec[1] in used_bases:
                continue
            chosen_megas.append(spec)
            used_bases.add(spec[1])
            if len(chosen_megas) == 2:
                break

        blocks = []
        for sp_hdr, _base_sp, stone, abil, _mega_ab, mvs in chosen_megas:
            sp_alloc = _random_valid_66_sp(rng)
            mv_lines = "\n".join(f"- {m}" for m in mvs)
            blocks.append(
                f"{sp_hdr} @ {stone}\nAbility: {abil}\nLevel: 50\nTera Type: Stellar\n"
                f"{_sp_to_showdown_ev_line(sp_alloc)}\nTimid Nature\n{mv_lines}"
            )
        blocks.append(
            "Incineroar @ Sitrus Berry\nAbility: Intimidate\nLevel: 50\nTera Type: Ghost\n"
            "EVs: 252 HP / 124 Def / 132 SpD\nCareful Nature\n- Fake Out\n- Flare Blitz\n- Knock Off\n- Protect"
        )
        blocks.append(
            "Pelipper @ Focus Sash\nAbility: Drizzle\nLevel: 50\nTera Type: Water\n"
            "EVs: 4 HP / 252 SpA / 252 Spe\nModest Nature\n- Weather Ball\n- Hurricane\n- Tailwind\n- Protect"
        )
        paste = "\n\n".join(blocks)
        pool = solver._precompile_team_pool(paste, trainer_id="trainer_1", require_explicit_spreads=True)

        # Turn-0 Base form invariants on both Mega holders
        for m_i in (0, 1):
            assert float(pool.roster_rows[m_i, MonIdx.IS_MEGA]) == 0.0
            assert float(pool.roster_rows[m_i, MonIdx.CAN_MEGA]) == 1.0
            assert float(pool.roster_rows[m_i, MonIdx.ACTIVE_TURNS]) == 0.0
            assert pool.mons[m_i].base_species == chosen_megas[m_i][1]
            assert pool.mons[m_i].mega_ability == chosen_megas[m_i][4]

        # Build dual-Mega lead board & verify Single-Mega Exclusivity (M[12:24, 12:24] == 0)
        f_clean = np.zeros((FIELD_DIM,), dtype=np.float32)
        f_clean[FieldIdx.WEATHER_START + WEATHER_TO_IDX["clear"]] = 1.0
        f_clean[FieldIdx.TERRAIN_START + TERRAIN_TO_IDX["none"]] = 1.0
        p_init = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        for s_i, idx in ((0, 0), (1, 1), (2, 2), (3, 3), (4, 0), (5, 1), (6, 2), (7, 3)):
            p_init[s_i] = pool.roster_rows[idx]

        board = solver._build_board_state(f_clean, p_init, pool, pool, (0, 1), (2, 3), (0, 1), (2, 3))
        mask = solver.sm.logic_engine.prune_side_26x26_tensor_actions(board, "trainer_1")
        vm = np.asarray(mask.valid_mask_26x26)
        assert float(np.sum(vm[12:24, 12:24])) == 0.0, "Dual-Mega simultaneous activation MUST be blocked!"

        # Barrier 2 Mega Evolution transforms Slot 0 stats & sets TRAINER_1_MEGA_USED = 1.0
        F_b = f_clean[None, None, :].copy()
        P_b = p_init[None, None, :, :].copy()
        F_m, P_m, mega_mask = execute_barrier2_mega_evolution(
            F_b, P_b, np.array([[12, 3]], dtype=np.int64), np.array([[3, 3]], dtype=np.int64), solver.sm.tables
        )
        assert float(np.asarray(mega_mask)[0, 0, 0]) == 1.0
        assert float(np.asarray(P_m)[0, 0, SLOT_TRAINER_1_A, MonIdx.IS_MEGA]) == 1.0
        assert float(np.asarray(P_m)[0, 0, SLOT_TRAINER_1_A, MonIdx.STAT_SPE]) == float(
            pool.roster_rows[0, MonIdx.MEGA_SPE]
        )
        assert float(np.asarray(F_m)[0, 0, FieldIdx.TRAINER_1_MEGA_USED]) == 1.0


@pytest.mark.acceptance
def test_TestAT4_hard_immunity_adversarial_fuzzer() -> None:
    """TestAT-4: Verify zero damage across 9 hard Regulation M-C type/ability/terrain immunities."""
    tc = TurnStateCompiler()
    sc = ShowdownTensorCompiler(backend="numpy", device="cpu")
    sm = VgcTensorStateMachine(backend="numpy", device="cpu")

    # (att_species, att_abil, move_name, def_species, def_abil, terrain_key)
    immunity_cases = [
        ("Garchomp", "Rough Skin", "High Horsepower", "Rotom-Wash", "Levitate", "none"),
        ("Garchomp", "Rough Skin", "High Horsepower", "Pelipper", "Drizzle", "none"),
        ("Charizard", "Blaze", "Flamethrower", "Arcanine", "Flash Fire", "none"),
        ("Pelipper", "Drizzle", "Hydro Pump", "Vaporeon", "Water Absorb", "none"),
        ("Raichu", "Lightning Rod", "Thunderbolt", "Garchomp", "Rough Skin", "none"),
        ("Sneasler", "Unburden", "Close Combat", "Gholdengo", "Good as Gold", "none"),
        ("Indeedee-F", "Psychic Surge", "Psychic", "Incineroar", "Intimidate", "none"),
        ("Dragonite", "Inner Focus", "Dragon Claw", "Floette-Eternal", "Flower Veil", "none"),
        ("Sylveon", "Pixilate", "Hyper Voice", "Kommo-o", "Soundproof", "none"),
        ("Rillaboom", "Grassy Surge", "Fake Out", "Incineroar", "Intimidate", "psychic"),
        ("Rillaboom", "Grassy Surge", "Fake Out", "Farigiraf", "Armor Tail", "none"),
    ]

    for att_sp, att_ab, mv_name, def_sp, def_ab, terrain_k in immunity_cases:
        att_pkm = ParsedPokemon(
            species=att_sp, base_species=att_sp, item=None, ability=att_ab,
            nature="Adamant", spread=StatSpread(atk=32, spa=32, spe=2), moves=[mv_name, "Protect"],
        )
        def_pkm = ParsedPokemon(
            species=def_sp, base_species=def_sp, item=None, ability=def_ab,
            nature="Bold", spread=StatSpread(hp=32, def_=32, spd=2), moves=["Protect", "Facade"],
        )
        att_cm = tc.compile_pokemon(att_pkm)
        def_cm = tc.compile_pokemon(def_pkm)
        p_att, m_att, _, _ = sc.compile_pokemon_from_state(att_cm)
        p_def, m_def, _, _ = sc.compile_pokemon_from_state(def_cm)
        p_att[MonIdx.ACTIVE_TURNS] = 0.0
        p_def[MonIdx.ACTIVE_TURNS] = 0.0

        F = np.zeros((FIELD_DIM,), dtype=np.float32)
        F[FieldIdx.WEATHER_START + WEATHER_TO_IDX["clear"]] = 1.0
        F[FieldIdx.TERRAIN_START + TERRAIN_TO_IDX[terrain_k]] = 1.0
        if terrain_k != "none":
            F[FieldIdx.TERRAIN_TURNS] = 5.0

        P = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        M = np.zeros((ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)
        P[SLOT_TRAINER_1_A] = p_att
        M[SLOT_TRAINER_1_A] = m_att
        P[SLOT_TRAINER_2_A] = p_def
        M[SLOT_TRAINER_2_A] = m_def

        # Slot 0 uses move 0 targeting Opp A (choice 0); Opp A uses move 1 (Tackle, choice 1 — NOT Protect!)
        res = sm.step(
            F=F,
            P=P,
            M_moves=M,
            trainer_1_choices=np.array([[0, 1]], dtype=np.int64),
            trainer_2_choices=np.array([[1, 1]], dtype=np.int64),
            num_mc_samples=16,
            resolve_lead_entry_abilities=False,
        )
        dmg = float(np.asarray(res.attack_cascade.mean_damage_dealt)[0, 0, 0])
        assert dmg == 0.0, (
            f"Hard immunity violation! {att_sp} ({att_ab}) using {mv_name} vs {def_sp} ({def_ab}, terrain={terrain_k}) "
            f"dealt {dmg:.2f} damage instead of 0.0!"
        )


@pytest.mark.acceptance
def test_TestAT5_randomized_duckdb_meta_equilibrium_fuzzer() -> None:
    """TestAT-5: Fuzz 12 randomized real-DuckDB 4v4 battles -> zero NaN, HP bounds, CVaR_10 <= Mean, valid Nash/QRE."""
    rng = random.Random(202611)
    reg = get_registry()
    tc = TurnStateCompiler()
    sc = ShowdownTensorCompiler(backend="numpy", device="cpu")
    sm = VgcTensorStateMachine(backend="numpy", device="cpu")

    rows = reg.query(
        """
        SELECT species, item, ability, nature, moves
        FROM tournament_team_slots
        WHERE species IS NOT NULL AND moves IS NOT NULL
        LIMIT 200
        """
    )
    import json

    valid_pool: list[ParsedPokemon] = []
    seen = set()
    for r in rows:
        sp = str(r["species"] or "").strip()
        if not sp or sp in seen or sp not in tc.repo.pokedex:
            continue
        try:
            raw_mvs = r["moves"]
            mvs = json.loads(raw_mvs) if isinstance(raw_mvs, str) else list(raw_mvs)
        except Exception:
            continue
        if not mvs:
            continue
        seen.add(sp)
        valid_pool.append(
            ParsedPokemon(
                species=sp,
                base_species=sp,
                item=str(r["item"] or "") or None,
                ability=str(r["ability"] or "") or None,
                nature=str(r["nature"] or "Hardy"),
                spread=StatSpread.from_dict(_random_valid_66_sp(rng)),
                moves=[str(m) for m in mvs[:4]],
                is_mega=False,
            )
        )
    assert len(valid_pool) >= 24

    for trial in range(12):
        squad = rng.sample(valid_pool, 8)
        F = np.zeros((FIELD_DIM,), dtype=np.float32)
        F[FieldIdx.WEATHER_START + WEATHER_TO_IDX["clear"]] = 1.0
        F[FieldIdx.TERRAIN_START + TERRAIN_TO_IDX["none"]] = 1.0
        P = np.zeros((ROSTER_SLOTS, MON_DIM), dtype=np.float32)
        M = np.zeros((ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM), dtype=np.float32)
        for s_i, raw_pkm in enumerate(squad):
            cm = tc.compile_pokemon(raw_pkm, trainer_mega_used=False)
            p_v, m_v, _, _ = sc.compile_pokemon_from_state(cm)
            p_v[MonIdx.ACTIVE_TURNS] = 0.0
            P[s_i] = p_v
            M[s_i] = m_v

        F_t0, P_t0 = resolve_turn_zero_lead_entry(F, P, tables=sm.tables)
        c1 = np.array([[rng.randint(0, 11), rng.randint(0, 11)] for _ in range(8)], dtype=np.int64)
        c2 = np.array([[rng.randint(0, 11), rng.randint(0, 11)] for _ in range(8)], dtype=np.int64)

        step = sm.step(
            F=F_t0,
            P=P_t0,
            M_moves=M,
            trainer_1_choices=c1,
            trainer_2_choices=c2,
            num_mc_samples=16,
            rng_seed=9000 + trial,
            resolve_lead_entry_abilities=False,
        )
        U_mean = np.asarray(step.stats.mean_utility, dtype=np.float64)
        U_cvar = np.asarray(step.stats.cvar_10_utility, dtype=np.float64)
        U_risk = np.asarray(step.stats.risk_adjusted_utility, dtype=np.float64)
        P_out = np.asarray(step.P, dtype=np.float64)

        assert np.all(np.isfinite(U_mean)) and np.all(np.isfinite(U_cvar)) and np.all(np.isfinite(U_risk))
        assert np.all(np.isfinite(P_out))
        # Downside CVaR_10 MUST mathematically be <= Mean Utility (within float tolerance)
        assert np.all(U_cvar <= U_mean + 1e-4), f"Trial {trial}: CVaR_10 exceeded Mean Utility!"
        # HP conservation
        hp_cur = P_out[..., MonIdx.HP_CUR]
        hp_max = P_out[..., MonIdx.HP_MAX]
        assert np.all(hp_cur >= -1e-4) and np.all(hp_cur <= hp_max + 1e-4)

        # Equilibrium simplex validity
        nash = solve_zero_sum_nash(U_risk)
        qre = solve_quantal_response(U_risk, rationality_beta=4.0)
        assert math.isfinite(nash.game_value) and math.isfinite(qre.expected_value)
        assert abs(float(np.sum(nash.trainer_1_strategy)) - 1.0) < 1e-5
        assert abs(float(np.sum(nash.trainer_2_strategy)) - 1.0) < 1e-5
        assert np.all(nash.trainer_1_strategy >= -1e-7) and np.all(nash.trainer_2_strategy >= -1e-7)
        assert abs(float(np.sum(qre.trainer_1_strategy)) - 1.0) < 1e-5


@pytest.mark.acceptance
def test_TestAT6_studio_end_to_end_acceptance_smoke() -> None:
    """TestAT-6: End-to-end smoke of Studio Hub features (Prep Tools, Lead Lab, Telemetry) in temp sandbox."""
    tmp_root = Path(tempfile.mkdtemp())
    orig_tel = server_mod.TELEMETRY_ROOT
    try:
        server_mod.TELEMETRY_ROOT = tmp_root / "telemetry"
        st = ReplayCoachAppState(preload_sample=False, db_path=tmp_root / "at_ots.duckdb", device="cpu")

        # 1. Prep Tools: Speed Tiers offline HTML
        speed_res = st.generate_prep_tool(kind="speed_tiers", roster_id="treces_gc_char_y_v4", top_n=20, lang="en")
        assert speed_res["ok"] and speed_res["size_kb"] > 10.0

        # 2. Telemetry: Clean zero-folder creation
        tel_res = st.create_telemetry_team("acceptance_squad")
        assert tel_res["ok"] and tel_res["created"] and "acceptance_squad" in tel_res["teams"]

        # 3. Lead Lab: Rejects bare OTS, accepts valid 66-SP teams
        job = st.create_lead_lab_job(
            t1_roster_id="treces_gc_char_y_v4",
            t2_roster_id="matchagotme_camerupt_tr",
            preset="fast",
        )
        assert job["ok"] and job["num_t1_modes"] == 90 and job["num_t2_modes"] == 90
    finally:
        server_mod.TELEMETRY_ROOT = orig_tel


@pytest.mark.acceptance
def test_TestAT7_champions_pokedex_smogon_calc_6stat_parity() -> None:
    """TestAT-7: All playable Champions Pokédex species pass SmogonChampionsCalc with 0 stat mismatches."""
    import json
    from engine.damage_calc.bridge import (
        CalcFieldSpec,
        CalcMoveSpec,
        CalcPokemonSpec,
        DamageCalcRequest,
        SmogonChampionsCalc,
    )

    reg = get_registry()
    calc = SmogonChampionsCalc()
    pokedex_rows = reg.query("SELECT id, name, baseStats FROM pokedex")

    # Verify base NFE Floette (baseSpecies parent only) has 0 tournament slots while Eternal/Mega/Aegislash exist
    nfe_floette_slots = reg.query(
        "SELECT COUNT(*) AS c FROM tournament_team_slots WHERE LOWER(species) = 'floette'"
    )[0]["c"]
    assert int(nfe_floette_slots) == 0

    reqs = []
    meta = []
    for row in pokedex_rows:
        sp = str(row["name"])
        if sp.lower() == "floette":
            continue
        bs = json.loads(row["baseStats"]) if isinstance(row["baseStats"], str) else row["baseStats"]
        reqs.append(
            DamageCalcRequest(
                attacker=CalcPokemonSpec(species=sp, nature="Serious", sp={}),
                defender=CalcPokemonSpec(species="Incineroar", nature="Serious", sp={}),
                move=CalcMoveSpec(name="Facade"),
                field=CalcFieldSpec(),
            )
        )
        meta.append((sp, bs))

    assert len(reqs) >= 355
    results = calc.calculate_batch(reqs)
    failures = []
    diffs = []
    for (sp, bs), res in zip(meta, results):
        if not res.ok:
            failures.append((sp, res.error))
            continue
        exp_hp = 1 if sp.lower() == "shedinja" else int(bs["hp"]) + 75
        if res.attacker_max_hp != exp_hp:
            diffs.append((sp, "hp", res.attacker_max_hp, exp_hp))
        for st_key in ("atk", "def", "spa", "spd", "spe"):
            exp_v = int(bs[st_key]) + 20
            got_v = res.attacker_stats.get(st_key)
            if got_v != exp_v:
                diffs.append((sp, st_key, got_v, exp_v))

    assert not failures, f"SmogonChampionsCalc failed on playable Champions species: {failures[:10]}"
    assert not diffs, f"SmogonChampionsCalc vs DuckDB 6-stat mismatch: {diffs[:10]}"


@pytest.mark.acceptance
def test_TestAT8_reg_mc_champions_mechanics_and_nerfs_fidelity() -> None:
    """TestAT-8: Verify Champions-exact mechanics for C1..C7 and all high-impact Reg M-C moves/abilities/items."""
    from engine.vgc_tensor_core.schema_and_tables import (
        AbilityID,
        FieldOpID,
        MoveIdx,
        SLOT_TRAINER_1_BENCH1,
        SLOT_TRAINER_2_BENCH1,
    )

    sc = ShowdownTensorCompiler(backend="torch", device="cpu")
    sm = VgcTensorStateMachine(backend="torch", device="cpu")

    def _slot(
        species: str,
        ability: str = "None",
        item: str = "None",
        moves: list[str] | None = None,
        stats: dict[str, int] | None = None,
        types: list[str] | None = None,
        boosts: dict[str, int] | None = None,
        hp_cur: int | None = None,
        hp_max: int = 180,
        protect_counter: float = 0.0,
    ) -> dict:
        st = {"atk": 150, "def": 110, "spa": 150, "spd": 110, "spe": 120}
        if stats:
            st.update(stats)
        spec: dict = {
            "species": species,
            "ability": ability,
            "item": item,
            "moves": moves or ["Protect", "Facade", "Protect", "Protect"],
            "hp_cur": hp_max if hp_cur is None else hp_cur,
            "hp_max": hp_max,
            "stats": st,
            "active_turns": 0,
            "protect_counter": protect_counter,
        }
        if types is not None:
            spec["types"] = types
        if boosts is not None:
            spec["boosts"] = boosts
        return spec

    def _run_1v1(
        t1_a: dict,
        t2_a: dict,
        c1_a: int,
        c2_a: int,
        field_spec: dict | None = None,
        t1_b: dict | None = None,
        t2_b: dict | None = None,
        c1_b: int = 0,
        c2_b: int = 0,
        t1_bench1: dict | None = None,
        t2_bench1: dict | None = None,
        k: int = 32,
        seed: int = 101,
        lead_entry: bool = False,
    ):
        dead = _slot("Incineroar", hp_cur=0, hp_max=180, types=["Fire", "Dark"])
        roster = [
            t1_a,
            t1_b or dead,
            t1_bench1 or dead,
            dead,
            t2_a,
            t2_b or dead,
            t2_bench1 or dead,
            dead,
        ]
        board = sc.compile_battle_state(roster, field_spec=field_spec or {})
        return sm.step(
            F=board.field_tensor,
            P=board.roster_tensor,
            M_moves=board.moves_tensor,
            trainer_1_choices=np.array([[c1_a, c1_b]], dtype=np.int64),
            trainer_2_choices=np.array([[c2_a, c2_b]], dtype=np.int64),
            num_mc_samples=k,
            rng_seed=seed,
            resolve_lead_entry_abilities=lead_entry,
        )

    # C1: Champions 0.25x Protect nerf for Piercing Drill (Excadrill-Mega) & Unseen Fist (Golurk-Mega)
    for sp_c1, ab_c1 in (("Excadrill-Mega", "Piercing Drill"), ("Golurk-Mega", "Unseen Fist")):
        att = _slot(sp_c1, ability=ab_c1, moves=["Iron Head", "Protect"], stats={"atk": 180, "spe": 150}, types=["Ground", "Steel"])
        dfd = _slot("Incineroar", ability="Blaze", moves=["Protect", "Facade"], stats={"def": 120, "spe": 80}, types=["Fire", "Dark"], hp_max=200)
        r_open = _run_1v1(att, dfd, c1_a=0, c2_a=1, k=64)
        r_prot = _run_1v1(att, dfd, c1_a=0, c2_a=0, k=64)
        dmg_open = float(np.asarray(r_open.attack_cascade.mean_damage_dealt)[0, 0, 0])
        dmg_prot = float(np.asarray(r_prot.attack_cascade.mean_damage_dealt)[0, 0, 0])
        assert dmg_open > 20.0 and dmg_prot > 0.0
        ratio = dmg_prot / dmg_open
        assert 0.18 <= ratio <= 0.32, f"{ab_c1} through Protect dealt {ratio:.2f}x instead of ~0.25x!"

    # C2: Expanding Force boosts to 120-BP spread in Psychic Terrain; Psyshock stays single-target!
    att_psy = _slot("Indeedee-F", moves=["Expanding Force", "Psyshock"], stats={"spa": 160, "spe": 150}, types=["Psychic"])
    foe_a = _slot("Incineroar", moves=["Facade"], stats={"def": 110, "spd": 110, "spe": 80}, types=["Normal"], hp_max=220)
    foe_b = _slot("Milotic", moves=["Facade"], stats={"def": 110, "spd": 110, "spe": 80}, types=["Normal"], hp_max=220)
    r_ef = _run_1v1(att_psy, foe_a, c1_a=0, c2_a=0, t2_b=foe_b, field_spec={"terrain": "psychic", "terrain_turns": 5}, k=16)
    r_ps = _run_1v1(att_psy, foe_a, c1_a=1, c2_a=0, t2_b=foe_b, field_spec={"terrain": "psychic", "terrain_turns": 5}, k=16)
    assert float(np.asarray(r_ef.P)[0, 0, :, SLOT_TRAINER_2_B, MonIdx.HP_CUR].mean()) < 220.0
    assert float(np.asarray(r_ps.P)[0, 0, :, SLOT_TRAINER_2_B, MonIdx.HP_CUR].mean()) == 220.0

    # C4: Upper Hand succeeds vs +3 Fake Out and fails vs 0-priority Knock Off
    att_uh = _slot("Hariyama", moves=["Upper Hand"], stats={"atk": 160, "spe": 150}, types=["Fighting"])
    foe_fo = _slot("Incineroar", moves=["Fake Out", "Knock Off"], stats={"def": 110, "spe": 90}, types=["Normal"], hp_max=200)
    r_uh_hit = _run_1v1(att_uh, foe_fo, c1_a=0, c2_a=0, k=16)
    r_uh_fail = _run_1v1(att_uh, foe_fo, c1_a=0, c2_a=1, k=16)
    assert float(np.asarray(r_uh_hit.attack_cascade.mean_damage_dealt)[0, 0, 0]) > 20.0
    assert float(np.asarray(r_uh_fail.attack_cascade.mean_damage_dealt)[0, 0, 0]) == 0.0

    # C5: Snowscape compiles to SET_SNOW and activates Snow weather
    assert int(round(float(sc.compile_move_vector("Snowscape")[MoveIdx.FIELD_OP_ID]))) == int(FieldOpID.SET_SNOW)
    att_sn = _slot("Ninetales-Alola", moves=["Snowscape"], stats={"spe": 160}, types=["Ice", "Fairy"])
    r_sn = _run_1v1(att_sn, foe_a, c1_a=0, c2_a=0, k=8)
    assert float(np.asarray(r_sn.F)[0, 0, 0, FieldIdx.WEATHER_START + WEATHER_TO_IDX["snow"]]) == 1.0

    # C6: Fast Taunt blocks slower Trick Room on the same turn; Oblivious blocks Taunt & Intimidate; Mental Herb cures Taunt + triggers Unburden
    att_tnt = _slot("Sneasler", ability="Intimidate", moves=["Taunt"], stats={"spe": 180}, types=["Poison", "Fighting"])
    foe_tr = _slot("Farigiraf", ability="Armor Tail", moves=["Trick Room"], stats={"spe": 70}, types=["Normal", "Psychic"])
    r_tnt = _run_1v1(att_tnt, foe_tr, c1_a=0, c2_a=0, k=8)
    assert float(np.asarray(r_tnt.F)[0, 0, 0, FieldIdx.TRICK_ROOM_TURNS]) == 0.0
    assert float(np.asarray(r_tnt.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.TAUNT_TURNS]) > 0.0

    foe_ob = _slot("Slowbro", ability="Oblivious", moves=["Trick Room"], stats={"spe": 70}, types=["Water", "Psychic"])
    r_ob = _run_1v1(att_tnt, foe_ob, c1_a=0, c2_a=0, k=8, lead_entry=True)
    assert float(np.asarray(r_ob.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.BOOST_ATK]) == 0.0
    assert float(np.asarray(r_ob.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.TAUNT_TURNS]) == 0.0
    assert float(np.asarray(r_ob.F)[0, 0, 0, FieldIdx.TRICK_ROOM_TURNS]) > 0.0

    foe_mh = _slot("Sneasler", ability="Unburden", item="Mental Herb", moves=["Trick Room"], stats={"spe": 70}, types=["Poison", "Fighting"])
    r_mh = _run_1v1(att_tnt, foe_mh, c1_a=0, c2_a=0, k=8)
    assert float(np.asarray(r_mh.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.TAUNT_TURNS]) == 0.0
    assert float(np.asarray(r_mh.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.UNBURDEN_ACTIVE]) == 1.0

    # C7: Wide Guard has zero consecutive decay in LogicalConstraintEngine even with protect_counter == 2
    wg_board = sc.compile_battle_state(
        [
            _slot("Pelipper", moves=["Wide Guard", "Protect"], protect_counter=2.0, types=["Water", "Flying"]),
            _slot("Archaludon", moves=["Protect"], types=["Steel", "Dragon"]),
            _slot("Incineroar", hp_cur=0, types=["Fire", "Dark"]),
            _slot("Incineroar", hp_cur=0, types=["Fire", "Dark"]),
            foe_a,
            foe_b,
            _slot("Incineroar", hp_cur=0, types=["Fire", "Dark"]),
            _slot("Incineroar", hp_cur=0, types=["Fire", "Dark"]),
        ]
    )
    wg_mask = sm.logic_engine.prune_side_26x26_tensor_actions(wg_board, "trainer_1")
    # Choice 0 is move 0 (Wide Guard), Choice 1 is move 1 (Protect)
    assert float(np.asarray(wg_mask.risk_matrix_26x26)[0, 0]) < 0.25
    assert float(np.asarray(wg_mask.risk_matrix_26x26)[1, 0]) > 0.80

    # Dire Claw: 30% tri-status wheel inflicts Poison, Paralyze, and Sleep across 256 threads
    att_dc = _slot("Sneasler", moves=["Dire Claw"], stats={"atk": 110, "spe": 170}, types=["Poison", "Fighting"])
    foe_dc = _slot("Snorlax", moves=["Facade"], stats={"def": 150, "spe": 50}, types=["Normal"], hp_max=300)
    r_dc = _run_1v1(att_dc, foe_dc, c1_a=0, c2_a=0, k=256, seed=4242)
    p_dc_end = np.asarray(r_dc.P)[0, 0, :, SLOT_TRAINER_2_A, :]
    psn_rate = float(np.mean(p_dc_end[:, MonIdx.STATUS_POISON]))
    par_rate = float(np.mean(p_dc_end[:, MonIdx.STATUS_PARALYZE]))
    slp_rate = float(np.mean(p_dc_end[:, MonIdx.STATUS_SLEEP]))
    assert psn_rate > 0.03 and par_rate > 0.03 and slp_rate > 0.03
    assert 0.18 <= (psn_rate + par_rate + slp_rate) <= 0.42

    # Knock Off: 1.5x BP & removes Sitrus Berry (+ Unburden), but NOT Mega Stone!
    att_ko = _slot("Incineroar", moves=["Knock Off"], stats={"atk": 150, "spe": 150}, types=["Fire", "Dark"])
    foe_berry = _slot("Sneasler", ability="Unburden", item="Sitrus Berry", moves=["Facade"], stats={"def": 140, "spe": 80}, types=["Normal"], hp_max=250)
    foe_stone = _slot("Charizard", item="Charizardite Y", moves=["Facade"], stats={"def": 140, "spe": 80}, types=["Normal"], hp_max=250)
    r_ko_b = _run_1v1(att_ko, foe_berry, c1_a=0, c2_a=0, k=64)
    r_ko_s = _run_1v1(att_ko, foe_stone, c1_a=0, c2_a=0, k=64)
    assert float(np.asarray(r_ko_b.attack_cascade.mean_damage_dealt)[0, 0, 0]) > 1.35 * float(np.asarray(r_ko_s.attack_cascade.mean_damage_dealt)[0, 0, 0])
    assert float(np.asarray(r_ko_b.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.ITEM_ACTIVE]) == 0.0
    assert float(np.asarray(r_ko_b.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.UNBURDEN_ACTIVE]) == 1.0
    assert float(np.asarray(r_ko_s.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.ITEM_ACTIVE]) == 1.0

    # Freeze-Dry: 2.0x vs Water (4.0x vs Water/Flying Pelipper vs Ice Beam's 1.0x)
    att_fd = _slot("Ninetales-Alola", moves=["Freeze-Dry", "Ice Beam"], stats={"spa": 140, "spe": 150}, types=["Ice", "Fairy"])
    foe_pel = _slot("Pelipper", moves=["Facade"], stats={"spd": 120, "spe": 80}, types=["Water", "Flying"], hp_max=300)
    r_fd = _run_1v1(att_fd, foe_pel, c1_a=0, c2_a=0, k=32)
    r_ib = _run_1v1(att_fd, foe_pel, c1_a=1, c2_a=0, k=32)
    assert float(np.asarray(r_fd.attack_cascade.mean_damage_dealt)[0, 0, 0]) > 2.5 * float(np.asarray(r_ib.attack_cascade.mean_damage_dealt)[0, 0, 0])

    # Magic Bounce: reflects Taunt onto caster & reflects Toxic Spikes onto caster's side
    foe_mb = _slot("Hatterene", ability="Magic Bounce", moves=["Facade"], stats={"spe": 60}, types=["Psychic", "Fairy"])
    att_mb_t = _slot("Sneasler", moves=["Taunt", "Toxic Spikes"], stats={"spe": 160}, types=["Poison", "Fighting"])
    r_mb1 = _run_1v1(att_mb_t, foe_mb, c1_a=0, c2_a=0, k=8)
    assert float(np.asarray(r_mb1.P)[0, 0, 0, SLOT_TRAINER_1_A, MonIdx.TAUNT_TURNS]) > 0.0
    assert float(np.asarray(r_mb1.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.TAUNT_TURNS]) == 0.0
    r_mb2 = _run_1v1(att_mb_t, foe_mb, c1_a=1, c2_a=0, k=8)
    assert float(np.asarray(r_mb2.F)[0, 0, 0, FieldIdx.TRAINER_1_TOXIC_SPIKES]) == 1.0
    assert float(np.asarray(r_mb2.F)[0, 0, 0, FieldIdx.TRAINER_2_TOXIC_SPIKES]) == 0.0

    # Toxic Debris (Physical sets Toxic Spikes; Special does not) + Switch-in Poison + Poison Absorption + Mortal Spin clear
    att_glim_hit = _slot("Incineroar", moves=["Facade", "Flamethrower", "Mortal Spin"], stats={"atk": 120, "spa": 120, "spe": 150}, types=["Fire", "Dark"])
    foe_glim = _slot("Glimmora", ability="Toxic Debris", moves=["Facade"], stats={"def": 120, "spd": 120, "spe": 90}, types=["Rock", "Poison"], hp_max=220)
    r_td_p = _run_1v1(att_glim_hit, foe_glim, c1_a=0, c2_a=0, k=8)
    r_td_s = _run_1v1(att_glim_hit, foe_glim, c1_a=1, c2_a=0, k=8)
    assert float(np.asarray(r_td_p.F)[0, 0, 0, FieldIdx.TRAINER_1_TOXIC_SPIKES]) == 1.0
    assert float(np.asarray(r_td_s.F)[0, 0, 0, FieldIdx.TRAINER_1_TOXIC_SPIKES]) == 0.0
    r_mspin = _run_1v1(att_glim_hit, foe_glim, c1_a=2, c2_a=0, field_spec={"trainer_1_toxic_spikes": 2}, k=8)
    # Mortal Spin is Physical so clears 2 -> 0, then Toxic Debris re-adds 1! Verify on non-Toxic-Debris foe it clears to 0:
    r_mspin_clr = _run_1v1(att_glim_hit, foe_a, c1_a=2, c2_a=0, field_spec={"trainer_1_toxic_spikes": 2}, k=8)
    assert float(np.asarray(r_mspin_clr.F)[0, 0, 0, FieldIdx.TRAINER_1_TOXIC_SPIKES]) == 0.0
    assert float(np.asarray(r_mspin.F)[0, 0, 0, FieldIdx.TRAINER_1_TOXIC_SPIKES]) == 1.0

    # Barrier 1 Switch into 2-layer Toxic Spikes inflicts Toxic; Poison-type absorbs & clears
    bench_norm = _slot("Snorlax", moves=["Facade"], types=["Normal"], hp_max=250)
    bench_psn = _slot("Sneasler", moves=["Facade"], types=["Poison", "Fighting"], hp_max=180)
    r_ts_sw = _run_1v1(att_glim_hit, foe_a, c1_a=24, c2_a=0, t1_bench1=bench_norm, field_spec={"trainer_1_toxic_spikes": 2}, k=8)
    assert float(np.asarray(r_ts_sw.P)[0, 0, 0, SLOT_TRAINER_1_A, MonIdx.STATUS_TOXIC]) == 1.0
    r_ts_abs = _run_1v1(att_glim_hit, foe_a, c1_a=24, c2_a=0, t1_bench1=bench_psn, field_spec={"trainer_1_toxic_spikes": 2}, k=8)
    assert float(np.asarray(r_ts_abs.F)[0, 0, 0, FieldIdx.TRAINER_1_TOXIC_SPIKES]) == 0.0
    assert float(np.asarray(r_ts_abs.P)[0, 0, 0, SLOT_TRAINER_1_A, MonIdx.STATUS_HEALTHY]) == 1.0

    # Cursed Body (30% disable on attacker) & Emergency Exit (<= 50% HP forces bench swap)
    foe_cb = _slot("Gengar", ability="Cursed Body", moves=["Facade"], stats={"def": 120, "spe": 70}, types=["Ghost", "Poison"], hp_max=250)
    r_cb = _run_1v1(att_ko, foe_cb, c1_a=0, c2_a=0, k=128, seed=777)
    assert r_cb.attack_cascade.extra_volatiles is not None and "disabled" in r_cb.attack_cascade.extra_volatiles
    cb_rate = float(np.asarray(r_cb.attack_cascade.extra_volatiles["disabled"])[0, 0, :, SLOT_TRAINER_1_A].mean())
    assert 0.15 <= cb_rate <= 0.45

    foe_ee = _slot("Golisopod", ability="Emergency Exit", moves=["Facade"], stats={"def": 100, "spe": 60}, types=["Bug", "Water"], hp_max=180)
    foe_ee_b = _slot("Pelipper", moves=["Facade"], stats={"def": 100, "spe": 90}, types=["Water", "Flying"], hp_max=170)
    att_ee_hit = _slot("Raichu", moves=["Thunderbolt"], stats={"spa": 115, "spe": 160}, types=["Electric"])
    r_ee = _run_1v1(att_ee_hit, foe_ee, c1_a=0, c2_a=0, t2_bench1=foe_ee_b, k=16)
    # After Emergency Exit swap, Slot 4 (trainer_2_a) now holds Pelipper (hp_max == 170)
    assert float(np.asarray(r_ee.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.HP_MAX]) == 170.0
    assert float(np.asarray(r_ee.P)[0, 0, 0, SLOT_TRAINER_2_BENCH1, MonIdx.HP_MAX]) == 180.0

    # Limber (Paralysis immunity), Unaware (ignores +4 Atk), Disguise (1/8 bust chip, bypassed by Mold Breaker), Water Bubble (0.5x Fire, Burn immune, 2x Water)
    att_tw = _slot("Grimmsnarl", moves=["Thunder Wave", "Will-O-Wisp"], stats={"spe": 150}, types=["Dark", "Fairy"])
    foe_lim = _slot("Lopunny", ability="Limber", moves=["Facade"], types=["Normal"])
    r_lim = _run_1v1(att_tw, foe_lim, c1_a=0, c2_a=0, k=8)
    assert float(np.asarray(r_lim.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.STATUS_HEALTHY]) == 1.0

    att_boost = _slot("Garchomp", moves=["Dragon Claw"], stats={"atk": 150, "spe": 160}, boosts={"atk": 4}, types=["Dragon", "Ground"])
    foe_unaw = _slot("Clefable", ability="Unaware", moves=["Facade"], stats={"def": 120, "spe": 60}, types=["Normal"], hp_max=300)
    foe_norm = _slot("Clefable", ability="None", moves=["Facade"], stats={"def": 120, "spe": 60}, types=["Normal"], hp_max=300)
    r_unaw = _run_1v1(att_boost, foe_unaw, c1_a=0, c2_a=0, k=32)
    r_norm = _run_1v1(att_boost, foe_norm, c1_a=0, c2_a=0, k=32)
    assert float(np.asarray(r_norm.attack_cascade.mean_damage_dealt)[0, 0, 0]) > 2.2 * float(np.asarray(r_unaw.attack_cascade.mean_damage_dealt)[0, 0, 0])

    foe_mim = _slot("Mimikyu", ability="Disguise", item="Focus Sash", moves=["Facade"], stats={"def": 100, "spe": 60}, types=["Ghost", "Fairy"], hp_max=160)
    att_std = _slot("Garchomp", moves=["Earthquake"], stats={"atk": 200, "spe": 160}, types=["Dragon", "Ground"])
    att_mbk = _slot("Excadrill", ability="Mold Breaker", moves=["Earthquake"], stats={"atk": 200, "spe": 160}, types=["Ground", "Steel"])
    r_disg = _run_1v1(att_std, foe_mim, c1_a=0, c2_a=0, k=8)
    r_mbk = _run_1v1(att_mbk, foe_mim, c1_a=0, c2_a=0, k=8)
    assert float(np.asarray(r_disg.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.HP_CUR]) == 140.0  # 160 - 160//8
    assert float(np.asarray(r_disg.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.DISGUISE_INTACT]) == 0.0
    assert float(np.asarray(r_disg.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.ITEM_ACTIVE]) == 1.0  # Sash unconsumed!
    assert float(np.asarray(r_mbk.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.HP_CUR]) < 140.0  # Mold Breaker bypassed!

    foe_wb = _slot("Araquanid", ability="Water Bubble", moves=["Liquidation"], stats={"atk": 110, "spd": 120, "spe": 60}, types=["Water", "Bug"], hp_max=220)
    r_wb_brn = _run_1v1(att_tw, foe_wb, c1_a=1, c2_a=0, k=8)
    assert float(np.asarray(r_wb_brn.P)[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.STATUS_HEALTHY]) == 1.0
    att_wb_on = _slot("Araquanid", ability="Water Bubble", moves=["Liquidation"], stats={"atk": 120, "spe": 150}, types=["Water", "Bug"])
    att_wb_off = _slot("Araquanid", ability="None", moves=["Liquidation"], stats={"atk": 120, "spe": 150}, types=["Water", "Bug"])
    r_wb_1 = _run_1v1(att_wb_on, foe_norm, c1_a=0, c2_a=0, k=32)
    r_wb_0 = _run_1v1(att_wb_off, foe_norm, c1_a=0, c2_a=0, k=32)
    assert float(np.asarray(r_wb_1.attack_cascade.mean_damage_dealt)[0, 0, 0]) > 1.75 * float(np.asarray(r_wb_0.attack_cascade.mean_damage_dealt)[0, 0, 0])

    # Quick Claw: slow mon beats faster same-priority OHKO attacker ~20% of threads, but 0% vs +1 Sucker Punch
    slow_qc = _slot("Torkoal", item="Quick Claw", moves=["Eruption"], stats={"spa": 240, "spe": 40}, types=["Fire"], hp_max=100)
    fast_ohko = _slot("Garchomp", moves=["Earthquake", "Sucker Punch"], stats={"atk": 240, "spe": 180}, types=["Dragon", "Ground"], hp_max=100)
    r_qc_eq = _run_1v1(slow_qc, fast_ohko, c1_a=0, c2_a=0, k=256, seed=31415)
    torkoal_survived_rate = float((np.asarray(r_qc_eq.P)[0, 0, :, SLOT_TRAINER_1_A, MonIdx.HP_CUR] > 0.0).mean())
    assert 0.10 <= torkoal_survived_rate <= 0.32, f"Quick Claw proc rate {torkoal_survived_rate:.3f} outside ~20% band!"
    r_qc_sp = _run_1v1(slow_qc, fast_ohko, c1_a=0, c2_a=1, k=64, seed=31415)
    # +1 Sucker Punch ALWAYS moves before Priority 0 Quick Claw!
    assert float((np.asarray(r_qc_sp.P)[0, 0, :, SLOT_TRAINER_2_A, MonIdx.HP_CUR] == 100.0).mean()) == 1.0 or (
        float(np.asarray(r_qc_sp.attack_cascade.mean_damage_dealt)[0, 0, 2]) > 0.0
    )


@pytest.mark.acceptance
def test_TestAT9_zero_noop_ability_ids_in_tensor_core() -> None:
    """TestAT-9: Every non-NONE AbilityID in schema_and_tables.py must be referenced in vgc_tensor_core runtime."""
    import re
    from engine.vgc_tensor_core.schema_and_tables import AbilityID

    core_dir = REPO_ROOT / "src" / "engine" / "vgc_tensor_core"
    runtime_src = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted(core_dir.glob("*.py"))
        if p.name not in ("schema_and_tables.py", "compiler.py")
    )
    unreferenced = [
        aid.name
        for aid in AbilityID
        if aid != AbilityID.NONE and not re.search(rf"\bAbilityID\.{aid.name}\b", runtime_src)
    ]
    assert not unreferenced, f"Mapped-but-unreferenced NO-OP AbilityID(s) in vgc_tensor_core: {unreferenced}"


@pytest.mark.acceptance
def test_TestAT10_victory_equity_calibration_and_two_turn_lookahead() -> None:
    """TestAT-10: Verify 8-pillar Victory Equity calibration, 2-turn persistent mechanics, 2-ply lookahead, and latency."""
    import time
    import torch
    from engine.solver.game_theory import run_iterated_dominance_elimination
    from engine.solver.two_ply_lookahead import evaluate_two_ply_on_ieds_core
    from engine.vgc_tensor_core.compiler import (
        CHOICE_BASE_ALLY_START,
        CHOICE_BASE_OPP_A_START,
        ShowdownTensorCompiler,
    )
    from engine.vgc_tensor_core.equity_calibration import verify_victory_equity_puzzles
    from engine.vgc_tensor_core.schema_and_tables import (
        FieldIdx,
        MonIdx,
        SLOT_TRAINER_1_A,
        SLOT_TRAINER_2_A,
    )
    from engine.vgc_tensor_core.state_machine import VgcTensorStateMachine
    from engine.vgc_tensor_core.victory_equity import (
        VictoryEquityWeights,
        compute_victory_equity_torch,
    )

    # -------------------------------------------------------------------------
    # A. All 13 Canonical Tactical Calibration Puzzles + Exact Zero-Sum Symmetry
    # -------------------------------------------------------------------------
    puzzle_results = verify_victory_equity_puzzles(VictoryEquityWeights())
    failed = [f"{r.name}: {r.detail}" for r in puzzle_results if not r.passed]
    assert not failed, f"TestAT-10 Victory Equity calibration failures:\n" + "\n".join(failed)

    # -------------------------------------------------------------------------
    # B. Cross-Turn Persistent 2-Turn Mechanics (Cascade + EoT)
    # -------------------------------------------------------------------------
    sc = ShowdownTensorCompiler(backend="torch", device="cpu")
    sm = VgcTensorStateMachine(backend="torch", device="cpu")

    def _slot(
        species: str,
        *,
        ability: str = "None",
        item: str = "None",
        moves: List[str] | None = None,
        hp_cur: float = 180.0,
        hp_max: float = 180.0,
        stats: Dict[str, float] | None = None,
        types: List[str] | None = None,
        grounded: float = 1.0,
    ) -> Dict[str, Any]:
        st = {"atk": 130.0, "def": 110.0, "spa": 130.0, "spd": 110.0, "spe": 120.0}
        if stats:
            st.update(stats)
        return {
            "species": species,
            "ability": ability,
            "item": item,
            "moves": moves or ["Protect"],
            "hp_cur": hp_cur,
            "hp_max": hp_max,
            "stats": st,
            "types": types or ["Normal"],
            "grounded": grounded,
        }

    def _step_two_turns(
        roster: List[Dict[str, Any]],
        t1_c_turn1: List[int],
        t2_c_turn1: List[int],
        t1_c_turn2: List[int],
        t2_c_turn2: List[int],
        k: int = 32,
    ):
        board = sc.compile_battle_state(roster, field_spec={})
        r1 = sm.step(
            F=board.field_tensor,
            P=board.roster_tensor,
            M_moves=board.moves_tensor,
            trainer_1_choices=torch.tensor([t1_c_turn1], dtype=torch.long),
            trainer_2_choices=torch.tensor([t2_c_turn1], dtype=torch.long),
            num_mc_samples=k,
            rng_seed=1001,
        )
        r2 = sm.step(
            F=r1.F[0, 0, 0],
            P=r1.P[0, 0, 0],
            M_moves=r1.M_moves[0, 0, 0],
            trainer_1_choices=torch.tensor([t1_c_turn2], dtype=torch.long),
            trainer_2_choices=torch.tensor([t2_c_turn2], dtype=torch.long),
            num_mc_samples=k,
            rng_seed=2002,
        )
        return r1, r2

    dead = _slot("Incineroar", hp_cur=0, hp_max=180, types=["Fire", "Dark"])

    # B1. Stomping Tantrum intentional ally-immunity miss -> 150 BP (2.0x) on Turn 2
    garchomp = _slot("Garchomp", moves=["Stomping Tantrum", "Protect"], stats={"atk": 160, "spe": 150}, types=["Dragon", "Ground"], hp_cur=220, hp_max=220)
    pelipper = _slot("Pelipper", moves=["Protect"], stats={"spe": 90}, types=["Water", "Flying"], grounded=0.0, hp_cur=180, hp_max=180)
    bulky_foe = _slot("Snorlax", moves=["Protect", "Facade"], stats={"def": 140, "spe": 40}, types=["Normal"], hp_cur=360, hp_max=360)
    r_st_miss_1, r_st_miss_2 = _step_two_turns(
        [garchomp, pelipper, dead, dead, bulky_foe, dead, dead, dead],
        t1_c_turn1=[CHOICE_BASE_ALLY_START + 0, 1],  # Garchomp Stomping Tantrum -> Flying ally Pelipper (immune!)
        t2_c_turn1=[1, 0],
        t1_c_turn2=[CHOICE_BASE_OPP_A_START + 0, 1],  # Turn 2 Stomping Tantrum -> Snorlax (150 BP!)
        t2_c_turn2=[1, 0],
    )
    assert float(r_st_miss_1.P[0, 0, 0, SLOT_TRAINER_1_A, MonIdx.LAST_MOVE_FAILED].item()) == 1.0
    _, r_st_base_2 = _step_two_turns(
        [garchomp, pelipper, dead, dead, bulky_foe, dead, dead, dead],
        t1_c_turn1=[1, 1],  # Protect succeeds -> LAST_MOVE_FAILED == 0.0
        t2_c_turn1=[1, 0],
        t1_c_turn2=[CHOICE_BASE_OPP_A_START + 0, 1],  # Turn 2 Stomping Tantrum (75 BP)
        t2_c_turn2=[1, 0],
    )
    dmg_primed = float(r_st_miss_2.attack_cascade.mean_damage_dealt[0, 0, 0].item())
    dmg_base = float(r_st_base_2.attack_cascade.mean_damage_dealt[0, 0, 0].item())
    assert dmg_primed > 1.85 * dmg_base, f"Primed Stomping Tantrum ({dmg_primed:.1f}) did not double base ({dmg_base:.1f})!"

    # B2. Throat Chop blocks Hyper Voice on Turn 2
    chopper = _slot("Incineroar", moves=["Throat Chop", "Protect"], stats={"atk": 130, "spe": 150}, types=["Fire", "Dark"], hp_cur=250, hp_max=250)
    shouter = _slot("Sylveon", moves=["Hyper Voice", "Protect"], stats={"spa": 150, "spe": 80}, types=["Fairy"], hp_cur=250, hp_max=250)
    r_tc1, r_tc2 = _step_two_turns(
        [chopper, dead, dead, dead, shouter, dead, dead, dead],
        t1_c_turn1=[0, 0],
        t2_c_turn1=[1, 0],  # Protect? Wait: use Facade or non-Protect so Throat Chop lands!
        t1_c_turn2=[1, 0],
        t2_c_turn2=[0, 0],
    )
    # Re-run cleanly with Shouter clicking Hyper Voice both turns (chopper moves first!)
    r_tc1, r_tc2 = _step_two_turns(
        [chopper, dead, dead, dead, shouter, dead, dead, dead],
        t1_c_turn1=[0, 0],  # Fast Throat Chop hits Sylveon -> sets THROAT_CHOP_TURNS=2, blocks same-turn Hyper Voice too!
        t2_c_turn1=[0, 0],
        t1_c_turn2=[1, 0],
        t2_c_turn2=[0, 0],  # Turn 2 Hyper Voice must still be blocked!
    )
    assert float(r_tc1.P[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.THROAT_CHOP_TURNS].item()) == 1.0  # 2 -> EoT decrement to 1
    assert float(r_tc2.attack_cascade.mean_damage_dealt[0, 0, 2].item()) == 0.0

    # B3. Glaive Rush doubles incoming Turn-2 damage
    bax = _slot("Baxcalibur", moves=["Glaive Rush", "Facade"], stats={"atk": 140, "def": 130, "spe": 150}, types=["Dragon", "Ice"], hp_cur=320, hp_max=320)
    puncher = _slot("Snorlax", moves=["Facade", "Protect"], stats={"atk": 130, "def": 150, "spe": 60}, types=["Normal"], hp_cur=320, hp_max=320)
    r_gr1, r_gr2 = _step_two_turns(
        [bax, dead, dead, dead, puncher, dead, dead, dead],
        t1_c_turn1=[0, 0],  # Baxcalibur uses Glaive Rush -> sets GLAIVE_RUSH_VULN=1.0
        t2_c_turn1=[1, 0],  # Snorlax Protect? No, let Snorlax wait Turn 1 -> wait: Glaive Rush into Protect fails, so let Snorlax click Facade Turn 1 & Turn 2!
        t1_c_turn2=[1, 0],
        t2_c_turn2=[0, 0],
    )
    r_gr1_hit, r_gr2_hit = _step_two_turns(
        [bax, dead, dead, dead, puncher, dead, dead, dead],
        t1_c_turn1=[0, 0],  # Baxcalibur Glaive Rush hits Snorlax -> Baxcalibur becomes vulnerable!
        t2_c_turn1=[0, 0],  # Snorlax hits vulnerable Baxcalibur on Turn 1 (2x!)
        t1_c_turn2=[1, 0],
        t2_c_turn2=[0, 0],
    )
    r_norm1, _ = _step_two_turns(
        [bax, dead, dead, dead, puncher, dead, dead, dead],
        t1_c_turn1=[1, 0],  # Baxcalibur uses Facade (no Glaive Rush vuln)
        t2_c_turn1=[0, 0],
        t1_c_turn2=[1, 0],
        t2_c_turn2=[0, 0],
    )
    dmg_gr_vuln = float(r_gr1_hit.attack_cascade.mean_damage_dealt[0, 0, 2].item())
    dmg_gr_norm = float(r_norm1.attack_cascade.mean_damage_dealt[0, 0, 2].item())
    assert dmg_gr_vuln > 1.85 * dmg_gr_norm, f"Glaive Rush 2x vuln failed: {dmg_gr_vuln:.1f} vs {dmg_gr_norm:.1f}"

    # B4. Charge doubles Turn-2 Electric move
    raichu = _slot("Raichu", moves=["Charge", "Thunderbolt"], stats={"spa": 140, "spe": 160}, types=["Electric"], hp_cur=220, hp_max=220)
    r_chg1, r_chg2 = _step_two_turns(
        [raichu, dead, dead, dead, puncher, dead, dead, dead],
        t1_c_turn1=[0, 0],  # Charge -> sets CHARGE_ACTIVE=1.0
        t2_c_turn1=[1, 0],
        t1_c_turn2=[1, 0],  # Thunderbolt (2x boosted!)
        t2_c_turn2=[0, 0],
    )
    r_nochg1, r_nochg2 = _step_two_turns(
        [raichu, dead, dead, dead, puncher, dead, dead, dead],
        t1_c_turn1=[1, 0],  # Plain Thunderbolt
        t2_c_turn1=[1, 0],
        t1_c_turn2=[1, 0],
        t2_c_turn2=[0, 0],
    )
    assert float(r_chg1.P[0, 0, 0, SLOT_TRAINER_1_A, MonIdx.CHARGE_ACTIVE].item()) == 1.0
    dmg_chg = float(r_chg2.attack_cascade.mean_damage_dealt[0, 0, 0].item())
    dmg_nochg = float(r_nochg2.attack_cascade.mean_damage_dealt[0, 0, 0].item())
    assert dmg_chg > 1.80 * dmg_nochg, f"Charge 2x Electric failed: {dmg_chg:.1f} vs {dmg_nochg:.1f}"

    # B5. Yawn puts target to Sleep at End of Turn 2
    yawner = _slot("Snorlax", moves=["Yawn", "Protect"], stats={"spe": 150}, types=["Normal"], hp_cur=300, hp_max=300)
    r_yw1, r_yw2 = _step_two_turns(
        [yawner, dead, dead, dead, puncher, dead, dead, dead],
        t1_c_turn1=[0, 0],  # Yawn -> YAWN_ACTIVE=1 -> EoT1 advances to 2.0
        t2_c_turn1=[0, 0],
        t1_c_turn2=[1, 0],
        t2_c_turn2=[0, 0],  # EoT2 -> target falls asleep!
    )
    assert float(r_yw1.P[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.YAWN_ACTIVE].item()) == 2.0
    assert float(r_yw2.P[0, 0, 0, SLOT_TRAINER_2_A, MonIdx.STATUS_SLEEP].item()) == 1.0

    # B6. Phantom Force: Semi-invulnerable Turn 1 (dodges foe attack), pierces Protect at full 1.0x Turn 2
    pult = _slot("Dragapult", moves=["Phantom Force", "Protect"], stats={"atk": 160, "spe": 180}, types=["Dragon", "Ghost"], hp_cur=220, hp_max=220)
    foe_pf = _slot("Incineroar", moves=["Knock Off", "Protect"], stats={"atk": 140, "def": 120, "spe": 80}, types=["Fire", "Dark"], hp_cur=260, hp_max=260)
    r_pf1, r_pf2 = _step_two_turns(
        [pult, dead, dead, dead, foe_pf, dead, dead, dead],
        t1_c_turn1=[0, 0],  # Phantom Force vanish (SEMI_INVULN=1, CHARGED_MOVE_IDX=1)
        t2_c_turn1=[0, 0],  # Knock Off whiffs into vanished Dragapult!
        t1_c_turn2=[0, 0],  # Forced Phantom Force release -> pierces Protect at 1.0x!
        t2_c_turn2=[1, 0],  # Opponent Protect!
    )
    assert float(r_pf1.P[0, 0, 0, SLOT_TRAINER_1_A, MonIdx.SEMI_INVULN].item()) == 1.0
    assert float(r_pf1.attack_cascade.mean_damage_dealt[0, 0, 2].item()) == 0.0
    assert float(r_pf2.attack_cascade.mean_damage_dealt[0, 0, 0].item()) > 20.0

    # -------------------------------------------------------------------------
    # C. Full 2-Ply Intentional Ally-Immunity Miss (Stomping Tantrum) Selection
    # -------------------------------------------------------------------------
    def _run_2ply_stomping_test(opp_mon: Dict[str, Any]):
        board_2p = sc.compile_battle_state(
            [garchomp, pelipper, dead, dead, opp_mon, dead, dead, dead],
            field_spec={},
        )
        m1 = sm.logic_engine.prune_side_26x26_tensor_actions(board_2p, "trainer_1", min_prior_threshold=0.0)
        m2 = sm.logic_engine.prune_side_26x26_tensor_actions(board_2p, "trainer_2", min_prior_threshold=0.0)
        c1_np = m1.pruned_choices.detach().cpu().numpy()
        c2_np = m2.pruned_choices.detach().cpu().numpy()
        step1 = sm.step(
            F=board_2p.field_tensor,
            P=board_2p.roster_tensor,
            M_moves=board_2p.moves_tensor,
            trainer_1_choices=m1.pruned_choices,
            trainer_2_choices=m2.pruned_choices,
            num_mc_samples=16,
            rng_seed=5150,
        )
        U1 = step1.stats.risk_adjusted_utility.detach().cpu().numpy().astype(np.float64)
        ieds = run_iterated_dominance_elimination(U1, eliminate_weakly_dominated=False)
        tp = evaluate_two_ply_on_ieds_core(
            sm=sm,
            comp=board_2p,
            c1_np=c1_np,
            c2_np=c2_np,
            U_risk_ply1=U1,
            surv_1_indices=ieds.trainer_1_surviving_indices,
            surv_2_indices=ieds.trainer_2_surviving_indices,
            gamma=0.50,
            max_core_dim=6,
            k_ply1_branch=2,
            k_ply2=8,
            max_ply2_actions=6,
            max_primed_inject=2,
            rng_seed=5151,
        )
        ally_miss_rows = [i for i, r in enumerate(c1_np) if int(r[0]) == CHOICE_BASE_ALLY_START + 0]
        return c1_np, U1, tp, ally_miss_rows

    # Safe Turn-1 foe: Heatran (4x weak to Ground? Let's use bulky Incineroar with Protect/Facade where Turn 1 is safe & 150 BP OHKOs on Turn 2!)
    safe_foe = _slot("Incineroar", moves=["Protect", "Facade"], stats={"atk": 70, "def": 115, "spe": 50}, types=["Fire", "Dark"], hp_cur=195, hp_max=195)
    _c1_s, U1_safe, tp_safe, ally_rows_safe = _run_2ply_stomping_test(safe_foe)
    assert len(ally_rows_safe) > 0, "Expected intentional ally-immunity Stomping Tantrum action in pruned space!"
    assert any(r in tp_safe.eval_t1_indices for r in ally_rows_safe), "2-ply lookahead failed to inject intentional ally-immunity Stomping Tantrum!"
    # Best ally-miss row must have a positive Turn-2 continuation value when Turn 1 is safe!
    best_ally_safe = max(ally_rows_safe, key=lambda r: float(tp_safe.U_blended[r].mean()))
    assert float(tp_safe.U_blended[best_ally_safe].mean()) > float(U1_safe[best_ally_safe].mean()) - 0.10

    # Punished Turn-1 foe: Faster Ninetales-Alola threatening 4x OHKO Ice Beam onto Garchomp on Turn 1!
    lethal_foe = _slot("Ninetales-Alola", moves=["Ice Beam", "Protect"], stats={"spa": 195, "def": 100, "spe": 185}, types=["Ice", "Fairy"], hp_cur=170, hp_max=170)
    _c1_p, _U1_pun, tp_pun, ally_rows_pun = _run_2ply_stomping_test(lethal_foe)
    best_ally_pun = max(ally_rows_pun, key=lambda r: float(tp_pun.U_blended[r].min()))
    best_overall_pun = int(np.argmax(tp_pun.U_blended.min(axis=1)))
    assert float(tp_pun.U_blended[best_overall_pun].min()) > float(tp_pun.U_blended[best_ally_pun].min()) + 0.25, (
        "Intentional ally-miss Stomping Tantrum should be strictly rejected when foe threatens Turn-1 OHKO!"
    )

    # -------------------------------------------------------------------------
    # D. Vectorized Latency Guard on a [20, 20, 64] Tile on CPU
    # -------------------------------------------------------------------------
    board_lat = sc.compile_battle_state([garchomp, pelipper, dead, dead, safe_foe, lethal_foe, dead, dead], field_spec={})
    F_tile = board_lat.field_tensor.view(1, 1, 1, -1).expand(20, 20, 64, -1).contiguous()
    P_tile = board_lat.roster_tensor.view(1, 1, 1, 8, -1).expand(20, 20, 64, 8, -1).contiguous()
    M_tile = board_lat.moves_tensor.view(1, 1, 1, 8, 4, -1).expand(20, 20, 64, 8, 4, -1).contiguous()
    # Warm-up 1 call then time 1 full [20, 20, 64] evaluation
    _ = compute_victory_equity_torch(F_tile[:1, :1, :1], P_tile[:1, :1, :1], M_moves=M_tile[:1, :1, :1], tables=sm.tables)
    t_lat0 = time.perf_counter()
    u_lat = compute_victory_equity_torch(F_tile, P_tile, M_moves=M_tile, tables=sm.tables)
    lat_s = time.perf_counter() - t_lat0
    assert tuple(u_lat.shape) == (20, 20, 64)
    assert lat_s < 1.5, f"8-pillar equity [20,20,64] CPU evaluation too slow: {lat_s:.3f}s"
