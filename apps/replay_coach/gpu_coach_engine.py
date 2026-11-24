# -*- coding: utf-8 -*-
"""Persistent Tensor Core Replay Coach Engine (PyTorch CUDA / CPU + DuckDB).

Compiles each `TurnSnapshot` from `protocol_parser.py` into exact `CompiledBattleState`
tensors, evaluates the `[Strats_1 x Strats_2]` discrete-RNG payoff matrix on the best
available PyTorch accelerator (CUDA GPU or multi-core CPU via `VgcTensorStateMachine`),
runs Strict & Weak IEDS (`run_iterated_dominance_elimination`), Zero-Sum Nash
(`solve_zero_sum_nash`), Logit QRE (`solve_quantal_response`), and feeds the witnesses
into `commentary_engine.py` (100% deterministic, zero LLM calls).
"""
from __future__ import annotations

import copy
import math
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import torch

from engine.solver.game_theory import (
    decode_joint_action,
    run_iterated_dominance_elimination,
    solve_quantal_response,
    solve_zero_sum_nash,
)
from engine.solver.two_ply_lookahead import evaluate_two_ply_on_ieds_core
from engine.state.state_compiler import TurnStateCompiler
from engine.terminology import export_glossary_payload
from engine.vgc_tensor_core import (
    FieldIdx,
    MonIdx,
    MoveIdx,
    ShowdownTensorCompiler,
    VgcTensorStateMachine,
)
from engine.vgc_tensor_core.state_machine import AnalysisCancelledError
from engine.vgc_tensor_core.compiler import CHOICE_SWITCH_BENCH1, CHOICE_SWITCH_BENCH2

from .commentary_engine import (
    _classify_verdict_key,
    generate_all_commentary_variants,
)
from .ots_db import OTSRosterDatabase, resolve_sprite_urls
from .protocol_parser import ParsedReplay, RecordedSlotAction, TurnSnapshot


