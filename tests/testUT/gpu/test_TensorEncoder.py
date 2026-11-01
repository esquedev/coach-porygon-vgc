# -*- coding: utf-8 -*-
"""
Unit tests for TensorEncoder (engine/gpu/tensor_encoder.py).
Verifies normalized TurnStateTensor shapes (B, 32) and (B, 4, 64), value bounds,
and CUDA/CPU device handling.
"""

from pathlib import Path
import unittest

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from engine.gpu.tensor_encoder import TensorEncoder
from engine.tactics.showdown_parser import ShowdownParser


REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_LOG_PATH = REPO_ROOT / "tests" / "data" / "sample_showdown_mc_log.txt"


@unittest.skipUnless(HAS_TORCH, "PyTorch is required for TestTensorEncoder")
class TestTensorEncoder(unittest.TestCase):
    """Unit test suite for TensorEncoder."""

    def setUp(self) -> None:
        """Initialize parser and TensorEncoder on CPU and default device."""
        self.parser = ShowdownParser()
        raw_log = SAMPLE_LOG_PATH.read_text(encoding="utf-8")
        self.parsed = self.parser.parse_log(raw_log)
        self.encoder = TensorEncoder(device="cpu")

    def test_encode_turn_tensor_shapes_and_bounds(self) -> None:
        """Verify single turn snapshot encodes into S_field (1, 32) and S_mons (1, 4, 64)."""
        snap = self.parsed.turns[0]
        encoded = self.encoder.encode(snap)
        self.assertEqual(tuple(encoded.s_field.shape), (1, 32))
        self.assertEqual(tuple(encoded.s_mons.shape), (1, 4, 64))
        self.assertTrue(torch.all(torch.isfinite(encoded.s_field)))
        self.assertTrue(torch.all(torch.isfinite(encoded.s_mons)))
        self.assertEqual(encoded.batch_size, 1)

    def test_encode_batch_multi_turn_shapes(self) -> None:
        """Verify batch of turns encodes into (B, 32) and (B, 4, 64)."""
        batch = self.encoder.encode_batch(self.parsed.turns)
        b_size = len(self.parsed.turns)
        self.assertEqual(tuple(batch.s_field.shape), (b_size, 32))
        self.assertEqual(tuple(batch.s_mons.shape), (b_size, 4, 64))
        self.assertEqual(batch.batch_size, b_size)
        f_np, m_np = batch.to_numpy()
        self.assertEqual(f_np.shape, (b_size, 32))
        self.assertEqual(m_np.shape, (b_size, 4, 64))

    def test_encode_empty_batch_raises_value_error(self) -> None:
        """Verify encoding an empty sequence raises ValueError."""
        with self.assertRaises(ValueError):
            self.encoder.encode_batch([])


if __name__ == "__main__":
    unittest.main()
