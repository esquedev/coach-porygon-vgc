# -*- coding: utf-8 -*-
"""
VGC Tensor Core — Dynamic Showdown State Vector Translator & Checkpoint Manager
================================================================================

Reconstructs authentic, bit-exact Pokémon Showdown protocol lines entirely on the CPU
from GPU/CPU tensor state transitions ([F, P, M]), action choice vectors, and team manifests.
Maintains immutable CPU host checkpoints between calculation stages for full traceability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from .schema_and_tables import (
    CANONICAL_TERRAINS,
    CANONICAL_TYPES,
    CANONICAL_WEATHERS,
    FIELD_DIM,
    FieldIdx,
    HAS_TORCH,
    ItemID,
    MON_DIM,
    MOVE_DIM,
    MOVES_PER_MON,
    MonIdx,
    MoveIdx,
    ROSTER_SLOTS,
    SLOT_P1A,
    SLOT_P1B,
    SLOT_P1_BENCH1,
    SLOT_P1_BENCH2,
    SLOT_P2A,
    SLOT_P2B,
    SLOT_P2_BENCH1,
    SLOT_P2_BENCH2,
    TargetType,
)

if HAS_TORCH:
    import torch
    TensorOrArray = Union["torch.Tensor", np.ndarray]
else:
    TensorOrArray = np.ndarray

ACTIVE_SLOTS = (SLOT_P1A, SLOT_P1B, SLOT_P2A, SLOT_P2B)

SLOT_TO_IDENTIFIER: Dict[int, str] = {
    SLOT_P1A: "p1a",
    SLOT_P1B: "p1b",
    SLOT_P1_BENCH1: "p1_bench1",
    SLOT_P1_BENCH2: "p1_bench2",
    SLOT_P2A: "p2a",
    SLOT_P2B: "p2b",
    SLOT_P2_BENCH1: "p2_bench1",
    SLOT_P2_BENCH2: "p2_bench2",
}

STATUS_NAMES = ["healthy", "brn", "par", "slp", "frz", "psn", "tox"]


@dataclass
class SlotMetadata:
    """Carries human-readable Pokémon identity, permuting alongside tensor slots."""
    species: str
    nickname: Optional[str] = None
    level: int = 50
    gender: str = "M"
    item: str = "none"
    ability: str = "none"
    mega_species: Optional[str] = None
    moves: List[str] = field(default_factory=lambda: ["Protect", "Protect", "Protect", "Protect"])

    @property
    def display_name(self) -> str:
        return self.nickname or self.species


@dataclass
class TeamManifest:
    """Manifest of 8 Pokémon slots tracking active positions and switches."""
    slots: Dict[int, SlotMetadata]

    def permute_slots(self, slot_a: int, slot_b: int) -> None:
        """Swaps two slots in lockstep with the 8x8 switch permutation matrix."""
        self.slots[slot_a], self.slots[slot_b] = self.slots[slot_b], self.slots[slot_a]

    def clone(self) -> TeamManifest:
        return TeamManifest(
            slots={s: SlotMetadata(**vars(m)) for s, m in self.slots.items()}
        )


@dataclass(frozen=True)
class TurnCheckpoint:
    """Immutable CPU snapshot of board state at a specific sub-turn boundary."""
    turn_number: int
    stage: str
    F_cpu: np.ndarray
    P_cpu: np.ndarray
    M_cpu: np.ndarray
    manifest: TeamManifest
    showdown_lines: List[str]
    human_readable_log: List[str]


def _slice_to_cpu_numpy(tensor: TensorOrArray) -> np.ndarray:
    """Extracts batch 0, Monte Carlo sample 0 from GPU VRAM to CPU NumPy with exact terminal shapes."""
    if HAS_TORCH and isinstance(tensor, torch.Tensor):
        arr = tensor.detach().cpu().numpy()
    else:
        arr = np.asarray(tensor)

    # Global Field Tensor -> Target shape: (24,)
    if arr.shape[-1] == FIELD_DIM and arr.ndim > 1:
        while arr.ndim > 1:
            arr = arr[0]
        return arr

    # 8-Slot Roster Tensor -> Target shape: (8, 84)
    if arr.ndim >= 2 and arr.shape[-2:] == (ROSTER_SLOTS, MON_DIM):
        while arr.ndim > 2:
            arr = arr[0]
        return arr

    # 8-Slot Move Tensor -> Target shape: (8, 4, 52)
    if arr.ndim >= 3 and arr.shape[-3:] == (ROSTER_SLOTS, MOVES_PER_MON, MOVE_DIM):
        while arr.ndim > 3:
            arr = arr[0]
        return arr

    # Fallback flattening
    while arr.ndim > 2:
        arr = arr[0]
    return arr


class ShowdownStateTranslator:
    """
    Decodes tensor transitions on CPU into authentic Showdown wire protocol lines.
    Produces dual protocol output: standard pipe syntax + formatted board summary table.
    """

    def __init__(self, manifest: Optional[TeamManifest] = None):
        self.manifest = manifest or self._create_default_manifest()
        self.checkpoints: Dict[str, TurnCheckpoint] = {}

    def _create_default_manifest(self) -> TeamManifest:
        return TeamManifest(
            slots={
                SLOT_P1A: SlotMetadata(species="Raichu", mega_species="Raichu-Mega-X", moves=["Fake Out", "Volt Tackle", "Protect", "Volt Switch"]),
                SLOT_P1B: SlotMetadata(species="Kingambit", moves=["Kowtow Cleave", "Iron Head", "Sucker Punch", "Protect"]),
                SLOT_P1_BENCH1: SlotMetadata(species="Garchomp", moves=["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]),
                SLOT_P1_BENCH2: SlotMetadata(species="Charizard", moves=["Heat Wave", "Air Slash", "Solar Beam", "Protect"]),
                SLOT_P2A: SlotMetadata(species="Rillaboom", moves=["Grassy Glide", "Wood Hammer", "Fake Out", "U-turn"]),
                SLOT_P2B: SlotMetadata(species="Charizard", mega_species="Charizard-Mega-Y", moves=["Heat Wave", "Solar Beam", "Air Slash", "Protect"]),
                SLOT_P2_BENCH1: SlotMetadata(species="Raichu", moves=["Thunderbolt", "Volt Switch", "Protect", "Fake Out"]),
                SLOT_P2_BENCH2: SlotMetadata(species="Basculegion-F", moves=["Wave Crash", "Shadow Ball", "Ice Beam", "Protect"]),
            }
        )

    def _parse_wire_to_english(self, wire_lines: List[str]) -> List[str]:
        """Lightweight parser to translate Showdown wire protocol into human-readable English."""
        english_log = []
        def clean_name(raw: str) -> str:
            return raw.split(":", 1)[1].strip() if ":" in raw else raw

        for line in wire_lines:
            if not line.startswith("|"):
                continue
            parts = line.split("|")[1:]
            if not parts:
                continue
            
            tag = parts[0]
            if tag == "turn":
                english_log.append(f"--- Turn {parts[1]} Actions ---")
            elif tag == "switch":
                incoming = parts[2].split(",")[0]
                english_log.append(f"{clean_name(parts[1])} switched out for {incoming}!")
            elif tag == "move":
                actor, move = clean_name(parts[1]), parts[2]
                target = f" on {clean_name(parts[3])}" if len(parts) > 3 and parts[3] else ""
                english_log.append(f"{actor} used {move}{target}!")
            elif tag == "-damage":
                english_log.append(f"{clean_name(parts[1])} took damage! (HP: {parts[2]})")
            elif tag == "-heal":
                english_log.append(f"{clean_name(parts[1])} restored some HP.")
            elif tag == "faint":
                english_log.append(f"{clean_name(parts[1])} fainted!")
            elif tag == "cant":
                reason = "flinched and couldn't move" if parts[2] == "flinch" else f"couldn't move ({parts[2]})"
                english_log.append(f"{clean_name(parts[1])} {reason}!")
            elif tag == "-mega":
                english_log.append(f"{clean_name(parts[1])} Mega Evolved into {parts[2]}!")
            elif tag in ("-weather", "-fieldstart"):
                effect = parts[1].replace("move: ", "")
                english_log.append(f"The field changed to {effect}!")

        return english_log

    def save_checkpoint(
        self,
        turn: int,
        stage: str,
        F: TensorOrArray,
        P: TensorOrArray,
        M_moves: TensorOrArray,
        showdown_lines: List[str],
        human_readable: List[str],
    ) -> TurnCheckpoint:
        """Captures an immutable CPU host checkpoint for audit and rollback."""
        cp = TurnCheckpoint(
            turn_number=turn,
            stage=stage,
            F_cpu=_slice_to_cpu_numpy(F).copy(),
            P_cpu=_slice_to_cpu_numpy(P).copy(),
            M_cpu=_slice_to_cpu_numpy(M_moves).copy(),
            manifest=self.manifest.clone(),
            showdown_lines=list(showdown_lines),
            human_readable_log=list(human_readable),
        )
        self.checkpoints[f"T{turn}_{stage}"] = cp
        return cp

    def decode_turn_events(
        self,
        turn: int,
        pre_F: TensorOrArray,
        pre_P: TensorOrArray,
        pre_M: TensorOrArray,
        post_step_res: Any,
        p1_choices: TensorOrArray,
        p2_choices: TensorOrArray,
    ) -> Tuple[List[str], List[str]]:
        """
        Dynamically reconstructs full Showdown wire protocol lines and summary table
        purely by comparing pre- and post-tensor slices on the CPU.
        """
        f_pre = _slice_to_cpu_numpy(pre_F)
        p_pre = _slice_to_cpu_numpy(pre_P)
        f_post = _slice_to_cpu_numpy(post_step_res.F)
        p_post = _slice_to_cpu_numpy(post_step_res.P)

        if p1_choices.ndim > 1:
            c1 = p1_choices[0].detach().cpu().numpy() if (HAS_TORCH and isinstance(p1_choices, torch.Tensor)) else np.asarray(p1_choices[0])
        else:
            c1 = p1_choices.detach().cpu().numpy() if (HAS_TORCH and isinstance(p1_choices, torch.Tensor)) else np.asarray(p1_choices)

        if p2_choices.ndim > 1:
            c2 = p2_choices[0].detach().cpu().numpy() if (HAS_TORCH and isinstance(p2_choices, torch.Tensor)) else np.asarray(p2_choices[0])
        else:
            c2 = p2_choices.detach().cpu().numpy() if (HAS_TORCH and isinstance(p2_choices, torch.Tensor)) else np.asarray(p2_choices)

        p1_choice_tuple = (int(c1[0]), int(c1[1]))
        p2_choice_tuple = (int(c2[0]), int(c2[1]))

        showdown_lines: List[str] = [f"|turn|{turn}"]

        # ---------------------------------------------------------------------
        # 1. BARRIER 1: VOLUNTARY SWITCHES
        # ---------------------------------------------------------------------
        choices_map = {
            SLOT_P1A: p1_choice_tuple[0],
            SLOT_P1B: p1_choice_tuple[1],
            SLOT_P2A: p2_choice_tuple[0],
            SLOT_P2B: p2_choice_tuple[1],
        }

        switched_incoming_hps: Dict[int, Tuple[float, float]] = {}

        for act_slot, choice_val in choices_map.items():
            if choice_val in (24, 25):  # Switch Bench 1 or Bench 2
                bench_slot = (SLOT_P1_BENCH1 if choice_val == 24 else SLOT_P1_BENCH2) if act_slot < 4 else (SLOT_P2_BENCH1 if choice_val == 24 else SLOT_P2_BENCH2)
                outgoing_meta = self.manifest.slots[act_slot]
                incoming_meta = self.manifest.slots[bench_slot]

                ident = SLOT_TO_IDENTIFIER[act_slot]
                # Incoming Pokémon HP comes from pre-switch bench slot
                hp_cur_enter = int(p_pre[bench_slot, MonIdx.HP_CUR])
                hp_max_enter = int(p_pre[bench_slot, MonIdx.HP_MAX])
                pct = (hp_cur_enter / max(1, hp_max_enter)) * 100.0

                showdown_lines.append(
                    f"|switch|{ident}: {outgoing_meta.display_name}|{incoming_meta.species}, L{incoming_meta.level}, {incoming_meta.gender}|{hp_cur_enter}/{hp_max_enter} ({pct:.1f}%)"
                )
                switched_incoming_hps[act_slot] = (float(hp_cur_enter), float(hp_max_enter))
                self.manifest.permute_slots(act_slot, bench_slot)

        # ---------------------------------------------------------------------
        # 2. BARRIER 2: MEGA EVOLUTION
        # ---------------------------------------------------------------------
        for act_slot, choice_val in choices_map.items():
            if 12 <= choice_val <= 23:  # Mega evolution choice
                meta = self.manifest.slots[act_slot]
                ident = SLOT_TO_IDENTIFIER[act_slot]
                mega_name = meta.mega_species or f"{meta.species}-Mega"
                stone_name = f"{meta.species}ite"

                showdown_lines.append(f"|detailschange|{ident}: {meta.display_name}|{mega_name}, L{meta.level}, {meta.gender}")
                showdown_lines.append(f"|-mega|{ident}: {meta.display_name}|{mega_name}|{stone_name}")

                ab_lower = meta.ability.lower()
                if "electric surge" in ab_lower:
                    showdown_lines.append(f"|-fieldstart|move: Electric Terrain|[from] ability: Electric Surge|[of] {ident}: {meta.display_name}")
                elif "drought" in ab_lower:
                    showdown_lines.append(f"|-weather|SunnyDay|[from] ability: Drought|[of] {ident}: {meta.display_name}")
                elif "drizzle" in ab_lower:
                    showdown_lines.append(f"|-weather|RainDance|[from] ability: Drizzle|[of] {ident}: {meta.display_name}")
                elif "grassy surge" in ab_lower:
                    showdown_lines.append(f"|-fieldstart|move: Grassy Terrain|[from] ability: Grassy Surge|[of] {ident}: {meta.display_name}")

        # ---------------------------------------------------------------------
        # 3. PHASE 4: SPEED-ORDERED ATTACK CASCADE RESOLUTION
        # ---------------------------------------------------------------------
        # Extract post-cascade roster tensor BEFORE Phase 5 flinch reset
        p_cascade = _slice_to_cpu_numpy(post_step_res.attack_cascade.P)

        exec_order = post_step_res.pre_attack.execution_order
        if HAS_TORCH and isinstance(exec_order, torch.Tensor):
            order_indices = exec_order.detach().cpu().numpy()
        else:
            order_indices = np.asarray(exec_order)
        while order_indices.ndim > 1:
            order_indices = order_indices[0]

        active_slot_array = [SLOT_P1A, SLOT_P1B, SLOT_P2A, SLOT_P2B]

        for order_k in order_indices:
            actor_slot = active_slot_array[int(order_k)]
            choice_val = choices_map[actor_slot]

            if choice_val in (24, 25):
                continue  # Switched in Barrier 1

            actor_meta = self.manifest.slots[actor_slot]
            actor_ident = SLOT_TO_IDENTIFIER[actor_slot]

            # Check if actor flinched in attack cascade (before EOT reset)
            if p_cascade[actor_slot, MonIdx.FLINCHED] > 0.5:
                showdown_lines.append(f"|cant|{actor_ident}: {actor_meta.display_name}|flinch")
                continue

            move_slot = choice_val % 4
            move_name = actor_meta.moves[move_slot] if move_slot < len(actor_meta.moves) else f"Move_{move_slot}"

            # Target Resolution
            target_slot = self._resolve_target_slot(actor_slot, choice_val)
            target_meta = self.manifest.slots[target_slot]
            target_ident = SLOT_TO_IDENTIFIER[target_slot]

            # Check Protect
            if p_post[target_slot, MonIdx.PROTECT_ACTIVE] > 0.5:
                showdown_lines.append(f"|move|{actor_ident}: {actor_meta.display_name}|{move_name}|{target_ident}: {target_meta.display_name}")
                showdown_lines.append(f"|-activate|{target_ident}: {target_meta.display_name}|move: Protect")
                continue

            showdown_lines.append(f"|move|{actor_ident}: {actor_meta.display_name}|{move_name}|{target_ident}: {target_meta.display_name}")

            # Calculate damage
            if target_slot in switched_incoming_hps:
                hp_before, hp_max = switched_incoming_hps[target_slot]
            else:
                hp_before = float(p_pre[target_slot, MonIdx.HP_CUR])
                hp_max = float(p_post[target_slot, MonIdx.HP_MAX])

            hp_after = float(p_post[target_slot, MonIdx.HP_CUR])
            dmg_taken = max(0.0, hp_before - hp_after)

            if dmg_taken > 0.0:
                pct = (hp_after / max(1.0, hp_max)) * 100.0
                showdown_lines.append(f"|-damage|{target_ident}: {target_meta.display_name}|{hp_after:.0f}/{hp_max:.0f} ({pct:.1f}%)")

            # Check faint
            if hp_after <= 0.0:
                showdown_lines.append(f"|faint|{target_ident}: {target_meta.display_name}")
        # ---------------------------------------------------------------------
        # 4. PHASE 5: END-OF-TURN RESIDUALS
        # ---------------------------------------------------------------------
        for slot in ACTIVE_SLOTS:
            meta = self.manifest.slots[slot]
            ident = SLOT_TO_IDENTIFIER[slot]
            cur_hp = float(p_post[slot, MonIdx.HP_CUR])
            max_hp = float(p_post[slot, MonIdx.HP_MAX])

            # Grassy Terrain Heal
            is_grassy = f_post[FieldIdx.TERRAIN_START + 2] > 0.5
            is_grounded = p_post[slot, MonIdx.GROUNDED_FLAG] > 0.5
            if is_grassy and is_grounded and 0.0 < cur_hp < max_hp:
                showdown_lines.append(f"|-heal|{ident}: {meta.display_name}|{cur_hp:.0f}/{max_hp:.0f}|[from] Grassy Terrain")

        showdown_lines.append("|upkeep")

        # ---------------------------------------------------------------------
        # 5. HUMAN-READABLE BOARD STATE SUMMARY TABLE & ACTION LOG
        # ---------------------------------------------------------------------
        human_actions = self._parse_wire_to_english(showdown_lines)
        summary_table = self.describe_board_state(f_post, p_post, turn)
        
        # Combine the English actions and the ASCII board into a single log
        combined_human_log = human_actions + [""] + summary_table

        return showdown_lines, combined_human_log

    def _resolve_target_slot(self, actor_slot: int, choice_val: int) -> int:
        """Translates discrete 26-choice index into concrete target slot."""
        if actor_slot in (SLOT_P1A, SLOT_P1B):
            if choice_val in (0, 1, 2, 3, 12, 13, 14, 15):
                return SLOT_P2A
            elif choice_val in (4, 5, 6, 7, 16, 17, 18, 19):
                return SLOT_P2B
            else:
                return SLOT_P1B if actor_slot == SLOT_P1A else SLOT_P1A
        else:
            if choice_val in (0, 1, 2, 3, 12, 13, 14, 15):
                return SLOT_P1A
            elif choice_val in (4, 5, 6, 7, 16, 17, 18, 19):
                return SLOT_P1B
            else:
                return SLOT_P2B if actor_slot == SLOT_P2A else SLOT_P2A

    def describe_board_state(self, f_arr: np.ndarray, p_arr: np.ndarray, turn_number: int) -> List[str]:
        """Generates formatted human-readable ASCII summary table."""
        while f_arr.ndim > 1:
            f_arr = f_arr[0]
        while p_arr.ndim > 2:
            p_arr = p_arr[0]

        lines: List[str] = [f"=== Board State at Turn {turn_number} ==="]

        w_idx = int(np.argmax(f_arr[FieldIdx.WEATHER_START:FieldIdx.WEATHER_END]))
        w_turns = int(f_arr[FieldIdx.WEATHER_TURNS])
        w_name = CANONICAL_WEATHERS[w_idx]

        t_idx = int(np.argmax(f_arr[FieldIdx.TERRAIN_START:FieldIdx.TERRAIN_END]))
        t_turns = int(f_arr[FieldIdx.TERRAIN_TURNS])
        t_name = CANONICAL_TERRAINS[t_idx]

        lines.append(f"Field: Weather = {w_name} ({w_turns} turns left) | Terrain = {t_name} ({t_turns} turns left)")

        for slot in (SLOT_P1A, SLOT_P1B, SLOT_P2A, SLOT_P2B):
            side = "Player 1" if slot < 4 else "Player 2"
            slot_str = SLOT_TO_IDENTIFIER[slot]
            meta = self.manifest.slots[slot]
            name = meta.mega_species if (p_arr[slot, MonIdx.IS_MEGA] > 0.5 and meta.mega_species) else meta.display_name

            hp_cur = float(p_arr[slot, MonIdx.HP_CUR])
            hp_max = float(p_arr[slot, MonIdx.HP_MAX])
            hp_pct = (hp_cur / max(1.0, hp_max)) * 100.0

            status_idx = int(np.argmax(p_arr[slot, MonIdx.STATUS_START:MonIdx.STATUS_END]))
            status_str = f" [{STATUS_NAMES[status_idx].upper()}]" if status_idx > 0 else ""

            vols = []
            if p_arr[slot, MonIdx.FLINCHED] > 0.5:
                vols.append("Flinched")
            if p_arr[slot, MonIdx.PROTECT_ACTIVE] > 0.5:
                vols.append("Protected")
            if p_arr[slot, MonIdx.IS_MEGA] > 0.5:
                vols.append("Mega-Evolved")

            vol_str = f" ({', '.join(vols)})" if vols else ""
            alive_tag = "ALIVE" if hp_cur > 0.0 else "FAINTED"

            lines.append(
                f"  [{side}] {slot_str}: {name} -> {hp_cur:.0f}/{hp_max:.0f} HP ({hp_pct:.1f}%){status_str}{vol_str} [{alive_tag}]"
            )

        return lines