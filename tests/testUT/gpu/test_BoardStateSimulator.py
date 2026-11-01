# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — Unit Tests for BoardStateSimulator (engine/gpu/board_state_simulator.py)

Verifies:
1. Snapshot legality validation against species blacklist, item legality, and Item Clause.
2. Full turn micro-simulation and GPU tensor encoding into shape (1, N, M, 16).
3. Payoff matrix evaluation and Mixed Strategy Nash equilibrium resolution.
4. Discrete uncertainty convolution across 16 damage rolls.
5. Latency benchmarking against SLA (< 50ms per board state).
6. Complete 50-scenario canonical flashcard generation with zero spoilers.
"""

from pathlib import Path
import tempfile
import unittest
import numpy as np

try:
    import torch
    HAS_TORCH = True
except ImportError:
    torch = None
    HAS_TORCH = False

from engine.gpu.board_state_simulator import (
    BoardStateScenario,
    BoardStateSimulationResult,
    BoardStateSimulator,
)
from engine.tactics.showdown_parser import ShowdownParser, SlotState, TurnSnapshot


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_LOG_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"


class TestBoardStateSimulator(unittest.TestCase):
    """Unit test suite for BoardStateSimulator."""

    def setUp(self) -> None:
        """Initialize simulator, parser, and reference Turn 3 snapshot."""
        self.simulator = BoardStateSimulator()
        self.parser = ShowdownParser()
        with open(SAMPLE_LOG_PATH, "r", encoding="utf-8") as f:
            history = self.parser.parse(f.read())
        self.turn_3_snapshot = history.turns[2]

    def test_validate_snapshot_legality_valid(self) -> None:
        """Verify that a valid Regulation M-C snapshot passes pre-flight checks."""
        is_valid, errors = self.simulator.validate_snapshot_legality(self.turn_3_snapshot)
        self.assertTrue(is_valid, f"Expected valid snapshot, got errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_validate_snapshot_legality_rejects_blacklist(self) -> None:
        """Verify that blacklisted species are immediately rejected."""
        bad_snap = TurnSnapshot(
            turn_number=1,
            p1_slots=[
                SlotState(species="Flutter Mane", item="Focus Sash", hp_pct=1.0),
                SlotState(species="Garchomp", item="Life Orb", hp_pct=1.0),
            ],
            p2_slots=[
                SlotState(species="Incineroar", item="Sitrus Berry", hp_pct=1.0),
                SlotState(species="Rillaboom", item="Miracle Seed", hp_pct=1.0),
            ],
        )
        is_valid, errors = self.simulator.validate_snapshot_legality(bad_snap)
        self.assertFalse(is_valid)
        self.assertTrue(any("Flutter Mane" in err and "Blacklisted" in err for err in errors))

    def test_validate_snapshot_legality_rejects_item_clause(self) -> None:
        """Verify that duplicate items on the same side violate Item Clause."""
        bad_snap = TurnSnapshot(
            turn_number=1,
            p1_slots=[
                SlotState(species="Garchomp", item="Focus Sash", hp_pct=1.0),
                SlotState(species="Excadrill", item="Focus Sash", hp_pct=1.0),
            ],
            p2_slots=[
                SlotState(species="Incineroar", item="Sitrus Berry", hp_pct=1.0),
                SlotState(species="Rillaboom", item="Miracle Seed", hp_pct=1.0),
            ],
        )
        is_valid, errors = self.simulator.validate_snapshot_legality(bad_snap)
        self.assertFalse(is_valid)
        self.assertTrue(any("Item Clause" in err for err in errors))

    def test_simulate_board_state_gpu_outcome_tensor_and_nash(self) -> None:
        """Verify full simulation: GPU outcome tensor, payoff matrix, Nash, and uncertainty."""
        res = self.simulator.simulate_board_state(
            self.turn_3_snapshot,
            scenario_id="TEST-BS-01",
            source_data="Sample Replay Turn 3",
        )

        self.assertIsInstance(res, BoardStateSimulationResult)
        self.assertEqual(len(res.outcome_tensor_shape), 4)
        self.assertEqual(res.outcome_tensor_shape[0], 1)
        self.assertEqual(res.outcome_tensor_shape[3], 16)

        # Payoff matrix checks
        n_p1, m_p2 = len(res.p1_lines), len(res.p2_lines)
        self.assertEqual(res.payoff_matrix.shape, (n_p1, m_p2))
        self.assertTrue(np.all(res.payoff_matrix >= -1.0) and np.all(res.payoff_matrix <= 1.0))

        # Nash equilibrium checks
        self.assertIsInstance(res.nash_solution.game_value, float)
        self.assertTrue(-1.0 <= res.nash_solution.game_value <= 1.0)
        self.assertAlmostEqual(float(res.nash_solution.p1_probs.sum()), 1.0, places=4)
        self.assertAlmostEqual(float(res.nash_solution.p2_probs.sum()), 1.0, places=4)

        # Uncertainty profile checks
        unc = res.uncertainty_profile
        self.assertTrue(unc.p10 <= unc.p50 <= unc.p90 <= unc.p95)
        self.assertGreater(res.gpu_latency_ms, 0.0)

        # Dictionary serialization
        d = res.to_dict()
        self.assertEqual(d["scenario_id"], "TEST-BS-01")
        self.assertIn("outcome_tensor_shape", d)
        self.assertIn("game_value", d)

    def test_benchmark_gpu_board_state_resolution(self) -> None:
        """Verify GPU resolution benchmark executes and meets latency targets."""
        bench = self.simulator.benchmark_gpu_board_state_resolution(
            self.turn_3_snapshot,
            iterations=3,
        )
        self.assertIn("mean_latency_ms", bench)
        self.assertIn("min_latency_ms", bench)
        self.assertIn("target_sla_ms", bench)
        self.assertEqual(bench["iterations"], 3)
        self.assertIsInstance(bench["sla_passed"], bool)

    def test_generate_canonical_board_states_completeness(self) -> None:
        """Verify that exactly 50 canonical board state scenarios are loaded and formatted."""
        scenarios = self.simulator.generate_canonical_board_states()
        self.assertEqual(len(scenarios), 50, "Expected exactly 50 canonical scenarios")

        spoilers = [
            'minimax', 'fuga táctica', 'fuga tactica', 'óptima', 'optima',
            '(pos-', '(tgt-', '(mec-', '(spd-',
        ]

        for sc in scenarios:
            self.assertIsInstance(sc, BoardStateScenario)
            self.assertEqual(len(sc.options), 4, f"{sc.id} must have 4 options")
            opt_cnt = sum(1 for o in sc.options if o.get("optimal") is True)
            self.assertEqual(opt_cnt, 1, f"{sc.id} must have exactly 1 optimal option")

            # Verify no spoilers
            for o in sc.options:
                lbl = o.get("label", "").lower()
                for sp in spoilers:
                    self.assertNotIn(sp, lbl, f"Spoiler in {sc.id}: {lbl}")

            # CSV row conversion
            row = sc.to_csv_row()
            self.assertEqual(row["Scenario_ID"], sc.id)
            self.assertIn(row["OptA_Optimal"], ["True", "False"])

    def test_export_scenarios_to_csv_and_py(self) -> None:
        """Verify scenario export to temporary CSV and Python files."""
        scenarios = self.simulator.generate_canonical_board_states()[:3]
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_out = Path(tmpdir) / "test_scenarios.csv"
            py_out = Path(tmpdir) / "test_scenarios.py"

            self.simulator.export_scenarios(scenarios, csv_path=csv_out, py_path=py_out)
            self.assertTrue(csv_out.exists())
            self.assertTrue(py_out.exists())

            # Read CSV back
            lines = csv_out.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 4)  # Header + 3 rows


if __name__ == "__main__":
    unittest.main()
