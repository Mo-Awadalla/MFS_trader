"""Tests for immutable Yahoo-versus-Massive parity evidence."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.compare_etf_tsm_yahoo_massive import compare_sources, write_immutable_report
from storage.parquet_io import write_bars


def test_compare_sources_aligns_daily_timestamps_and_reports_field_metrics(tmp_path: Path) -> None:
    yahoo_dir = tmp_path / "yahoo"
    massive_dir = tmp_path / "massive"
    yahoo_index = pd.date_range("2024-01-02 13:30", periods=2, freq="D", tz="UTC")
    massive_index = pd.date_range("2024-01-02 04:00", periods=2, freq="D", tz="UTC")
    yahoo = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000.0, 1100.0],
        },
        index=yahoo_index,
    )
    massive = yahoo.copy()
    massive.index = massive_index
    massive["close"] += 0.01
    write_bars(yahoo, yahoo_dir / "SPY_1d.parquet")
    write_bars(massive, massive_dir / "SPY_1d.parquet")

    report = compare_sources(yahoo_dir, massive_dir, symbols=("SPY",))

    symbol_report = report["symbols_report"]["SPY"]
    assert report["manual_review_required"] is True
    assert symbol_report["overlap"]["row_count"] == 2
    assert symbol_report["field_metrics"]["close"]["max_abs_diff"] == pytest.approx(0.01)
    assert symbol_report["field_metrics"]["open"]["within_1bp_fraction"] == 1.0
    assert len(symbol_report["input_hashes"]["yahoo"]) == 64


def test_parity_report_is_immutable(tmp_path: Path) -> None:
    path = tmp_path / "parity.json"
    write_immutable_report({"status": "complete"}, path)

    with pytest.raises(FileExistsError):
        write_immutable_report({"status": "changed"}, path)
