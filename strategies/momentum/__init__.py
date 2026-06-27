"""Cross-sectional 12-1 momentum strategy template."""

from strategies.momentum.signal import MomentumParams, generate_signals
from strategies.momentum.strategy import CrossSectionalMomentumStrategy

__all__ = [
    "CrossSectionalMomentumStrategy",
    "MomentumParams",
    "generate_signals",
]
