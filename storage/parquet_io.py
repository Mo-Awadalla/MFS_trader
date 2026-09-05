"""Parquet IO helpers — read/write OHLCV bars and research artifacts.

1-min raw bars are the source of truth. Resampling happens downstream.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def parquet_path(storage_dir: str | Path, symbol: str, frequency: str, source: str = "") -> Path:
    """Build a deterministic Parquet path for a symbol/frequency/source.

    Layout: {storage_dir}/{source}/{symbol}_{frequency}.parquet
    """
    base = Path(storage_dir)
    safe_symbol = symbol.replace("/", "_")
    fname = f"{safe_symbol}_{frequency}.parquet"
    if source:
        return base / source / fname
    return base / fname


def write_bars(df: pd.DataFrame, path: str | Path, *, compression: str = "snappy") -> None:
    """Write an OHLCV DataFrame to Parquet (Snappy compression).

    The DatetimeIndex is preserved as a 'timestamp' column so it survives
    the round-trip through Parquet.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reset index to preserve it as a column
    out = df.reset_index()
    # Ensure the index column is named 'timestamp'
    if "index" in out.columns and "timestamp" not in out.columns:
        out = out.rename(columns={"index": "timestamp"})
    table = pa.Table.from_pandas(out, preserve_index=False)
    pq.write_table(table, str(path), compression=compression)  # type: ignore[no-untyped-call]


def read_bars(path: str | Path) -> pd.DataFrame:
    """Read an OHLCV Parquet file, returning a DataFrame with DatetimeIndex."""
    table = pq.read_table(str(path))  # type: ignore[no-untyped-call]
    df = table.to_pandas()
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp").sort_index()
    return df


def append_bars(df: pd.DataFrame, path: str | Path, *, compression: str = "snappy") -> int:
    """Append new bars to an existing Parquet file, deduplicating by timestamp.

    Returns the number of new rows added.
    """
    path = Path(path)
    if path.exists():
        existing = read_bars(path)
        combined = pd.concat([existing, df])
        combined = combined[~combined.index.duplicated(keep="last")]
        new_count = len(combined) - len(existing)
    else:
        combined = df
        new_count = len(df)
    combined = combined.sort_index()
    write_bars(combined, path, compression=compression)
    return new_count


def write_artifact(df: pd.DataFrame, path: str | Path, *, compression: str = "snappy") -> None:
    """Write a generic DataFrame artifact (equity curves, trades, WFA folds) to Parquet."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=True)
    pq.write_table(table, str(path), compression=compression)  # type: ignore[no-untyped-call]


def read_artifact(path: str | Path) -> pd.DataFrame:
    """Read a generic Parquet artifact."""
    table = pq.read_table(str(path))  # type: ignore[no-untyped-call]
    return table.to_pandas()


def write_timeseries(df: pd.DataFrame, path: str | Path, *, compression: str = "snappy") -> None:
    """Atomically write a non-OHLCV UTC time series such as funding or open interest."""
    path = Path(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Time-series artifacts require a DatetimeIndex")
    if df.index.tz is None:
        raise ValueError("Time-series artifacts require timezone-aware timestamps")
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.sort_index().reset_index()
    if "index" in out.columns and "timestamp" not in out.columns:
        out = out.rename(columns={"index": "timestamp"})
    table = pa.Table.from_pandas(out, preserve_index=False)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        pq.write_table(table, str(temporary_path), compression=compression)  # type: ignore[no-untyped-call]
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def read_timeseries(path: str | Path) -> pd.DataFrame:
    """Read a time-series artifact written by :func:`write_timeseries`."""
    table = pq.read_table(str(path))  # type: ignore[no-untyped-call]
    df = table.to_pandas()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.set_index("timestamp").sort_index()
