# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Counter-Based Hash Scrambling & Dual-Draw Spinning-Wheel RNG Engine
=======================================================================================

Implements de-biased, per-event deterministic/quasi-cryptographic random number generation
for parallel GPU (`torch.Tensor`) and CPU (`np.ndarray`) simulation threads.

Why Dual-Draw (Spinning-Wheel Rolling Window) + Counter-Based Hash Scrambling?
------------------------------------------------------------------------------
1. **Eliminates Top-of-Distribution Clustering ("Spinning the Roulette Wheel")**:
   In naive RNG checks (`u < threshold`), every MISS or non-proc is trapped at the top
   of the `[0, 100]` interval (`[threshold, 100]`). If a generator has any tail correlation,
   high rolls and misses become coupled.
   Here, every event in every simulation thread `k` draws TWO independent values on `[0, 100)`:
   - Draw 1 (`window_start ~ Uniform(0, 100)`): Spins the wheel to place the target arc
     at a random starting angle on the `0..100` circle.
   - Draw 2 (`dart ~ Uniform(0, 100)`): Throws the dart onto the `0..100` circle.
   - Cyclic Arc Check: `((dart - window_start) % 100.0) < threshold_pct`.
   Because the arc wraps around `100.0`, the probability of landing inside an arc of length
   `threshold_pct` is mathematically exact (`threshold_pct / 100.0`), while hits and misses
   occur uniformly across low, middle, and high values of `0..100`.

2. **Counter-Based SplitMix64 / MurmurHash3 Scrambling (Independent Dice per Event)**:
   Instead of pulling sequential numbers from a single stateful stream where event `n`
   can correlate with event `n+1`, each `(seed, sim_k, step_idx, actor_slot, target_slot, hit_idx, event_id)`
   tuple is hashed through a bijective 64-bit SplitMix64 mixing cascade. Accuracy, Critical Hit,
   Cartridge Damage Roll (`85..100`), Secondary Effect, Flinch, Paralysis, and Speed Ties each
   receive their own statistically independent dice stream.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Tuple, Union

import numpy as np

from .schema_and_tables import HAS_TORCH

if HAS_TORCH:
    import torch
    TensorOrArray = Union["torch.Tensor", np.ndarray]
else:
    TensorOrArray = np.ndarray


class RNGEventID(IntEnum):
    """Canonical event stream identifiers for counter-based hash scrambling."""

    SPEED_TIE_JITTER = 1
    PARALYSIS_IMMOBILIZE = 2
    FREEZE_THAW = 3
    SLEEP_WAKE = 4
    PROTECT_CHAIN = 5
    MOVE_ACCURACY = 6
    MULTIHIT_COUNT = 7
    CRITICAL_HIT = 8
    DAMAGE_ROLL_16 = 9
    SECONDARY_STATUS = 10
    STAT_STAGE_PROC = 11
    FLINCH_PROC = 12


# Official Gen 9 / Champions Cartridge Critical Hit Probability Percentages by Stage (0..3+)
# Stage 0: 1/24 (~4.1667%), Stage 1: 1/8 (12.5%), Stage 2: 1/2 (50.0%), Stage >= 3: 1/1 (100.0%)
CRIT_STAGE_THRESHOLDS_PCT: Tuple[float, float, float, float] = (
    100.0 / 24.0,  # Stage 0: 4.1666667%
    12.5,          # Stage 1: 12.5%
    50.0,          # Stage 2: 50.0%
    100.0,         # Stage 3+: 100.0%
)

# 16 Canonical Cartridge Damage Multipliers: 85/100, 86/100, ..., 100/100
CARTRIDGE_16_ROLLS: Tuple[float, ...] = tuple(r / 100.0 for r in range(85, 101))


def _splitmix64_numpy(x: np.ndarray) -> np.ndarray:
    """Vectorized 64-bit SplitMix64 bijective bit-scrambler in NumPy (`uint64`)."""
    with np.errstate(over="ignore"):
        z = (x.astype(np.uint64) + np.uint64(0x9E3779B97F4A7C15))
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        z = z ^ (z >> np.uint64(31))
    return z


