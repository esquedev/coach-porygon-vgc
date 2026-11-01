# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — State-to-Tensor Encoder (engine/gpu/tensor_encoder.py)

Encodes VGC 4v4 Doubles board states (TurnSnapshot or ClientReplaySimulator state dicts)
into PyTorch CUDA/CPU tensors following the canonical mathematical specification:
- Field State Tensor S_field: shape (B, 32)
  - Weather One-Hot (5): None, Sun, Rain, Sand, Snow + Weather Turns (1)
  - Terrain One-Hot (5): None, Electric, Grassy, Psychic, Misty + Terrain Turns (1)
  - Trick Room Turns (1)
  - Side Conditions P1/P2 (8): Tailwind (P1, P2), Reflect (P1, P2), Light Screen (P1, P2), Aurora Veil (P1, P2)
  - Bench & Mega Economy (6): P1 Bench Alive, P2 Bench Alive, P1 Mega Used, P2 Mega Used, Gravity, Turn Number
  - Reserved padding (5) -> Total 32 features
- Active Monsters Tensor S_mons: shape (B, 4, 64) for [P1_Slot1, P1_Slot2, P2_Slot1, P2_Slot2]:
  - 0..2: HP_pct [0.0, 1.0], HP_current normalized (/300.0), HP_max normalized (/300.0)
  - 3..9: Primary Status One-Hot (7): Healthy, Burn, Paralyze, Sleep, Freeze, Poison, Toxic
  - 10..14: Volatile Status (5): Protect count/flag, Substitute, Taunt, Encore, Helping Hand
  - 15..21: Stat Stages (7): Atk, Def, SpA, SpD, Spe, Acc, Eva normalized (/6.0)
  - 22..39: Elemental Type 1 / 2 Multi-Hot (18 canonical types)
  - 40..57: Secondary / Mega / Active Type Alignment Multi-Hot (18 types)
  - 58: Mega / Special Transformation active flag (boolean 0.0 / 1.0)
  - 59..60: Ability ID normalized [0.0, 1.0], Item ID normalized [0.0, 1.0]
  - 61..63: Runtime effective stats (Max Offensive Stat, Max Defensive Stat, Effective Speed) normalized (/250.0)
