"""Tests for SameClockIntradaySeasonalityETF-v1 signals."""

from __future__ import annotations

import pandas as pd

from research.same_clock_intraday_seasonality_pipeline import (
    backtest_same_clock_intraday_seasonality,
)
from strategies.same_clock_intraday_seasonality.signal import (
    SameClockIntradaySeasonalityParams,
    generate_signals,
    params_from_dict,
    params_to_dict,
)


def _panel(days: int = 25, bars_per_day: int = 13) -> pd.DataFrame:
    symbols = ("IWM", "QQQ", "SPY")
    sessions = pd.bdate_range("2024-01-02", periods=days, tz="UTC")
    idx = []
    for session in sessions:
        start = session + pd.Timedelta(hours=14, minutes=30)
        idx.extend(start + pd.Timedelta(minutes=30 * i) for i in range(bars_per_day))
    index = pd.DatetimeIndex(idx)
    frames = []
    for symbol_no, symbol in enumerate(symbols):
        price = 100.0 + symbol_no * 10.0
        closes = []
        for _session in sessions:
            for slot in range(bars_per_day):
                if slot == 0:
                    step = 0.0
                elif symbol in {"SPY", "QQQ"} and slot == 3:
                    step = 0.002
                elif symbol == "IWM" and slot == 3:
                    step = -0.002
                else:
                    step = 0.0
                price *= 1.0 + step
                closes.append(price)
        close = pd.Series(closes, index=index)
        open_ = close.shift(1).fillna(close.iloc[0])
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


def test_same_clock_enters_for_positive_prior_slot_and_flattens_before_close():
    df = _panel(days=25)
    params = SameClockIntradaySeasonalityParams(lookback_sessions=20)
    signals = generate_signals(df, params)
    weights = signals.xs("weight", axis=1, level="field").astype(float)

    session = df.index.normalize().unique()[20]
    session_idx = df.index[df.index.normalize() == session]
    decision_bar = session_idx[2]
    traded_slot_bar = session_idx[3]
    close_bar = session_idx[-1]

    assert weights.loc[decision_bar, "SPY"] == 0.5
    assert weights.loc[decision_bar, "QQQ"] == 0.5
    assert weights.loc[decision_bar, "IWM"] == 0.0
    result = backtest_same_clock_intraday_seasonality(df, params, initial_capital=25_000.0)
    assert result.weights.loc[decision_bar].abs().sum() == 0.0
    assert result.weights.loc[traded_slot_bar, "SPY"] == 0.5
    assert result.weights.loc[close_bar].abs().sum() == 0.0


def test_same_clock_params_round_trip():
    params = SameClockIntradaySeasonalityParams(lookback_sessions=30)

    assert params_from_dict(params_to_dict(params)) == params
