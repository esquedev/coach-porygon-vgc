# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Esports-Grade Rich Telemetry & Risk-Resilience Matrix Formatter
===================================================================================

Translates multidimensional tensor operations and `K`-thread discrete RNG simulations
into human-readable terminal dashboards and formatted string reports:

1. **Hardware Telemetry Header**:
   - Exact CUDA Device name, compute capability, and VRAM footprint.
2. **Action Pruning Matrix (`26x26` Grid)**:
   - Displays legal combinations vs pruned invalid cells (`trainer_1` / `trainer_2`).
3. **Pre-Attack Barrier Vector Tables**:
   - Effective Speed (`S_eff`), Effective Priority (`p_eff`), Spinning-Wheel Jitter,
     speed-tie alerts, and execution order permutations.
4. **Discrete-RNG Simulation & Downside-Risk Dashboard (`K` Repetitions)**:
   - Displays empirical Hit Rate, Crit Rate, Mean Damage, Faint Probability (`KO%`),
     Survival Probability, Expected Utility (`Mean`), Worst-10% Bad-Luck Tail (`CVaR_10`),
     `P5 / P95` quantiles, and `Risk-Adjusted Utility`.
5. **End-of-Turn Delta Dashboard**:
   - Residual chip, healing, field countdowns, and match termination status.
