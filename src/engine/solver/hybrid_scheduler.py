# -*- coding: utf-8 -*-
"""Hybrid GPU + Multi-Threaded CPU Dual-End Work-Stealing Turn Scheduler.

Accelerates turn-by-turn replay auditing by exploiting the independence of
Showdown turn snapshots:
  1. Pre-scans every turn (`< 5 ms`) to compute exact simulation cost
     `C_t = B1_t * B2_t * num_mc * (2.5 if two_ply else 1.0)`.
  2. Sorts turns descending into a thread-safe work-stealing deque:
       - **GPU Worker (`[GPU]`):** pops from the **heaviest** end (`popleft()`)
         where CUDA's massive SIMT parallelism crushes CPU by 15–40×.
       - **`W` Parallel CPU Workers (`[CPU-W1..WN]`):** concurrently steal from
         the **lightest** end (`pop()`) using isolated lock-free CPU state
         machines (PyTorch C++ kernels release the Python GIL).
  3. Prevents tail-latency stragglers by gating CPU workers off ultra-heavy
     turns while the GPU is active, while scaling seamlessly to full
     multi-worker CPU parallelism on CPU-only machines.

Pure domain module: ZERO web framework, HTTP, or UI dependencies.
Strictly uses `trainer_1` / `trainer_2` naming conventions.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import os
import threading
import time
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Tuple

ComputeMode = Literal["auto", "gpu_only", "cpu_parallel"]


@dataclass(frozen=True)
class TurnWorkItem:
    """One independent turn simulation unit scheduled by `HybridTurnScheduler`."""

    turn_number: int
    estimated_cost: float
    b1: int = 0
    b2: int = 0
    payload: Any = None


@dataclass
class HybridSchedulerStats:
    """Execution telemetry summary emitted after a batch schedule finishes."""

    mode: str
    has_gpu: bool
    cpu_workers: int
    total_turns: int
    gpu_turns: int
    cpu_turns: int
    elapsed_s: float
    worker_turn_map: Dict[int, str] = field(default_factory=dict)
    hardware_turn_map: Dict[int, str] = field(default_factory=dict)
    execution_counts: Dict[int, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize scheduler telemetry to a JSON-safe dictionary."""
        return {
            "mode": self.mode,
            "has_gpu": self.has_gpu,
            "cpu_workers": self.cpu_workers,
            "total_turns": self.total_turns,
            "gpu_turns": self.gpu_turns,
            "cpu_turns": self.cpu_turns,
            "elapsed_s": round(float(self.elapsed_s), 3),
            "worker_turn_map": {str(k): v for k, v in sorted(self.worker_turn_map.items())},
            "hardware_turn_map": {str(k): v for k, v in sorted(self.hardware_turn_map.items())},
            "execution_counts": {str(k): int(v) for k, v in sorted(self.execution_counts.items())},
        }


