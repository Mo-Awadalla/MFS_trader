"""Executable-liquidity measurements for fixed-depth order-book snapshots."""

from __future__ import annotations

import numpy as np


def executable_quantity(
    midpoint: float,
    prices: np.ndarray,
    amounts: np.ndarray,
    band_bps: float,
) -> float:
    """Return displayed quantity no farther than ``band_bps`` from midpoint."""
    distance = np.abs(prices / midpoint - 1.0) * 10_000.0
    return float(amounts[distance <= band_bps + 1e-12].sum())


def sweep_cost_bps(
    midpoint: float,
    prices: np.ndarray,
    amounts: np.ndarray,
    quantity: float,
) -> float:
    """Return absolute VWAP displacement for a market order, or NaN if unfilled."""
    remaining = quantity
    notional = 0.0
    filled = 0.0
    for price, amount in zip(prices, amounts, strict=True):
        take = min(float(amount), remaining)
        notional += float(price) * take
        filled += take
        remaining -= take
        if remaining <= 1e-12:
            break
    if filled + 1e-12 < quantity:
        return float("nan")
    return abs(notional / filled / midpoint - 1.0) * 10_000.0


def executable_profile(
    asks_price: np.ndarray,
    asks_amount: np.ndarray,
    bids_price: np.ndarray,
    bids_amount: np.ndarray,
) -> dict[str, float]:
    """Measure near-touch depth and symmetric sweep costs for a 25-level book."""
    midpoint = float((asks_price[0] + bids_price[0]) / 2.0)
    result: dict[str, float] = {}
    for band in (1, 2, 5, 10):
        ask_qty = executable_quantity(midpoint, asks_price, asks_amount, band)
        bid_qty = executable_quantity(midpoint, bids_price, bids_amount, band)
        result[f"near_qty_{band}bps_min"] = min(ask_qty, bid_qty)
        result[f"near_qty_{band}bps_total"] = ask_qty + bid_qty
    costs: dict[int, float] = {}
    for quantity in (1, 3, 5):
        buy = sweep_cost_bps(midpoint, asks_price, asks_amount, quantity)
        sell = sweep_cost_bps(midpoint, bids_price, bids_amount, quantity)
        costs[quantity] = float(np.nanmean([buy, sell]))
        result[f"sweep_cost_{quantity}btc_bps"] = costs[quantity]
    result["sweep_convexity_bps_per_btc"] = (
        (costs[5] - costs[3]) / 2.0 - (costs[3] - costs[1]) / 2.0
    )
    return result