def _norm_id(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


class GPUReplayCoachEngine:
    """Warm singleton Tensor Core solver wrapping `VgcTensorStateMachine` (CUDA GPU or CPU) and DuckDB OTS DB."""

    def __init__(self, ots_db: OTSRosterDatabase, device: Optional[str] = None) -> None:
        self.ots_db = ots_db
        self._gpu_lock = threading.Lock()
        self.sc = TurnStateCompiler()

        req = (device or "auto").strip().lower()
        if req == "cpu":
            resolved_dev = torch.device("cpu")
        elif req.startswith("cuda") and torch.cuda.is_available():
            resolved_dev = torch.device(req if ":" in req else "cuda:0")
        else:
            resolved_dev = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")

        self.sm = VgcTensorStateMachine(backend="torch", device=resolved_dev, risk_aversion_lambda=0.25)
        # Sync device if BilinearLookupTables gracefully fell back from CUDA OOM to CPU
        actual_dev = self.sm.tables.device if hasattr(self.sm.tables, "device") else resolved_dev
        if isinstance(actual_dev, torch.device):
            self.sm.device = actual_dev
            resolved_dev = actual_dev
        self.device_type: str = resolved_dev.type
        self.tc = ShowdownTensorCompiler(registry=self.sc.registry, backend="torch", device=resolved_dev)
        self.device_name = (
            torch.cuda.get_device_name(resolved_dev)
            if resolved_dev.type == "cuda"
            else "CPU (PyTorch)"
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
                P[s_idx, MonIdx.MUST_RECHARGE] = 1.0 if getattr(mon, "must_recharge", False) else 0.0
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
        if rec.kind == "recharge":
            return 0, False
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
        enable_two_ply: bool = False,
        log_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """Run full Tensor Core IEDS + Nash + QRE + Zero-AI Commentary for one turn."""
        if cancel_event is not None and cancel_event.is_set():
            raise AnalysisCancelledError("Analysis cancelled before turn start.")

        # min_prior is permanently locked to 0.0 (strictly mathematical pruner, zero heuristics)
        min_prior = 0.0
        snap = next((t for t in replay.turns if t.turn_number == turn_number), None)
        if snap is None:
            raise ValueError(f"Turn {turn_number} not found in replay {replay.replay_id}")

        turn_logs: List[Dict[str, Any]] = []

        def _emit_log(
            phase: str,
            es_vgc: str,
            en_vgc: str,
            es_sci: str,
            en_sci: str,
            in_place: bool = False,
            extra: Optional[Dict[str, Any]] = None,
        ) -> None:
            entry: Dict[str, Any] = {
                "turn": int(turn_number),
                "phase": phase,
                "in_place": bool(in_place),
                "messages": {
                    "es_vgc": es_vgc,
                    "en_vgc": en_vgc,
                    "es_scientific": es_sci,
                    "en_scientific": en_sci,
                },
            }
            if extra:
                entry.update(extra)
            if not in_place:
                turn_logs.append(entry)
            if log_cb is not None:
                try:
                    log_cb(entry)
                except Exception:
                    pass

        # Always execute live Tensor Core computation (no stale turn-result caching)
        t0 = time.time()
        with self._gpu_lock:
            if cancel_event is not None and cancel_event.is_set():
                raise AnalysisCancelledError("Analysis cancelled while acquiring compute lock.")
            t_comp0 = time.perf_counter()
            comp = self._compile_snapshot(snap)
            t_comp_ms = (time.perf_counter() - t_comp0) * 1000.0
            t1_leads = f"{comp.slot_species[0]} + {comp.slot_species[1]}"
            t2_leads = f"{comp.slot_species[4]} + {comp.slot_species[5]}"
            _emit_log(
                "COMPILE",
                f"Turno {turn_number}: Tablero y equipos 66-SP preparados ({t1_leads} vs. {t2_leads}) en {t_comp_ms:.0f}ms",
                f"Turn {turn_number}: Board & 66-SP teams compiled ({t1_leads} vs. {t2_leads}) in {t_comp_ms:.0f}ms",
                f"Turno {turn_number}: Tensores F[24], P[8,87], M[8,4,59] compilados ({t1_leads} vs. {t2_leads}) en {t_comp_ms:.1f}ms",
                f"Turn {turn_number}: Compiled tensors F[24], P[8,87], M[8,4,59] ({t1_leads} vs. {t2_leads}) in {t_comp_ms:.1f}ms",
            )

            t_pr0 = time.perf_counter()
            m1 = self.sm.logic_engine.prune_side_26x26_tensor_actions(
                comp, "trainer_1", min_prior_threshold=0.0
            )
            m2 = self.sm.logic_engine.prune_side_26x26_tensor_actions(
                comp, "trainer_2", min_prior_threshold=0.0
            )
            t_pr_ms = (time.perf_counter() - t_pr0) * 1000.0
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
            tot_cells = B1 * B2
            tot_timelines = tot_cells * num_mc
            _emit_log(
                "PRUNE",
                f"Jugadas legales: {B1} opciones tuyas × {B2} del rival = {tot_cells:,} cruces ({t_pr_ms:.0f}ms)",
                f"Legal plays: {B1} your options × {B2} rival options = {tot_cells:,} matchups ({t_pr_ms:.0f}ms)",
                f"26×26 Mechanical Pruner (min_prior=0.0): Strats_1={B1} × Strats_2={B2} ({tot_cells:,} cells, {t_pr_ms:.1f}ms)",
                f"26×26 Mechanical Pruner (min_prior=0.0): Strats_1={B1} × Strats_2={B2} ({tot_cells:,} cells, {t_pr_ms:.1f}ms)",
            )

            t1_t = torch.tensor(c1_np, dtype=torch.long, device=self.sm.device)
            t2_t = torch.tensor(c2_np, dtype=torch.long, device=self.sm.device)
            t_sim_start = time.perf_counter()

            def _sm_progress(ev: Dict[str, Any]) -> None:
                ev_type = ev.get("event")
                if ev_type == "tile_progress":
                    ti, tn = ev["tile"], ev["total_tiles"]
                    tr_d, tr_t = ev["trajectories_done"], ev["total_trajectories"]
                    pct = min(100, int(round(100.0 * tr_d / max(1, tr_t))))
                    el = max(0.01, time.perf_counter() - t_sim_start)
                    eta = (el * (tr_t - tr_d) / tr_d) if tr_d > 0 else 0.0
                    eta_str = f" · ETA ~{eta:.1f}s" if (0 < pct < 100 and eta >= 0.5) else ""
                    ck = ev.get("chunk")
                    ck_tot = ev.get("total_chunks")
                    ck_str = f" (lote {ck}/{ck_tot})" if ck and ck_tot and ck_tot > 1 else ""
                    ck_str_en = f" (chunk {ck}/{ck_tot})" if ck and ck_tot and ck_tot > 1 else ""
                    _emit_log(
                        "TILE_PROGRESS",
                        f"Simulando en {self.device_name}: {pct}% · Bloque {ti}/{tn}{ck_str} · {tr_d:,} / {tr_t:,} simulaciones{eta_str}",
                        f"Simulating on {self.device_name}: {pct}% · Tile {ti}/{tn}{ck_str_en} · {tr_d:,} / {tr_t:,} sims{eta_str}",
                        f"2D Tiling ({self.device_name}): {pct}% · Tile {ti}/{tn}{ck_str} · {tr_d:,} / {tr_t:,} MC threads (K={num_mc}){eta_str}",
                        f"2D Tiling ({self.device_name}): {pct}% · Tile {ti}/{tn}{ck_str_en} · {tr_d:,} / {tr_t:,} MC threads (K={num_mc}){eta_str}",
                        in_place=True,
                        extra={
                            "tile": ti,
                            "total_tiles": tn,
                            "pct": pct,
                            "trajectories_done": tr_d,
                            "total_trajectories": tr_t,
                        },
                    )
                elif ev_type == "phases_summary":
                    sw_c = ev["switch_cells"]
                    mg_c = ev["mega_cells"]
                    st_c = ev["speed_tie_cells"]
                    pre_s = ev["pre_attack_s"]
                    att_s = ev["attack_s"]
                    eot_s = ev["eot_s"]
                    tn = ev["total_tiles"]
                    _emit_log(
                        "PHASE_1",
                        f"Fase 1 (Cambios): {sw_c:,} cruces con cambios de banca y habilidades de entrada",
                        f"Phase 1 (Switches): {sw_c:,} matchups with bench swaps & switch-in abilities",
                        f"Phase 1 (Barrier +6): Permutación 8×8 P/M_moves + habilidades de entrada ({sw_c:,} switch cells)",
                        f"Phase 1 (Barrier +6): 8×8 P/M_moves permutation & entry abilities ({sw_c:,} switch cells)",
                    )
                    _emit_log(
                        "PHASE_2",
                        f"Fase 2 (Mega Evolución): recálculo instantáneo de stats y velocidad en {mg_c:,} líneas Mega",
                        f"Phase 2 (Mega Evolution): instant stat & speed recalculation across {mg_c:,} Mega lines",
                        f"Phase 2 (Barrier +5.5): Interpolación Mega in-place y habilidades ({mg_c:,} Mega cells)",
                        f"Phase 2 (Barrier +5.5): In-place Mega stat interpolation & abilities ({mg_c:,} Mega cells)",
                    )
                    _emit_log(
                        "PHASE_3",
                        f"Fase 3 (Velocidad y Prioridad): {st_c:,} empates de velocidad resueltos al 50/50 ({pre_s:.2f}s)",
                        f"Phase 3 (Speed & Priority): {st_c:,} speed ties resolved via 50/50 coinflip ({pre_s:.2f}s)",
                        f"Phase 3 (Priority/Speed Sort): S_eff + SplitMix64 50/50 tie-break ({st_c:,} tied cells, {pre_s:.2f}s)",
                        f"Phase 3 (Priority/Speed Sort): S_eff + SplitMix64 50/50 tie-break ({st_c:,} tied cells, {pre_s:.2f}s)",
                    )
                    _emit_log(
                        "PHASE_4",
                        f"Fase 4 (Ataques y RNG): {tot_timelines:,} simulaciones de daño, críticos y precisión ({tn} bloques) en {att_s:.2f}s",
                        f"Phase 4 (Attacks & RNG): {tot_timelines:,} damage roll, crit & accuracy sims ({tn} tiles) in {att_s:.2f}s",
                        f"Phase 4 (Attack Cascade): {tot_timelines:,} discrete threads [Strats_1,Strats_2,K={num_mc}] ({tn} tiles) in {att_s:.2f}s",
                        f"Phase 4 (Attack Cascade): {tot_timelines:,} discrete threads [Strats_1,Strats_2,K={num_mc}] ({tn} tiles) in {att_s:.2f}s",
                    )
                    _emit_log(
                        "PHASE_5",
                        f"Fase 5 (Fin de Turno): daño residual, clima/terreno y escenario de peor 10% de RNG en {eot_s:.2f}s",
                        f"Phase 5 (End-of-Turn): residual chip, weather/terrain & worst 10% RNG floor in {eot_s:.2f}s",
                        f"Phase 5 (End-of-Turn & CVaR_10): Residuales, U(F_eot,P_eot) y CVaR_10 (λ=0.25) en {eot_s:.2f}s",
                        f"Phase 5 (End-of-Turn & CVaR_10): Residuals, U(F_eot,P_eot) & CVaR_10 (λ=0.25) in {eot_s:.2f}s",
                    )

            with torch.inference_mode():
                try:
                    res = self.sm.step(
                        comp.field_tensor,
                        comp.roster_tensor,
                        comp.moves_tensor,
                        t1_t,
                        t2_t,
                        num_mc_samples=num_mc,
                        rng_seed=202600 + turn_number * 1009,
                        progress_callback=_sm_progress,
                        cancel_event=cancel_event,
                    )
                except torch.cuda.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    res = self.sm.step(
                        comp.field_tensor,
                        comp.roster_tensor,
                        comp.moves_tensor,
                        t1_t,
                        t2_t,
                        num_mc_samples=num_mc,
                        rng_seed=202600 + turn_number * 1009,
                        tile_size=8,
                        max_sim_chunk_size=64,
                        progress_callback=_sm_progress,
                        cancel_event=cancel_event,
                    )
                U_risk = res.stats.risk_adjusted_utility.detach().cpu().numpy().astype(np.float64)
                U_mean = res.stats.mean_utility.detach().cpu().numpy().astype(np.float64)
                U_cvar = res.stats.cvar_10_utility.detach().cpu().numpy().astype(np.float64)
                U_win = res.stats.win_turn_prob.detach().cpu().numpy().astype(np.float64)

        if cancel_event is not None and cancel_event.is_set():
            raise AnalysisCancelledError("Analysis cancelled after simulation step.")

        idx_act1 = next(i for i, r in enumerate(c1_np) if (int(r[0]), int(r[1])) == actual_t1)
        idx_act2 = next(j for j, r in enumerate(c2_np) if (int(r[0]), int(r[1])) == actual_t2)

        # Strict & Weak IEDS
        t_ieds0 = time.perf_counter()
        ieds_strict = run_iterated_dominance_elimination(
            U_risk, dominance_Margin_eps=0.0, eliminate_weakly_dominated=False
        )
        ieds_weak = run_iterated_dominance_elimination(
            U_risk, dominance_Margin_eps=0.0, eliminate_weakly_dominated=True
        )
        t_ieds_s = time.perf_counter() - t_ieds0
        _emit_log(
            "IEDS",
            f"Filtro de jugadas viables: {B1} -> {ieds_strict.num_trainer_1_surviving} tuyas · {B2} -> {ieds_strict.num_trainer_2_surviving} rivales ({t_ieds_s*1000:.0f}ms)",
            f"Viable play filter: {B1} -> {ieds_strict.num_trainer_1_surviving} yours · {B2} -> {ieds_strict.num_trainer_2_surviving} rival ({t_ieds_s*1000:.0f}ms)",
            f"IEDS Dominance: Strict Strats_1 {B1}->{ieds_strict.num_trainer_1_surviving} ({ieds_strict.rounds_executed}r), Weak->{ieds_weak.num_trainer_1_surviving} · Strats_2 {B2}->{ieds_strict.num_trainer_2_surviving} ({t_ieds_s*1000:.1f}ms)",
            f"IEDS Dominance: Strict Strats_1 {B1}->{ieds_strict.num_trainer_1_surviving} ({ieds_strict.rounds_executed}r), Weak->{ieds_weak.num_trainer_1_surviving} · Strats_2 {B2}->{ieds_strict.num_trainer_2_surviving} ({t_ieds_s*1000:.1f}ms)",
        )

        # Optional Selective 2-Ply Lookahead on the Strict-IEDS surviving core
        two_ply_meta: Dict[str, Any] = {"enabled": False, "cells_evaluated": 0, "elapsed_s": 0.0, "gamma": 0.35}
        if enable_two_ply:
            with self._gpu_lock:
                tp_res = evaluate_two_ply_on_ieds_core(
                    sm=self.sm,
                    comp=comp,
                    c1_np=c1_np,
                    c2_np=c2_np,
                    U_risk_ply1=U_risk,
                    surv_1_indices=ieds_strict.trainer_1_surviving_indices,
                    surv_2_indices=ieds_strict.trainer_2_surviving_indices,
                    gamma=0.35,
                    max_core_dim=6,
                    k_ply1_branch=4,
                    k_ply2=16,
                    max_ply2_actions=8,
                    rng_seed=202600 + turn_number * 1009,
                    cancel_event=cancel_event,
                )
            U_risk = tp_res.U_blended
            ieds_strict = run_iterated_dominance_elimination(
                U_risk, dominance_Margin_eps=0.0, eliminate_weakly_dominated=False
            )
            ieds_weak = run_iterated_dominance_elimination(
                U_risk, dominance_Margin_eps=0.0, eliminate_weakly_dominated=True
            )
            two_ply_meta = {
                "enabled": True,
                "cells_evaluated": int(tp_res.cells_evaluated),
                "core_shape": [len(tp_res.eval_t1_indices), len(tp_res.eval_t2_indices)],
                "elapsed_s": round(float(tp_res.elapsed_s), 3),
                "gamma": float(tp_res.gamma),
            }
            _emit_log(
                "PLY_2",
                f"Proyección 2-Ply: {tp_res.cells_evaluated} líneas clave evaluadas al siguiente turno en {tp_res.elapsed_s:.2f}s",
                f"2-Ply Lookahead: {tp_res.cells_evaluated} key matchups projected into Turn+2 in {tp_res.elapsed_s:.2f}s",
                f"Selective 2-Ply Lookahead (γ={tp_res.gamma:.2f}): {len(tp_res.eval_t1_indices)}×{len(tp_res.eval_t2_indices)} IEDS core ({tp_res.cells_evaluated} cells, K2=16) in {tp_res.elapsed_s:.2f}s",
                f"Selective 2-Ply Lookahead (γ={tp_res.gamma:.2f}): {len(tp_res.eval_t1_indices)}×{len(tp_res.eval_t2_indices)} IEDS core ({tp_res.cells_evaluated} cells, K2=16) in {tp_res.elapsed_s:.2f}s",
            )

        # Zero-Sum Nash Equilibrium on Strict-IEDS core
        t_nash0 = time.perf_counter()
        nash_sub = solve_zero_sum_nash(ieds_strict.reduced_payoff_matrix)
        p_nash = np.zeros(B1, dtype=np.float64)
        q_nash = np.zeros(B2, dtype=np.float64)
        p_nash[ieds_strict.trainer_1_surviving_indices] = nash_sub.trainer_1_strategy
        q_nash[ieds_strict.trainer_2_surviving_indices] = nash_sub.trainer_2_strategy

        # Logit QRE (beta=4.0 human behavioral model)
        qre_res = solve_quantal_response(U_risk, rationality_beta=4.0)
        t_nash_s = time.perf_counter() - t_nash0

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

        k_ko = max(256, num_mc)
        with self._gpu_lock, torch.inference_mode():
            res_act = self.sm.step(
                comp.field_tensor,
                comp.roster_tensor,
                comp.moves_tensor,
                torch.tensor([[actual_t1[0], actual_t1[1]]], dtype=torch.long, device=self.sm.device),
                torch.tensor([[actual_t2[0], actual_t2[1]]], dtype=torch.long, device=self.sm.device),
                num_mc_samples=k_ko,
                rng_seed=909090 + turn_number * 131,
                cancel_event=cancel_event,
            )
            faint_act = res_act.faint_prob[0, 0].detach().cpu().numpy()

        _emit_log(
            "NASH_QRE",
            f"Equilibrio del turno calculado: Ventaja = {nash_sub.game_value:+.2f} · Prob. de KO ({k_ko} rolls) en {t_nash_s*1000:.0f}ms",
            f"Turn equilibrium solved: Turn Advantage = {nash_sub.game_value:+.2f} · KO odds ({k_ko} rolls) in {t_nash_s*1000:.0f}ms",
            f"HiGHS Nash LP + Logit QRE (β=4.0): Nash_Eq_Value={nash_sub.game_value:+.4f} (gap={nash_sub.exploitability_gap:.5f}) + {k_ko}-thread KO audit ({t_nash_s*1000:.1f}ms)",
            f"HiGHS Nash LP + Logit QRE (β=4.0): Nash_Eq_Value={nash_sub.game_value:+.4f} (gap={nash_sub.exploitability_gap:.5f}) + {k_ko}-thread KO audit ({t_nash_s*1000:.1f}ms)",
        )

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

        # Build roster state summary for UI display (with local species & item sprite URLs)
        P_np = comp.roster_tensor.detach().cpu().numpy()
        board_slots: Dict[str, List[Dict[str, Any]]] = {"trainer_1": [], "trainer_2": []}
        for tid, slots in (("trainer_1", (0, 1, 2, 3)), ("trainer_2", (4, 5, 6, 7))):
            team_obj = snap.battle_state.trainer_1 if tid == "trainer_1" else snap.battle_state.trainer_2
            for pos, s in enumerate(slots):
                sp_name = comp.slot_species[s]
                mon_obj = team_obj.get_pokemon(sp_name) if sp_name else None
                item_name = mon_obj.item if (mon_obj and P_np[s, MonIdx.ITEM_ACTIVE] > 0.5) else None
                ability_name = mon_obj.ability if mon_obj else None
                sprites = resolve_sprite_urls(sp_name, item_name)
                hp_c = float(P_np[s, MonIdx.HP_CUR])
                hp_m = max(1.0, float(P_np[s, MonIdx.HP_MAX]))
                board_slots[tid].append(
                    {
                        "species": sp_name,
                        "role": "Active" if pos < 2 else "Bench",
                        "item": item_name,
                        "ability": ability_name,
                        "sprite_url": sprites["sprite_url"],
                        "item_sprite_url": sprites["item_sprite_url"],
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
        verdict_key = _classify_verdict_key(
            actual_row.get("strict_dominated_by"),
            actual_row.get("weak_dominated_by"),
            float(actual_row.get("nash_regret", 0.0)),
            float(actual_row.get("nash_pct", 0.0)),
        )

        elapsed_s = round(time.time() - t0, 2)
        _emit_log(
            "VERDICT",
            f"Turno {turn_number} listo ({elapsed_s:.2f}s) -> [{commentary['symbol']}] {commentary['badge']} (Costo: {actual_row['nash_regret']:.2f})",
            f"Turn {turn_number} done ({elapsed_s:.2f}s) -> [{commentary_variants['en_vgc']['symbol']}] {commentary_variants['en_vgc']['badge']} (Cost: {actual_row['nash_regret']:.2f})",
            f"Turno {turn_number} finalizado ({elapsed_s:.2f}s) -> [{commentary_variants['es_scientific']['symbol']}] {commentary_variants['es_scientific']['badge']} (Nash_Utility_Loss={actual_row['nash_regret']:.4f})",
            f"Turn {turn_number} finished ({elapsed_s:.2f}s) -> [{commentary_variants['en_scientific']['symbol']}] {commentary_variants['en_scientific']['badge']} (Nash_Utility_Loss={actual_row['nash_regret']:.4f})",
        )

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
            "verdict_key": verdict_key,
            "commentary": commentary,
            "commentary_variants": commentary_variants,
            "terminology": export_glossary_payload(),
            "two_ply": two_ply_meta,
            "pipeline_logs": turn_logs,
        }
        return payload


def compute_match_summary(turn_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute Chess.com-style overall Match Accuracy %, badge counts, and Biggest Turning Point."""
    if not turn_results:
        return {
            "accuracy_pct": 100.0,
            "badge_counts": {
                "optimal": 0,
                "good": 0,
                "inaccuracy": 0,
                "weak_dominated": 0,
                "strict_dominated": 0,
            },
            "turning_point_turn": 1,
            "turning_point_regret": 0.0,
            "total_turns": 0,
            "total_timelines": 0,
            "total_elapsed_s": 0.0,
            "mean_nash_value": 0.0,
        }

    counts = {
        "optimal": 0,
        "good": 0,
        "inaccuracy": 0,
        "weak_dominated": 0,
        "strict_dominated": 0,
    }
    acc_scores: List[float] = []
    worst_turn = int(turn_results[0].get("turn", 1))
    worst_regret = -1.0
    total_timelines = 0
    total_elapsed = 0.0
    nash_vals: List[float] = []

    for tr in sorted(turn_results, key=lambda x: int(x.get("turn", 0))):
        t_num = int(tr.get("turn", 1))
        act = tr.get("actual_action") or {}
        reg = max(0.0, float(act.get("nash_regret", 0.0)))
        v_key = tr.get("verdict_key") or _classify_verdict_key(
            act.get("strict_dominated_by"),
            act.get("weak_dominated_by"),
            reg,
            float(act.get("nash_pct", 0.0)),
        )
        counts[v_key] = counts.get(v_key, 0) + 1

        # Exponential regret decay + dominance penalty -> smooth [0, 100] accuracy score
        base_score = 100.0 * math.exp(-1.85 * reg)
        if v_key == "strict_dominated":
            base_score *= 0.55
        elif v_key == "weak_dominated":
            base_score *= 0.78
        acc_scores.append(max(0.0, min(100.0, base_score)))

        # Weight strict/weak dominance slightly when selecting the biggest turning point
        tp_score = reg + (0.25 if v_key == "strict_dominated" else (0.10 if v_key == "weak_dominated" else 0.0))
        if tp_score > worst_regret:
            worst_regret = tp_score
            worst_turn = t_num

        total_timelines += int(tr.get("total_timelines", 0))
        total_elapsed += float(tr.get("elapsed_s", 0.0))
        nash_vals.append(float(tr.get("nash_value", 0.0)))

    return {
        "accuracy_pct": round(float(sum(acc_scores) / max(1, len(acc_scores))), 1),
        "badge_counts": counts,
        "turning_point_turn": int(worst_turn),
        "turning_point_regret": round(max(0.0, float(worst_regret)), 3),
        "total_turns": len(turn_results),
        "total_timelines": int(total_timelines),
        "total_elapsed_s": round(float(total_elapsed), 2),
        "mean_nash_value": round(float(sum(nash_vals) / max(1, len(nash_vals))), 3),
    }