def _splitmix64_torch(x: "torch.Tensor") -> "torch.Tensor":
    """Vectorized 64-bit SplitMix64-inspired bit-scrambler in PyTorch (`int64`)."""
    # Use signed 64-bit arithmetic (two's complement wraps identically to uint64 for +, *, ^)
    c1 = -7046029254386353131  # 0x9E3779B97F4A7C15 in signed int64
    c2 = -4658895280553007687  # 0xBF58476D1CE4E5B9 in signed int64
    c3 = -7723592293110705685  # 0x94D049BB133111EB in signed int64

    z = x + c1
    z = (z ^ ((z >> 30) & 0x3FFFFFFFF)) * c2
    z = (z ^ ((z >> 27) & 0x1FFFFFFFFF)) * c3
    z = z ^ ((z >> 31) & 0x1FFFFFFFF)
    return z


def counter_uniform_0_100_numpy(
    shape: Tuple[int, ...],
    seed: int,
    event_id: int,
    step_idx: int = 0,
    hit_idx: int = 0,
    sub_draw: int = 0,
) -> np.ndarray:
    """Generate a tensor of uniform random floats in `[0.0, 100.0)` using counter-based hashing.

    Every element `(b1, b2, k, ...)` receives a unique counter coordinate mixed with
    `(seed, event_id, step_idx, hit_idx, sub_draw)` so draws are reproducible and decorrelated.
    """
    total = int(np.prod(shape))
    flat_idx = np.arange(total, dtype=np.uint64).reshape(shape)
    with np.errstate(over="ignore"):
        key = (
            np.uint64(seed & 0xFFFFFFFFFFFFFFFF)
            ^ (np.uint64(event_id + 1) * np.uint64(0x517CC1B727220A95))
            ^ (np.uint64(step_idx + 1) * np.uint64(0x9E3779B97F4A7C15))
            ^ (np.uint64(hit_idx + 1) * np.uint64(0xBF58476D1CE4E5B9))
            ^ (np.uint64(sub_draw + 1) * np.uint64(0x94D049BB133111EB))
        )
        hashed = _splitmix64_numpy(flat_idx ^ key)
    # Extract top 53 bits to [0.0, 100.0)
    u01 = (hashed >> np.uint64(11)).astype(np.float64) * (1.0 / float(1 << 53))
    return (u01 * 100.0).astype(np.float32)


def counter_uniform_0_100_torch(
    shape: Tuple[int, ...],
    device: "torch.device",
    seed: int,
    event_id: int,
    step_idx: int = 0,
    hit_idx: int = 0,
    sub_draw: int = 0,
) -> "torch.Tensor":
    """Generate a PyTorch tensor of uniform random floats in `[0.0, 100.0)` on GPU/CPU."""
    total = int(np.prod(shape))
    flat_idx = torch.arange(total, dtype=torch.int64, device=device).view(shape)
    key = (
        int(seed)
        ^ ((int(event_id) + 1) * 5871781006564002453)
        ^ ((int(step_idx) + 1) * 2685821657736338717)
        ^ ((int(hit_idx) + 1) * 4101842887655102017)
        ^ ((int(sub_draw) + 1) * 7364136223846793005)
    ) & 0x7FFFFFFFFFFFFFFF
    hashed = _splitmix64_torch(flat_idx ^ key)
    # Mask positive 53-bit integer and scale to [0.0, 100.0)
    mantissa = (hashed >> 11) & 0x1FFFFFFFFFFFFF
    u_pct = (mantissa.to(torch.float32) / float(1 << 53)) * 100.0
    return torch.clamp(u_pct, min=0.0, max=99.9999)


def spin_wheel_gate(
    threshold_pct: TensorOrArray,
    seed: int,
    event_id: int,
    step_idx: int = 0,
    hit_idx: int = 0,
) -> TensorOrArray:
    """Evaluate a discrete probability check via the Dual-Draw Spinning-Wheel on `[0, 100)`.

    Args:
        threshold_pct: Tensor/ndarray of event success probabilities in `[0.0, 100.0]`
            (values `>= 100.0` always succeed; values `<= 0.0` always fail).
        seed: Base simulation RNG seed.
        event_id: `RNGEventID` stream selector.
        step_idx: Turn order step index (`0..3`).
        hit_idx: Multi-hit index (`0..9`).

    Returns:
        Boolean mask (`bool` Tensor or ndarray) of the same shape as `threshold_pct`,
        where `True` means the discrete event triggered in that simulation thread.
    """
    if HAS_TORCH and isinstance(threshold_pct, torch.Tensor):
        shape = tuple(threshold_pct.shape)
        window_start = counter_uniform_0_100_torch(
            shape, threshold_pct.device, seed, event_id, step_idx, hit_idx, sub_draw=0
        )
        dart = counter_uniform_0_100_torch(
            shape, threshold_pct.device, seed, event_id, step_idx, hit_idx, sub_draw=1
        )
        cyclic_dist = torch.remainder(dart - window_start + 100.0, 100.0)
        return (threshold_pct >= 100.0) | ((threshold_pct > 0.0) & (cyclic_dist < threshold_pct))

    arr_thresh = np.asarray(threshold_pct, dtype=np.float32)
    shape = arr_thresh.shape
    window_start = counter_uniform_0_100_numpy(
        shape, seed, event_id, step_idx, hit_idx, sub_draw=0
    )
    dart = counter_uniform_0_100_numpy(
        shape, seed, event_id, step_idx, hit_idx, sub_draw=1
    )
    cyclic_dist = np.mod(dart - window_start + 100.0, 100.0)
    return (arr_thresh >= 100.0) | ((arr_thresh > 0.0) & (cyclic_dist < arr_thresh))


