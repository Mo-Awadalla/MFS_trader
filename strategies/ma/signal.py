"""Dual MA crossover strategy — momentum baseline.

This is a pipeline validator, not a serious edge candidate. Its job is to
test data, reports, WFA/MC/DSR, and paper execution plumbing.

Signal logic only — no I/O, no order management, no portfolio logic.
The function takes OHLCV and parameters, returns a signals DataFrame.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MAParams:
    """Parameters for the dual MA crossover strategy."""

    fast_ma_type: Literal["sma", "ema"] = "sma"
    fast_ma_window: int = 20
    slow_ma_type: Literal["sma", "ema"] = "sma"
    slow_ma_window: int = 100
    trend_filter_active: bool = True
    trend_filter_window: int = 200
    trend_filter_type: Literal["sma", "ema"] = "sma"
    long_only: bool = True  # long-only flat exit; if false, also short
    exit_on_flip: bool = True  # exit when fast crosses below slow


def compute_ma(series: pd.Series, window: int, ma_type: str) -> pd.Series:
    """Compute SMA or EMA."""
    if ma_type == "sma":
        return series.rolling(window=window, min_periods=window).mean()
    elif ma_type == "ema":
        return series.ewm(span=window, min_periods=window, adjust=False).mean()
    else:
        raise ValueError(f"Unknown MA type: {ma_type}")


def generate_signals(df: pd.DataFrame, params: MAParams) -> pd.DataFrame:
    """Generate entry/exit signals for the dual MA crossover strategy.

    Args:
        df: OHLCV DataFrame with DatetimeIndex.
        params: Strategy parameters.

    Returns:
        DataFrame with columns:
          - fast_ma: fast moving average
          - slow_ma: slow moving average
          - trend_filter: trend filter MA (if active)
          - cross_above: True when fast crosses above slow
          - cross_below: True when fast crosses below slow
          - position: target position (+1 long, -1 short, 0 flat)
          - signal: entry/exit signal (1 enter long, -1 enter short, 0 exit/hold)

    Signal convention:
        - Signals are generated at bar close and executed at the NEXT bar open.
          This prevents lookahead bias — the signal at timestamp T uses data
          up to and including T, and the trade happens at T+1.
        - The `position` column is the TARGET position to hold AFTER the signal
          fires (i.e., what you should be holding going into the next bar).
    """
    if len(df) < params.slow_ma_window:
        return pd.DataFrame(
            index=df.index,
            columns=["fast_ma", "slow_ma", "trend_filter", "cross_above", "cross_below", "position", "signal"],
        )

    close = df["close"]
    fast_ma = compute_ma(close, params.fast_ma_window, params.fast_ma_type)
    slow_ma = compute_ma(close, params.slow_ma_window, params.slow_ma_type)

    # Trend filter: only take long signals when price > trend_filter MA
    if params.trend_filter_active:
        trend_filter = compute_ma(close, params.trend_filter_window, params.trend_filter_type)
        trend_ok = close > trend_filter
    else:
        trend_filter = pd.Series(index=df.index, dtype=float)
        trend_ok = pd.Series(True, index=df.index)

    # Crossover detection
    fast_above = fast_ma > slow_ma
    cross_above = fast_above & ~fast_above.shift(1, fill_value=False)
    cross_below = ~fast_above & fast_above.shift(1, fill_value=False)

    # Build target position
    # Long-only mode: +1 when fast > slow AND trend_ok, else 0
    # Long/short mode: +1 when fast > slow, -1 when fast < slow (trend filter for longs only)
    if params.long_only:
        raw_position = pd.Series(np.nan, index=df.index, dtype=float)
        raw_position[cross_above & trend_ok] = 1.0
        if params.exit_on_flip:
            raw_position[cross_below] = 0.0
        position = raw_position.ffill().fillna(0).astype(int)
        position = position.where(trend_ok, 0)
    else:
        position = pd.Series(0, index=df.index, dtype=int)
        # Enter long on cross_above (with trend filter)
        position[cross_above & trend_ok] = 1
        # Enter short on cross_below
        position[cross_below] = -1
        # Hold until flip
        position = position.replace(0, pd.NA).ffill().fillna(0).astype(int)

    # Signal = change in position (what action to take at next bar)
    signal = position.diff().fillna(0).astype(int)

    return pd.DataFrame(
        {
            "fast_ma": fast_ma,
            "slow_ma": slow_ma,
            "trend_filter": trend_filter if params.trend_filter_active else pd.Series(index=df.index, dtype=float),
            "cross_above": cross_above,
            "cross_below": cross_below,
            "position": position,
            "signal": signal,
        },
        index=df.index,
    )


def default_params() -> MAParams:
    """Default parameters for the MA crossover strategy."""
    return MAParams(
        fast_ma_type="sma",
        fast_ma_window=20,
        slow_ma_type="sma",
        slow_ma_window=100,
        trend_filter_active=True,
        trend_filter_window=200,
        trend_filter_type="sma",
        long_only=True,
        exit_on_flip=True,
    )


def sweep_grid() -> list[MAParams]:
    """Generate the parameter sweep grid for the MA crossover strategy.

    Sweep:
        - fast_ma_type: sma, ema
        - fast_ma_window: 5..50 step 5
        - slow_ma_window: 30..200 step 5 (must be > fast_ma_window)
        - trend_filter_active: true, false
    """
    params_list: list[MAParams] = []
    for fast_type in ["sma", "ema"]:
        for fast_window in range(5, 51, 5):
            for slow_window in range(30, 201, 5):
                if slow_window <= fast_window:
                    continue
                for trend_active in [True, False]:
                    params_list.append(
                        MAParams(
                            fast_ma_type=fast_type,  # type: ignore[arg-type]
                            fast_ma_window=fast_window,
                            slow_ma_type="sma",
                            slow_ma_window=slow_window,
                            trend_filter_active=trend_active,
                            trend_filter_window=200,
                            long_only=True,
                            exit_on_flip=True,
                        )
                    )
    return params_list


def compact_sweep_grid() -> list[MAParams]:
    """Small grid for fast tests and smoke sweeps."""
    return [
        MAParams(fast_ma_window=10, slow_ma_window=50, trend_filter_active=False, long_only=True),
        MAParams(fast_ma_window=20, slow_ma_window=100, trend_filter_active=True, long_only=True),
        MAParams(fast_ma_type="ema", fast_ma_window=15, slow_ma_window=60, trend_filter_active=False, long_only=True),
    ]