"""

from dataclasses import dataclass
import hashlib
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

try:
    import torch
    HAS_TORCH = True
except ImportError:
    torch = None
    HAS_TORCH = False

from engine.tactics.showdown_parser import ShowdownParser, TurnSnapshot
from engine.turn_simulator import BASE_STATS_DB, calculate_level_50_stats


FIELD_TENSOR_DIM = 32
MON_SLOTS_COUNT = 4
MON_FEATURE_DIM = 64

CANONICAL_TYPES: Tuple[str, ...] = (
    "Normal", "Fire", "Water", "Grass", "Electric", "Ice",
    "Fighting", "Poison", "Ground", "Flying", "Psychic", "Bug",
    "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy",
)
TYPE_TO_INDEX: Dict[str, int] = {t.lower(): i for i, t in enumerate(CANONICAL_TYPES)}

WEATHER_TO_INDEX: Dict[str, int] = {
    "none": 0, "clear": 0, "sun": 1, "sunnyday": 1,
    "rain": 2, "raindance": 2, "sand": 3, "sandstorm": 3,
    "snow": 4, "hail": 4,
}

TERRAIN_TO_INDEX: Dict[str, int] = {
    "none": 0, "clear": 0, "electric": 1, "electricterrain": 1,
    "grassy": 2, "grassyterrain": 2, "psychic": 3, "psychicterrain": 3,
    "misty": 4, "mistyterrain": 4,
}

STATUS_TO_INDEX: Dict[str, int] = {
    "none": 0, "healthy": 0, "": 0,
    "brn": 1, "burn": 1,
    "par": 2, "paralyze": 2,
    "slp": 3, "sleep": 3,
    "frz": 4, "freeze": 4,
    "psn": 5, "poison": 5,
    "tox": 6, "toxic": 6,
}


def _stable_hash_norm(text: str) -> float:
    """Compute a deterministic normalized embedding ID in [0.0, 1.0] for an ability or item string."""
    clean = (text or "").strip().lower()
    if not clean or clean == "none":
        return 0.0
    digest = hashlib.md5(clean.encode("utf-8")).digest()
    val = int.from_bytes(digest[:4], byteorder="big")
    return round((val % 10000) / 10000.0, 4)


@dataclass
class TurnStateTensor:
    """
    Container holding encoded batch tensors for field conditions and active monsters.

    Attributes:
        s_field: Tensor or ndarray of shape (B, 32) representing field state.
        s_mons: Tensor or ndarray of shape (B, 4, 64) representing the 4 active slots.
        device: Compute device string ('cuda:0' or 'cpu').
    """

    s_field: Any
    s_mons: Any
    device: str = "cpu"

    @property
    def batch_size(self) -> int:
        """Return batch dimension B."""
        return int(self.s_field.shape[0])

    def to_numpy(self) -> Tuple[np.ndarray, np.ndarray]:
        """Convert s_field and s_mons to float32 NumPy arrays."""
        if HAS_TORCH and isinstance(self.s_field, torch.Tensor):
            return (
                self.s_field.detach().cpu().numpy(),
                self.s_mons.detach().cpu().numpy(),
            )
        return np.asarray(self.s_field, dtype=np.float32), np.asarray(self.s_mons, dtype=np.float32)


class TensorEncoder:
    """
    Deterministic State-to-Tensor encoder converting TurnSnapshot or simulator dicts
    into normalized PyTorch tensors S_field (B, 32) and S_mons (B, 4, 64).
    """

    def __init__(self, device: Optional[str] = None) -> None:
        """
        Initialize TensorEncoder with automatic CUDA detection and CPU fallback.

        Args:
            device: Optional target device ('cuda', 'cuda:0', or 'cpu').
        """
        if HAS_TORCH and torch is not None:
            if device is None or device == "auto":
                self.device_str = "cuda:0" if torch.cuda.is_available() else "cpu"
            elif device == "cuda" and not torch.cuda.is_available():
                self.device_str = "cpu"
            else:
                self.device_str = str(device)
            self.device = torch.device(self.device_str)
        else:
            self.device_str = "cpu"
            self.device = None
        self._parser = ShowdownParser()

    def _normalize_to_sim_state(
        self, state: Union[TurnSnapshot, Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], int, int, bool, bool]:
        """Convert either a TurnSnapshot or raw simulator dict into canonical simulator format."""
        if isinstance(state, TurnSnapshot):
            sim_dict = self._parser.to_simulator_state(state)
            return (
                sim_dict,
                state.p1_bench_alive,
                state.p2_bench_alive,
                state.p1_mega_used,
                state.p2_mega_used,
            )
        if not isinstance(state, dict):
            raise ValueError(f"Unsupported state type: {type(state).__name__}")
        p1_b = int(state.get("p1_bench_alive", 2))
        p2_b = int(state.get("p2_bench_alive", 2))
        p1_m = bool(state.get("p1_mega_used", False))
        p2_m = bool(state.get("p2_mega_used", False))
        return state, p1_b, p2_b, p1_m, p2_m

    def encode_single_numpy(
        self, state: Union[TurnSnapshot, Dict[str, Any]]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Encode a single turn state into NumPy arrays of shape (32,) and (4, 64).

        Args:
            state: TurnSnapshot or ClientReplaySimulator state dictionary.

        Returns:
            Tuple of (field_vec (32,), mons_mat (4, 64)) in float32.
        """
        sim_state, p1_bench, p2_bench, p1_mega, p2_mega = self._normalize_to_sim_state(state)

        field_vec = np.zeros(FIELD_TENSOR_DIM, dtype=np.float32)
        f_data = sim_state.get("field", {})
        p1_side = sim_state.get("p1", {})
        p2_side = sim_state.get("p2", {})

        # 0..4: Weather One-Hot (None, Sun, Rain, Sand, Snow)
        w_raw = str(f_data.get("weather") or "none").lower()
        w_idx = WEATHER_TO_INDEX.get(w_raw, 0)
        field_vec[w_idx] = 1.0
        # 5: Weather turns remaining normalized
        field_vec[5] = min(1.0, float(f_data.get("weather_turns", 0)) / 8.0)

        # 6..10: Terrain One-Hot (None, Electric, Grassy, Psychic, Misty)
        t_raw = str(f_data.get("terrain") or "none").lower()
        t_idx = TERRAIN_TO_INDEX.get(t_raw, 0)
        field_vec[6 + t_idx] = 1.0
        # 11: Terrain turns remaining normalized
        field_vec[11] = min(1.0, float(f_data.get("terrain_turns", 0)) / 8.0)

        # 12: Trick Room turns remaining
        field_vec[12] = min(1.0, float(f_data.get("trick_room_turns", 0)) / 5.0)

        # 13..20: Side screens & Tailwind (P1 & P2)
        field_vec[13] = min(1.0, float(p1_side.get("tailwind_turns", 0)) / 4.0)
        field_vec[14] = min(1.0, float(p2_side.get("tailwind_turns", 0)) / 4.0)
        field_vec[15] = min(1.0, float(p1_side.get("reflect_turns", 0)) / 5.0)
        field_vec[16] = min(1.0, float(p2_side.get("reflect_turns", 0)) / 5.0)
        field_vec[17] = min(1.0, float(p1_side.get("light_screen_turns", 0)) / 5.0)
        field_vec[18] = min(1.0, float(p2_side.get("light_screen_turns", 0)) / 5.0)
        field_vec[19] = min(1.0, float(p1_side.get("aurora_veil_turns", 0)) / 5.0)
        field_vec[20] = min(1.0, float(p2_side.get("aurora_veil_turns", 0)) / 5.0)

        # 21..26: Bench & Mega Economy + Turn metadata
        field_vec[21] = min(1.0, max(0.0, float(p1_bench) / 2.0))
        field_vec[22] = min(1.0, max(0.0, float(p2_bench) / 2.0))
        field_vec[23] = 1.0 if p1_mega else 0.0
        field_vec[24] = 1.0 if p2_mega else 0.0
        field_vec[25] = min(1.0, float(f_data.get("gravity_turns", 0)) / 5.0)
        field_vec[26] = min(1.0, float(sim_state.get("turn", 1)) / 20.0)

        # Encode 4 Active Monsters [p1a, p1b, p2a, p2b] -> (4, 64)
        mons_mat = np.zeros((MON_SLOTS_COUNT, MON_FEATURE_DIM), dtype=np.float32)
        slots_dict = sim_state.get("slots", {})
        slot_keys = ("p1a", "p1b", "p2a", "p2b")

        for s_idx, s_key in enumerate(slot_keys):
            slot = slots_dict.get(s_key, {})
            if not slot:
                continue

            species = str(slot.get("species", "Charizard"))
            max_hp_val = int(slot.get("max_hp", 0))
            stats_dict = slot.get("stats", {})
            if max_hp_val <= 0 or not stats_dict:
                max_hp_val, stats_dict = calculate_level_50_stats(
                    species, slot.get("sp_spread", {}), slot.get("nature", "Hardy")
                )

            hp_pct = float(slot.get("current_hp_pct", 100.0)) / 100.0
            hp_pct = max(0.0, min(1.0, hp_pct))
            hp_cur = int(slot.get("hp", round(max_hp_val * hp_pct)))

            # 0..2: HP features
            mons_mat[s_idx, 0] = hp_pct
            mons_mat[s_idx, 1] = min(1.0, float(hp_cur) / 300.0)
            mons_mat[s_idx, 2] = min(1.0, float(max_hp_val) / 300.0)

            # 3..9: Primary Status One-Hot (7)
            st_raw = str(slot.get("status") or "healthy").lower()
            st_i = STATUS_TO_INDEX.get(st_raw, 0)
            mons_mat[s_idx, 3 + st_i] = 1.0

            # 10..14: Volatile status flags (Protect, Substitute, Taunt, Encore, Helping Hand)
            vols = slot.get("volatiles", {})
            mons_mat[s_idx, 10] = 1.0 if slot.get("protected") else 0.0
            mons_mat[s_idx, 11] = 1.0 if vols.get("substitute") else 0.0
            mons_mat[s_idx, 12] = min(1.0, float(vols.get("taunt", 0)) / 3.0)
            mons_mat[s_idx, 13] = 1.0 if vols.get("encore") else 0.0
            mons_mat[s_idx, 14] = 1.0 if float(slot.get("helping_hand_mult", 1.0)) > 1.0 else 0.0

            # 15..21: 7 Stat Stages [-6, +6] normalized to [-1.0, +1.0]
            boosts = slot.get("boosts", {})
            for b_i, b_key in enumerate(("atk", "def", "spa", "spd", "spe", "accuracy", "evasion")):
                b_val = float(max(-6, min(6, int(boosts.get(b_key, 0)))))
                mons_mat[s_idx, 15 + b_i] = b_val / 6.0

            # 22..39: Type 1 One-Hot (18 types)
            types_list = slot.get("types") or BASE_STATS_DB.get(species, {}).get("types", ["Normal"])
            if len(types_list) >= 1:
                t1_idx = TYPE_TO_INDEX.get(str(types_list[0]).lower(), 0)
                mons_mat[s_idx, 22 + t1_idx] = 1.0

            # 40..57: Type 2 / Secondary Type One-Hot (18 types)
            if len(types_list) >= 2:
                t2_idx = TYPE_TO_INDEX.get(str(types_list[1]).lower(), 0)
                mons_mat[s_idx, 40 + t2_idx] = 1.0
            elif len(types_list) == 1:
                t1_idx = TYPE_TO_INDEX.get(str(types_list[0]).lower(), 0)
                mons_mat[s_idx, 40 + t1_idx] = 1.0

            # 58: Mega / Active Transformation boolean
            is_mega = "mega" in species.lower() or bool(slot.get("is_mega"))
            mons_mat[s_idx, 58] = 1.0 if is_mega else 0.0

            # 59..60: Ability ID & Item ID normalized
            mons_mat[s_idx, 59] = _stable_hash_norm(str(slot.get("ability", "")))
            mons_mat[s_idx, 60] = _stable_hash_norm(str(slot.get("item", "")))

            # 61..63: Runtime effective stats (Offense, Defense, Speed)
            atk_v = float(stats_dict.get("atk", 100))
            spa_v = float(stats_dict.get("spa", 100))
            def_v = float(stats_dict.get("def", 100))
            spd_v = float(stats_dict.get("spd", 100))
            spe_v = float(stats_dict.get("spe", 100))

            mons_mat[s_idx, 61] = min(1.5, max(atk_v, spa_v) / 250.0)
            mons_mat[s_idx, 62] = min(1.5, ((def_v + spd_v) * 0.5) / 250.0)
            mons_mat[s_idx, 63] = min(1.5, spe_v / 250.0)

        return field_vec, mons_mat

    def encode_batch(
        self, states: List[Union[TurnSnapshot, Dict[str, Any]]]
    ) -> TurnStateTensor:
        """
        Encode a batch of B turn states into TurnStateTensor with shapes (B, 32) and (B, 4, 64).

        Args:
            states: Non-empty list of TurnSnapshot or simulator state dicts.

        Returns:
            TurnStateTensor allocated on target PyTorch device (or NumPy fallback).

        Raises:
            ValueError: If states list is empty.
        """
        if not states:
            raise ValueError("Cannot encode an empty batch of states.")

        b_size = len(states)
        batch_field = np.zeros((b_size, FIELD_TENSOR_DIM), dtype=np.float32)
        batch_mons = np.zeros((b_size, MON_SLOTS_COUNT, MON_FEATURE_DIM), dtype=np.float32)

        for idx, st in enumerate(states):
            f_vec, m_mat = self.encode_single_numpy(st)
            batch_field[idx] = f_vec
            batch_mons[idx] = m_mat

        if HAS_TORCH and torch is not None and self.device is not None:
            t_field = torch.from_numpy(batch_field).to(self.device, dtype=torch.float32)
            t_mons = torch.from_numpy(batch_mons).to(self.device, dtype=torch.float32)
            return TurnStateTensor(s_field=t_field, s_mons=t_mons, device=self.device_str)

        return TurnStateTensor(s_field=batch_field, s_mons=batch_mons, device="cpu")

    def encode(self, state: Union[TurnSnapshot, Dict[str, Any]]) -> TurnStateTensor:
        """Convenience method to encode a single state as a batch of size B=1."""
        return self.encode_batch([state])