"""

from __future__ import annotations

from typing import Any, List, Optional, Union
import numpy as np

from .attack_cascade import AttackCascadeResult
from .phases_pre_attack import ACTIVE_SLOT_NAMES, ACTIVE_SLOTS, PreAttackPhaseResult
from .schema_and_tables import (
    CANONICAL_TERRAINS,
    CANONICAL_WEATHERS,
    FieldIdx,
    HAS_TORCH,
)
from .state_machine import EndOfTurnResult, StepResult, TurnSimulationStatistics

if HAS_TORCH:
    import torch


def _to_numpy(x: Any) -> np.ndarray:
    if HAS_TORCH and isinstance(x, torch.Tensor):
        return x.detach().cpu().numpy()
    return np.asarray(x)


def format_cuda_device_header(device: Any = None) -> str:
    """Format an executive hardware telemetry header showing GPU/CPU specs and VRAM usage."""
    lines: List[str] = []
    lines.append("+==============================================================================================+")
    lines.append("|                           VGC TENSOR CORE 2.0 HARDWARE TELEMETRY                             |")
    lines.append("+==============================================================================================+")

    if HAS_TORCH and torch.cuda.is_available():
        dev_idx = 0 if device is None or not hasattr(device, "index") or device.index is None else device.index
        gpu_name = torch.cuda.get_device_name(dev_idx)
        cap = torch.cuda.get_device_capability(dev_idx)
        mem_alloc = torch.cuda.memory_allocated(dev_idx) / (1024.0 ** 2)
        mem_res = torch.cuda.memory_reserved(dev_idx) / (1024.0 ** 2)
        total_mem = torch.cuda.get_device_properties(dev_idx).total_memory / (1024.0 ** 2)

        lines.append(f"|  Compute Device  : {gpu_name:<73} |")
        lines.append(f"|  Architecture    : CUDA Compute Capability {cap[0]}.{cap[1]} (PyTorch {torch.__version__:<14})               |")
        lines.append(f"|  VRAM Footprint  : {mem_alloc:.2f} MB Allocated | {mem_res:.2f} MB Reserved / {total_mem:.0f} MB Total                |")
    else:
        backend_str = "PyTorch (CPU-Only Mode)" if HAS_TORCH else "NumPy Pure Vectorized Engine"
        lines.append(f"|  Compute Device  : Host CPU ({backend_str:<56}) |")
        lines.append("|  CUDA Status     : Offline / CPU Fallback Active                                             |")

    lines.append("+==============================================================================================+")
    return "\n".join(lines)


def format_action_pruning_matrix(
    valid_mask_26x26: Union[np.ndarray, Any],
    prior_matrix_26x26: Optional[Union[np.ndarray, Any]] = None,
    side_name: str = "trainer_1",
) -> str:
    """Format an intuitive ASCII representation of the `26x26` joint action matrix."""
    valid_np = _to_numpy(valid_mask_26x26)
    total_cells = 26 * 26  # 676
    legal_cells = int(np.sum(valid_np > 0.5))
    pruned_cells = total_cells - legal_cells
    sparsity_pct = (pruned_cells / total_cells) * 100.0

    lines: List[str] = []
    lines.append(f"\n+-- {side_name.upper()} 26x26 ACTION PRUNING MATRIX (676 COMBINATORIAL BRANCHES) --------------+")
    lines.append(
        f"| Total Branches: {total_cells}  | Legal: {legal_cells:<3}  | Pruned: {pruned_cells:<3}  | Sparsity: {sparsity_pct:.1f}%                |"
    )
    lines.append("+----------------------------------------------------------------------------------------------+")
    lines.append(
        "| [Slot A \\ Slot B]  0..3 (OppA)  4..7 (OppB)  8..11 (Ally)  12..23 (Mega)  24 (Sw1)  25 (Sw2)   |"
    )

    sectors = [
        ("Base Opp A  (0..3)", 0, 4),
        ("Base Opp B  (4..7)", 4, 8),
        ("Base Partner(8..11)", 8, 12),
        ("Mega Moves  (12..23)", 12, 24),
        ("Switch Bench 1 (24)", 24, 25),
        ("Switch Bench 2 (25)", 25, 26),
    ]

    for name_a, s_a, e_a in sectors:
        row_str = f"| {name_a:<20} "
        for _, s_b, e_b in sectors:
            sub = valid_np[s_a:e_a, s_b:e_b]
            legal_in_sub = np.sum(sub > 0.5)
            total_in_sub = (e_a - s_a) * (e_b - s_b)
            if legal_in_sub == total_in_sub:
                status = " [OK] ALL "
            elif legal_in_sub == 0:
                status = " [X] NONE "
            else:
                status = f"~{int(legal_in_sub)}/{total_in_sub}"
            row_str += f"{status:^10} "
        row_str += "|"
        lines.append(row_str)

    lines.append("+----------------------------------------------------------------------------------------------+")
    return "\n".join(lines)


def format_pre_attack_barrier_table(
    pre_res: PreAttackPhaseResult,
    cell_b1: int = 0,
    cell_b2: int = 0,
) -> str:
    """Format the speed, priority, and execution order table for the 4 active slots."""
    eff_spe = _to_numpy(pre_res.effective_speeds)[cell_b1, cell_b2]
    eff_prio = _to_numpy(pre_res.effective_priorities)[cell_b1, cell_b2]
    jitter = _to_numpy(pre_res.jitter_applied)[cell_b1, cell_b2]
    order = _to_numpy(pre_res.execution_order)[cell_b1, cell_b2]
    switched = _to_numpy(pre_res.switched_mask)[cell_b1, cell_b2]
    mega = _to_numpy(pre_res.mega_evolved_mask)[cell_b1, cell_b2]
    tie_alert = float(_to_numpy(pre_res.speed_tie_alert)[cell_b1, cell_b2])

    lines: List[str] = []
    lines.append("\n+-- PRE-ATTACK SYNCHRONIZATION BARRIERS (TURN ORDER & SPEED CALCS) ----------------------------+")
    lines.append("| Step | Active Slot        | Base Slot | Eff Prio | Eff Spe | Jitter  | Switch   | Mega | Tie?  |")
    lines.append("+------+--------------------+-----------+----------+---------+---------+----------+------+-------+")

    for step_idx in range(4):
        act_idx = int(order[step_idx])
        slot_num = ACTIVE_SLOTS[act_idx]
        slot_name = ACTIVE_SLOT_NAMES[slot_num]
        prio_val = eff_prio[act_idx]
        spe_val = eff_spe[act_idx]
        jit_val = jitter[act_idx]
        sw_str = "YES (+6)" if switched[act_idx] > 0.5 else "no"
        mg_str = "YES" if mega[act_idx] > 0.5 else "no"
        tie_str = "ALERT" if tie_alert > 0.5 else "none"

        lines.append(
            f"|  {step_idx}   | {slot_name:<18} | Slot {slot_num}    |  {prio_val:>+4.1f}    |  {spe_val:>5.1f}  | {jit_val:>+6.3f}  | {sw_str:<8} | {mg_str:<4} | {tie_str:<5} |"
        )

    lines.append("+------+--------------------+-----------+----------+---------+---------+----------+------+-------+")
    return "\n".join(lines)


def format_monte_carlo_damage_matrix(
    attack_res: AttackCascadeResult,
    stats: Optional[TurnSimulationStatistics] = None,
    cell_b1: int = 0,
    cell_b2: int = 0,
) -> str:
    """Format discrete-RNG damage distributions, hit/crit rates, KO odds, and risk telemetry."""
    mean_hp = _to_numpy(attack_res.mean_hp)[cell_b1, cell_b2]
    faint_prob = _to_numpy(attack_res.faint_prob)[cell_b1, cell_b2]
    var_alert = _to_numpy(attack_res.roll_variance_alert)[cell_b1, cell_b2]
    mean_dmg = _to_numpy(attack_res.mean_damage_dealt)[cell_b1, cell_b2]
    hit_rate = _to_numpy(attack_res.hit_rate_observed)[cell_b1, cell_b2]
    crit_rate = _to_numpy(attack_res.crit_rate_observed)[cell_b1, cell_b2]

    lines: List[str] = []
    lines.append("\n+-- PHASE 4: DISCRETE-RNG ATTACK CASCADE (SPINNING-WHEEL HIT / CRIT / 16-ROLLS) ---------------+")
    lines.append(
        "| Active Slot        | Dmg Dealt | Hit Rate | Crit Rate | End Mean HP | KO Prob | Variance?    |"
    )
    lines.append(
        "+--------------------+-----------+----------+-----------+-------------+---------+--------------+"
    )

    for act_idx, slot in enumerate(ACTIVE_SLOTS):
        slot_name = ACTIVE_SLOT_NAMES[slot]
        dmg_val = mean_dmg[act_idx]
        hr_pct = hit_rate[act_idx] * 100.0
        cr_pct = crit_rate[act_idx] * 100.0
        hp_val = mean_hp[slot]
        fp_pct = faint_prob[slot] * 100.0
        va_str = "RNG-SENSITIVE" if var_alert[slot] > 0.5 else "Deterministic"

        lines.append(
            f"| {slot_name:<18} |  {dmg_val:>6.1f}   |  {hr_pct:>5.1f}%  |   {cr_pct:>5.1f}%  |   {hp_val:>6.1f}    | {fp_pct:>5.1f}%  | {va_str:<12} |"
        )

    lines.append(
        "+--------------------+-----------+----------+-----------+-------------+---------+--------------+"
    )

    if stats is not None:
        m_u = float(_to_numpy(stats.mean_utility)[cell_b1, cell_b2])
        s_u = float(_to_numpy(stats.std_utility)[cell_b1, cell_b2])
        cvar_u = float(_to_numpy(stats.cvar_10_utility)[cell_b1, cell_b2])
        p5_u = float(_to_numpy(stats.p5_utility)[cell_b1, cell_b2])
        p95_u = float(_to_numpy(stats.p95_utility)[cell_b1, cell_b2])
        r_u = float(_to_numpy(stats.risk_adjusted_utility)[cell_b1, cell_b2])
        win_p = float(_to_numpy(stats.win_turn_prob)[cell_b1, cell_b2]) * 100.0
        lines.append(
            f"| K={stats.num_simulations:<5} Sims | Mean U={m_u:>+6.3f} | Std={s_u:>5.3f} | CVaR_10(Worst10%)={cvar_u:>+6.3f} | RiskAdj U={r_u:>+6.3f} |"
        )
        lines.append(
            f"| Quantiles    | P5={p5_u:>+6.3f}     | P95={p95_u:>+6.3f} | WinTurnProb={win_p:>5.1f}%                         |"
        )
        lines.append(
            "+----------------------------------------------------------------------------------------------+"
        )

    return "\n".join(lines)


def format_end_of_turn_dashboard(
    eot_res: EndOfTurnResult,
    cell_b1: int = 0,
    cell_b2: int = 0,
) -> str:
    """Format Phase 5 end-of-turn status, field countdowns, and match termination."""
    F_slice = _to_numpy(eot_res.F)[cell_b1, cell_b2, 0]
    t1_faints = float(_to_numpy(eot_res.trainer_1_fainted_count)[cell_b1, cell_b2])
    t2_faints = float(_to_numpy(eot_res.trainer_2_fainted_count)[cell_b1, cell_b2])
    is_term = float(_to_numpy(eot_res.is_terminal)[cell_b1, cell_b2]) > 0.5
    winner = int(_to_numpy(eot_res.winner)[cell_b1, cell_b2])

    w_idx = int(np.argmax(F_slice[FieldIdx.WEATHER_START:FieldIdx.WEATHER_END]))
    w_name = CANONICAL_WEATHERS[w_idx]
    w_turns = int(F_slice[FieldIdx.WEATHER_TURNS])

    t_idx = int(np.argmax(F_slice[FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END]))
    t_name = CANONICAL_TERRAINS[t_idx]
    t_turns = int(F_slice[FieldIdx.TERRAIN_TURNS])

    t1_tw = int(F_slice[FieldIdx.TRAINER_1_TAILWIND_TURNS])
    t2_tw = int(F_slice[FieldIdx.TRAINER_2_TAILWIND_TURNS])

    winner_str = (
        "MATCH IN PROGRESS"
        if not is_term
        else ("TRAINER_1 WINS!" if winner == 1 else "TRAINER_2 WINS!")
    )

    lines: List[str] = []
    lines.append("\n+-- PHASE 5: END-OF-TURN RESIDUAL RESOLUTION & MATCH STATUS -----------------------------------+")
    lines.append(
        f"| Weather : {w_name:<10} ({w_turns} turns left)  | Terrain: {t_name:<10} ({t_turns} turns left)                       |"
    )
    lines.append(
        f"| Tailwind: trainer_1={t1_tw}t, trainer_2={t2_tw}t  | Faints : trainer_1={t1_faints:.1f}/4, trainer_2={t2_faints:.1f}/4                |"
    )
    lines.append(f"| Status  : {winner_str:<83} |")
    lines.append("+----------------------------------------------------------------------------------------------+")
    return "\n".join(lines)


def format_full_turn_report(
    step_res: StepResult,
    cell_b1: int = 0,
    cell_b2: int = 0,
    device: Any = None,
) -> str:
    """Generate an executive, publication-grade terminal match analysis dossier."""
    parts = [
        format_cuda_device_header(device),
        format_pre_attack_barrier_table(step_res.pre_attack, cell_b1, cell_b2),
        format_monte_carlo_damage_matrix(step_res.attack_cascade, step_res.stats, cell_b1, cell_b2),
        format_end_of_turn_dashboard(step_res.end_of_turn, cell_b1, cell_b2),
    ]
    return "\n".join(parts)

