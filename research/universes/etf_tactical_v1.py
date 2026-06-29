"""Static low-budget ETF universe for tactical momentum v1."""

from __future__ import annotations

RISK_ASSETS: tuple[str, ...] = ("SPY", "QQQ", "IWM")
DEFENSIVE_ASSETS: tuple[str, ...] = ("IEF", "GLD", "SHY")
DIVERSIFIER_ASSETS: tuple[str, ...] = ("DBC",)
SYMBOLS: tuple[str, ...] = RISK_ASSETS + DEFENSIVE_ASSETS + DIVERSIFIER_ASSETS


def risk_assets() -> tuple[str, ...]:
    return RISK_ASSETS


def defensive_assets() -> tuple[str, ...]:
    return DEFENSIVE_ASSETS


def diversifier_assets() -> tuple[str, ...]:
    return DIVERSIFIER_ASSETS


def all_symbols() -> tuple[str, ...]:
    return SYMBOLS
