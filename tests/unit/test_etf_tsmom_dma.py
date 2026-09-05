"""Tests for BayesianDMAWeeklyETF-v1."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.etf_tsmom_dma import dma_tsmom_signal


def _prices(days: int = 1260, assets: int = 10) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-02", periods=days, tz="UTC")
    columns = [f"A{i}" for i in range(assets)]
    data = {}
    for i, column in enumerate(columns):
        data[column] = 100.0 * (1.0 + 0.0002 + i * 0.00001) ** np.arange(days)
    return pd.DataFrame(data, index=idx)


def test_output_shape() -> None:
    prices = _prices()

    positions, model_weights = dma_tsmom_signal(prices)

    assert positions.shape[1] == 10
    assert model_weights.shape == (len(positions), 10, 3)
    assert list(positions.columns) == list(prices.columns)
    assert all(ts.weekday() == 4 for ts in positions.index)


def test_position_values_long_only_and_long_short() -> None:
    prices = _prices()

    long_only, _ = dma_tsmom_signal(prices, long_only=True)
    long_short, _ = dma_tsmom_signal(prices, long_only=False)

    assert set(np.unique(long_only.to_numpy())).issubset({0, 1})
    assert set(np.unique(long_short.to_numpy())).issubset({-1, 0, 1})
    assert not long_only.isna().any().any()
    assert not long_short.isna().any().any()


def test_model_weights_sum_to_one() -> None:
    prices = _prices()

    _, model_weights = dma_tsmom_signal(prices)

    np.testing.assert_allclose(model_weights.sum(axis=2), 1.0, atol=1e-6)
    assert float(model_weights.min()) >= 0.0


def test_trend_reversal_pushes_weight_toward_short_lookback() -> None:
    idx = pd.bdate_range("2020-01-02", periods=260, tz="UTC")
    up = 100.0 * (1.002 ** np.arange(130))
    down = up[-1] * (0.995 ** np.arange(1, 131))
    prices = pd.DataFrame({"A0": np.concatenate([up, down])}, index=idx)

    positions, model_weights = dma_tsmom_signal(prices)
    after_reversal = positions.index[positions.index >= idx[170]][0]
    before_reversal = positions.index[positions.index < idx[130]][-1]
    before_idx = positions.index.get_loc(before_reversal)
    after_idx = positions.index.get_loc(after_reversal)

    assert model_weights[after_idx, 0, 0] > model_weights[before_idx, 0, 0]


def test_no_lookahead_for_current_week_price() -> None:
    prices = _prices(days=320, assets=3)
    positions, _ = dma_tsmom_signal(prices)
    target_week = positions.index[20]
    modified = prices.copy()
    modified.loc[target_week, "A0"] *= 100.0

    changed, _ = dma_tsmom_signal(modified)

    pd.testing.assert_series_equal(positions.loc[target_week], changed.loc[target_week])


def test_determinism() -> None:
    prices = _prices(days=320, assets=3)

    positions_a, model_weights_a = dma_tsmom_signal(prices)
    positions_b, model_weights_b = dma_tsmom_signal(prices)

    pd.testing.assert_frame_equal(positions_a, positions_b)
    np.testing.assert_array_equal(model_weights_a, model_weights_b)
