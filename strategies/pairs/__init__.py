"""Pairs Trading strategy package."""

from strategies.pairs.discovery import (
    PairCandidate,
    PairRelationship,
    PairsParams,
    SpreadDiagnostics,
)
from strategies.pairs.strategy import PairsTradingStrategy, get_strategy

__all__ = [
    "PairCandidate",
    "PairRelationship",
    "PairsParams",
    "PairsTradingStrategy",
    "SpreadDiagnostics",
    "get_strategy",
]
