"""Static ETF universe for Global Dual Momentum Defensive v1."""

from __future__ import annotations

RISK_ASSETS: tuple[str, ...] = ("SPY", "QQQ", "IWM", "EFA", "EEM")
DEFENSIVE_ASSETS: tuple[str, ...] = ("IEF", "TLT", "SHY")
SYMBOLS: tuple[str, ...] = RISK_ASSETS + DEFENSIVE_ASSETS


def risk_assets() -> tuple[str, ...]:
    return RISK_ASSETS


def defensive_assets() -> tuple[str, ...]:
    return DEFENSIVE_ASSETS


def all_symbols() -> tuple[str, ...]:
    return SYMBOLS
