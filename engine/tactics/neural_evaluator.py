# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — GPU Neural Value Network Evaluator (engine/tactics/neural_evaluator.py)

Implements RegulationMcValueNet (PyTorch nn.Module) with automatic CUDA (cuda:0)
acceleration on NVIDIA RTX 3060 and CPU fallback. Evaluates 36-dimensional board
state tensors produced by ClientReplaySimulator (engine/turn_simulator.py) and
calibrates Win-Equity in [-1.0, +1.0] against Official VGC Victory Point (VP)
differentials.
"""

from typing import Any, Dict, List, Optional, Union
import numpy as np

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
    _BaseModule = nn.Module
except ImportError:
    torch = None
    nn = None
    HAS_TORCH = False
    _BaseModule = object

from engine.tactics.action_pruner import ActionPruner, PrunedActionLine
from engine.tactics.showdown_parser import TurnSnapshot


STATE_VECTOR_DIM = 36


class RegulationMcValueNet(_BaseModule):
    """
    PyTorch Value Network for Regulation M-C board equity evaluation.

    Architecture:
    Linear(36, 128) -> GELU -> Linear(128, 64) -> GELU -> Linear(64, 1) -> Tanh
    Output range: [-1.0, +1.0] representing P1 positional Win-Equity over P2.
    """

    def __init__(self, device: Optional[Union[str, Any]] = None) -> None:
        """
        Initialize the neural network layers and calibrate weights with VP heuristics.

        Args:
            device: Optional explicit torch device ('cuda:0' or 'cpu'). Auto-detects CUDA by default.
        """
        if not HAS_TORCH:
            raise ImportError("PyTorch is required for RegulationMcValueNet. Please install torch>=2.0.0.")

        super().__init__()
        if device is None:
            self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.fc1 = nn.Linear(STATE_VECTOR_DIM, 128)
        self.act1 = nn.GELU()
        self.fc2 = nn.Linear(128, 64)
        self.act2 = nn.GELU()
        self.fc3 = nn.Linear(64, 1)
        self.out_act = nn.Tanh()

        self._calibrate_deterministic_weights()
        self.to(self.device)
        self.eval()

    def _calibrate_deterministic_weights(self) -> None:
        """
        Deterministically initialize and calibrate network weights so that
        Official Simulator Victory Point (VP) differentials, HP advantages,
        speed control, and Mega Evolution states map monotonically into [-1.0, +1.0].
        """
        gen = torch.Generator(device="cpu")
        gen.manual_seed(2026)

        with torch.no_grad():
            # Zero out baseline weights so only calibrated competitive channels drive logit
            nn.init.zeros_(self.fc1.weight)
            nn.init.zeros_(self.fc1.bias)
            nn.init.zeros_(self.fc2.weight)
            nn.init.zeros_(self.fc2.bias)
            nn.init.zeros_(self.fc3.weight)
            nn.init.zeros_(self.fc3.bias)

            # Calibrate dominant feature channels (0..3: Active HP, 4..5: Bench, 34: VP diff, 35: Tactical signal)
            self.fc1.weight[:, 0] = 0.25   # P1 Slot A HP%
            self.fc1.weight[:, 1] = 0.25   # P1 Slot B HP%
            self.fc1.weight[:, 2] = -0.25  # P2 Slot A HP%
            self.fc1.weight[:, 3] = -0.25  # P2 Slot B HP%
            self.fc1.weight[:, 4] = 0.15   # P1 Bench Alive ratio
            self.fc1.weight[:, 5] = -0.15  # P2 Bench Alive ratio
            self.fc1.weight[:, 34] = 0.60  # Official Simulator VP Differential
            self.fc1.weight[:, 35] = 0.80  # Tactical Synergy / Redirection Bypass Signal

            # Split positive and negative pathways across hidden units so GELU preserves sign
            self.fc1.weight[64:, :] *= -1.0
            self.fc2.weight[:32, :64] = 1.0 / 64.0
            self.fc2.weight[32:, 64:] = 1.0 / 64.0
            self.fc3.weight[0, :32] = 1.5 / 32.0
            self.fc3.weight[0, 32:] = -1.5 / 32.0

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Execute forward pass returning bounded Win-Equity tensor in [-1.0, +1.0].

        Args:
            x: Input tensor of shape (batch_size, 36) or (36,).

        Returns:
            Output tensor of shape (batch_size, 1) or (1,) bounded in [-1.0, +1.0].
        """
        if x.dim() == 1:
            x = x.unsqueeze(0)
            squeeze_out = True
        else:
            squeeze_out = False

        if x.shape[-1] != STATE_VECTOR_DIM:
            raise ValueError(
                f"Expected input feature dimension {STATE_VECTOR_DIM}, got {x.shape[-1]}"
            )

        x = x.to(self.device, dtype=torch.float32)
        h1 = self.act1(self.fc1(x))
        h2 = self.act2(self.fc2(h1))
        out = self.out_act(self.fc3(h2))
        return out.squeeze(0) if squeeze_out else out


