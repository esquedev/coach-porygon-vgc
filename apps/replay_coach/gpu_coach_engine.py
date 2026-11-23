# -*- coding: utf-8 -*-
"""Persistent GPU Tensor Core Replay Coach Engine (RTX 3060 CUDA + DuckDB).

Compiles each `TurnSnapshot` from `protocol_parser.py` into exact `CompiledBattleState`
tensors, evaluates the `[B1 x B2]` discrete-RNG payoff matrix on GPU (`VgcTensorStateMachine`),
runs Strict & Weak IEDS (`run_iterated_dominance_elimination`), Zero-Sum Nash
(`solve_zero_sum_nash`), Logit QRE (`solve_quantal_response`), and feeds the witnesses
into `commentary_engine.py` (100% deterministic, zero LLM calls).
"""
from __future__ import annotations

import copy
import hashlib
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch

from engine.solver.game_theory import (
    decode_joint_action,
    run_iterated_dominance_elimination,
    solve_quantal_response,
    solve_zero_sum_nash,
)
from engine.state.state_compiler import TurnStateCompiler
from engine.terminology import export_glossary_payload
from engine.vgc_tensor_core import (
    FieldIdx,
    MonIdx,
    MoveIdx,
    ShowdownTensorCompiler,
    VgcTensorStateMachine,
)
from engine.vgc_tensor_core.compiler import CHOICE_SWITCH_BENCH1, CHOICE_SWITCH_BENCH2

from .commentary_engine import (
    generate_all_commentary_variants,
    generate_deterministic_commentary,
)
from .ots_db import OTSRosterDatabase
from .protocol_parser import ParsedReplay, RecordedSlotAction, TurnSnapshot


