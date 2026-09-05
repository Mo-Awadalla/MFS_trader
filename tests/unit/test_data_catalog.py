from __future__ import annotations

import pandas as pd
import pytest

from data.catalog import BarRequest, DataCatalog, StrictPanelRequest
from storage.parquet_io import write_bars


def _bars(start: str, count: int = 3) -> pd.DataFrame:
    index = pd.date_range(start, periods=count, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": range(10, 10 + count),
            "high": range(11, 11 + count),
            "low": range(9, 9 + count),
            "close": range(10, 10 + count),
            "volume": range(100, 100 + count),
        },
        index=index,
    )


def test_catalog_loads_single_symbol_with_provenance(tmp_path) -> None:
    path = tmp_path / "alpaca" / "AAPL_1d.parquet"
    write_bars(_bars("2024-01-01"), path)

    loaded = DataCatalog().load(
        BarRequest(
            storage_dir=tmp_path,
            symbols=("AAPL",),
            frequency="1d",
            source="alpaca",
            start="2024-01-02",
            end="2024-01-03",
        )
    )

    assert list(loaded.frame.index) == list(_bars("2024-01-02", 2).index)
    assert loaded.provenance.symbols == ("AAPL",)
    assert loaded.provenance.paths == (str(path),)


def test_catalog_loads_aligned_panel(tmp_path) -> None:
    for symbol in ("SPY", "TLT"):
        write_bars(_bars("2024-01-01"), tmp_path / "yahoo" / f"{symbol}_1d.parquet")

    loaded = DataCatalog().load(
        BarRequest(
            storage_dir=tmp_path,
            symbols=("SPY", "TLT"),
            frequency="1d",
            source="yahoo",
        )
    )

    assert loaded.frame.columns.names == ["symbol", "field"]
    assert tuple(loaded.frame.columns.get_level_values("symbol").unique()) == ("SPY", "TLT")


def test_catalog_rejects_misaligned_required_panel(tmp_path) -> None:
    write_bars(_bars("2024-01-01", 3), tmp_path / "yahoo" / "SPY_1d.parquet")
    write_bars(_bars("2024-01-02", 3), tmp_path / "yahoo" / "TLT_1d.parquet")

    with pytest.raises(ValueError, match="Incomplete or misaligned"):
        DataCatalog().load(
            BarRequest(
                storage_dir=tmp_path,
                symbols=("SPY", "TLT"),
                frequency="1d",
                source="yahoo",
            )
        )


def test_catalog_strict_panel_rejects_missing_expected_session(tmp_path) -> None:
    for symbol in ("SPY", "TLT"):
        write_bars(_bars("2024-01-01", 2), tmp_path / "alpaca_sip" / f"{symbol}_1d.parquet")

    with pytest.raises(ValueError, match="session mismatch"):
        DataCatalog().load_strict_panel(
            StrictPanelRequest(
                bars=BarRequest(
                    storage_dir=tmp_path,
                    symbols=("SPY", "TLT"),
                    frequency="1d",
                    source="alpaca_sip",
                ),
                expected_sessions=("2024-01-01", "2024-01-02", "2024-01-03"),
                expected_session_closes=("2024-01-01T21:00:00Z", "2024-01-02T21:00:00Z", "2024-01-03T21:00:00Z"),
                cutoff="2024-01-04",
            )
        )


def test_catalog_strict_panel_rejects_close_on_wrong_session(tmp_path) -> None:
    for symbol in ("SPY", "TLT"):
        write_bars(_bars("2024-01-01", 2), tmp_path / "alpaca_sip" / f"{symbol}_1d.parquet")

    with pytest.raises(ValueError, match="closes do not align"):
        DataCatalog().load_strict_panel(
            StrictPanelRequest(
                bars=BarRequest(
                    storage_dir=tmp_path,
                    symbols=("SPY", "TLT"),
                    frequency="1d",
                    source="alpaca_sip",
                ),
                expected_sessions=("2024-01-01", "2024-01-02"),
                expected_session_closes=("2024-01-02T21:00:00Z", "2024-01-03T21:00:00Z"),
                cutoff="2024-01-04",
            )
        )