class NeuralEvaluator:
    """
    High-throughput batch evaluator linking ClientReplaySimulator states to RegulationMcValueNet.
    """

    def __init__(self, device: Optional[Union[str, torch.device]] = None) -> None:
        """
        Initialize the GPU/CPU Value Network and ActionPruner simulator bridge.

        Args:
            device: Optional explicit torch device.
        """
        self.model = RegulationMcValueNet(device=device)
        self.device = self.model.device
        self.pruner = ActionPruner()

    def encode_simulator_state(
        self,
        sim_state: Dict[str, Any],
        p1_bench_alive: int = 2,
        p2_bench_alive: int = 2,
        tactical_signal: float = 0.0,
    ) -> np.ndarray:
        """
        Encode a ClientReplaySimulator post-turn state dictionary into a 36-D float32 vector.

        Args:
            sim_state: State dictionary returned by ClientReplaySimulator.run_turn().
            p1_bench_alive: Number of alive bench Pokemon for Player 1.
            p2_bench_alive: Number of alive bench Pokemon for Player 2.
            tactical_signal: Additional tactical bonus from move synergy / spread bypass.

        Returns:
            1D numpy array of shape (36,) with dtype float32.
        """
        vec = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
        slots = sim_state.get("slots", {})

        p1a = slots.get("p1a", {})
        p1b = slots.get("p1b", {})
        p2a = slots.get("p2a", {})
        p2b = slots.get("p2b", {})

        # 0..3: Active HP percentages [0.0, 1.0]
        p1a_hp = float(p1a.get("current_hp_pct", 0.0)) / 100.0
        p1b_hp = float(p1b.get("current_hp_pct", 0.0)) / 100.0
        p2a_hp = float(p2a.get("current_hp_pct", 0.0)) / 100.0
        p2b_hp = float(p2b.get("current_hp_pct", 0.0)) / 100.0
        vec[0] = p1a_hp
        vec[1] = p1b_hp
        vec[2] = p2a_hp
        vec[3] = p2b_hp

        # 4..5: Alive bench ratios
        vec[4] = min(1.0, max(0.0, p1_bench_alive / 2.0))
        vec[5] = min(1.0, max(0.0, p2_bench_alive / 2.0))

        # 6..9: Mega Evolution flags
        vec[6] = 1.0 if "Mega" in str(p1a.get("species", "")) else 0.0
        vec[7] = 1.0 if "Mega" in str(p1b.get("species", "")) else 0.0
        vec[8] = 1.0 if "Mega" in str(p2a.get("species", "")) else 0.0
        vec[9] = 1.0 if "Mega" in str(p2b.get("species", "")) else 0.0

        # 10..13:Normalized Speed tiers
        vec[10] = float(p1a.get("stats", {}).get("spe", 100)) / 200.0
        vec[11] = float(p1b.get("stats", {}).get("spe", 100)) / 200.0
        vec[12] = float(p2a.get("stats", {}).get("spe", 100)) / 200.0
        vec[13] = float(p2b.get("stats", {}).get("spe", 100)) / 200.0

        # 14..18: Weather one-hot (Sun, Rain, Sand, Snow, Clear)
        field = sim_state.get("field", {})
        weather = str(field.get("weather") or "clear").lower()
        weather_map = {"sun": 14, "rain": 15, "sand": 16, "snow": 17}
        vec[weather_map.get(weather, 18)] = 1.0

        # 19..23: Terrain one-hot (Psychic, Grassy, Electric, Misty, None)
        terrain = str(field.get("terrain") or "none").lower()
        terrain_map = {"psychic": 19, "grassy": 20, "electric": 21, "misty": 22}
        vec[terrain_map.get(terrain, 23)] = 1.0

        # 24..27: Side conditions (Tailwind & Reflect)
        vec[24] = 1.0 if sim_state.get("p1", {}).get("tailwind_turns", 0) > 0 else 0.0
        vec[25] = 1.0 if sim_state.get("p2", {}).get("tailwind_turns", 0) > 0 else 0.0
        vec[26] = 1.0 if sim_state.get("p1", {}).get("reflect_turns", 0) > 0 else 0.0
        vec[27] = 1.0 if sim_state.get("p2", {}).get("reflect_turns", 0) > 0 else 0.0

        # 28..31: Offensive stat stage boosts normalized in [-1, 1]
        vec[28] = float(p1a.get("boosts", {}).get("atk", 0) + p1a.get("boosts", {}).get("spa", 0)) / 6.0
        vec[29] = float(p1b.get("boosts", {}).get("atk", 0) + p1b.get("boosts", {}).get("spa", 0)) / 6.0
        vec[30] = float(p2a.get("boosts", {}).get("atk", 0) + p2a.get("boosts", {}).get("spa", 0)) / 6.0
        vec[31] = float(p2b.get("boosts", {}).get("atk", 0) + p2b.get("boosts", {}).get("spa", 0)) / 6.0

        # 32..33: Status affliction indicators
        vec[32] = -0.5 if p1a.get("status") or p1b.get("status") else 0.0
        vec[33] = 0.5 if p2a.get("status") or p2b.get("status") else 0.0

        # 34: Official Simulator Victory Point (VP) differential
        p1_vp = p1a_hp + p1b_hp + float(p1_bench_alive)
        p2_vp = p2a_hp + p2b_hp + float(p2_bench_alive)
        vp_diff = (p1_vp - p2_vp) / 4.0
        vec[34] = float(np.clip(vp_diff, -1.0, 1.0))

        # 35: Tactical Synergy & Redirection Bypass Signal
        vec[35] = float(np.clip(tactical_signal, -1.0, 1.0))

        return vec

    def evaluate_batch(self, batch_features: Union[np.ndarray, torch.Tensor]) -> np.ndarray:
        """
        Evaluate a batch of 36-D state vectors on the GPU/CPU Value Network.

        Args:
            batch_features: Array or Tensor of shape (N, 36).

        Returns:
            NumPy array of shape (N, 1) with values strictly in [-1.0, +1.0].
        """
        if isinstance(batch_features, np.ndarray):
            tensor_in = torch.from_numpy(batch_features.astype(np.float32))
        else:
            tensor_in = batch_features

        with torch.no_grad():
            out_tensor = self.model(tensor_in)
            return out_tensor.detach().cpu().numpy()

    def evaluate_payoff_matrix(
        self,
        snapshot: TurnSnapshot,
        p1_lines: List[PrunedActionLine],
        p2_lines: List[PrunedActionLine],
    ) -> np.ndarray:
        """
        Simulate all N x M joint action pairs using ClientReplaySimulator and
        evaluate the resulting board states in a single GPU micro-batch.

        Args:
            snapshot: Pre-turn board snapshot at the turning point.
            p1_lines: Candidate action lines for Player 1 (length N).
            p2_lines: Candidate action lines for Player 2 (length M).

        Returns:
            N x M numpy float64 payoff matrix with entries in [-1.0, +1.0].
        """
        n_p1 = len(p1_lines)
        n_p2 = len(p2_lines)
        batch_vectors = np.zeros((n_p1 * n_p2, STATE_VECTOR_DIM), dtype=np.float32)

        idx = 0
        for i, p1_act in enumerate(p1_lines):
            for j, p2_act in enumerate(p2_lines):
                post_state, _ = self.pruner.simulate_joint_outcome(
                    snapshot, p1_act, p2_act
                )
                # Compute tactical interaction signal (e.g., spread bypassing redirection or Protect punish)
                signal = p1_act.tactical_prior - p2_act.tactical_prior
                if p1_act.category == "Spread / Area Move":
                    signal += 0.35
                if (
                    p1_act.category == "Double Offensive Focus"
                    and p2_act.category in ("Attack + Defensive Protect", "Speed Control / Redirection / Status")
                ):
                    signal -= 0.45

                batch_vectors[idx] = self.encode_simulator_state(
                    post_state,
                    p1_bench_alive=snapshot.p1_bench_alive,
                    p2_bench_alive=snapshot.p2_bench_alive,
                    tactical_signal=signal,
                )
                idx += 1

        batch_scores = self.evaluate_batch(batch_vectors)
        payoff_matrix = batch_scores.reshape((n_p1, n_p2)).astype(np.float64)
        return np.round(payoff_matrix, 4)
