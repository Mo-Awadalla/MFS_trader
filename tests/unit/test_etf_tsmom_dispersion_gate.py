"""Tests for CrossSectionalDispersionGateWeeklyETF-v1."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.etf_tsmom_dispersion_gate import (
    CASH_PROXY,
    RISK_ASSETS,
    dispersion_gate_tsmom_signal,
    dispersion_metric,
)


def _prices(days: int = 1260) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-02", periods=days, tz="UTC")
    data = {}
    for i, symbol in enumerate(RISK_ASSETS):
        data[symbol] = 100.0 * (1.0 + 0.0003 + i * 0.00001) ** np.arange(days)
    data[CASH_PROXY] = 100.0 * (1.0 + 0.00003) ** np.arange(days)
    return pd.DataFrame(data, index=idx)


def test_output_shape() -> None:
    prices = _prices()

    positions, gate_state = dispersion_gate_tsmom_signal(prices)

    assert positions.shape[1] == 11
    assert gate_state.shape == (len(positions),)
    assert list(positions.columns) == list(prices.columns)
    assert all(ts.weekday() == 4 for ts in positions.index)


def test_position_values_and_row_sums() -> None:
    prices = _prices()

    positions, _ = dispersion_gate_tsmom_signal(prices)

    assert float(positions.min().min()) >= 0.0
    assert float(positions.max().max()) <= 1.0
    assert not positions.isna().any().any()
    np.testing.assert_allclose(positions.sum(axis=1), 1.0, atol=1e-8)


def test_gate_state_consistency() -> None:
    prices = _prices()

    positions, gate_state = dispersion_gate_tsmom_signal(prices)

    assert gate_state.dtype == bool
    gate_off = positions.loc[~gate_state]
    if not gate_off.empty:
        np.testing.assert_allclose(gate_off.loc[:, list(RISK_ASSETS)].sum(axis=1), 0.0)
        np.testing.assert_allclose(gate_off[CASH_PROXY], 1.0)
    gate_on = positions.loc[gate_state]
    if not gate_on.empty:
        assert bool((gate_on.loc[:, list(RISK_ASSETS)].sum(axis=1) > 0.0).all())


def test_dispersion_metric_is_higher_for_independent_assets() -> None:
    idx = pd.bdate_range("2020-01-02", periods=320, tz="UTC")
    base = 100.0 * (1.001 ** np.arange(len(idx)))
    together = pd.DataFrame(dict.fromkeys(RISK_ASSETS, base), index=idx)
    rng = np.random.default_rng(42)
    independent_returns = rng.normal(0.0003, 0.01, size=(len(idx), len(RISK_ASSETS)))
    independent = pd.DataFrame(
        100.0 * np.cumprod(1.0 + independent_returns, axis=0),
        index=idx,
        columns=list(RISK_ASSETS),
    )

    together_metric = dispersion_metric(together).dropna()
    independent_metric = dispersion_metric(independent).dropna()

    assert float(together_metric.min()) >= 0.0
    assert float(independent_metric.min()) >= 0.0
    assert independent_metric.mean() > together_metric.mean()


def test_threshold_adapts_after_dispersion_regime_shift() -> None:
    idx = pd.bdate_range("2020-01-02", periods=600, tz="UTC")
    rng = np.random.default_rng(7)
    low = rng.normal(0.0002, 0.002, size=(300, len(RISK_ASSETS)))
    high = rng.normal(0.0002, 0.03, size=(300, len(RISK_ASSETS)))
    returns = np.vstack([low, high])
    prices = pd.DataFrame(100.0 * np.cumprod(1.0 + returns, axis=0), index=idx, columns=list(RISK_ASSETS))
    metric = dispersion_metric(prices)
    threshold = metric.rolling(126).quantile(0.80).dropna()

    assert threshold.loc[idx[-60]:].mean() > threshold.loc[idx[180:240]].mean()


def test_no_lookahead_for_current_week_price() -> None:
    prices = _prices(days=420)
    positions, gate_state = dispersion_gate_tsmom_signal(prices)
    target_week = positions.index[60]
    modified = prices.copy()
    modified.loc[target_week, "SPY"] *= 100.0

    changed_positions, changed_gate = dispersion_gate_tsmom_signal(modified)

    pd.testing.assert_series_equal(positions.loc[target_week], changed_positions.loc[target_week])
    assert bool(gate_state.loc[target_week]) == bool(changed_gate.loc[target_week])


def test_determinism() -> None:
    prices = _prices(days=420)

    positions_a, gate_a = dispersion_gate_tsmom_signal(prices)
    positions_b, gate_b = dispersion_gate_tsmom_signal(prices)

    pd.testing.assert_frame_equal(positions_a, positions_b)
    pd.testing.assert_series_equal(gate_a, gate_b)
