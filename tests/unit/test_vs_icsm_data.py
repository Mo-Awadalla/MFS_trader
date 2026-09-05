"""Tests for VS-ICSM data helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.vs_icsm_data import load_vs_icsm_mixed_panel
from storage.parquet_io import write_bars


def _bars(index: pd.DatetimeIndex, base: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [base + i for i in range(len(index))],
            "high": [base + i + 1.0 for i in range(len(index))],
            "low": [base + i - 1.0 for i in range(len(index))],
            "close": [base + i + 0.5 for i in range(len(index))],
            "volume": [1000.0 + i for i in range(len(index))],
        },
        index=index,
    )


def test_load_vs_icsm_mixed_panel_uses_alpaca_before_boundary_and_massive_after(
    tmp_path: Path,
) -> None:
    boundary = pd.Timestamp("2021-07-01 00:00:00", tz="UTC")
    alpaca_index = pd.DatetimeIndex(
        [
            pd.Timestamp("2021-06-30 23:00:00", tz="UTC"),
            pd.Timestamp("2021-07-01 00:00:00", tz="UTC"),
        ]
    )
    massive_index = pd.DatetimeIndex(
        [
            pd.Timestamp("2021-07-01 00:00:00", tz="UTC"),
            pd.Timestamp("2021-07-01 01:00:00", tz="UTC"),
        ]
    )
    write_bars(_bars(alpaca_index, 10.0), tmp_path / "alpaca" / "AAA_1h.parquet")
    write_bars(_bars(massive_index, 20.0), tmp_path / "massive" / "AAA_1h.parquet")

    panel = load_vs_icsm_mixed_panel(["AAA"], storage_dir=tmp_path, boundary=boundary)

    assert list(panel.index) == [
        pd.Timestamp("2021-06-30 23:00:00", tz="UTC"),
        pd.Timestamp("2021-07-01 00:00:00", tz="UTC"),
        pd.Timestamp("2021-07-01 01:00:00", tz="UTC"),
    ]
    assert panel.loc[pd.Timestamp("2021-06-30 23:00:00", tz="UTC"), ("AAA", "open")] == 10.0
    assert panel.loc[pd.Timestamp("2021-07-01 00:00:00", tz="UTC"), ("AAA", "open")] == 20.0
