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
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch

from engine.solver.game_theory import (
    decode_joint_action,
    run_iterated_dominance_elimination,
    solve_quantal_response,
    solve_zero_sum_nash,
)
from engine.solver.hybrid_scheduler import (
    HybridSchedulerStats,
    HybridTurnScheduler,
    TurnWorkItem,
    resolve_worker_topology,
)
from engine.solver.two_ply_lookahead import evaluate_two_ply_on_ieds_core
from engine.state.state_compiler import TurnStateCompiler
from engine.terminology import export_glossary_payload
from engine.vgc_tensor_core import (
    EQUITY_ENGINE_VERSION,
    FIELD_DIM,
    FieldIdx,
    MON_DIM,
    MOVE_DIM,
    MonIdx,
    MoveIdx,
    PILLAR_NAMES,
    ShowdownTensorCompiler,
    VgcTensorStateMachine,
    compute_victory_equity_torch,
)
from engine.vgc_tensor_core.state_machine import AnalysisCancelledError
from engine.vgc_tensor_core.compiler import CHOICE_SWITCH_BENCH1, CHOICE_SWITCH_BENCH2

from .commentary_engine import (
    _classify_verdict_key,
    generate_all_commentary_variants,
)
from .ots_db import OTSRosterDatabase, resolve_sprite_urls
from .protocol_parser import ParsedReplay, RecordedSlotAction, TurnSnapshot


DEFAULT_EQUITY_SAMPLES_PATH: Path = Path("data/telemetry/equity_samples.jsonl")


