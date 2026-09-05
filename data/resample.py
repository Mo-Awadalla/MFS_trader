"""Resample 1-min raw bars to higher frequencies.

Source of truth is 1-min. All downstream consumers call resample_to().
Resampling semantics are explicit:
  - bar label = left (start of period)
  - closed = left
  - timezone = UTC internally
"""

from __future__ import annotations

import pandas as pd

VALID_FREQUENCIES = {"1min", "5min", "15min", "30min", "1h", "4h", "1d", "1D"}


def resample_to(df: pd.DataFrame, frequency: str) -> pd.DataFrame:
    """Resample a 1-min OHLCV DataFrame to a higher frequency.

    Args:
        df: DataFrame with DatetimeIndex (UTC) and open/high/low/close/volume.
        frequency: Target frequency (5min, 15min, 30min, 1h, 4h, 1d).

    Returns:
        Resampled OHLCV DataFrame with left-labeled, left-closed bars.
    """
    if frequency == "1min":
        return df.copy()

    if frequency not in VALID_FREQUENCIES:
        raise ValueError(f"Unsupported frequency: {frequency}. Valid: {VALID_FREQUENCIES}")

    if df.empty:
        return df.copy()

    # Normalize deprecated lowercase 'd' to uppercase 'D' for pandas
    freq_normalized = frequency.replace("d", "D") if frequency.endswith("d") else frequency

    df = df.tz_localize("UTC") if df.index.tzinfo is None else df.tz_convert("UTC")

    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "quote_volume": "sum",
        "trade_count": "sum",
        "taker_buy_volume": "sum",
        "taker_buy_quote_volume": "sum",
    }
    # Only aggregate columns that exist
    agg = {k: v for k, v in agg.items() if k in df.columns}

    resampled = df.resample(freq_normalized, label="left", closed="left").agg(agg)
    # Drop bars with no data (all NaN)
    resampled = resampled.dropna(subset=["open", "close"]).copy()
    return resampled


def available_frequencies(df: pd.DataFrame) -> list[str]:
    """Detect what frequencies the data can be resampled to based on the index."""
    if len(df) < 2:
        return ["1min"]
    median_diff = df.index.to_series().diff().median()
    if median_diff is None or pd.isna(median_diff):
        return ["1min"]
    seconds = median_diff.total_seconds()
    if seconds <= 60:
        return ["1min", "5min", "15min", "30min", "1h", "4h", "1d"]
    elif seconds <= 300:
        return ["5min", "15min", "30min", "1h", "4h", "1d"]
    elif seconds <= 3600:
        return ["1h", "4h", "1d"]
    return ["1d"]