def resolve_worker_topology(
    mode: str = "auto",
    has_cuda: bool = False,
    total_turns: int = 1,
    cpu_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Compute optimal `(use_gpu, cpu_workers, threads_per_cpu_worker)` for the current machine."""
    cores = max(1, int(cpu_count or os.cpu_count() or 4))
    clean_mode = str(mode or "auto").strip().lower()
    if clean_mode not in ("auto", "gpu_only", "cpu_parallel"):
        clean_mode = "auto"

    if clean_mode == "gpu_only":
        return {
            "mode": "gpu_only" if has_cuda else "cpu_parallel",
            "use_gpu": bool(has_cuda),
            "cpu_workers": 0 if has_cuda else 1,
            "threads_per_cpu_worker": max(1, cores // 2),
        }

    if clean_mode == "cpu_parallel" or not has_cuda:
        max_w = min(4, max(1, cores // 2))
        w = min(max(1, int(total_turns)), max_w)
        t_per_w = max(1, cores // max(1, w))
        return {
            "mode": "cpu_parallel",
            "use_gpu": False,
            "cpu_workers": w,
            "threads_per_cpu_worker": t_per_w,
        }

    # Hybrid Auto mode (CUDA GPU + W parallel multi-core CPU workers):
    # Reserve 2 physical cores (4 logical threads) for the CUDA GPU host dispatcher & OS,
    # and partition the remaining physical cores across 1..3 parallel CPU workers:
    # - total_turns <= 1: 0 CPU workers (GPU solos single turn)
    # - 2..3 turns: 1 CPU worker
    # - 4..23 turns (e.g. 10-turn Bo3 match): up to 2 parallel CPU workers (CPU-W1, CPU-W2)
    # - >= 24 items (e.g. 90x90 Lead Lab with 36..225 cells): up to 3 parallel CPU workers (CPU-W1..CPU-W3)
    if total_turns <= 1:
        return {
            "mode": "auto",
            "use_gpu": True,
            "cpu_workers": 0,
            "threads_per_cpu_worker": max(1, cores // 2),
        }
    if total_turns <= 3 or cores < 6:
        cpu_w = 1
    elif total_turns < 24:
        cpu_w = min(2, max(1, cores // 6))
    else:
        cpu_w = min(3, max(1, cores // 5))
    avail_threads = max(2, cores - 4)
    t_per_w = max(2, min(4, avail_threads // max(1, cpu_w)))
    return {
        "mode": "auto",
        "use_gpu": True,
        "cpu_workers": cpu_w,
        "threads_per_cpu_worker": t_per_w,
    }


class HybridTurnScheduler:
    """Cost-aware Dual-End Work-Stealing Scheduler pairing 1 GPU worker with `W` CPU workers."""

    def __init__(
        self,
        mode: str = "auto",
        has_cuda: bool = False,
        cpu_count: Optional[int] = None,
        cpu_slowdown_factor: float = 5.5,
    ) -> None:
        self.requested_mode = str(mode or "auto").strip().lower()
        self.has_cuda = bool(has_cuda)
        self.cpu_count = int(cpu_count or os.cpu_count() or 4)
        self.cpu_slowdown_factor = max(1.0, float(cpu_slowdown_factor))

    def execute(
        self,
        items: Sequence[TurnWorkItem],
        gpu_runner: Callable[[TurnWorkItem, str], Any],
        cpu_runner: Callable[[TurnWorkItem, int, str], Any],
        on_item_start: Optional[Callable[[TurnWorkItem, str], None]] = None,
        on_item_done: Optional[Callable[[TurnWorkItem, str, Any], None]] = None,
        on_item_error: Optional[Callable[[TurnWorkItem, str, Exception], None]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Tuple[Dict[int, Any], HybridSchedulerStats]:
        """Run all unique `TurnWorkItem` tasks exactly once across the hybrid pool and join all workers."""
        t0 = time.perf_counter()
        # Deduplicate upfront by turn_number so a turn can NEVER be queued twice
        unique_by_turn: Dict[int, TurnWorkItem] = {}
        for it in items:
            tn = int(it.turn_number)
            if tn not in unique_by_turn:
                unique_by_turn[tn] = it
        dedup_items = list(unique_by_turn.values())

        if not dedup_items:
            return {}, HybridSchedulerStats(
                mode=self.requested_mode,
                has_gpu=self.has_cuda,
                cpu_workers=0,
                total_turns=0,
                gpu_turns=0,
                cpu_turns=0,
                elapsed_s=0.0,
            )

        topo = resolve_worker_topology(
            mode=self.requested_mode,
            has_cuda=self.has_cuda,
            total_turns=len(dedup_items),
            cpu_count=self.cpu_count,
        )
        use_gpu = bool(topo["use_gpu"])
        cpu_w = int(topo["cpu_workers"])

        # Sort descending by estimated cost: left = heaviest (GPU), right = lightest (CPU)
        sorted_items = sorted(dedup_items, key=lambda it: (-float(it.estimated_cost), int(it.turn_number)))
        work_deque: deque[TurnWorkItem] = deque(sorted_items)
        dq_lock = threading.Lock()
        res_lock = threading.Lock()
        claimed_turns: set[int] = set()
        execution_counts: Dict[int, int] = {}
        results: Dict[int, Any] = {}
        worker_map: Dict[int, str] = {}
        hardware_map: Dict[int, str] = {}
        gpu_done = 0
        cpu_done = 0
        gpu_in_flight_cost = 0.0
        # Account for mild memory-bandwidth sharing when multiple CPU workers run concurrently with CUDA
        eff_slowdown = self.cpu_slowdown_factor * (1.0 + 0.15 * max(0, cpu_w - 1))

        def _should_cancel() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        def _record_result(item: TurnWorkItem, worker_lbl: str, out: Any, is_gpu: bool) -> None:
            nonlocal gpu_done, cpu_done
            hw_label = ""
            if isinstance(out, dict):
                dev_str = str(out.get("hardware_device") or out.get("device") or "").strip()
                hw_label = f"{worker_lbl} · {dev_str}" if dev_str else worker_lbl
            else:
                hw_label = worker_lbl
            with res_lock:
                results[item.turn_number] = out
                worker_map[item.turn_number] = worker_lbl
                hardware_map[item.turn_number] = hw_label
                if is_gpu:
                    gpu_done += 1
                else:
                    cpu_done += 1

        def _gpu_loop() -> None:
            nonlocal gpu_in_flight_cost
            worker_lbl = "GPU"
            while not _should_cancel():
                item: Optional[TurnWorkItem] = None
                with dq_lock:
                    while work_deque:
                        cand = work_deque.popleft()
                        if cand.turn_number not in claimed_turns:
                            claimed_turns.add(cand.turn_number)
                            execution_counts[cand.turn_number] = execution_counts.get(cand.turn_number, 0) + 1
                            gpu_in_flight_cost = float(cand.estimated_cost)
                            item = cand
                            break
                    if item is None:
                        gpu_in_flight_cost = 0.0
                        break
                if on_item_start is not None:
                    on_item_start(item, worker_lbl)
                try:
                    out = gpu_runner(item, worker_lbl)
                except Exception as exc:
                    if on_item_error is not None:
                        on_item_error(item, worker_lbl, exc)
                    continue
                finally:
                    with dq_lock:
                        gpu_in_flight_cost = 0.0
                _record_result(item, worker_lbl, out, is_gpu=True)
                if on_item_done is not None:
                    on_item_done(item, worker_lbl, out)

        def _cpu_loop(worker_idx: int) -> None:
            worker_lbl = f"CPU-W{worker_idx + 1}"
            while not _should_cancel():
                item: Optional[TurnWorkItem] = None
                with dq_lock:
                    while work_deque:
                        candidate = work_deque[-1]
                        if candidate.turn_number in claimed_turns:
                            work_deque.pop()
                            continue
                        # Scale-invariant Critical-Path Makespan Guard (HEFT work-stealing):
                        # Only steal `candidate` onto CPU if its estimated CPU wall-clock cost
                        # fits cleanly inside the GPU's remaining queued + in-flight work.
                        if use_gpu:
                            cand_cost = float(candidate.estimated_cost)
                            remaining_other = sum(float(it.estimated_cost) for it in work_deque) - cand_cost
                            gpu_remaining_budget = remaining_other + 0.55 * gpu_in_flight_cost
                            if (cand_cost * eff_slowdown) > gpu_remaining_budget:
                                break
                        item = work_deque.pop()
                        claimed_turns.add(item.turn_number)
                        execution_counts[item.turn_number] = execution_counts.get(item.turn_number, 0) + 1
                        break
                    if item is None:
                        break
                if on_item_start is not None:
                    on_item_start(item, worker_lbl)
                try:
                    out = cpu_runner(item, worker_idx, worker_lbl)
                except Exception as exc:
                    if on_item_error is not None:
                        on_item_error(item, worker_lbl, exc)
                    continue
                _record_result(item, worker_lbl, out, is_gpu=False)
                if on_item_done is not None:
                    on_item_done(item, worker_lbl, out)

        threads: List[threading.Thread] = []
        if use_gpu:
            t_gpu = threading.Thread(target=_gpu_loop, name="porygon-gpu-worker", daemon=True)
            threads.append(t_gpu)
        for wi in range(cpu_w):
            t_cpu = threading.Thread(
                target=_cpu_loop,
                args=(wi,),
                name=f"porygon-cpu-worker-{wi + 1}",
                daemon=True,
            )
            threads.append(t_cpu)

        for th in threads:
            th.start()
        for th in threads:
            th.join()

        elapsed = time.perf_counter() - t0
        stats = HybridSchedulerStats(
            mode=str(topo["mode"]),
            has_gpu=use_gpu,
            cpu_workers=cpu_w,
            total_turns=len(dedup_items),
            gpu_turns=gpu_done,
            cpu_turns=cpu_done,
            elapsed_s=elapsed,
            worker_turn_map=worker_map,
            hardware_turn_map=hardware_map,
            execution_counts=execution_counts,
        )
        return results, stats