def spin_wheel_damage_rolls_16(
    shape: Tuple[int, ...],
    seed: int,
    step_idx: int = 0,
    hit_idx: int = 0,
    is_torch: bool = False,
    device: object = None,
) -> TensorOrArray:
    """Draw exact discrete cartridge damage rolls in `{0.85, 0.86, ..., 1.00}` per simulation thread.

    Uses the Dual-Draw Spinning-Wheel cyclic distance `(dart - window_start) % 100.0` mapped
    uniformly onto the 16 discrete integer buckets `{0..15}` -> `{85..100} / 100.0`.
    """
    if is_torch and HAS_TORCH:
        dev = device or torch.device("cpu")
        window_start = counter_uniform_0_100_torch(
            shape, dev, seed, int(RNGEventID.DAMAGE_ROLL_16), step_idx, hit_idx, sub_draw=0
        )
        dart = counter_uniform_0_100_torch(
            shape, dev, seed, int(RNGEventID.DAMAGE_ROLL_16), step_idx, hit_idx, sub_draw=1
        )
        cyclic_pct = torch.remainder(dart - window_start + 100.0, 100.0)
        bucket_idx = torch.clamp(torch.floor(cyclic_pct * (16.0 / 100.0)).long(), min=0, max=15)
        return (85.0 + bucket_idx.to(torch.float32)) / 100.0

    window_start = counter_uniform_0_100_numpy(
        shape, seed, int(RNGEventID.DAMAGE_ROLL_16), step_idx, hit_idx, sub_draw=0
    )
    dart = counter_uniform_0_100_numpy(
        shape, seed, int(RNGEventID.DAMAGE_ROLL_16), step_idx, hit_idx, sub_draw=1
    )
    cyclic_pct = np.mod(dart - window_start + 100.0, 100.0)
    bucket_idx = np.clip(np.floor(cyclic_pct * (16.0 / 100.0)).astype(np.int32), 0, 15)
    return ((85 + bucket_idx).astype(np.float32)) / 100.0


def spin_wheel_crit_gate(
    crit_stage: TensorOrArray,
    seed: int,
    step_idx: int = 0,
    hit_idx: int = 0,
) -> TensorOrArray:
    """Resolve discrete Critical Hit triggers per simulation thread from `crit_stage` (`0..3+`).

    Official Gen 9 / Champions crit thresholds:
    - Stage 0: `1/24` (`4.1667%`)
    - Stage 1: `1/8` (`12.5%`)
    - Stage 2: `1/2` (`50.0%`)
    - Stage >= 3: `1/1` (`100.0%`, e.g., Wicked Blow, Surging Strikes, Flower Trick)
    """
    if HAS_TORCH and isinstance(crit_stage, torch.Tensor):
        st = torch.clamp(torch.round(crit_stage).long(), min=0, max=3)
        lut = torch.tensor(CRIT_STAGE_THRESHOLDS_PCT, dtype=torch.float32, device=crit_stage.device)
        thresh_pct = lut[st]
        return spin_wheel_gate(
            thresh_pct, seed=seed, event_id=int(RNGEventID.CRITICAL_HIT), step_idx=step_idx, hit_idx=hit_idx
        )

    st = np.clip(np.round(np.asarray(crit_stage)).astype(np.int32), 0, 3)
    lut = np.array(CRIT_STAGE_THRESHOLDS_PCT, dtype=np.float32)
    thresh_pct = lut[st]
    return spin_wheel_gate(
        thresh_pct, seed=seed, event_id=int(RNGEventID.CRITICAL_HIT), step_idx=step_idx, hit_idx=hit_idx
    )


