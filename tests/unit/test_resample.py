"""Tests for the resample module."""

from __future__ import annotations

import pandas as pd
import pytest

from data.resample import available_frequencies, resample_to


def _make_1min(n: int = 120, start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": range(n),
            "high": [x + 1 for x in range(n)],
            "low": [x - 1 for x in range(n)],
            "close": [x + 0.5 for x in range(n)],
            "volume": [100.0] * n,
        },
        index=idx,
    )


class TestResample:
    def test_1min_returns_copy(self):
        df = _make_1min(60)
        result = resample_to(df, "1min")
        assert len(result) == 60
        assert result is not df

    def test_5min_aggregation(self):
        df = _make_1min(60)
        result = resample_to(df, "5min")
        # 60 minutes / 5 = 12 bars
        assert len(result) == 12
        # First bar: open=0 (first), high=max(0..4)+1=5, low=min(0..4)-1=-1
        assert result["open"].iloc[0] == 0
        assert result["high"].iloc[0] == 5
        assert result["low"].iloc[0] == -1
        assert result["close"].iloc[0] == 4.5
        assert result["volume"].iloc[0] == 500.0

    def test_1h_aggregation(self):
        df = _make_1min(120)
        result = resample_to(df, "1h")
        # 120 minutes = 2 hours
        assert len(result) == 2
        assert result["volume"].iloc[0] == 6000.0  # 60 bars * 100

    def test_1d_aggregation(self):
        df = _make_1min(1440)  # 1 day of minutes
        result = resample_to(df, "1d")
        assert len(result) == 1
        assert result["volume"].iloc[0] == 1440 * 100

    def test_invalid_frequency_raises(self):
        df = _make_1min(60)
        with pytest.raises(ValueError):
            resample_to(df, "2min")

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df.index = pd.DatetimeIndex([], tz="UTC")
        result = resample_to(df, "1h")
        assert result.empty

    def test_naive_index_gets_utc(self):
        df = _make_1min(60)
        df.index = df.index.tz_localize(None)
        result = resample_to(df, "5min")
        assert result.index.tz is not None

    def test_left_label_left_closed(self):
        """Bar label should be the start of the period (left)."""
        df = _make_1min(60, start="2024-01-01 09:00")
        result = resample_to(df, "5min")
        # First 5-min bar should be labeled 09:00, not 09:05
        assert result.index[0] == pd.Timestamp("2024-01-01 09:00", tz="UTC")

    def test_available_frequencies(self):
        df = _make_1min(60)
        freqs = available_frequencies(df)
        assert "1min" in freqs
        assert "1h" in freqs
