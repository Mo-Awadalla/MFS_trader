from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.vs_icsm_pipeline import backtest_vs_icsm
from strategies.vs_icsm.signal import VSICSMParams, average_true_range, generate_signals


def _panel(n_bars: int = 80, n_symbols: int = 20) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02 14:30", periods=n_bars, freq="1h", tz="UTC")
    symbols = tuple(f"S{i:03d}" for i in range(n_symbols))
    columns = pd.MultiIndex.from_product(
        [symbols, ("open", "high", "low", "close", "volume")],
        names=["symbol", "field"],
    )
    df = pd.DataFrame(index=idx, columns=columns, dtype=float)
    for i, symbol in enumerate(symbols):
        drift = 0.0001 + i * 0.00001
        close = 20.0 + i + np.cumsum(np.full(n_bars, drift))
        df[(symbol, "open")] = close
        df[(symbol, "high")] = close * 1.002
        df[(symbol, "low")] = close * 0.998
        df[(symbol, "close")] = close
        df[(symbol, "volume")] = 2_000_000 + i * 1000
    return df


def _small_params() -> VSICSMParams:
    return VSICSMParams(
        liquidity_lookback_bars=20,
        universe_size=20,
        min_history_bars=20,
        k_names=5,
        momentum_lookback_bars=6,
        volatility_lookback_bars=13,
        atr_lookback_bars=13,
    )


def test_average_true_range_uses_high_low_and_previous_close() -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="1h", tz="UTC")
    high = pd.DataFrame({"A": [11.0, 12.0, 13.0]}, index=idx)
    low = pd.DataFrame({"A": [9.0, 10.0, 11.0]}, index=idx)
    close = pd.DataFrame({"A": [10.0, 11.0, 12.0]}, index=idx)

    atr = average_true_range(high, low, close, 2)

    assert atr["A"].iloc[-1] == 2.0


def test_generate_signals_selects_top_k_inverse_atr_weights() -> None:
    df = _panel()
    params = _small_params()

    signals = generate_signals(df, params)
    weights = signals.xs("weight", axis=1, level="field")
    late = weights.iloc[-1]

    assert (late > 0).sum() == params.k_names
    assert late.sum() == pytest.approx(params.gross_exposure)
    assert not signals[("portfolio", "rebalance_skipped")].astype(bool).tail(10).any()


def test_backtest_rejects_panel_smaller_than_frozen_universe() -> None:
    with pytest.raises(ValueError, match="requires at least 200 symbols"):
        backtest_vs_icsm(_panel(n_symbols=20))


def test_backtest_runs_with_small_test_params_and_records_fills() -> None:
    df = _panel()
    result = backtest_vs_icsm(df, _small_params())

    assert result.bar_count == len(df)
    assert result.trade_count > 0
    assert 0.0 <= result.metrics["fill_rate"] <= 1.0
