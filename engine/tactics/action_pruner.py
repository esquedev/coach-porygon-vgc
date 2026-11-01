# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Combinatorial Action Space Pruner (engine/tactics/action_pruner.py)

Prunes the raw 81x81 VGC joint action tree down to the Top-5 canonical tactical
lines per side using type effectiveness (TYPE_CHART), move metadata (MOVE_DB),
and move synergy (evaluate_move_synergy) from engine/turn_simulator.py.
Generates exact choice dictionaries for ClientReplaySimulator.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from engine.tactics.showdown_parser import (
    OpenTeamSheet,
    ShowdownParser,
    SlotState,
    TurnSnapshot,
)
from engine.turn_simulator import (
    BASE_STATS_DB,
    ClientReplaySimulator,
    MOVE_DB,
    PROTECT_MOVES,
    TYPE_CHART,
    evaluate_move_synergy,
)


CANONICAL_SPECIES_MOVES: Dict[str, Dict[str, str]] = {
    "Charizard": {
        "single": "Scorching Sands",
        "spread": "Heat Wave",
        "support": "Tailwind",
        "protect": "Protect",
    },
    "Charizard-Mega-Y": {
        "single": "Scorching Sands",
        "spread": "Heat Wave",
        "support": "Tailwind",
        "protect": "Protect",
    },
    "Kingambit": {
        "single": "Iron Head",
        "spread": "Kowtow Cleave",
        "support": "Sucker Punch",
        "protect": "Protect",
    },
    "Garchomp": {
        "single": "Stomping Tantrum",
        "spread": "Earthquake",
        "support": "Swords Dance",
        "protect": "Protect",
    },
    "Grimmsnarl": {
        "single": "Spirit Break",
        "spread": "Spirit Break",
        "support": "Reflect",
        "protect": "Protect",
    },
    "Sinistcha": {
        "single": "Matcha Gotcha",
        "spread": "Matcha Gotcha",
        "support": "Rage Powder",
        "protect": "Protect",
    },
    "Floette-Eternal": {
        "single": "Draining Kiss",
        "spread": "Dazzling Gleam",
        "support": "Calm Mind",
        "protect": "Protect",
    },
    "Floette-Mega": {
        "single": "Draining Kiss",
        "spread": "Dazzling Gleam",
        "support": "Calm Mind",
        "protect": "Protect",
    },
    "Sneasler": {
        "single": "Poison Jab",
        "spread": "Close Combat",
        "support": "Fake Out",
        "protect": "Quick Guard",
    },
    "Incineroar": {
        "single": "Flare Blitz",
        "spread": "Snarl",
        "support": "Fake Out",
        "protect": "Parting Shot",
    },
}


@dataclass
class PrunedActionLine:
    """Represents one of the Top-5 pruned canonical joint action lines for a side."""

    index: int
    category: str
    label: str
    slot_a_move: str
    slot_b_move: str
    simulator_choices: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tactical_prior: float = 0.0


