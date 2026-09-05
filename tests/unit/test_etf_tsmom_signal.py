"""Tests for ETFTimeSeriesMomentumVolTarget-v1."""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.etf_tsmom.signal import (
    DEFAULT_UNIVERSE,
    ETFTSMOMParams,
    generate_weight_signals,
)


def _panel(days: int = 320, *, positive: bool = True) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-02", periods=days, tz="UTC")
    columns = pd.MultiIndex.from_product(
        [DEFAULT_UNIVERSE, ("open", "high", "low", "close", "volume")],
        names=["symbol", "field"],
    )
    df = pd.DataFrame(index=idx, columns=columns, dtype=float)
    for i, symbol in enumerate(DEFAULT_UNIVERSE):
        slope = (0.0005 + i * 0.0001) if positive else -0.0005
        close = 100.0 * (1.0 + slope) ** np.arange(days)
        df[(symbol, "open")] = close
        df[(symbol, "high")] = close * 1.01
        df[(symbol, "low")] = close * 0.99
        df[(symbol, "close")] = close
        df[(symbol, "volume")] = 1_000_000.0
    return df


def test_parks_in_shy_when_no_etf_has_positive_absolute_momentum() -> None:
    df = _panel(320, positive=False)

    weights, _, portfolio = generate_weight_signals(df)
    active = portfolio.index[portfolio["eligible_count"] == 0][-1]

    assert weights.loc[active, "SHY"] == 1.0
    assert weights.loc[active].drop("SHY").sum() == 0.0


def test_selects_top_three_positive_etfs_and_caps_single_name_weight() -> None:
    df = _panel(320, positive=True)

    weights, _, portfolio = generate_weight_signals(df)
    active = portfolio.index[portfolio["eligible_count"] > 0][-1]
    selected = weights.loc[active][weights.loc[active] > 0.0]

    assert len(selected) == 3
    assert selected.max() <= 0.50 * 1.5 + 1e-12
    assert weights.loc[active].sum() <= 1.5 + 1e-12


def test_no_lookahead_for_future_month_data() -> None:
    df = _panel(360, positive=True)
    weights, _, _ = generate_weight_signals(df)
    modified = df.copy()
    modified.loc["2021-03-01":, ("SPY", "close")] *= 5.0

    changed, _, _ = generate_weight_signals(modified)

    pd.testing.assert_frame_equal(weights.loc[:"2021-02-28"], changed.loc[:"2021-02-28"])


def test_vol_target_can_scale_below_one() -> None:
    df = _panel(320, positive=True)
    idx = np.arange(len(df))
    for symbol in DEFAULT_UNIVERSE:
        close = 100.0 * (1.002 ** idx) * (1.0 + 0.10 * np.sin(idx))
        df[(symbol, "open")] = close
        df[(symbol, "high")] = close * 1.02
        df[(symbol, "low")] = close * 0.98
        df[(symbol, "close")] = close
    params = ETFTSMOMParams(annual_vol_target=0.01)

    weights, _, portfolio = generate_weight_signals(df, params)
    active = portfolio.index[portfolio["eligible_count"] > 0][-1]

    assert 0.0 < weights.loc[active].sum() < 1.0
