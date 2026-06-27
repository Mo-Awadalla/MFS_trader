"""Cross-sectional mean reversion strategy template."""

from strategies.csmr.signal import CSMRParams, generate_signals
from strategies.csmr.strategy import CrossSectionalMeanReversionStrategy

__all__ = [
    "CSMRParams",
    "CrossSectionalMeanReversionStrategy",
    "generate_signals",
]
