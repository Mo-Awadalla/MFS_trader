"""Tests for market intraday momentum v1 signals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.market_intraday_momentum_pipeline import backtest_market_intraday_momentum
from strategies.market_intraday_momentum.signal import (
    MarketIntradayMomentumParams,
    generate_signals,
    params_from_dict,
    params_to_dict,
)


def _panel(days: int = 4, bars_per_day: int = 13) -> pd.DataFrame:
    symbols = ("IWM", "QQQ", "SPY")
    sessions = pd.bdate_range("2024-01-02", periods=days, tz="UTC")
    idx = []
    for session in sessions:
        start = session + pd.Timedelta(hours=14, minutes=30)
        idx.extend(start + pd.Timedelta(minutes=30 * i) for i in range(bars_per_day))
    index = pd.DatetimeIndex(idx)
    frames = []
    for symbol_no, symbol in enumerate(symbols):
        base = 100.0 + symbol_no * 10.0
        close = pd.Series(base + np.arange(len(index)) * 0.01, index=index)
        open_ = close.copy()
        # Make first bar positive for SPY/QQQ and negative for IWM.
        for session in sessions:
            first = session + pd.Timedelta(hours=14, minutes=30)
            if symbol == "IWM":
                open_.loc[first] = close.loc[first] * 1.002
            else:
                open_.loc[first] = close.loc[first] * 0.998
        df = pd.DataFrame(
            {
                "open": open_,
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
                "volume": 1_000_000.0,
            }
        )
        df.columns = pd.MultiIndex.from_product([[symbol], df.columns], names=["symbol", "field"])
        frames.append(df)
    return pd.concat(frames, axis=1).sort_index()


def test_market_intraday_momentum_enters_after_opening_bar_and_flattens_before_close():
    df = _panel(days=3)
    params = MarketIntradayMomentumParams()
    signals = generate_signals(df, params)
    weights = signals.xs("weight", axis=1, level="field").astype(float)

    first_session = df.index.normalize()[0]
    session_idx = df.index[df.index.normalize() == first_session]
    opening_bar = session_idx[0]
    mid_bar = session_idx[2]
    penultimate_bar = session_idx[-2]
    close_bar = session_idx[-1]

    assert weights.loc[opening_bar, "SPY"] == 0.5
    assert weights.loc[opening_bar, "QQQ"] == 0.5
    assert weights.loc[opening_bar, "IWM"] == 0.0
    assert weights.loc[mid_bar, "SPY"] == 0.5
    assert weights.loc[penultimate_bar].abs().sum() == 0.0
    assert weights.loc[close_bar].abs().sum() == 0.0


def test_market_intraday_backtest_has_flat_session_close_positions():
    result = backtest_market_intraday_momentum(_panel(days=80), initial_capital=25_000.0)
    last_by_session = result.weights.abs().sum(axis=1).groupby(result.weights.index.normalize()).tail(1)

    assert result.trade_count > 100
    assert (last_by_session == 0.0).all()
    assert result.metrics["annualization_factor"] == 252 * 13


def test_params_round_trip():
    params = MarketIntradayMomentumParams(min_opening_return=0.001)

    assert params_from_dict(params_to_dict(params)) == params
