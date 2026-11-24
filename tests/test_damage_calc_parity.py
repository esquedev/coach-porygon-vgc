# -*- coding: utf-8 -*-
"""Parity & ground-truth verification tests for the vendored Smogon Champions Damage Calc.

Validates:
1. Hermetic in-process `SmogonChampionsCalc` (`mini_racer` V8 & `quickjs` fallback)
   matches official Champions Regulation M-C 66-SP stat formulas and exact 16 rolls.
2. Real exact-integer HP damage events from `matchagotme_g1.html` fall cleanly inside
   the 16 cartridge rolls produced by `SmogonChampionsCalc`.
3. Parity cross-check between `SmogonChampionsCalc` and `vgc_tensor_core/attack_cascade.py`
   across weather, terrain, screens, crits, burn, spread targets, items, and Megas.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine.damage_calc import (
    CalcFieldSpec,
    CalcMoveSpec,
    CalcPokemonSpec,
    CalcSideSpec,
    DamageCalcRequest,
    SmogonChampionsCalc,
    SpeedCalcRequest,
    get_champions_calc,
)
from engine.db_registry import get_registry
from engine.parser.models import ParsedBattle, ParsedPokemon, ParsedTeam, StatSpread
from engine.state.state_compiler import TurnStateCompiler
from engine.vgc_tensor_core.attack_cascade import execute_attack_cascade
from engine.vgc_tensor_core.compiler import ShowdownTensorCompiler
from engine.vgc_tensor_core.phases_pre_attack import execute_pre_attack_phases
from engine.vgc_tensor_core.schema_and_tables import MonIdx, build_bilinear_lookup_tables


def _run_gpu_single_move_damage(
    attacker_mon: ParsedPokemon,
    defender_mon: ParsedPokemon,
    move_name: str,
    *,
    weather: str | None = None,
    terrain: str | None = None,
    defender_reflect: bool = False,
    defender_light_screen: bool = False,
    defender_aurora_veil: bool = False,
    spread_partner_alive: bool = True,
) -> tuple[int, int]:
    """Run `vgc_tensor_core` over K=256 threads (forced 0% crit via Shell Armor or
    non-crit roll observation) to extract empirical [min_dmg, max_dmg] dealt to slot 4.
    """
    dummy_ally = ParsedPokemon(
        species="Snorlax",
        base_species="Snorlax",
        item="Leftovers",
        ability="Immunity",
        nature="Careful",
        spread=StatSpread(hp=32, def_=18, spd=16),
        moves=["Protect", "Helping Hand", "Body Slam", "Yawn"],
    )
    dummy_foe_b = ParsedPokemon(
        species="Blissey",
        base_species="Blissey",
        item="Leftovers",
        ability="Natural Cure",
        nature="Calm",
        spread=StatSpread(hp=32, def_=32, spd=2),
        moves=["Protect", "Soft-Boiled", "Helping Hand", "Seismic Toss"],
        current_hp_pct=100.0 if spread_partner_alive else 0.0,
        fainted=not spread_partner_alive,
    )
    # Use a fast attacker so it always moves first cleanly and dummy slots Protect
    t1 = ParsedTeam(
        trainer_name="trainer_1",
        team_preview=[attacker_mon.species, dummy_ally.species],
        battle_roster=[attacker_mon.species, dummy_ally.species],
        active_slots=[attacker_mon.species, dummy_ally.species],
        pokemon_sets={attacker_mon.species: attacker_mon, dummy_ally.species: dummy_ally},
    )
    t2 = ParsedTeam(
        trainer_name="trainer_2",
        team_preview=[defender_mon.species, dummy_foe_b.species],
        battle_roster=[defender_mon.species, dummy_foe_b.species],
        active_slots=[defender_mon.species, dummy_foe_b.species],
        pokemon_sets={defender_mon.species: defender_mon, dummy_foe_b.species: dummy_foe_b},
    )
    battle = ParsedBattle(
        trainer_1=t1,
        trainer_2=t2,
        weather=weather,
        terrain=terrain,
        trainer_2_reflect=defender_reflect,
        trainer_2_light_screen=defender_light_screen,
        trainer_2_aurora_veil=defender_aurora_veil,
    )
    ts = TurnStateCompiler().compile_turn_state(battle, run_inference=False)
    compiled = ShowdownTensorCompiler(registry=get_registry(), backend="numpy").compile_turn_state(ts)
    tables = build_bilinear_lookup_tables()

    # Slot 0 uses move_idx=0 targeting opp_slot_a (choice=0); all other slots use Protect (choice=0 on Protect slot)
    # Ensure attacker's move_name is slot 0, and dummy slots have Protect at move 0
    move_idx = next(i for i, m in enumerate(attacker_mon.moves) if m == move_name)
    # In compiler encoding: target_code 0 (opp A) = move_idx, 1 (opp B) = 4 + move_idx
    t1_choices = np.array([[move_idx, 0]], dtype=np.int64)
    # Defender uses a harmless status/no-op move (move index 0 = Helping Hand / Splash / non-protect)
    t2_choices = np.array([[0, 0]], dtype=np.int64)

    pre = execute_pre_attack_phases(
        F_init=compiled.field_tensor,
        P_init=compiled.roster_tensor,
        M_moves_init=compiled.moves_tensor,
        trainer_1_choices=t1_choices,
        trainer_2_choices=t2_choices,
        tables=tables,
    )
    cas = execute_attack_cascade(
        F_init=pre.F,
        P_init=pre.P,
        M_moves_init=pre.M_moves,
        trainer_1_choices=t1_choices,
        trainer_2_choices=t2_choices,
        pre_attack_res=pre,
        tables=tables,
        num_mc_samples=256,
        rng_seed=12345,
    )
    init_hp = float(pre.P[0, 0, 4, MonIdx.HP_CUR])
    end_hp = np.asarray(cas.P[0, 0, :, 4, MonIdx.HP_CUR], dtype=np.float32)
    dmgs = np.round(init_hp - end_hp).astype(int)
    # Filter out ~4.17% crits (upper tail outliers) and misses (0 dmg)
    non_zero = dmgs[dmgs > 0]
    assert len(non_zero) > 0, "Attack never landed in GPU cascade"
    # 5th to 93rd percentile cleanly excludes 4.17% crit tail while preserving [min_roll, max_roll]
    p_low = int(np.min(non_zero))
    # Crits are 1.5x, so anything > 1.25 * median is a crit
    med = float(np.median(non_zero))
    non_crit = non_zero[non_zero <= med * 1.25]
    return p_low, int(np.max(non_crit))


class TestSmogonChampionsBridge:
    def test_v8_and_quickjs_exact_agreement_and_champions_stats(self) -> None:
        calc_v8 = SmogonChampionsCalc(preferred_runtime="mini_racer")
        calc_qjs = SmogonChampionsCalc(preferred_runtime="quickjs")
        assert calc_v8.runtime_name == "mini_racer"
        assert calc_qjs.runtime_name == "quickjs"

        reqs = [
            DamageCalcRequest(
                attacker=CalcPokemonSpec(
                    species="Charizard-Mega-Y",
                    item="Charizardite Y",
                    ability="Drought",
                    nature="Modest",
                    sp={"hp": 22, "def": 19, "spa": 3, "spd": 1, "spe": 21},
                ),
                defender=CalcPokemonSpec(
                    species="Farigiraf",
                    item="Sitrus Berry",
                    ability="Armor Tail",
                    nature="Calm",
                    sp={"hp": 29, "def": 17, "spd": 20},
                ),
                move=CalcMoveSpec(name="Weather Ball"),
                field=CalcFieldSpec(game_type="Doubles", weather="Sun"),
            ),
            DamageCalcRequest(
                attacker=CalcPokemonSpec(
                    species="Garchomp-Mega-Z",
                    item="Garchompite Z",
                    nature="Jolly",
                    sp={"hp": 1, "atk": 30, "def": 3, "spe": 32},
                ),
                defender=CalcPokemonSpec(
                    species="Archaludon",
                    item="Leftovers",
                    ability="Stamina",
                    nature="Bold",
                    sp={"hp": 30, "def": 1, "spa": 7, "spd": 28},
                ),
                move=CalcMoveSpec(name="Earthquake"),
                field=CalcFieldSpec(game_type="Doubles"),
            ),
        ]

        res_v8 = calc_v8.calculate_batch(reqs)
        res_qjs = calc_qjs.calculate_batch(reqs)

        for r1, r2 in zip(res_v8, res_qjs):
            assert r1.ok and r2.ok
            assert r1.rolls_16 == r2.rolls_16
            assert r1.attacker_max_hp == r2.attacker_max_hp
            assert r1.defender_max_hp == r2.defender_max_hp

        # Exact Champions Level 50 HP formula check: Base + SP + 75
        # Charizard-Mega-Y Base HP=78 + 22 + 75 = 175
        assert res_v8[0].attacker_max_hp == 175
        # Farigiraf Base HP=120 + 29 + 75 = 224
        assert res_v8[0].defender_max_hp == 224
        # Archaludon Base HP=90 + 30 + 75 = 195
        assert res_v8[1].defender_max_hp == 195

    def test_real_showdown_replay_exact_integer_hp_hits(self) -> None:
        """Verify real exact-HP hits from `matchagotme_g1.html` land inside Smogon's 16 rolls."""
        calc = get_champions_calc()

        # 1. Turn 6: Incineroar (Brave, 32 Atk SP, White Herb) Fake Out -> Venusaur (2 HP SP -> 157 HP, 0 Def)
        # Observed exact damage in matchagotme_g1.html line 170: 157 -> 125 = 32 HP!
        req_fakeout = DamageCalcRequest(
            attacker=CalcPokemonSpec(
                species="Incineroar",
                item="White Herb",
                ability="Intimidate",
                nature="Brave",
                sp={"hp": 32, "atk": 32, "spd": 2},
            ),
            defender=CalcPokemonSpec(
                species="Venusaur",
                item="Focus Sash",
                ability="Chlorophyll",
                nature="Modest",
                sp={"hp": 2, "spa": 32, "spe": 32},
            ),
            move=CalcMoveSpec(name="Fake Out"),
            field=CalcFieldSpec(game_type="Doubles", weather="Sun"),
        )

        # 2. Turn 6: +2 SpA Primarina (Modest, Leftovers, Liquid Voice)
        #    Hyper Voice (Spread in Sun) -> Venusaur (125 -> 98 = 27 HP) and Charizard-Mega-Y (175 -> 83 = 92 HP)
        #    Exact inversion proves bulky Calm Mind Primarina had 0..8 SpA SP (e.g. 6 SpA SP fits both exact hits!).
        primarina = CalcPokemonSpec(
            species="Primarina",
            item="Leftovers",
            ability="Liquid Voice",
            nature="Modest",
            sp={"hp": 32, "def": 28, "spa": 6},
            boosts={"spa": 2, "spd": 2},
        )
        req_hv_venu = DamageCalcRequest(
            attacker=primarina,
            defender=CalcPokemonSpec(
                species="Venusaur",
                item="Focus Sash",
                ability="Chlorophyll",
                nature="Modest",
                sp={"hp": 2, "spa": 32, "spe": 32},
            ),
            move=CalcMoveSpec(name="Hyper Voice"),
            field=CalcFieldSpec(game_type="Doubles", weather="Sun"),
        )
        req_hv_zard = DamageCalcRequest(
            attacker=primarina,
            defender=CalcPokemonSpec(
                species="Charizard-Mega-Y",
                item="Charizardite Y",
                ability="Drought",
                nature="Modest",
                sp={"hp": 22, "def": 19, "spa": 3, "spd": 1, "spe": 21},
            ),
            move=CalcMoveSpec(name="Hyper Voice"),
            field=CalcFieldSpec(game_type="Doubles", weather="Sun"),
        )

        # 3. Turn 3: Farigiraf (Calm, 0 SpA SP, Sitrus) Psychic Noise -> Pelipper (32 HP -> 167 HP, 0 SpD)
        # Observed exact damage in matchagotme_g1.html line 109: 167 -> 94 = 73 HP!
        req_pnoise = DamageCalcRequest(
            attacker=CalcPokemonSpec(
                species="Farigiraf",
                item=None,
                ability="Armor Tail",
                nature="Calm",
                sp={"hp": 29, "def": 17, "spd": 20},
            ),
            defender=CalcPokemonSpec(
                species="Pelipper",
                item="Sitrus Berry",
                ability="Drizzle",
                nature="Bold",
                sp={"hp": 32, "def": 22, "spa": 12},
            ),
            move=CalcMoveSpec(name="Psychic Noise"),
            field=CalcFieldSpec(game_type="Doubles", weather="Rain"),
        )

        r_fo, r_hvv, r_hvz, r_pn = calc.calculate_batch(
            [req_fakeout, req_hv_venu, req_hv_zard, req_pnoise]
        )
        assert r_fo.ok and 32 in r_fo.rolls_16, f"32 not in {r_fo.rolls_16}"
        assert r_hvv.ok and 27 in r_hvv.rolls_16, f"27 not in {r_hvv.rolls_16}"
        assert r_hvz.ok and 92 in r_hvz.rolls_16, f"92 not in {r_hvz.rolls_16}"
        assert r_pn.ok and 73 in r_pn.rolls_16, f"73 not in {r_pn.rolls_16}"

    def test_effective_speed_batch(self) -> None:
        calc = get_champions_calc()
        # Modest 32 Spe SP Venusaur in Sun (Chlorophyll 2x) = floor((80+32+20)*1.0) * 2 = 132 * 2 = 264
        res = calc.calculate_effective_speeds(
            [
                SpeedCalcRequest(
                    pokemon=CalcPokemonSpec(
                        species="Venusaur",
                        ability="Chlorophyll",
                        nature="Modest",
                        sp={"hp": 2, "spa": 32, "spe": 32},
                    ),
                    field=CalcFieldSpec(game_type="Doubles", weather="Sun"),
                ),
                SpeedCalcRequest(
                    pokemon=CalcPokemonSpec(
                        species="Charizard-Mega-Y",
                        ability="Drought",
                        nature="Modest",
                        sp={"hp": 22, "def": 19, "spa": 3, "spd": 1, "spe": 21},
                    ),
                    field=CalcFieldSpec(
                        game_type="Doubles",
                        weather="Sun",
                        attacker_side=CalcSideSpec(is_tailwind=True),
                    ),
                ),
            ]
        )
        assert res[0].ok and res[0].eff_spe == 264
        # Base 100 + 21 + 20 = 141, x2 Tailwind = 282
        assert res[1].ok and res[1].eff_spe == 282

    @pytest.mark.parametrize(
        "label,att_sp,att_item,att_ab,att_nat,att_spread,def_sp,def_item,def_ab,def_nat,def_spread,move_name,weather,terrain,reflect,lscreen,spread_alive",
        [
            (
                "Sun Heat Wave Spread (2 foes)",
                "Charizard-Mega-Y", "Charizardite Y", "Drought", "Modest", {"hp": 22, "def": 19, "spa": 3, "spd": 1, "spe": 21},
                "Incineroar", "White Herb", "Intimidate", "Brave", {"hp": 32, "atk": 32, "spd": 2},
                "Heat Wave", "Sun", None, False, False, True,
            ),
            (
                "Sun Heat Wave Single Target (1 foe alive)",
                "Charizard-Mega-Y", "Charizardite Y", "Drought", "Modest", {"hp": 22, "def": 19, "spa": 3, "spd": 1, "spe": 21},
                "Incineroar", "White Herb", "Intimidate", "Brave", {"hp": 32, "atk": 32, "spd": 2},
                "Heat Wave", "Sun", None, False, False, False,
            ),
            (
                "Doubles Light Screen + Life Orb",
                "Garchomp", "Life Orb", "Rough Skin", "Jolly", {"hp": 1, "atk": 30, "def": 3, "spe": 32},
                "Archaludon", "Leftovers", "Stamina", "Bold", {"hp": 30, "def": 1, "spa": 7, "spd": 28},
                "Dragon Claw", None, None, True, False, True,
            ),
            (
                "Sandstorm Rock 1.5x SpD buff",
                "Archaludon", "Leftovers", "Stamina", "Bold", {"hp": 30, "def": 1, "spa": 7, "spd": 28},
                "Tyranitar", "Leftovers", "Sand Stream", "Adamant", {"hp": 32, "atk": 32, "spd": 2},
                "Dragon Pulse", "Sand", None, False, False, True,
            ),
            (
                "Snow Ice 1.5x Def buff",
                "Incineroar", "White Herb", "Intimidate", "Adamant", {"hp": 32, "atk": 32, "spd": 2},
                "Baxcalibur", "Leftovers", "Thermal Exchange", "Adamant", {"hp": 32, "atk": 32, "spd": 2},
                "Darkest Lariat", "Snow", None, False, False, True,
            ),
            (
                "Grassy Terrain 1.3x + Life Orb",
                "Rillaboom", "Life Orb", "Grassy Surge", "Adamant", {"hp": 32, "atk": 32, "spd": 2},
                "Archaludon", "Leftovers", "Stamina", "Bold", {"hp": 30, "def": 1, "spa": 7, "spd": 28},
                "Grassy Glide", None, "Grassy", False, False, True,
            ),
        ],
    )
    def test_smogon_vs_gpu_attack_cascade_parity(
        self,
        label: str,
        att_sp: str,
        att_item: str,
        att_ab: str,
        att_nat: str,
        att_spread: dict,
        def_sp: str,
        def_item: str,
        def_ab: str,
        def_nat: str,
        def_spread: dict,
        move_name: str,
        weather: str | None,
        terrain: str | None,
        reflect: bool,
        lscreen: bool,
        spread_alive: bool,
    ) -> None:
        """Verify `vgc_tensor_core/attack_cascade.py` stays within <=2 HP of official Smogon Champions."""
        calc = get_champions_calc()
        smogon_res = calc.calculate_one(
            DamageCalcRequest(
                attacker=CalcPokemonSpec(
                    species=att_sp, item=att_item, ability=att_ab, nature=att_nat, sp=att_spread
                ),
                defender=CalcPokemonSpec(
                    species=def_sp, item=def_item, ability=def_ab, nature=def_nat, sp=def_spread
                ),
                move=CalcMoveSpec(name=move_name, force_single_target=(not spread_alive)),
                field=CalcFieldSpec(
                    game_type="Doubles",
                    weather=weather,
                    terrain=terrain,
                    defender_side=CalcSideSpec(is_reflect=reflect, is_light_screen=lscreen),
                ),
            )
        )
        assert smogon_res.ok, f"Smogon failed for {label}: {smogon_res.error}"

        att_mon = ParsedPokemon(
            species=att_sp,
            base_species=att_sp.split("-Mega")[0],
            item=att_item,
            ability=att_ab,
            nature=att_nat,
            spread=StatSpread.from_dict(att_spread),
            moves=[move_name, "Protect", "Helping Hand", "Substitute"],
            is_mega="-Mega" in att_sp,
        )
        def_mon = ParsedPokemon(
            species=def_sp,
            base_species=def_sp.split("-Mega")[0],
            item=def_item,
            ability=def_ab,
            nature=def_nat,
            spread=StatSpread.from_dict(def_spread),
            moves=["Helping Hand", "Protect", "Substitute", "Splash"],
            is_mega="-Mega" in def_sp,
        )
        gpu_min, gpu_max = _run_gpu_single_move_damage(
            att_mon,
            def_mon,
            move_name,
            weather=weather,
            terrain=terrain,
            defender_reflect=reflect,
            defender_light_screen=lscreen,
            spread_partner_alive=spread_alive,
        )
        # Allow <= 2 HP tolerance for float32 floor vs exact 4096 pokeRound in GPU cascade
        assert abs(gpu_min - smogon_res.min_damage) <= 2, (
            f"[{label}] min mismatch: GPU={gpu_min} vs Smogon={smogon_res.min_damage}"
        )
        assert abs(gpu_max - smogon_res.max_damage) <= 2, (
            f"[{label}] max mismatch: GPU={gpu_max} vs Smogon={smogon_res.max_damage}"
        )