def spin_wheel_multihit_count(
    expected_hits_code: TensorOrArray,
    has_loaded_dice: TensorOrArray,
    has_skill_link: TensorOrArray,
    seed: int,
    step_idx: int = 0,
) -> TensorOrArray:
    """Resolve discrete hit count `H in {1..10}` for each simulation thread.

    Encoding in `MoveIdx.EXPECTED_HITS`:
    - `1.0`: Single-hit move -> always `1` hit
    - `2.0`, `3.0`, `4.0`, `10.0`: Fixed multi-hit count (`2`, `3`, `4`, `10`)
    - `3.1`: Variable `2..5` multi-hit move (`Bullet Seed`, `Scale Shot`, `Icicle Spear`, `Rock Blast`):
      * With `Skill Link`: always `5` hits.
      * With `Loaded Dice`: `50%` 4 hits, `50%` 5 hits.
      * Standard Cartridge Wheel on `[0, 100)`:
        - `[0, 35)` -> `2` hits (35%)
        - `[35, 70)` -> `3` hits (35%)
        - `[70, 85)` -> `4` hits (15%)
        - `[85, 100)` -> `5` hits (15%)
    """
    if HAS_TORCH and isinstance(expected_hits_code, torch.Tensor):
        shape = tuple(expected_hits_code.shape)
        dev = expected_hits_code.device
        window_start = counter_uniform_0_100_torch(
            shape, dev, seed, int(RNGEventID.MULTIHIT_COUNT), step_idx, sub_draw=0
        )
        dart = counter_uniform_0_100_torch(
            shape, dev, seed, int(RNGEventID.MULTIHIT_COUNT), step_idx, sub_draw=1
        )
        cyclic_pct = torch.remainder(dart - window_start + 100.0, 100.0)

        is_var_2_5 = torch.abs(expected_hits_code - 3.1) < 0.05
        std_hits = torch.where(
            cyclic_pct < 35.0,
            torch.tensor(2, dtype=torch.int64, device=dev),
            torch.where(
                cyclic_pct < 70.0,
                torch.tensor(3, dtype=torch.int64, device=dev),
                torch.where(
                    cyclic_pct < 85.0,
                    torch.tensor(4, dtype=torch.int64, device=dev),
                    torch.tensor(5, dtype=torch.int64, device=dev),
                ),
            ),
        )
        dice_hits = torch.where(
            cyclic_pct < 50.0,
            torch.tensor(4, dtype=torch.int64, device=dev),
            torch.tensor(5, dtype=torch.int64, device=dev),
        )
        var_hits = torch.where(
            has_skill_link > 0.5,
            torch.tensor(5, dtype=torch.int64, device=dev),
            torch.where(has_loaded_dice > 0.5, dice_hits, std_hits),
        )
        fixed_hits = torch.clamp(torch.round(expected_hits_code).long(), min=1, max=10)
        return torch.where(is_var_2_5, var_hits, fixed_hits)

    arr_code = np.asarray(expected_hits_code, dtype=np.float32)
    arr_dice = np.asarray(has_loaded_dice, dtype=np.float32)
    arr_slink = np.asarray(has_skill_link, dtype=np.float32)
    shape = arr_code.shape

    window_start = counter_uniform_0_100_numpy(
        shape, seed, int(RNGEventID.MULTIHIT_COUNT), step_idx, sub_draw=0
    )
    dart = counter_uniform_0_100_numpy(
        shape, seed, int(RNGEventID.MULTIHIT_COUNT), step_idx, sub_draw=1
    )
    cyclic_pct = np.mod(dart - window_start + 100.0, 100.0)

    is_var_2_5 = np.abs(arr_code - 3.1) < 0.05
    std_hits = np.where(
        cyclic_pct < 35.0,
        2,
        np.where(cyclic_pct < 70.0, 3, np.where(cyclic_pct < 85.0, 4, 5)),
    )
    dice_hits = np.where(cyclic_pct < 50.0, 4, 5)
    var_hits = np.where(arr_slink > 0.5, 5, np.where(arr_dice > 0.5, dice_hits, std_hits))
    fixed_hits = np.clip(np.round(arr_code).astype(np.int32), 1, 10)
    return np.where(is_var_2_5, var_hits, fixed_hits).astype(np.int32)

