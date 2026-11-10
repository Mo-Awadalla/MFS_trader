from __future__ import annotations

import numpy as np

from research.executable_liquidity import (
    executable_profile,
    executable_quantity,
    sweep_cost_bps,
)


def test_executable_quantity_respects_midpoint_band() -> None:
    prices = np.array([100.005, 100.01, 100.03])
    amounts = np.array([1.0, 2.0, 4.0])
    assert executable_quantity(100.0, prices, amounts, 1.0) == 3.0
    assert executable_quantity(100.0, prices, amounts, 5.0) == 7.0


def test_sweep_cost_is_monotone_for_ordered_asks() -> None:
    prices = np.array([100.01, 100.02, 100.04])
    amounts = np.array([1.0, 2.0, 3.0])
    one = sweep_cost_bps(100.0, prices, amounts, 1.0)
    five = sweep_cost_bps(100.0, prices, amounts, 5.0)
    assert five > one > 0
    assert np.isnan(sweep_cost_bps(100.0, prices, amounts, 7.0))


def test_profile_contains_depth_and_sweep_shape() -> None:
    profile = executable_profile(
        asks_price=np.array([100.005, 100.01, 100.03]),
        asks_amount=np.array([2.0, 2.0, 4.0]),
        bids_price=np.array([99.995, 99.99, 99.97]),
        bids_amount=np.array([1.0, 2.0, 5.0]),
    )
    assert profile["near_qty_1bps_min"] == 3.0
    assert profile["near_qty_5bps_total"] == 16.0
    assert profile["sweep_cost_5btc_bps"] > profile["sweep_cost_1btc_bps"]
