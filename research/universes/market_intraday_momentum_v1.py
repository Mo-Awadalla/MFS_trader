"""Static liquid ETF universe for market intraday momentum v1."""

from __future__ import annotations

SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "IWM")


def all_symbols() -> tuple[str, ...]:
    return SYMBOLS