def _norm_id(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


class GPUReplayCoachEngine:
    """Warm singleton GPU solver wrapping `VgcTensorStateMachine` and DuckDB OTS DB."""

    def __init__(self, ots_db: OTSRosterDatabase) -> None:
        self.ots_db = ots_db
        self._gpu_lock = threading.Lock()
        self.sc = TurnStateCompiler()
        self.tc = ShowdownTensorCompiler(registry=self.sc.registry, backend="torch")
        self.sm = VgcTensorStateMachine(backend="torch", risk_aversion_lambda=0.25)
        self.device_name = (
            torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU (PyTorch)"
        )

    def _compile_snapshot(self, snap: TurnSnapshot) -> Any:
        """Compile a `TurnSnapshot` into exact GPU tensors preserving exact timers & volatiles."""
        battle = snap.battle_state
        t1_act_norm = {_norm_id(s) for s in battle.trainer_1.active_slots}
        t2_act_norm = {_norm_id(s) for s in battle.trainer_2.active_slots}

        t1_bench = [
            s for s in battle.trainer_1.battle_roster if _norm_id(s) not in t1_act_norm
        ]
        t2_bench = [
            s for s in battle.trainer_2.battle_roster if _norm_id(s) not in t2_act_norm
        ]
        # Pad bench from preview if fewer than 4 mons were revealed in an incomplete replay
        for s in battle.trainer_1.team_preview:
            if len(t1_bench) >= 2:
                break
            if _norm_id(s) not in t1_act_norm and _norm_id(s) not in {_norm_id(x) for x in t1_bench}:
                t1_bench.append(s)
        for s in battle.trainer_2.team_preview:
            if len(t2_bench) >= 2:
                break
            if _norm_id(s) not in t2_act_norm and _norm_id(s) not in {_norm_id(x) for x in t2_bench}:
                t2_bench.append(s)

        ts = self.sc.compile_turn_state(
            battle,
            run_inference=False,
            trainer_1_bench_override=t1_bench[:2],
            trainer_2_bench_override=t2_bench[:2],
        )
        comp = self.tc.compile_turn_state(ts)
        F = comp.field_tensor.clone()
        P = comp.roster_tensor.clone()

        # Apply exact weather, terrain, Trick Room, and Tailwind timers from protocol snapshot
        w_map = {None: 0, "Sun": 1, "Rain": 2, "Sand": 3, "Snow": 4}
        t_map = {None: 0, "Electric": 1, "Grassy": 2, "Misty": 3, "Psychic": 4}
        F[FieldIdx.WEATHER_START:FieldIdx.WEATHER_END] = 0.0
        F[FieldIdx.WEATHER_START + w_map.get(snap.weather, 0)] = 1.0
        F[FieldIdx.WEATHER_TURNS] = float(snap.weather_turns)

        F[FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END] = 0.0
        F[FieldIdx.TERRAIN_START + t_map.get(snap.terrain, 0)] = 1.0
        F[FieldIdx.TERRAIN_TURNS] = float(snap.terrain_turns)
        F[FieldIdx.TRICK_ROOM_TURNS] = float(snap.trick_room_turns)
        F[FieldIdx.TRAINER_1_TAILWIND_TURNS] = float(snap.trainer_1_tailwind_turns)
        F[FieldIdx.TRAINER_2_TAILWIND_TURNS] = float(snap.trainer_2_tailwind_turns)
        if any(m.is_mega for m in battle.trainer_1.pokemon_sets.values()):
            F[FieldIdx.TRAINER_1_MEGA_USED] = 1.0
        if any(m.is_mega for m in battle.trainer_2.pokemon_sets.values()):
            F[FieldIdx.TRAINER_2_MEGA_USED] = 1.0

        # Enforce exact HP, active_turns, protect_counter, boosts, and consumed items
        for tid, slots in (("trainer_1", (0, 1, 2, 3)), ("trainer_2", (4, 5, 6, 7))):
            team = battle.trainer_1 if tid == "trainer_1" else battle.trainer_2
            for s_idx in slots:
                sp_name = comp.slot_species[s_idx]
                mon = team.get_pokemon(sp_name)
                if mon is None:
                    continue
                hp_max = float(P[s_idx, MonIdx.HP_MAX].item())
                if mon.fainted or mon.current_hp_pct <= 0.0:
                    P[s_idx, MonIdx.HP_CUR] = 0.0
                    P[s_idx, MonIdx.ALIVE_FLAG] = 0.0
                else:
                    exact_hp = max(1.0, round(hp_max * (mon.current_hp_pct / 100.0)))
                    P[s_idx, MonIdx.HP_CUR] = min(hp_max, exact_hp)
                    P[s_idx, MonIdx.ALIVE_FLAG] = 1.0
                P[s_idx, MonIdx.ACTIVE_TURNS] = float(mon.active_turns)
                P[s_idx, MonIdx.PROTECT_COUNTER] = 1.0 if mon.used_protect_last_turn else 0.0
                if mon.item is None:
                    P[s_idx, MonIdx.ITEM_ACTIVE] = 0.0
                    P[s_idx, MonIdx.ITEM_ID] = 0.0
                P[s_idx, MonIdx.BOOST_ATK] = float(mon.boosts.get("atk", 0))
                P[s_idx, MonIdx.BOOST_DEF] = float(mon.boosts.get("def", 0))
                P[s_idx, MonIdx.BOOST_SPA] = float(mon.boosts.get("spa", 0))
                P[s_idx, MonIdx.BOOST_SPD] = float(mon.boosts.get("spd", 0))
                P[s_idx, MonIdx.BOOST_SPE] = float(mon.boosts.get("spe", 0))

        comp = copy.copy(comp)
        comp.field_tensor = F
        comp.roster_tensor = P
        return comp

    def _map_recorded_action_to_choice(
        self,
        comp: Any,
        trainer_id: str,
        is_slot_a: bool,
        rec: Optional[RecordedSlotAction],
        fallback_choice: int = 0,
    ) -> Tuple[int, bool]:
        """Map a recorded replay slot action (`RecordedSlotAction`) into tensor choice `0..25`."""
        if rec is None or rec.kind in ("none", "fainted"):
            return fallback_choice, False
        if rec.kind == "flinched":
            return fallback_choice, True

        actor_slot = (0 if is_slot_a else 1) if trainer_id == "trainer_1" else (4 if is_slot_a else 5)
        b1_slot = 2 if trainer_id == "trainer_1" else 6
        b2_slot = 3 if trainer_id == "trainer_1" else 7

        if rec.kind == "switch" and rec.switch_to_species:
            tgt = _norm_id(rec.switch_to_species)
            if _norm_id(comp.slot_species[b1_slot]) == tgt or tgt in _norm_id(comp.slot_species[b1_slot]):
                return CHOICE_SWITCH_BENCH1, False
            if _norm_id(comp.slot_species[b2_slot]) == tgt or tgt in _norm_id(comp.slot_species[b2_slot]):
                return CHOICE_SWITCH_BENCH2, False
            return CHOICE_SWITCH_BENCH1, False

        if rec.kind == "move" and rec.move_name:
            mv_norm = _norm_id(rec.move_name)
            mv_idx = 0
            for idx, m_name in enumerate(comp.slot_move_names[actor_slot]):
                if _norm_id(m_name) == mv_norm:
                    mv_idx = idx
                    break
            # Determine target bucket: 0=Opp A, 1=Opp B, 2=Ally Partner
            tgt_bucket = 0
            if rec.target_trainer == trainer_id:
                tgt_bucket = 2
            elif rec.target_slot_letter == "b":
                tgt_bucket = 1
            else:
                tgt_bucket = 0

            # Self / Field / Spread moves are canonicalized to bucket 0 by LogicalConstraintEngine
            c_base = tgt_bucket * 4 + mv_idx
            c_final = (12 + c_base) if rec.used_mega else c_base
            # Verify canonical decoded match if spread/self/ally_side
            return int(c_final), False

        return fallback_choice, False

    def _canonicalize_pair_against_pruned(
        self,
        comp: Any,
        trainer_id: str,
        pair: Tuple[int, int],
        pruned_np: np.ndarray,
    ) -> Tuple[int, int]:
        """Match a decoded move choice to its canonical bucket in `pruned_np` (e.g., Protect bucket 0)."""
        existing = {(int(r[0]), int(r[1])) for r in pruned_np}
        if pair in existing:
            return pair
        target_desc = decode_joint_action(comp, trainer_id, pair)
        for r in pruned_np:
            cand = (int(r[0]), int(r[1]))
            if decode_joint_action(comp, trainer_id, cand) == target_desc:
                return cand
        return pair

    @staticmethod
    def _is_non_protect_non_switch_choice(comp: Any, slot_idx: int, choice_val: int) -> bool:
        """Return True if `choice_val` is an active move (not Switch and not Protect/Guard)."""
        if choice_val >= CHOICE_SWITCH_BENCH1:
            return False
        m_idx = (choice_val % 12) % 4
        m_vec = comp.moves_tensor[slot_idx, m_idx]
        prot_val = float(m_vec[MoveIdx.PROTECT_TYPE].item() if hasattr(m_vec[MoveIdx.PROTECT_TYPE], "item") else m_vec[MoveIdx.PROTECT_TYPE])
        return prot_val <= 0.5

    def analyze_turn(
        self,
        replay: ParsedReplay,
        turn_number: int,
        min_prior: float = 0.0,
        num_mc: int = 128,
        force_recompute: bool = False,
    ) -> Dict[str, Any]:
        """Run full GPU Tensor Core IEDS + Nash + QRE + Zero-AI Commentary for one turn."""
        # min_prior is permanently locked to 0.0 (strictly mathematical pruner, zero heuristics)
        min_prior = 0.0
        snap = next((t for t in replay.turns if t.turn_number == turn_number), None)
        if snap is None:
            raise ValueError(f"Turn {turn_number} not found in replay {replay.replay_id}")

        # Build deterministic cache key from replay_id, spreads, turn, and solver settings
        spread_sig = hashlib.sha1(
            (
                replay.replay_id
                + f"|v2|t={turn_number}|mp={min_prior:.2f}|k={num_mc}|pov={replay.trainer_1_name}|"
                + str(
                    [
                        (m.species, m.spread.to_dict(), m.item, m.moves)
                        for m in list(snap.battle_state.trainer_1.pokemon_sets.values())
                        + list(snap.battle_state.trainer_2.pokemon_sets.values())
                    ]
                )
            ).encode("utf-8")
        ).hexdigest()[:20]

        if not force_recompute:
            cached = self.ots_db.get_cached_turn(spread_sig)
            if cached is not None:
                cached["from_cache"] = True
                return cached

        t0 = time.time()
        with self._gpu_lock:
            comp = self._compile_snapshot(snap)
            m1 = self.sm.logic_engine.prune_side_26x26_tensor_actions(
                comp, "trainer_1", min_prior_threshold=0.0
            )
            m2 = self.sm.logic_engine.prune_side_26x26_tensor_actions(
                comp, "trainer_2", min_prior_threshold=0.0
            )
            c1_np = m1.pruned_choices.detach().cpu().numpy()
            c2_np = m2.pruned_choices.detach().cpu().numpy()

            fb1_a = int(c1_np[0, 0]) if len(c1_np) else 0
            fb1_b = int(c1_np[0, 1]) if len(c1_np) else 0
            fb2_a = int(c2_np[0, 0]) if len(c2_np) else 0
            fb2_b = int(c2_np[0, 1]) if len(c2_np) else 0

            a1_c, fl1_a = self._map_recorded_action_to_choice(
                comp, "trainer_1", True, snap.trainer_1_slot_a_action, fb1_a
            )
            b1_c, fl1_b = self._map_recorded_action_to_choice(
                comp, "trainer_1", False, snap.trainer_1_slot_b_action, fb1_b
            )
            a2_c, fl2_a = self._map_recorded_action_to_choice(
                comp, "trainer_2", True, snap.trainer_2_slot_a_action, fb2_a
            )
            b2_c, fl2_b = self._map_recorded_action_to_choice(
                comp, "trainer_2", False, snap.trainer_2_slot_b_action, fb2_b
            )

            actual_t1 = self._canonicalize_pair_against_pruned(comp, "trainer_1", (a1_c, b1_c), c1_np)
            actual_t2 = self._canonicalize_pair_against_pruned(comp, "trainer_2", (a2_c, b2_c), c2_np)

            # Force-include actual played pairs so they are NEVER silently pruned
            if actual_t1 not in {(int(r[0]), int(r[1])) for r in c1_np}:
                c1_np = np.vstack([c1_np, np.array([[actual_t1[0], actual_t1[1]]], dtype=np.int64)])
            if actual_t2 not in {(int(r[0]), int(r[1])) for r in c2_np}:
                c2_np = np.vstack([c2_np, np.array([[actual_t2[0], actual_t2[1]]], dtype=np.int64)])

            B1, B2 = c1_np.shape[0], c2_np.shape[0]
            t1_t = torch.tensor(c1_np, dtype=torch.long, device=self.sm.device)
            t2_t = torch.tensor(c2_np, dtype=torch.long, device=self.sm.device)

            with torch.inference_mode():
                # Uses automatic 2D Tiling over (B1, B2) in VgcTensorStateMachine.step()
                res = self.sm.step(
                    comp.field_tensor,
                    comp.roster_tensor,
                    comp.moves_tensor,
                    t1_t,
                    t2_t,
                    num_mc_samples=num_mc,
                    rng_seed=202600 + turn_number * 1009,
                )
                U_risk = res.stats.risk_adjusted_utility.detach().cpu().numpy().astype(np.float64)
                U_mean = res.stats.mean_utility.detach().cpu().numpy().astype(np.float64)
                U_cvar = res.stats.cvar_10_utility.detach().cpu().numpy().astype(np.float64)
                U_win = res.stats.win_turn_prob.detach().cpu().numpy().astype(np.float64)

        idx_act1 = next(i for i, r in enumerate(c1_np) if (int(r[0]), int(r[1])) == actual_t1)
        idx_act2 = next(j for j, r in enumerate(c2_np) if (int(r[0]), int(r[1])) == actual_t2)

        # Strict & Weak IEDS
        ieds_strict = run_iterated_dominance_elimination(
            U_risk, dominance_Margin_eps=0.0, eliminate_weakly_dominated=False
        )
        ieds_weak = run_iterated_dominance_elimination(
            U_risk, dominance_Margin_eps=0.0, eliminate_weakly_dominated=True
        )

        # Zero-Sum Nash Equilibrium on Strict-IEDS core
        nash_sub = solve_zero_sum_nash(ieds_strict.reduced_payoff_matrix)
        p_nash = np.zeros(B1, dtype=np.float64)
        q_nash = np.zeros(B2, dtype=np.float64)
        p_nash[ieds_strict.trainer_1_surviving_indices] = nash_sub.trainer_1_strategy
        q_nash[ieds_strict.trainer_2_surviving_indices] = nash_sub.trainer_2_strategy

        # Logit QRE (beta=4.0 human behavioral model)
        qre_res = solve_quantal_response(U_risk, rationality_beta=4.0)

        ev_vs_q = U_risk @ q_nash
        mean_vs_q = U_mean @ q_nash
        cvar_vs_q = U_cvar @ q_nash
        win_vs_q = U_win @ q_nash
        min_j_vals = U_risk.min(axis=1)
        min_j_args = U_risk.argmin(axis=1)

        # When a slot of trainer_1 was flinched before acting, infer its best available
        # non-Protect/non-Switch attack paired with the partner's recorded action so the
        # turn is graded with one of the 5 real badges.
        if fl1_a or fl1_b:
            cand_indices = []
            for i_cand in range(B1):
                ca, cb = int(c1_np[i_cand, 0]), int(c1_np[i_cand, 1])
                if not fl1_a and ca != actual_t1[0]:
                    continue
                if not fl1_b and cb != actual_t1[1]:
                    continue
                if fl1_a and not self._is_non_protect_non_switch_choice(comp, 0, ca):
                    continue
                if fl1_b and not self._is_non_protect_non_switch_choice(comp, 1, cb):
                    continue
                cand_indices.append(i_cand)
            if cand_indices:
                idx_act1 = max(cand_indices, key=lambda idx: float(ev_vs_q[idx]))
                actual_t1 = (int(c1_np[idx_act1, 0]), int(c1_np[idx_act1, 1]))

        if fl2_a or fl2_b:
            cand_j = []
            p_dot_u = p_nash @ U_risk
            for j_cand in range(B2):
                ca, cb = int(c2_np[j_cand, 0]), int(c2_np[j_cand, 1])
                if not fl2_a and ca != actual_t2[0]:
                    continue
                if not fl2_b and cb != actual_t2[1]:
                    continue
                if fl2_a and not self._is_non_protect_non_switch_choice(comp, 4, ca):
                    continue
                if fl2_b and not self._is_non_protect_non_switch_choice(comp, 5, cb):
                    continue
                cand_j.append(j_cand)
            if cand_j:
                idx_act2 = min(cand_j, key=lambda jdx: float(p_dot_u[jdx]))
                actual_t2 = (int(c2_np[idx_act2, 0]), int(c2_np[idx_act2, 1]))

        with self._gpu_lock, torch.inference_mode():
            res_act = self.sm.step(
                comp.field_tensor,
                comp.roster_tensor,
                comp.moves_tensor,
                torch.tensor([[actual_t1[0], actual_t1[1]]], dtype=torch.long, device=self.sm.device),
                torch.tensor([[actual_t2[0], actual_t2[1]]], dtype=torch.long, device=self.sm.device),
                num_mc_samples=max(256, num_mc),
                rng_seed=909090 + turn_number * 131,
            )
            faint_act = res_act.faint_prob[0, 0].detach().cpu().numpy()

        strict_surv_set = set(int(x) for x in ieds_strict.trainer_1_surviving_indices)
        weak_surv_set = set(int(x) for x in ieds_weak.trainer_1_surviving_indices)
        strict_rec_map = {r.eliminated_idx: r for r in ieds_strict.eliminated_trainer_1}
        weak_rec_map = {r.eliminated_idx: r for r in ieds_weak.eliminated_trainer_1}

        def format_dom(rec_map: Dict[int, Any], row_i: int) -> Optional[Dict[str, Any]]:
            rec = rec_map.get(row_i)
            if rec is None:
                return None
            dom_pair = [int(c1_np[rec.dominated_by_idx, 0]), int(c1_np[rec.dominated_by_idx, 1])]
            return {
                "round": int(rec.round_eliminated),
                "choice_pair": dom_pair,
                "desc": decode_joint_action(comp, "trainer_1", dom_pair),
                "worst_margin": round(float(rec.worst_margin), 4),
                "mean_margin": round(float(rec.mean_margin), 4),
            }

        def build_action_row(row_i: int) -> Dict[str, Any]:
            cp = [int(c1_np[row_i, 0]), int(c1_np[row_i, 1])]
            wc_j = int(min_j_args[row_i])
            wc_pair = [int(c2_np[wc_j, 0]), int(c2_np[wc_j, 1])]
            return {
                "choice_pair": cp,
                "desc": decode_joint_action(comp, "trainer_1", cp),
                "risk_ev": round(float(ev_vs_q[row_i]), 4),
                "mean_ev": round(float(mean_vs_q[row_i]), 4),
                "cvar10": round(float(cvar_vs_q[row_i]), 4),
                "win_turn_pct": round(float(win_vs_q[row_i] * 100.0), 1),
                "nash_pct": round(float(p_nash[row_i] * 100.0), 1),
                "qre_pct": round(float(qre_res.trainer_1_strategy[row_i] * 100.0), 1),
                "nash_regret": round(float(max(0.0, nash_sub.game_value - ev_vs_q[row_i])), 4),
                "security_floor": round(float(min_j_vals[row_i]), 4),
                "worst_counter_desc": decode_joint_action(comp, "trainer_2", wc_pair),
                "survived_strict_ieds": row_i in strict_surv_set,
                "survived_weak_ieds": row_i in weak_surv_set,
                "strict_dominated_by": format_dom(strict_rec_map, row_i),
                "weak_dominated_by": format_dom(weak_rec_map, row_i),
                "vs_actual_opp_u": round(float(U_risk[row_i, idx_act2]), 4),
                "is_played": row_i == idx_act1,
            }

        sorted_rows = sorted(
            range(B1),
            key=lambda i: (-(1 if p_nash[i] > 1e-4 else 0), -float(p_nash[i]), -float(ev_vs_q[i])),
        )
        top_actions = [build_action_row(i) for i in sorted_rows[:8]]

        best_vs_opp_idx = int(np.argmax(U_risk[:, idx_act2]))
        actual_row = build_action_row(idx_act1)
        actual_row["rank"] = int(sorted_rows.index(idx_act1)) + 1
        actual_row["total_actions"] = int(B1)
        actual_row["opp_actual_desc"] = decode_joint_action(comp, "trainer_2", actual_t2)
        actual_row["oracle_best_desc"] = decode_joint_action(
            comp, "trainer_1", [int(c1_np[best_vs_opp_idx, 0]), int(c1_np[best_vs_opp_idx, 1])]
        )
        actual_row["oracle_best_u"] = round(float(U_risk[best_vs_opp_idx, idx_act2]), 4)
        actual_row["flinched_hidden"] = bool(fl1_a or fl1_b)
        actual_row["num_mc"] = int(max(256, num_mc))
        actual_row["ko_probs_vs_actual_opp"] = {
            comp.slot_species[s]: round(float(faint_act[s] * 100.0), 1)
            for s in (0, 1, 4, 5)
            if comp.slot_species[s] and comp.slot_species[s] != "None"
        }

        # Opponent top Nash strategies
        opp_sorted = sorted(range(B2), key=lambda j: (-float(q_nash[j]), float(U_risk[:, j].max())))[:4]
        opp_top = [
            {
                "choice_pair": [int(c2_np[j, 0]), int(c2_np[j, 1])],
                "desc": decode_joint_action(comp, "trainer_2", [int(c2_np[j, 0]), int(c2_np[j, 1])]),
                "nash_pct": round(float(q_nash[j] * 100.0), 1),
                "qre_pct": round(float(qre_res.trainer_2_strategy[j] * 100.0), 1),
                "is_played": j == idx_act2,
            }
            for j in opp_sorted
        ]

        # Build roster state summary for UI display
        P_np = comp.roster_tensor.detach().cpu().numpy()
        board_slots: Dict[str, List[Dict[str, Any]]] = {"trainer_1": [], "trainer_2": []}
        for tid, slots in (("trainer_1", (0, 1, 2, 3)), ("trainer_2", (4, 5, 6, 7))):
            for pos, s in enumerate(slots):
                hp_c = float(P_np[s, MonIdx.HP_CUR])
                hp_m = max(1.0, float(P_np[s, MonIdx.HP_MAX]))
                board_slots[tid].append(
                    {
                        "species": comp.slot_species[s],
                        "role": "Active" if pos < 2 else "Bench",
                        "hp_cur": int(round(hp_c)),
                        "hp_max": int(round(hp_m)),
                        "hp_pct": round(hp_c / hp_m * 100.0, 1),
                        "atk_boost": int(round(float(P_np[s, MonIdx.BOOST_ATK]))),
                        "spa_boost": int(round(float(P_np[s, MonIdx.BOOST_SPA]))),
                        "spd_boost": int(round(float(P_np[s, MonIdx.BOOST_SPD]))),
                        "spe": int(round(float(P_np[s, MonIdx.STAT_SPE]))),
                        "protect_prev": bool(P_np[s, MonIdx.PROTECT_COUNTER] > 0.5),
                    }
                )

        ieds_summary = {
            "t1_total": int(B1),
            "t1_strict": int(ieds_strict.num_trainer_1_surviving),
            "t1_strict_elim": int(len(ieds_strict.eliminated_trainer_1)),
            "t1_weak": int(ieds_weak.num_trainer_1_surviving),
            "t1_weak_elim": int(len(ieds_weak.eliminated_trainer_1)),
            "t2_total": int(B2),
            "t2_strict": int(ieds_strict.num_trainer_2_surviving),
            "t2_weak": int(ieds_weak.num_trainer_2_surviving),
            "strict_rounds": int(ieds_strict.rounds_executed),
            "weak_rounds": int(ieds_weak.rounds_executed),
            "sample_eliminations": [
                {
                    "eliminated": decode_joint_action(
                        comp, "trainer_1", [int(c1_np[r.eliminated_idx, 0]), int(c1_np[r.eliminated_idx, 1])]
                    ),
                    "dominated_by": decode_joint_action(
                        comp, "trainer_1", [int(c1_np[r.dominated_by_idx, 0]), int(c1_np[r.dominated_by_idx, 1])]
                    ),
                    "round": int(r.round_eliminated),
                    "worst_margin": round(float(r.worst_margin), 3),
                    "mean_margin": round(float(r.mean_margin), 3),
                }
                for r in ieds_strict.eliminated_trainer_1[:10]
            ],
        }

        events_dict = {
            "crits": snap.events.crits,
            "misses": snap.events.misses,
            "flinches": snap.events.flinches,
            "protects": snap.events.protects,
            "faints": snap.events.faints,
            "megas": snap.events.megas,
            "weather_changes": snap.events.weather_changes,
        }
        field_context = {
            "weather": snap.weather,
            "weather_turns": snap.weather_turns,
            "terrain": snap.terrain,
            "terrain_turns": snap.terrain_turns,
            "trick_room_turns": snap.trick_room_turns,
            "t1_tailwind": snap.trainer_1_tailwind_turns,
            "t2_tailwind": snap.trainer_2_tailwind_turns,
        }

        commentary_variants = generate_all_commentary_variants(
            turn_number=turn_number,
            actual_action=actual_row,
            top_actions=top_actions,
            nash_value=float(nash_sub.game_value),
            ieds_summary=ieds_summary,
            events=events_dict,
            field_context=field_context,
        )
        commentary = commentary_variants["es_vgc"]

        elapsed_s = round(time.time() - t0, 2)
        payload = {
            "turn": turn_number,
            "elapsed_s": elapsed_s,
            "from_cache": False,
            "device": self.device_name,
            "matrix_shape": [int(B1), int(B2)],
            "total_timelines": int(B1 * B2 * num_mc),
            "nash_value": round(float(nash_sub.game_value), 4),
            "qre_value": round(float(qre_res.expected_value), 4),
            "maximin": round(float(nash_sub.pure_maximin_value), 4),
            "minimax": round(float(nash_sub.pure_minimax_value), 4),
            "solver_used": nash_sub.solver_used,
            "exploitability_gap": round(float(nash_sub.exploitability_gap), 6),
            "field": field_context,
            "board": board_slots,
            "ieds": ieds_summary,
            "actual_action": actual_row,
            "top_actions": top_actions,
            "opp_top_actions": opp_top,
            "events": events_dict,
            "commentary": commentary,
            "commentary_variants": commentary_variants,
            "terminology": export_glossary_payload(),
        }
        self.ots_db.put_cached_turn(spread_sig, replay.replay_id, turn_number, payload)
        return payload