class ActionPruner:
    """
    Reduces the combinatorial joint action space (up to 81 combinations per side)
    into the 5 canonical VGC macro-strategies grounded in engine/turn_simulator.py:
    0. Double Offensive Focus (Dual single-target concentration)
    1. Attack + Defensive Protect (Preserve threatened slot while partner attacks)
    2. Spread / Area Move (Un-redirectable multi-target offense)
    3. Speed Control / Redirection / Status (Tailwind, Trick Room, Rage Powder, Fake Out)
    4. Strategic Pivot / Switch (Defensive reposition to bench)
    """

    def __init__(self) -> None:
        """Initialize the ActionPruner with a ShowdownParser helper for simulator state conversion."""
        self._parser = ShowdownParser()

    def _get_move_kit(
        self, species: str, ots: Optional[OpenTeamSheet] = None
    ) -> Dict[str, str]:
        """
        Resolve canonical or OTS move kit for a species using turn_simulator.MOVE_DB.

        Args:
            species: Canonical species name.
            ots: Optional OpenTeamSheet for exact move extraction.

        Returns:
            Dictionary with keys 'single', 'spread', 'support', and 'protect'.
        """
        ots_member = ots.get_member(species) if ots else None
        if ots_member and ots_member.moves:
            moves = ots_member.moves
            prot_candidates = [
                m
                for m in moves
                if m in PROTECT_MOVES
                or m
                in (
                    "Protect",
                    "Detect",
                    "Quick Guard",
                    "Wide Guard",
                    "Spiky Shield",
                    "Baneful Bunker",
                    "Silk Trap",
                )
            ]
            prot_move = prot_candidates[0] if prot_candidates else "Protect"

            known_spread = {
                "Heat Wave",
                "Hyper Voice",
                "Explosion",
                "Earthquake",
                "Dazzling Gleam",
                "Rock Slide",
                "Muddy Water",
                "Snarl",
                "Make It Rain",
                "Electroweb",
                "Blizzard",
                "Discharge",
                "Icy Wind",
                "Diamond Storm",
                "Bleakwind Storm",
                "Wildbolt Storm",
                "Sandsear Storm",
                "Springtide Storm",
                "Expanding Force",
            }
            spread_candidates = [
                m
                for m in moves
                if m in known_spread
                or MOVE_DB.get(m, {}).get("target") in ("allAdjacentFoes", "allAdjacent")
            ]
            spread_move = spread_candidates[0] if spread_candidates else ""

            known_support = {
                "Tailwind",
                "Trick Room",
                "Fake Out",
                "Rage Powder",
                "Follow Me",
                "Parting Shot",
                "Spore",
                "Hypnosis",
                "Calm Mind",
                "Nasty Plot",
                "Swords Dance",
                "Eerie Impulse",
                "Helping Hand",
                "Dragon Cheer",
                "Screech",
                "Volt Switch",
                "U-turn",
                "Reflect",
                "Light Screen",
                "Thunder Wave",
                "Will-O-Wisp",
                "Yawn",
                "Taunt",
                "Encore",
                "Coil",
            }
            support_candidates = [
                m
                for m in moves
                if m in known_support
                or (MOVE_DB.get(m, {}).get("cat") == "Status" and m != prot_move)
            ]
            support_move = support_candidates[0] if support_candidates else prot_move

            single_candidates = [
                m
                for m in moves
                if m != prot_move
                and m != spread_move
                and MOVE_DB.get(m, {}).get("cat") in ("Physical", "Special")
            ]
            if single_candidates:
                single_move = single_candidates[0]
            else:
                attacks = [
                    m
                    for m in moves
                    if m != prot_move
                    and MOVE_DB.get(m, {}).get("cat") in ("Physical", "Special")
                ]
                single_move = attacks[0] if attacks else moves[0]

            if not spread_move:
                spread_move = single_move

            return {
                "single": single_move,
                "spread": spread_move,
                "support": support_move,
                "protect": prot_move,
            }

        if species in CANONICAL_SPECIES_MOVES:
            return CANONICAL_SPECIES_MOVES[species]
        return {
            "single": "Tackle" if "Tackle" in MOVE_DB else "Iron Head",
            "spread": "Heat Wave",
            "support": "Protect",
            "protect": "Protect",
        }

    def _compute_type_effectiveness_prior(
        self, move_name: str, target_species: str
    ) -> float:
        """Compute type multiplier of move_name against target_species via TYPE_CHART."""
        mv_info = MOVE_DB.get(move_name, {})
        mv_type = mv_info.get("type", "Normal")
        tgt_types = BASE_STATS_DB.get(target_species, {}).get("types", ["Normal"])
        mult = 1.0
        for t in tgt_types:
            mult *= TYPE_CHART.get(mv_type, {}).get(t, 1.0)
        return mult

    def prune_side_actions(
        self, snapshot: TurnSnapshot, side: str = "p1"
    ) -> List[PrunedActionLine]:
        """
        Generate the Top-5 canonical action lines for the requested side ('p1' or 'p2').

        Args:
            snapshot: Current TurnSnapshot board state.
            side: 'p1' or 'p2'.

        Returns:
            List of 5 PrunedActionLine objects with ClientReplaySimulator choices.

        Raises:
            ValueError: If side is not 'p1' or 'p2'.
        """
        if side not in ("p1", "p2"):
            raise ValueError(f"side must be 'p1' or 'p2', got '{side}'")

        my_slots: List[SlotState] = (
            snapshot.p1_slots if side == "p1" else snapshot.p2_slots
        )
        opp_slots: List[SlotState] = (
            snapshot.p2_slots if side == "p1" else snapshot.p1_slots
        )
        opp_prefix = "p2" if side == "p1" else "p1"

        slot_a = my_slots[0] if len(my_slots) > 0 else SlotState(species="Charizard")
        slot_b = my_slots[1] if len(my_slots) > 1 else SlotState(species="Kingambit")
        opp_a = opp_slots[0] if len(opp_slots) > 0 else SlotState(species="Sinistcha")
        opp_b = (
            opp_slots[1] if len(opp_slots) > 1 else SlotState(species="Floette-Eternal")
        )

        my_ots = snapshot.p1_ots if side == "p1" else snapshot.p2_ots
        opp_ots = snapshot.p2_ots if side == "p1" else snapshot.p1_ots

        kit_a = self._get_move_kit(slot_a.species, ots=my_ots)
        kit_b = self._get_move_kit(slot_b.species, ots=my_ots)

        slot_a_id = f"{side}a"
        slot_b_id = f"{side}b"
        opp_a_id = f"{opp_prefix}a"
        opp_b_id = f"{opp_prefix}b"

        # Evaluate move synergy via engine/turn_simulator.py
        field_dict = {"weather": snapshot.weather.lower(), "terrain": snapshot.terrain.lower()}
        syn_a = evaluate_move_synergy(
            slot_a.species, slot_a.ability, slot_a.item, kit_a["spread"], field_dict
        )
        syn_bonus = 0.15 if syn_a.get("synergy_detected") else 0.0

        eff_a = self._compute_type_effectiveness_prior(kit_a["single"], opp_a.species)
        eff_b = self._compute_type_effectiveness_prior(kit_b["single"], opp_a.species)
        off_prior = min(0.5, (eff_a + eff_b) * 0.1)

        # 0. Double Offensive Focus
        line_0 = PrunedActionLine(
            index=0,
            category="Double Offensive Focus",
            label=f"Double Offensive Focus ({kit_a['single']} + {kit_b['single']})",
            slot_a_move=kit_a["single"],
            slot_b_move=kit_b["single"],
            simulator_choices={
                slot_a_id: {"choice": "move", "move_name": kit_a["single"], "target": opp_a_id},
                slot_b_id: {"choice": "move", "move_name": kit_b["single"], "target": opp_a_id},
            },
            tactical_prior=round(off_prior, 3),
        )

        # 1. Attack + Defensive Protect
        line_1 = PrunedActionLine(
            index=1,
            category="Attack + Defensive Protect",
            label=f"Attack + Defensive Protect ({kit_a['protect']} + {kit_b['single']})",
            slot_a_move=kit_a["protect"],
            slot_b_move=kit_b["single"],
            simulator_choices={
                slot_a_id: {"choice": "move", "move_name": kit_a["protect"], "target": slot_a_id},
                slot_b_id: {"choice": "move", "move_name": kit_b["single"], "target": opp_b_id},
            },
            tactical_prior=0.20,
        )

        # 2. Spread / Area Move (Un-redirectable)
        known_spread_names = {
            "Heat Wave",
            "Hyper Voice",
            "Explosion",
            "Earthquake",
            "Dazzling Gleam",
            "Rock Slide",
            "Muddy Water",
            "Snarl",
            "Make It Rain",
            "Electroweb",
            "Blizzard",
            "Discharge",
            "Icy Wind",
            "Diamond Storm",
            "Bleakwind Storm",
            "Wildbolt Storm",
            "Sandsear Storm",
            "Springtide Storm",
            "Expanding Force",
        }
        spread_a = (
            kit_a["spread"]
            if kit_a["spread"] in known_spread_names
            or MOVE_DB.get(kit_a["spread"], {}).get("target") in ("allAdjacentFoes", "allAdjacent")
            else kit_a["single"]
        )
        spread_b = (
            kit_b["spread"]
            if kit_b["spread"] in known_spread_names
            or MOVE_DB.get(kit_b["spread"], {}).get("target") in ("allAdjacentFoes", "allAdjacent")
            else kit_b["single"]
        )
        if spread_a == kit_a["single"] and spread_b == kit_b["single"]:
            spread_a = kit_a["spread"]
        line_2 = PrunedActionLine(
            index=2,
            category="Spread / Area Move",
            label=f"Spread / Area Move ({spread_a} + {spread_b})",
            slot_a_move=spread_a,
            slot_b_move=spread_b,
            simulator_choices={
                slot_a_id: {"choice": "move", "move_name": spread_a, "target": opp_a_id},
                slot_b_id: {"choice": "move", "move_name": spread_b, "target": opp_a_id},
            },
            tactical_prior=round(0.30 + syn_bonus, 3),
        )

        # 3. Speed Control / Redirection / Status
        line_3 = PrunedActionLine(
            index=3,
            category="Speed Control / Redirection / Status",
            label=f"Speed Control / Redirection ({kit_a['support']} + {kit_b['single']})",
            slot_a_move=kit_a["support"],
            slot_b_move=kit_b["single"],
            simulator_choices={
                slot_a_id: {"choice": "move", "move_name": kit_a["support"], "target": opp_a_id},
                slot_b_id: {"choice": "move", "move_name": kit_b["single"], "target": opp_b_id},
            },
            tactical_prior=0.15,
        )

        # 4. Strategic Pivot / Switch
        my_bench = snapshot.p1_bench_species if side == "p1" else snapshot.p2_bench_species
        bench_pivot = my_bench[0] if my_bench else ("Milotic" if side == "p1" else "Incineroar")
        line_4 = PrunedActionLine(
            index=4,
            category="Strategic Pivot / Switch",
            label=f"Strategic Pivot / Switch (Switch->{bench_pivot} + {kit_b['single']})",
            slot_a_move="Switch",
            slot_b_move=kit_b["single"],
            simulator_choices={
                slot_a_id: {"choice": "switch", "switch_to": bench_pivot},
                slot_b_id: {"choice": "move", "move_name": kit_b["single"], "target": opp_a_id},
            },
            tactical_prior=0.10,
        )

        return [line_0, line_1, line_2, line_3, line_4]

    def prune_dominated_actions(
        self,
        payoff_matrix: Any,
        p1_lines: List[PrunedActionLine],
        p2_lines: List[PrunedActionLine],
        eps: float = 1e-6,
    ) -> Tuple[Any, List[PrunedActionLine], List[PrunedActionLine]]:
        """
        Eliminate strictly dominated row/column actions from a payoff matrix to maximize
        tactical density on GPU (ensuring N <= 36, M <= 36).

        Args:
            payoff_matrix: 2D array of shape (N, M) representing P1 payoffs.
            p1_lines: Candidate action lines for Player 1.
            p2_lines: Candidate action lines for Player 2.
            eps: Strict dominance margin epsilon.

        Returns:
            Tuple of (filtered_payoff_matrix, surviving_p1_lines, surviving_p2_lines).
        """
        import numpy as np

        mat = np.asarray(payoff_matrix, dtype=np.float64)
        n_rows, m_cols = mat.shape

        # Identify non-dominated P1 rows (keep at least 2 rows)
        keep_rows: List[int] = []
        for i in range(n_rows):
            dominated = False
            for k in range(n_rows):
                if i != k and np.all(mat[k, :] >= mat[i, :] + eps):
                    dominated = True
                    break
            if not dominated:
                keep_rows.append(i)
        if not keep_rows:
            keep_rows = list(range(n_rows))

        # Identify non-dominated P2 columns (P2 minimizes P1 payoff)
        keep_cols: List[int] = []
        for j in range(m_cols):
            dominated = False
            for l_idx in range(m_cols):
                if j != l_idx and np.all(mat[:, l_idx] <= mat[:, j] - eps):
                    dominated = True
                    break
            if not dominated:
                keep_cols.append(j)
        if not keep_cols:
            keep_cols = list(range(m_cols))

        filtered_mat = mat[np.ix_(keep_rows, keep_cols)]
        surv_p1 = [p1_lines[i] for i in keep_rows]
        surv_p2 = [p2_lines[j] for j in keep_cols]
        return filtered_mat, surv_p1, surv_p2

    def simulate_joint_outcome(
        self,
        snapshot: TurnSnapshot,
        p1_line: PrunedActionLine,
        p2_line: PrunedActionLine,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Execute deterministic turn simulation via ClientReplaySimulator for a (p1, p2) action pair.

        Args:
            snapshot: Pre-turn board snapshot.
            p1_line: Selected canonical action line for Player 1.
            p2_line: Selected canonical action line for Player 2.

        Returns:
            Tuple of (post_turn_state_dict, formatted_replay_log) produced by ClientReplaySimulator.
        """
        sim_state = self._parser.to_simulator_state(snapshot)
        combined_choices: Dict[str, Dict[str, Any]] = {}
        combined_choices.update(p1_line.simulator_choices)
        combined_choices.update(p2_line.simulator_choices)

        simulator = ClientReplaySimulator(sim_state, combined_choices, pov_player="p1")
        return simulator.run_turn(roll_mode="fixed", fixed_roll=0.925)