def _norm_id(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def append_equity_training_sample(
    match_id: str,
    turn: int,
    phi_raw: Dict[str, float],
    winner_label: float,
    nash_value: float,
    ply2_nash_value: Optional[float] = None,
    samples_path: Path = DEFAULT_EQUITY_SAMPLES_PATH,
) -> None:
    """Passively append a compact 8-pillar equity training observation to JSONL for offline Texel tuning."""
    try:
        samples_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "match_id": str(match_id),
            "turn": int(turn),
            "phi_raw": {k: round(float(v), 6) for k, v in phi_raw.items()},
            "winner": float(winner_label),
            "nash_value": round(float(nash_value), 5),
            "ply2_nash_value": round(float(ply2_nash_value), 5) if ply2_nash_value is not None else None,
            "engine_version": EQUITY_ENGINE_VERSION,
            "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with samples_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Passive logging must never interrupt live replay coaching
        pass


_PROC_BO3_ENGINE: Optional["GPUReplayCoachEngine"] = None
_BO3_MP_LOCK = threading.Lock()
_BO3_MP_EXECUTOR: Any = None
_BO3_MP_WORKERS: int = 0


def _init_bo3_cpu_worker_process(omp_threads: int) -> None:
    """Initialize a persistent Zero-GIL CPU `GPUReplayCoachEngine` inside a worker subprocess."""
    global _PROC_BO3_ENGINE
    try:
        torch.set_num_threads(max(1, int(omp_threads)))
    except Exception:
        pass
    _PROC_BO3_ENGINE = GPUReplayCoachEngine(
        ots_db=None,  # type: ignore[arg-type]
        device="cpu",
        equity_samples_path=None,
    )


def _eval_bo3_turn_in_worker_process(
    replay: ParsedReplay,
    turn_number: int,
    num_mc: int,
    enable_two_ply: bool,
    worker_label: str,
) -> Dict[str, Any]:
    """Evaluate a single Bo3 turn inside an isolated Zero-GIL CPU worker process."""
    global _PROC_BO3_ENGINE
    if _PROC_BO3_ENGINE is None:
        _PROC_BO3_ENGINE = GPUReplayCoachEngine(
            ots_db=None,  # type: ignore[arg-type]
            device="cpu",
            equity_samples_path=None,
        )
    return _PROC_BO3_ENGINE.analyze_turn(
        replay,
        turn_number=turn_number,
        min_prior=0.0,
        num_mc=num_mc,
        enable_two_ply=enable_two_ply,
        log_cb=None,
        cancel_event=None,
        worker_label=worker_label,
    )


def _get_bo3_cpu_process_pool(num_workers: int, omp_threads: int) -> Any:
    """Return a persistent `spawn`-based `ProcessPoolExecutor` for Zero-GIL CPU turn workers."""
    global _BO3_MP_EXECUTOR, _BO3_MP_WORKERS
    import atexit
    import concurrent.futures as _cf
    import multiprocessing as _mp

    with _BO3_MP_LOCK:
        if _BO3_MP_EXECUTOR is not None and _BO3_MP_WORKERS == num_workers:
            return _BO3_MP_EXECUTOR
        if _BO3_MP_EXECUTOR is not None:
            try:
                _BO3_MP_EXECUTOR.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            _BO3_MP_EXECUTOR = None
        try:
            ctx = _mp.get_context("spawn")
            _BO3_MP_EXECUTOR = _cf.ProcessPoolExecutor(
                max_workers=max(1, int(num_workers)),
                mp_context=ctx,
                initializer=_init_bo3_cpu_worker_process,
                initargs=(max(1, int(omp_threads)),),
            )
            _BO3_MP_WORKERS = int(num_workers)
            atexit.register(lambda ex=_BO3_MP_EXECUTOR: ex.shutdown(wait=False, cancel_futures=True))
            return _BO3_MP_EXECUTOR
        except Exception:
            return None


class GPUReplayCoachEngine:
    """Warm singleton Tensor Core solver wrapping `VgcTensorStateMachine` (CUDA GPU or CPU) and DuckDB OTS DB."""

    def __init__(
        self,
        ots_db: Optional[OTSRosterDatabase],
        device: Optional[str] = None,
        equity_samples_path: Optional[Path] = DEFAULT_EQUITY_SAMPLES_PATH,
    ) -> None:
        self.ots_db = ots_db
        self._gpu_lock = threading.Lock()
        self._pool_lock = threading.Lock()
        self._cpu_worker_engines: Dict[int, "GPUReplayCoachEngine"] = {}
        self.equity_samples_path = equity_samples_path
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
        worker_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run full Tensor Core IEDS + Nash + QRE + Zero-AI Commentary for one turn."""
        if cancel_event is not None and cancel_event.is_set():
            raise AnalysisCancelledError("Analysis cancelled before turn start.")
        active_worker = str(worker_label or ("GPU" if self.device_type == "cuda" else "CPU")).strip()

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
                "compute_worker": active_worker,
                "hardware_device": self.device_name,
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
                f"Turno {turn_number}: Tensores F[{FIELD_DIM}], P[8,{MON_DIM}], M[8,4,{MOVE_DIM}] compilados ({t1_leads} vs. {t2_leads}) en {t_comp_ms:.1f}ms",
                f"Turn {turn_number}: Compiled tensors F[{FIELD_DIM}], P[8,{MON_DIM}], M[8,4,{MOVE_DIM}] ({t1_leads} vs. {t2_leads}) in {t_comp_ms:.1f}ms",
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
                "row_idx": int(row_i),
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

        best_row_idx = int(sorted_rows[0]) if sorted_rows else idx_act1
        opp_sorted_all = sorted(range(B2), key=lambda j: (-float(q_nash[j]), float(U_risk[:, j].max())))
        best_opp_idx = int(opp_sorted_all[0]) if opp_sorted_all else idx_act2
        best_t1_pair = (int(c1_np[best_row_idx, 0]), int(c1_np[best_row_idx, 1]))
        best_t2_pair = (int(c2_np[best_opp_idx, 0]), int(c2_np[best_opp_idx, 1]))
        equity_breakdown = self._compute_equity_attribution(
            comp=comp,
            best_t1=best_t1_pair,
            best_t2=best_t2_pair,
            played_t1=actual_t1,
            played_t2=actual_t2,
            res_played=res_act,
            k_sample=min(64, k_ko),
            rng_seed=919191 + turn_number * 137,
            resolve_lead_entry_abilities=False,
            cancel_event=cancel_event,
        )

        # Passively log 8-pillar feature vector when replay has a known match winner
        if self.equity_samples_path is not None and replay.winner:
            win_norm = _norm_id(replay.winner)
            t1_norm = _norm_id(replay.trainer_1_name)
            t2_norm = _norm_id(replay.trainer_2_name)
            winner_label: Optional[float] = None
            if win_norm and win_norm == t1_norm:
                winner_label = 1.0
            elif win_norm and win_norm == t2_norm:
                winner_label = 0.0
            if winner_label is not None and equity_breakdown.get("phi_raw"):
                append_equity_training_sample(
                    match_id=replay.replay_id,
                    turn=turn_number,
                    phi_raw=equity_breakdown["phi_raw"],
                    winner_label=winner_label,
                    nash_value=float(nash_sub.game_value),
                    ply2_nash_value=float(nash_sub.game_value) if enable_two_ply else None,
                    samples_path=self.equity_samples_path,
                )

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
                "col_idx": int(j),
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
                        "moves": [str(m) for m in (comp.slot_move_names[s] if s < len(comp.slot_move_names) else ()) if m],
                        "ots_verified": bool(mon_obj and mon_obj.moves),
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
            equity_breakdown=equity_breakdown,
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
            "hardware_device": self.device_name,
            "compute_worker": active_worker,
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
            "qre_matrix": {
                "U": [[round(float(U_risk[i, j]), 4) for j in range(B2)] for i in range(B1)],
                "default_beta": 4.0,
            },
            "events": events_dict,
            "verdict_key": verdict_key,
            "commentary": commentary,
            "commentary_variants": commentary_variants,
            "terminology": export_glossary_payload(),
            "two_ply": two_ply_meta,
            "equity_breakdown": equity_breakdown,
            "pipeline_logs": turn_logs,
        }
        return payload

    def _get_cpu_worker_engine(self, worker_idx: int) -> "GPUReplayCoachEngine":
        """Return an isolated CPU `GPUReplayCoachEngine` dedicated to `worker_idx` (zero lock contention)."""
        with self._pool_lock:
            eng = self._cpu_worker_engines.get(worker_idx)
            if eng is None:
                eng = GPUReplayCoachEngine(
                    ots_db=self.ots_db,
                    device="cpu",
                    equity_samples_path=self.equity_samples_path,
                )
                self._cpu_worker_engines[worker_idx] = eng
            return eng

    def estimate_turn_cost(
        self,
        replay: ParsedReplay,
        turn_number: int,
        num_mc: int = 128,
        enable_two_ply: bool = False,
    ) -> TurnWorkItem:
        """Fast `< 1 ms` pre-scan estimating exact simulation cost `B1 * B2 * K * ply` for one turn."""
        snap = next((t for t in replay.turns if t.turn_number == turn_number), None)
        if snap is None:
            return TurnWorkItem(turn_number=turn_number, estimated_cost=1.0, b1=1, b2=1)
        # Use isolated CPU compiler so pre-scan never blocks CUDA
        scan_eng = self if self.device_type == "cpu" else self._get_cpu_worker_engine(0)
        with scan_eng._gpu_lock:
            comp = scan_eng._compile_snapshot(snap)
            m1 = scan_eng.sm.logic_engine.prune_side_26x26_tensor_actions(
                comp, "trainer_1", min_prior_threshold=0.0
            )
            m2 = scan_eng.sm.logic_engine.prune_side_26x26_tensor_actions(
                comp, "trainer_2", min_prior_threshold=0.0
            )
            b1 = max(1, int(m1.pruned_choices.shape[0]))
            b2 = max(1, int(m2.pruned_choices.shape[0]))
        ply_mult = 2.5 if enable_two_ply else 1.0
        est_cost = float(b1 * b2 * max(16, int(num_mc)) * ply_mult)
        return TurnWorkItem(
            turn_number=int(turn_number),
            estimated_cost=est_cost,
            b1=b1,
            b2=b2,
            payload=snap,
        )

    def analyze_match_parallel(
        self,
        replay: ParsedReplay,
        start_turn: int = 1,
        num_mc: int = 128,
        enable_two_ply: bool = False,
        compute_mode: str = "auto",
        skip_turns: Optional[Sequence[int]] = None,
        on_scheduler_plan: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_worker_start: Optional[Callable[[int, str, str], None]] = None,
        on_log: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_turn: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[int, str, Exception], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Tuple[List[Dict[str, Any]], HybridSchedulerStats]:
        """Run unique turns `start_turn..N` (excluding `skip_turns`) exactly once across the Hybrid pool."""
        skip_set = {int(x) for x in (skip_turns or ())}
        seen_snaps: set[int] = set()
        target_snaps: List[TurnSnapshot] = []
        for s in replay.turns:
            tn = int(s.turn_number)
            if tn >= start_turn and tn not in skip_set and tn not in seen_snaps:
                seen_snaps.add(tn)
                target_snaps.append(s)

        has_cuda = self.device_type == "cuda"
        topo = resolve_worker_topology(
            mode=compute_mode,
            has_cuda=has_cuda,
            total_turns=len(target_snaps),
        )

        work_items: List[TurnWorkItem] = [
            self.estimate_turn_cost(replay, s.turn_number, num_mc=num_mc, enable_two_ply=enable_two_ply)
            for s in target_snaps
        ]
        if on_scheduler_plan is not None:
            try:
                on_scheduler_plan(
                    {
                        "mode": topo["mode"],
                        "use_gpu": topo["use_gpu"],
                        "gpu_device_name": self.device_name if topo["use_gpu"] else None,
                        "cpu_device_name": "CPU (PyTorch)",
                        "cpu_workers": topo["cpu_workers"],
                        "threads_per_cpu_worker": topo["threads_per_cpu_worker"],
                        "total_scheduled_turns": len(work_items),
                        "turns": [
                            {"turn": w.turn_number, "b1": w.b1, "b2": w.b2, "cost": round(w.estimated_cost, 1)}
                            for w in sorted(work_items, key=lambda x: -x.estimated_cost)
                        ],
                    }
                )
            except Exception:
                pass

        # Use Zero-GIL Multi-Process CPU Worker Pool for full Hybrid CUDA runs (K >= 32)
        # so multi-core CPU workers never contend for the parent process's Python GIL during CUDA kernel launches!
        import os as _os

        use_mp_cpu = bool(
            topo["use_gpu"]
            and int(topo["cpu_workers"]) >= 1
            and len(work_items) >= 3
            and (int(num_mc) >= 32 or _os.environ.get("PORYGON_BO3_MP_POOL") == "1")
        )
        mp_pool = (
            _get_bo3_cpu_process_pool(int(topo["cpu_workers"]), int(topo["threads_per_cpu_worker"]))
            if use_mp_cpu
            else None
        )

        # Pre-warm fallback CPU worker instances before parallel launch
        if mp_pool is None:
            for wi in range(int(topo["cpu_workers"])):
                self._get_cpu_worker_engine(wi)

        prev_torch_threads: Optional[int] = None
        if int(topo["cpu_workers"]) >= 1 and mp_pool is None:
            try:
                prev_torch_threads = int(torch.get_num_threads())
                torch.set_num_threads(max(1, int(topo["threads_per_cpu_worker"])))
            except Exception:
                prev_torch_threads = None

        scheduler = HybridTurnScheduler(mode=compute_mode, has_cuda=has_cuda)

        def _gpu_run(item: TurnWorkItem, w_lbl: str) -> Dict[str, Any]:
            return self.analyze_turn(
                replay,
                turn_number=item.turn_number,
                min_prior=0.0,
                num_mc=num_mc,
                enable_two_ply=enable_two_ply,
                log_cb=on_log,
                cancel_event=cancel_event,
                worker_label=w_lbl,
            )

        def _cpu_run(item: TurnWorkItem, worker_idx: int, w_lbl: str) -> Dict[str, Any]:
            if mp_pool is not None:
                fut = mp_pool.submit(
                    _eval_bo3_turn_in_worker_process,
                    replay,
                    int(item.turn_number),
                    int(num_mc),
                    bool(enable_two_ply),
                    w_lbl,
                )
                out_res = fut.result()
                if on_log is not None:
                    for lg in out_res.get("pipeline_logs") or ():
                        on_log(lg)
                return out_res
            cpu_eng = self._get_cpu_worker_engine(worker_idx)
            return cpu_eng.analyze_turn(
                replay,
                turn_number=item.turn_number,
                min_prior=0.0,
                num_mc=num_mc,
                enable_two_ply=enable_two_ply,
                log_cb=on_log,
                cancel_event=cancel_event,
                worker_label=w_lbl,
            )

        def _start_cb(item: TurnWorkItem, w_lbl: str) -> None:
            if on_worker_start is not None:
                hw_name = self.device_name if w_lbl == "GPU" else "CPU (PyTorch)"
                on_worker_start(item.turn_number, w_lbl, hw_name)

        def _done_cb(item: TurnWorkItem, w_lbl: str, res_dict: Dict[str, Any]) -> None:
            if on_turn is not None:
                on_turn(res_dict)

        def _err_cb(item: TurnWorkItem, w_lbl: str, exc: Exception) -> None:
            if on_error is not None:
                on_error(item.turn_number, w_lbl, exc)

        try:
            res_map, stats = scheduler.execute(
                items=work_items,
                gpu_runner=_gpu_run,
                cpu_runner=_cpu_run,
                on_item_start=_start_cb,
                on_item_done=_done_cb,
                on_item_error=_err_cb,
                cancel_event=cancel_event,
            )
        finally:
            if prev_torch_threads is not None:
                try:
                    torch.set_num_threads(prev_torch_threads)
                except Exception:
                    pass

        ordered_results = [res_map[t] for t in sorted(res_map.keys())]
        return ordered_results, stats

    @staticmethod
    def reconstruct_ordered_match_logs(
        ordered_results: Sequence[Dict[str, Any]],
        sched_stats: Optional[HybridSchedulerStats] = None,
        gpu_device_name: str = "CUDA GPU",
    ) -> List[Dict[str, Any]]:
        """Reconstruct a single strictly chronological (`T1 -> TN`), deduplicated, hardware-tagged log.

        Called strictly AFTER all parallel workers have finished and joined, guaranteeing that
        every turn appears at most once, in exact ascending order, with clear hardware attribution.
        """
        reconstructed: List[Dict[str, Any]] = []
        unique_sorted = sorted(
            {int(r["turn"]): r for r in ordered_results if "turn" in r}.values(),
            key=lambda r: int(r["turn"]),
        )

        if sched_stats is not None:
            turn_assign_parts = [
                f"T{int(r['turn'])}={r.get('compute_worker', '?')}"
                for r in unique_sorted
            ]
            assign_str = " · ".join(turn_assign_parts) if turn_assign_parts else "—"
            mode_up = str(sched_stats.mode or "auto").upper()
            hw_es = (
                f"Plan ejecutado [{mode_up}] en {sched_stats.elapsed_s:.2f}s · "
                f"{sched_stats.gpu_turns} turno(s) GPU ({gpu_device_name}) · "
                f"{sched_stats.cpu_turns} turno(s) CPU · Asignación: {assign_str}"
            )
            hw_en = (
                f"Completed schedule [{mode_up}] in {sched_stats.elapsed_s:.2f}s · "
                f"{sched_stats.gpu_turns} GPU turn(s) ({gpu_device_name}) · "
                f"{sched_stats.cpu_turns} CPU turn(s) · Assignment: {assign_str}"
            )
            reconstructed.append(
                {
                    "turn": 0,
                    "phase": "SCHEDULER",
                    "in_place": False,
                    "compute_worker": "BALANCER",
                    "hardware_device": f"{gpu_device_name} + CPU",
                    "messages": {
                        "es_vgc": hw_es,
                        "en_vgc": hw_en,
                        "es_scientific": hw_es,
                        "en_scientific": hw_en,
                    },
                }
            )

        for r in unique_sorted:
            t_num = int(r["turn"])
            w_lbl = str(r.get("compute_worker") or "GPU")
            hw_dev = str(r.get("hardware_device") or r.get("device") or w_lbl)
            for entry in r.get("pipeline_logs") or []:
                if entry.get("in_place"):
                    continue
                cloned = dict(entry)
                cloned["turn"] = t_num
                cloned["compute_worker"] = str(entry.get("compute_worker") or w_lbl)
                cloned["hardware_device"] = str(entry.get("hardware_device") or hw_dev)
                reconstructed.append(cloned)

        return reconstructed

    def _compute_equity_attribution(
        self,
        comp: Any,
        best_t1: Tuple[int, int],
        best_t2: Tuple[int, int],
        played_t1: Optional[Tuple[int, int]] = None,
        played_t2: Optional[Tuple[int, int]] = None,
        res_played: Optional[Any] = None,
        k_sample: int = 64,
        rng_seed: int = 919191,
        resolve_lead_entry_abilities: bool = False,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """Compute 8-pillar `VictoryEquityBreakdown` for Nash-optimal and played lines."""
        with self._gpu_lock, torch.inference_mode():
            def _eval_res(step_res_obj: Any) -> Any:
                _, bd = compute_victory_equity_torch(
                    step_res_obj.F,
                    step_res_obj.P,
                    M_moves=step_res_obj.M_moves,
                    tables=self.sm.tables,
                    extra_volatiles=step_res_obj.attack_cascade.extra_volatiles,
                    weights=self.sm.equity_weights,
                    return_breakdown=True,
                )
                return bd

            def _sim_pair(pair1: Tuple[int, int], pair2: Tuple[int, int], seed_off: int) -> Any:
                return self.sm.step(
                    comp.field_tensor,
                    comp.roster_tensor,
                    comp.moves_tensor,
                    torch.tensor([[pair1[0], pair1[1]]], dtype=torch.long, device=self.sm.device),
                    torch.tensor([[pair2[0], pair2[1]]], dtype=torch.long, device=self.sm.device),
                    num_mc_samples=max(16, int(k_sample)),
                    rng_seed=int(rng_seed + seed_off),
                    resolve_lead_entry_abilities=resolve_lead_entry_abilities,
                    cancel_event=cancel_event,
                )

            played_bd = _eval_res(res_played) if res_played is not None else None
            if played_bd is not None and played_t1 == best_t1 and played_t2 == best_t2:
                nash_bd = played_bd
            else:
                res_best = _sim_pair(best_t1, best_t2, 0)
                nash_bd = _eval_res(res_best)
                if played_bd is None:
                    if played_t1 is not None and played_t2 is not None and (played_t1 != best_t1 or played_t2 != best_t2):
                        res_pl = _sim_pair(played_t1, played_t2, 7919)
                        played_bd = _eval_res(res_pl)
                    else:
                        played_bd = nash_bd

        nash_d = nash_bd.to_dict()
        played_d = played_bd.to_dict()
        nash_p = nash_d["pillars"]
        played_p = played_d["pillars"]
        delta_p = {k: round(float(nash_p[k]) - float(played_p[k]), 4) for k in PILLAR_NAMES}

        non_mat = [k for k in PILLAR_NAMES if k != "material"]
        max_delta = max((abs(delta_p[k]) for k in non_mat), default=0.0)
        if played_t1 is not None and (played_t1 != best_t1 or played_t2 != best_t2) and max_delta >= 0.04:
            ranked = sorted(non_mat, key=lambda k: -abs(delta_p[k]))
            top_drivers = [
                {
                    "pillar": k,
                    "value": delta_p[k],
                    "nash_val": nash_p[k],
                    "played_val": played_p[k],
                    "mode": "delta",
                }
                for k in ranked[:3]
                if abs(delta_p[k]) >= 0.03
            ]
        else:
            ranked = sorted(non_mat, key=lambda k: -abs(float(nash_p[k])))
            top_drivers = [
                {
                    "pillar": k,
                    "value": float(nash_p[k]),
                    "nash_val": float(nash_p[k]),
                    "played_val": float(played_p[k]),
                    "mode": "state",
                }
                for k in ranked[:3]
                if abs(float(nash_p[k])) >= 0.03
            ]

        return {
            "engine_version": EQUITY_ENGINE_VERSION,
            "nash_pillars": nash_p,
            "nash_total": nash_d["total"],
            "played_pillars": played_p,
            "played_total": played_d["total"],
            "delta_pillars": delta_p,
            "phi_raw": played_d["phi_raw"],
            "nash_phi_raw": nash_d["phi_raw"],
            "top_drivers": top_drivers,
        }

    def analyze_compiled_turn1(
        self,
        comp: Any,
        turn0_events: Optional[List[str]] = None,
        num_mc: int = 128,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        """Run a full unpruned Turn-1 Tensor Core IEDS + Nash + QRE + 4-profile bilingual audit.

        Operates on an exact post-Turn-0 `CompiledBattleState` produced by
        `LeadMatchupSolver.build_turn1_battle_state(...)` with `resolve_lead_entry_abilities=False`
        so Turn-0 entry abilities never double-fire.
        """
        t0 = time.time()
        k_mc = max(16, int(num_mc))
        with self._gpu_lock:
            if cancel_event is not None and cancel_event.is_set():
                raise AnalysisCancelledError("Deep Turn-1 audit cancelled before start.")

            m1 = self.sm.logic_engine.prune_side_26x26_tensor_actions(
                comp, trainer_id="trainer_1", min_prior_threshold=0.0
            )
            m2 = self.sm.logic_engine.prune_side_26x26_tensor_actions(
                comp, trainer_id="trainer_2", min_prior_threshold=0.0
            )
            c1 = m1.pruned_choices
            c2 = m2.pruned_choices
            c1_np = c1.detach().cpu().numpy() if isinstance(c1, torch.Tensor) else np.asarray(c1)
            c2_np = c2.detach().cpu().numpy() if isinstance(c2, torch.Tensor) else np.asarray(c2)
            B1, B2 = int(c1_np.shape[0]), int(c2_np.shape[0])

            with torch.inference_mode():
                step_res = self.sm.step(
                    F=comp.field_tensor,
                    P=comp.roster_tensor,
                    M_moves=comp.moves_tensor,
                    trainer_1_choices=c1,
                    trainer_2_choices=c2,
                    num_mc_samples=k_mc,
                    rng_seed=424242,
                    resolve_lead_entry_abilities=False,
                    tile_size=24,
                    cancel_event=cancel_event,
                )

            U_risk = step_res.stats.risk_adjusted_utility.detach().cpu().numpy().astype(np.float64)
            U_mean = step_res.stats.mean_utility.detach().cpu().numpy().astype(np.float64)
            U_cvar = step_res.stats.cvar_10_utility.detach().cpu().numpy().astype(np.float64)
            U_win = step_res.stats.win_turn_prob.detach().cpu().numpy().astype(np.float64)

        ieds_strict = run_iterated_dominance_elimination(
            U_risk, dominance_Margin_eps=0.0, eliminate_weakly_dominated=False
        )
        ieds_weak = run_iterated_dominance_elimination(
            U_risk, dominance_Margin_eps=0.0, eliminate_weakly_dominated=True
        )
        nash_sub = solve_zero_sum_nash(ieds_strict.reduced_payoff_matrix)
        p_nash = np.zeros(B1, dtype=np.float64)
        q_nash = np.zeros(B2, dtype=np.float64)
        p_nash[ieds_strict.trainer_1_surviving_indices] = nash_sub.trainer_1_strategy
        q_nash[ieds_strict.trainer_2_surviving_indices] = nash_sub.trainer_2_strategy
        qre_res = solve_quantal_response(U_risk, rationality_beta=4.0)

        ev_vs_q = U_risk @ q_nash
        mean_vs_q = U_mean @ q_nash
        cvar_vs_q = U_cvar @ q_nash
        win_vs_q = U_win @ q_nash
        min_j_vals = U_risk.min(axis=1)
        min_j_args = U_risk.argmin(axis=1)

        strict_surv_set = set(int(x) for x in ieds_strict.trainer_1_surviving_indices)
        weak_surv_set = set(int(x) for x in ieds_weak.trainer_1_surviving_indices)
        strict_rec_map = {r.eliminated_idx: r for r in ieds_strict.eliminated_trainer_1}
        weak_rec_map = {r.eliminated_idx: r for r in ieds_weak.eliminated_trainer_1}

        def _fmt_dom(rec_map: Dict[int, Any], row_i: int) -> Optional[Dict[str, Any]]:
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

        sorted_rows = sorted(
            range(B1),
            key=lambda i: (-(1 if p_nash[i] > 1e-4 else 0), -float(p_nash[i]), -float(ev_vs_q[i])),
        )
        opp_sorted = sorted(range(B2), key=lambda j: (-float(q_nash[j]), float(U_risk[:, j].max())))
        top_opp_idx = int(opp_sorted[0]) if opp_sorted else 0

        def _build_row(row_i: int) -> Dict[str, Any]:
            cp = [int(c1_np[row_i, 0]), int(c1_np[row_i, 1])]
            wc_j = int(min_j_args[row_i])
            wc_pair = [int(c2_np[wc_j, 0]), int(c2_np[wc_j, 1])]
            return {
                "row_idx": int(row_i),
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
                "strict_dominated_by": _fmt_dom(strict_rec_map, row_i),
                "weak_dominated_by": _fmt_dom(weak_rec_map, row_i),
                "vs_actual_opp_u": round(float(U_risk[row_i, top_opp_idx]), 4),
                "is_played": False,
            }

        top_actions = [_build_row(i) for i in sorted_rows[:8]]
        ref_row = dict(top_actions[0]) if top_actions else {}
        ref_row["rank"] = 1
        ref_row["total_actions"] = int(B1)
        ref_row["opp_actual_desc"] = decode_joint_action(
            comp, "trainer_2", [int(c2_np[top_opp_idx, 0]), int(c2_np[top_opp_idx, 1])]
        )
        ref_row["num_mc"] = int(k_mc)
        ref_row["ko_probs_vs_actual_opp"] = {}

        opp_top = [
            {
                "choice_pair": [int(c2_np[j, 0]), int(c2_np[j, 1])],
                "desc": decode_joint_action(comp, "trainer_2", [int(c2_np[j, 0]), int(c2_np[j, 1])]),
                "nash_pct": round(float(q_nash[j] * 100.0), 1),
                "qre_pct": round(float(qre_res.trainer_2_strategy[j] * 100.0), 1),
            }
            for j in opp_sorted[:5]
        ]

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
                for r in ieds_strict.eliminated_trainer_1[:6]
            ],
        }

        F_np = comp.field_tensor.detach().cpu().numpy() if isinstance(comp.field_tensor, torch.Tensor) else np.asarray(comp.field_tensor)
        weather_lbl = None
        for w_i, w_nm in ((1, "Sun"), (2, "Rain"), (3, "Sand"), (4, "Snow")):
            if float(F_np[FieldIdx.WEATHER_START + w_i]) > 0.5:
                weather_lbl = w_nm
                break
        terrain_lbl = None
        for t_i, t_nm in ((1, "Electric"), (2, "Grassy"), (3, "Psychic"), (4, "Misty")):
            if float(F_np[FieldIdx.TERRAIN_START + t_i]) > 0.5:
                terrain_lbl = t_nm
                break
        field_context = {
            "weather": weather_lbl,
            "weather_turns": int(round(float(F_np[FieldIdx.WEATHER_TURNS]))),
            "terrain": terrain_lbl,
            "terrain_turns": int(round(float(F_np[FieldIdx.TERRAIN_TURNS]))),
            "trick_room_turns": 0,
            "t1_tailwind": 0,
            "t2_tailwind": 0,
        }
        empty_events = {
            "crits": [], "misses": [], "flinches": [], "protects": [],
            "faints": [], "megas": [], "weather_changes": [],
        }
        best_t1_idx = int(sorted_rows[0]) if sorted_rows else 0
        equity_breakdown = self._compute_equity_attribution(
            comp=comp,
            best_t1=(int(c1_np[best_t1_idx, 0]), int(c1_np[best_t1_idx, 1])),
            best_t2=(int(c2_np[top_opp_idx, 0]), int(c2_np[top_opp_idx, 1])),
            k_sample=min(64, k_mc),
            rng_seed=424999,
            resolve_lead_entry_abilities=False,
            cancel_event=cancel_event,
        )
        commentary_variants = generate_all_commentary_variants(
            turn_number=1,
            actual_action=ref_row,
            top_actions=top_actions,
            nash_value=float(nash_sub.game_value),
            ieds_summary=ieds_summary,
            events=empty_events,
            field_context=field_context,
            equity_breakdown=equity_breakdown,
        )

        return {
            "ok": True,
            "elapsed_s": round(time.time() - t0, 2),
            "device": self.device_name,
            "matrix_shape": [int(B1), int(B2)],
            "total_timelines": int(B1 * B2 * k_mc),
            "num_mc": int(k_mc),
            "nash_value": round(float(nash_sub.game_value), 4),
            "qre_value": round(float(qre_res.expected_value), 4),
            "maximin": round(float(nash_sub.pure_maximin_value), 4),
            "minimax": round(float(nash_sub.pure_minimax_value), 4),
            "exploitability_gap": round(float(nash_sub.exploitability_gap), 6),
            "turn0_events": list(turn0_events or []),
            "field": field_context,
            "ieds": ieds_summary,
            "top_actions": top_actions,
            "opp_top_actions": opp_top,
            "equity_breakdown": equity_breakdown,
            "commentary_variants": commentary_variants,
        }


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
