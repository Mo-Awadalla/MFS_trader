"""Conservative hypothetical passive-fill and markout measurements."""

from __future__ import annotations


def touch_fill_side(
    trade_price: float,
    is_buyer_maker: bool,
    bid: float,
    ask: float,
) -> int:
    """Return +1 for a passive bid fill, -1 for ask fill, or zero otherwise."""
    if is_buyer_maker and trade_price <= bid:
        return 1
    if not is_buyer_maker and trade_price >= ask:
        return -1
    return 0


def passive_markout_bps(fill_price: float, future_midpoint: float, passive_side: int) -> float:
    """Return signed passive PnL markout in basis points."""
    return passive_side * (future_midpoint / fill_price - 1.0) * 10_000.0
