"""Bollinger Bands mean-reversion strategy.

Long-only mean reversion first. Breakout mode reserved for later.

Signal logic only — no I/O, no order management, no portfolio logic.
Signals at bar close, executed at next bar open (no lookahead).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

WidthMode = Literal["none", "normal", "contracting"]


@dataclass(frozen=True)
class BBParams:
    """Parameters for the Bollinger Bands mean-reversion strategy."""

    window: int = 20
    std_mult: float = 2.0
    width_percentile_low: int = 25
    width_percentile_high: int = 75
    width_mode: WidthMode = "normal"
    width_lookback: int = 252
    long_only: bool = True
    mean_reversion: bool = True  # breakout mode deferred


def compute_bollinger_bands(
    close: pd.Series, window: int, std_mult: float
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Compute middle, upper, lower bands and normalized width."""
    middle = close.rolling(window=window, min_periods=window).mean()
    std = close.rolling(window=window, min_periods=window).std()
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    width = (upper - lower) / middle.replace(0, pd.NA)
    return middle, upper, lower, width


def width_filter_mask(width: pd.Series, params: BBParams) -> pd.Series:
    """Return True where width regime allows new entries."""
    if params.width_mode == "none":
        return pd.Series(True, index=width.index)

    lookback = max(params.width_lookback, params.window * 2)
    low_q = params.width_percentile_low / 100.0
    high_q = params.width_percentile_high / 100.0
    p_low = width.rolling(window=lookback, min_periods=lookback).quantile(low_q)
    p_high = width.rolling(window=lookback, min_periods=lookback).quantile(high_q)

    if params.width_mode == "normal":
        return (width >= p_low) & (width <= p_high)
    if params.width_mode == "contracting":
        return width <= p_low

    raise ValueError(f"Unknown width_mode: {params.width_mode}")


def generate_signals(df: pd.DataFrame, params: BBParams) -> pd.DataFrame:
    """Generate entry/exit signals for BB mean-reversion.

    Long-only mean reversion:
      - Enter long when close crosses below the lower band (oversold)
      - Exit when close crosses above the middle band

    Returns DataFrame with middle, upper, lower, width, width_ok, position, signal.
    """
    columns = [
        "middle",
        "upper",
        "lower",
        "width",
        "width_ok",
        "cross_below_lower",
        "cross_above_middle",
        "position",
        "signal",
    ]
    min_bars = max(params.window, params.width_lookback if params.width_mode != "none" else params.window)
    if len(df) < min_bars:
        return pd.DataFrame(index=df.index, columns=columns)

    close = df["close"]
    middle, upper, lower, width = compute_bollinger_bands(close, params.window, params.std_mult)
    width_ok = width_filter_mask(width, params)

    if not params.mean_reversion:
        raise NotImplementedError("Breakout mode is not implemented yet")

    cross_below_lower = (close < lower) & (close.shift(1) >= lower.shift(1))
    cross_above_middle = (close > middle) & (close.shift(1) <= middle.shift(1))

    # NaN = hold prior state; explicit 1 = enter, 0 = exit flat
    raw_position = pd.Series(np.nan, index=df.index, dtype=float)
    raw_position[cross_below_lower & width_ok.fillna(False)] = 1.0
    raw_position[cross_above_middle] = 0.0
    position = raw_position.ffill().fillna(0).astype(int)

    if params.long_only:
        position = position.clip(lower=0, upper=1)

    signal = position.diff().fillna(0).astype(int)

    return pd.DataFrame(
        {
            "middle": middle,
            "upper": upper,
            "lower": lower,
            "width": width,
            "width_ok": width_ok,
            "cross_below_lower": cross_below_lower,
            "cross_above_middle": cross_above_middle,
            "position": position,
            "signal": signal,
        },
        index=df.index,
    )


def diagnose_signals(df: pd.DataFrame, params: BBParams) -> dict[str, int | float]:
    """Template sanity metrics. Prefer BollingerBandsStrategy.diagnose_signals()."""
    from strategies.bb.strategy import BollingerBandsStrategy

    diag = BollingerBandsStrategy().diagnose_signals(df, params)
    return diag.to_dict()


def default_params() -> BBParams:
    """Default parameters for the boring first BB experiment (AAPL 1d)."""
    return BBParams(
        window=20,
        std_mult=2.0,
        width_percentile_low=25,
        width_percentile_high=75,
        width_mode="normal",
        width_lookback=252,
        long_only=True,
        mean_reversion=True,
    )


def sweep_grid() -> list[BBParams]:
    """Parameter sweep grid per PLAN.md."""
    params_list: list[BBParams] = []
    std_mult = 1.5
    while std_mult <= 3.0 + 1e-9:
        for window in range(10, 51, 5):
            for width_mode in ("none", "normal", "contracting"):
                params_list.append(
                    BBParams(
                        window=window,
                        std_mult=round(std_mult, 2),
                        width_percentile_low=25,
                        width_percentile_high=75,
                        width_mode=width_mode,
                        width_lookback=252,
                        long_only=True,
                        mean_reversion=True,
                    )
                )
        std_mult += 0.25
    return params_list


def compact_sweep_grid() -> list[BBParams]:
    """Small parameter grid for fast tests."""
    return [
        BBParams(window=10, std_mult=1.5, width_mode="none", width_lookback=30),
        BBParams(window=15, std_mult=2.0, width_mode="normal", width_lookback=30),
        BBParams(window=20, std_mult=2.5, width_mode="contracting", width_lookback=30),
    ]


def params_to_dict(params: BBParams) -> dict[str, object]:
    """Serialize params for WFA/replay metadata."""
    return {
        "window": params.window,
        "std_mult": params.std_mult,
        "width_percentile_low": params.width_percentile_low,
        "width_percentile_high": params.width_percentile_high,
        "width_mode": params.width_mode,
        "width_lookback": params.width_lookback,
        "long_only": params.long_only,
        "mean_reversion": params.mean_reversion,
    }


def params_from_dict(data: dict[str, Any]) -> BBParams:
    """Deserialize params from WFA/replay metadata."""
    return BBParams(
        window=int(data.get("window", 20)),
        std_mult=float(data.get("std_mult", 2.0)),
        width_percentile_low=int(data.get("width_percentile_low", 25)),
        width_percentile_high=int(data.get("width_percentile_high", 75)),
        width_mode=cast(WidthMode, str(data.get("width_mode", "normal"))),
        width_lookback=int(data.get("width_lookback", 252)),
        long_only=bool(data.get("long_only", True)),
        mean_reversion=bool(data.get("mean_reversion", True)),
    )
