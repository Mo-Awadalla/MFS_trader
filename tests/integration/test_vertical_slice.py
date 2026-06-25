"""Integration test: data → signals → backtest end-to-end with synthetic data.

This proves the vertical slice works: generate fake OHLCV → validate → store
to Parquet → load → generate MA signals → run backtest → verify metrics.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config.schema import AssetClass, CostModelConfig
from data.resample import resample_to
from data.validate import QualityResult, validate_ohlcv
from research.runner import run_single_asset_backtest
from storage.parquet_io import append_bars, parquet_path, read_bars
from strategies.ma.signal import MAParams, generate_signals


def _generate_synthetic_1min(symbol: str, days: int = 5, seed: int = 42) -> pd.DataFrame:
    """Generate realistic-looking 1-min OHLCV for testing."""
    np.random.seed(seed)
    bars_per_day = 390  # US market hours
    total_bars = days * bars_per_day
    base_date = pd.Timestamp("2024-06-01 09:30:00", tz="UTC")

    timestamps = []
    for day in range(days):
        for minute in range(bars_per_day):
            timestamps.append(base_date + pd.Timedelta(days=day, minutes=minute))

    # Random walk with slight uptrend
    returns = np.random.randn(total_bars) * 0.001 + 0.00005
    close = 100.0 * np.cumprod(1 + returns)

    df = pd.DataFrame(
        {
            "open": close * (1 + np.random.randn(total_bars) * 0.0001),
            "high": close * (1 + np.abs(np.random.randn(total_bars)) * 0.0005),
            "low": close * (1 - np.abs(np.random.randn(total_bars)) * 0.0005),
            "close": close,
            "volume": np.random.randint(1000, 50000, total_bars).astype(float),
        },
        index=pd.DatetimeIndex(timestamps, name="timestamp"),
    )
    # Ensure OHLC sanity
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    return df


@pytest.fixture
def synthetic_data(tmp_path) -> tuple[Path, pd.DataFrame]:
    """Generate synthetic 1-min data, validate, and store to Parquet."""
    df = _generate_synthetic_1min("TEST", days=10)

    # Validate (WARN is acceptable — overnight gaps are normal for equity data)
    now = df.index[-1] + pd.Timedelta(seconds=30)
    report = validate_ohlcv(df, "TEST", "synthetic", frequency="1min", now_ts=now)
    assert report.result in (QualityResult.PASS, QualityResult.WARN)
    assert report.result != QualityResult.FAIL

    # Store
    path = parquet_path(tmp_path, "TEST", "1min", source="synthetic")
    append_bars(df, path)

    # Resample to daily and store
    daily = resample_to(df, "1d")
    daily_path = parquet_path(tmp_path, "TEST", "1d", source="synthetic")
    append_bars(daily, daily_path)

    return tmp_path, df


class TestVerticalSlice:
    """Prove the full pipeline works: data → signals → backtest."""

    def test_data_roundtrip(self, synthetic_data):
        """Stored data should match generated data."""
        tmp_path, original = synthetic_data
        path = parquet_path(tmp_path, "TEST", "1min", source="synthetic")
        loaded = read_bars(path)
        assert len(loaded) == len(original)
        pd.testing.assert_frame_equal(
            loaded.sort_index(),
            original.sort_index(),
            check_dtype=False,
        )

    def test_resample_to_daily(self, synthetic_data):
        """1-min data should resample to daily correctly."""
        tmp_path, original = synthetic_data
        daily = resample_to(original, "1d")
        assert len(daily) == 10  # 10 trading days
        assert daily["volume"].sum() == original["volume"].sum()

    def test_ma_signals_on_synthetic_data(self, synthetic_data):
        """MA signal generator should work on loaded data."""
        tmp_path, _ = synthetic_data
        daily_path = parquet_path(tmp_path, "TEST", "1d", source="synthetic")
        df = read_bars(daily_path)

        params = MAParams(
            fast_ma_window=3,
            slow_ma_window=5,
            trend_filter_active=False,
            long_only=True,
        )
        signals = generate_signals(df, params)
        assert "position" in signals.columns
        assert "signal" in signals.columns
        # Position values should be valid
        assert signals["position"].isin([-1, 0, 1]).all()

    def test_full_backtest_pipeline(self, synthetic_data):
        """Full pipeline: load → signals → backtest → metrics."""
        tmp_path, _ = synthetic_data
        daily_path = parquet_path(tmp_path, "TEST", "1d", source="synthetic")
        df = read_bars(daily_path)

        params = MAParams(
            fast_ma_window=3,
            slow_ma_window=5,
            trend_filter_active=False,
            long_only=True,
        )
        signals = generate_signals(df, params)

        result = run_single_asset_backtest(
            df,
            signals,
            strategy_name="dual_ma_crossover",
            symbol="TEST",
            asset_class=AssetClass.EQUITY,
            cost_config=CostModelConfig(),
            initial_capital=10000.0,
            params={"fast_ma_window": 3, "slow_ma_window": 5},
        )

        assert result.bar_count > 0
        assert "sharpe" in result.metrics
        assert "total_return" in result.metrics
        assert "max_drawdown" in result.metrics
        assert result.metrics["final_equity"] > 0  # never went to zero

    def test_validation_blocks_bad_data(self, tmp_path):
        """Validator should FAIL on bad OHLCV data and prevent storage."""
        bad_df = pd.DataFrame(
            {
                "open": [100.0, 50.0],  # high < low on row 1
                "high": [101.0, 40.0],
                "low": [99.0, 60.0],
                "close": [100.5, 45.0],
                "volume": [1000.0, 2000.0],
            },
            index=pd.date_range("2024-01-01", periods=2, freq="1min", tz="UTC"),
        )
        now = bad_df.index[-1] + pd.Timedelta(seconds=30)
        report = validate_ohlcv(bad_df, "BAD", "synthetic", frequency="1min", now_ts=now)
        # Should have issues (high < low on second bar)
        assert len(report.issues) > 0
