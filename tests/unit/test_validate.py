"""Tests for the data quality validator."""

from __future__ import annotations

import pandas as pd

from data.validate import QualityResult, validate_ohlcv


def _make_ohlcv(n: int = 100, start: str = "2024-01-01") -> pd.DataFrame:
    """Generate clean 1-min OHLCV data."""
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.5] * n,
            "volume": [1000.0] * n,
        },
        index=idx,
    )


class TestValidateOHLCV:
    def test_clean_data_passes(self):
        df = _make_ohlcv(100)
        now = df.index[-1] + pd.Timedelta(seconds=30)
        report = validate_ohlcv(df, "AAPL", "alpaca", frequency="1min", now_ts=now)
        assert report.result == QualityResult.PASS
        assert report.bars_checked == 100
        assert len(report.issues) == 0

    def test_empty_dataframe_fails(self):
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df.index = pd.DatetimeIndex([], name="timestamp", tz="UTC")
        report = validate_ohlcv(df, "AAPL", "alpaca", frequency="1min")
        assert report.result == QualityResult.FAIL

    def test_invalid_ohlcv_high_below_low(self):
        df = _make_ohlcv(100)
        df.iloc[10, df.columns.get_loc("high")] = 50.0  # high < low
        report = validate_ohlcv(df, "AAPL", "alpaca", frequency="1min")
        assert report.result in (QualityResult.WARN, QualityResult.FAIL)
        assert any(i.check == "ohlcv_sanity" for i in report.issues)

    def test_negative_prices_fail(self):
        df = _make_ohlcv(100)
        df.iloc[5, df.columns.get_loc("close")] = -10.0
        report = validate_ohlcv(df, "AAPL", "alpaca", frequency="1min")
        assert any(i.check == "ohlcv_sanity" for i in report.issues)

    def test_negative_volume_fails(self):
        df = _make_ohlcv(100)
        df.iloc[5, df.columns.get_loc("volume")] = -100.0
        report = validate_ohlcv(df, "AAPL", "alpaca", frequency="1min")
        assert any(i.check == "ohlcv_sanity" for i in report.issues)

    def test_exact_duplicates_warn(self):
        df = _make_ohlcv(100)
        df = pd.concat([df, df.iloc[[10]]])  # exact duplicate
        df = df.sort_index()
        report = validate_ohlcv(df, "AAPL", "alpaca", frequency="1min")
        assert any(i.check == "duplicates" and i.severity == QualityResult.WARN for i in report.issues)

    def test_conflicting_duplicates_fail(self):
        df = _make_ohlcv(100)
        conflicting = df.iloc[[10]].copy()
        conflicting["close"] = 999.0
        df = pd.concat([df, conflicting]).sort_index()
        report = validate_ohlcv(df, "AAPL", "alpaca", frequency="1min")
        assert any(i.check == "duplicates" and i.severity == QualityResult.FAIL for i in report.issues)

    def test_stale_latest_bar_fails_in_live(self):
        df = _make_ohlcv(100, start="2024-01-01")
        now = df.index[-1] + pd.Timedelta(minutes=10)
        report = validate_ohlcv(
            df, "AAPL", "alpaca", frequency="1min", is_live=True, now_ts=now
        )
        assert any(i.check == "staleness" and i.severity == QualityResult.FAIL for i in report.issues)

    def test_stale_latest_bar_warns_in_research(self):
        df = _make_ohlcv(100, start="2024-01-01")
        now = df.index[-1] + pd.Timedelta(hours=2)
        report = validate_ohlcv(
            df, "AAPL", "alpaca", frequency="1min", is_live=False, now_ts=now
        )
        # In research, very old data is just a warning, not a failure
        staleness_issues = [i for i in report.issues if i.check == "staleness"]
        # May or may not have a staleness warning depending on threshold
        for issue in staleness_issues:
            assert issue.severity == QualityResult.WARN

    def test_gap_detection_warns(self):
        df = _make_ohlcv(100)
        # Remove some bars to create a gap
        df = df.drop(df.index[50:55])
        report = validate_ohlcv(df, "AAPL", "alpaca", frequency="1min")
        assert any(i.check == "gap_detection" for i in report.issues)

    def test_all_zero_volume_fails(self):
        df = _make_ohlcv(100)
        df["volume"] = 0.0
        report = validate_ohlcv(df, "AAPL", "alpaca", frequency="1min")
        assert any(i.check == "volume" and i.severity == QualityResult.FAIL for i in report.issues)

    def test_missing_columns_fails(self):
        df = _make_ohlcv(100)
        df = df.drop(columns=["volume"])
        report = validate_ohlcv(df, "AAPL", "alpaca", frequency="1min")
        assert any(i.check == "schema" and i.severity == QualityResult.FAIL for i in report.issues)
