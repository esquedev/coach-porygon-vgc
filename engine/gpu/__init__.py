# -*- coding: utf-8 -*-
"""
Coach Porygon VGC — GPU Acceleration & Probabilistic Uncertainty Backend (engine/gpu/__init__.py)

Provides PyTorch CUDA / CPU vectorized tensor encoding, simultaneous payoff matrix
construction, and exact 16-roll discrete damage + critical hit + accuracy convolution
for the Pokémon Champions (Regulation M-C) competitive ecosystem.
"""

from engine.gpu.tensor_encoder import TensorEncoder, TurnStateTensor
from engine.gpu.payoff_builder import PayoffBuilder
from engine.gpu.uncertainty import UncertaintyModel, UncertaintyProfile

__all__ = [
    "TensorEncoder",
    "TurnStateTensor",
    "PayoffBuilder",
    "UncertaintyModel",
    "UncertaintyProfile",
]
