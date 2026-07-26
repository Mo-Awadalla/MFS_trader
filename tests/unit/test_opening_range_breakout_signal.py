"""Tests for OpeningRangeBreakoutETF-v1 signals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.opening_range_breakout_pipeline import backtest_opening_range_breakout
from strategies.opening_range_breakout.signal import (
    OpeningRangeBreakoutParams,
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
        high = close * 1.001
        low = close * 0.999
        for session in sessions:
            session_idx = pd.DatetimeIndex(
                [session + pd.Timedelta(hours=14, minutes=30) + pd.Timedelta(minutes=30 * i) for i in range(bars_per_day)]
            )
            opening_high = base * 1.01
            high.loc[session_idx[:2]] = opening_high
            close.loc[session_idx[:2]] = base
            open_.loc[session_idx[:2]] = base
            low.loc[session_idx[:2]] = base * 0.99
            if symbol in {"SPY", "QQQ"}:
                close.loc[session_idx[2:11]] = opening_high * 1.002
                open_.loc[session_idx[2:11]] = opening_high * 1.001
                high.loc[session_idx[2:11]] = opening_high * 1.003
                low.loc[session_idx[2:11]] = opening_high * 0.999
            else:
                close.loc[session_idx[2:11]] = opening_high * 0.998
                open_.loc[session_idx[2:11]] = opening_high * 0.997
                high.loc[session_idx[2:11]] = opening_high * 0.999
                low.loc[session_idx[2:11]] = opening_high * 0.996
        df = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1_000_000.0,
            }
        )
        df.columns = pd.MultiIndex.from_product([[symbol], df.columns], names=["symbol", "field"])
        frames.append(df)
    return pd.concat(frames, axis=1).sort_index()


def test_opening_range_breakout_enters_after_range_break_and_flattens_before_close():
    df = _panel(days=3)
    params = OpeningRangeBreakoutParams()
    signals = generate_signals(df, params)
    weights = signals.xs("weight", axis=1, level="field").astype(float)

    first_session = df.index.normalize()[0]
    session_idx = df.index[df.index.normalize() == first_session]
    opening_bar = session_idx[0]
    range_complete_bar = session_idx[1]
    breakout_bar = session_idx[2]
    mid_bar = session_idx[4]
    penultimate_bar = session_idx[-2]
    close_bar = session_idx[-1]

    assert weights.loc[opening_bar].abs().sum() == 0.0
    assert weights.loc[range_complete_bar].abs().sum() == 0.0
    assert weights.loc[breakout_bar, "SPY"] == 0.5
    assert weights.loc[breakout_bar, "QQQ"] == 0.5
    assert weights.loc[breakout_bar, "IWM"] == 0.0
    assert weights.loc[mid_bar, "SPY"] == 0.5
    assert weights.loc[penultimate_bar].abs().sum() == 0.0
    assert weights.loc[close_bar].abs().sum() == 0.0


def test_opening_range_backtest_uses_next_bar_execution_and_flat_session_close():
    df = _panel(days=80)
    result = backtest_opening_range_breakout(df, initial_capital=25_000.0)
    first_session = df.index.normalize()[0]
    session_idx = df.index[df.index.normalize() == first_session]
    breakout_bar = session_idx[2]
    next_bar = session_idx[3]
    last_by_session = result.weights.abs().sum(axis=1).groupby(result.weights.index.normalize()).tail(1)

    assert result.weights.loc[breakout_bar].abs().sum() == 0.0
    assert result.weights.loc[next_bar, "SPY"] == 0.5
    assert result.trade_count > 100
    assert (last_by_session == 0.0).all()
    assert result.metrics["annualization_factor"] == 252 * 13


def test_opening_range_params_round_trip():
    params = OpeningRangeBreakoutParams(breakout_buffer_pct=0.001)

    assert params_from_dict(params_to_dict(params)) == params
