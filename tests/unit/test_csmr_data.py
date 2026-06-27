"""Tests for CSMR parquet panel loading."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.csmr_data import discover_ohlcv_parquet, load_csmr_panel
from storage.parquet_io import write_bars


def _write_symbol(root: Path, symbol: str) -> Path:
    idx = pd.date_range("2024-01-01", periods=3, freq="1D", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [10.0, 11.0, 12.0],
            "high": [11.0, 12.0, 13.0],
            "low": [9.0, 10.0, 11.0],
            "close": [10.5, 11.5, 12.5],
            "volume": [1_000.0, 1_100.0, 1_200.0],
        },
        index=idx,
    )
    path = root / "alpaca" / f"{symbol}_1d.parquet"
    write_bars(df, path)
    return path


def test_load_csmr_panel_combines_symbols(tmp_path: Path) -> None:
    a = _write_symbol(tmp_path, "AAA")
    b = _write_symbol(tmp_path, "BBB")

    panel = load_csmr_panel([a, b])

    assert panel.columns.names == ["symbol", "field"]
    assert ("AAA", "close") in panel.columns
    assert ("BBB", "volume") in panel.columns
    assert panel.loc[pd.Timestamp("2024-01-02", tz="UTC"), ("AAA", "close")] == 11.5


def test_discover_ohlcv_parquet(tmp_path: Path) -> None:
    path = _write_symbol(tmp_path, "AAA")

    assert discover_ohlcv_parquet(tmp_path, source="alpaca", frequency="1d") == [path]


def test_load_csmr_panel_normalizes_daily_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "alpaca" / "AAA_1d.parquet"
    idx = pd.DatetimeIndex(
        [
            pd.Timestamp("2024-01-02 05:00:00", tz="UTC"),
            pd.Timestamp("2024-01-03 05:00:00", tz="UTC"),
        ]
    )
    df = pd.DataFrame(
        {
            "open": [10.0, 11.0],
            "high": [11.0, 12.0],
            "low": [9.0, 10.0],
            "close": [10.5, 11.5],
            "volume": [1_000.0, 1_100.0],
        },
        index=idx,
    )
    write_bars(df, path)

    panel = load_csmr_panel([path])

    assert list(panel.index) == [
        pd.Timestamp("2024-01-02 00:00:00", tz="UTC"),
        pd.Timestamp("2024-01-03 00:00:00", tz="UTC"),
    ]
