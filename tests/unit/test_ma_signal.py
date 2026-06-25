"""Tests for the MA crossover signal generator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.ma.signal import MAParams, compute_ma, generate_signals, sweep_grid


def _make_trending_ohlcv(n: int = 300, start_price: float = 100.0, trend: float = 0.1) -> pd.DataFrame:
    """Generate OHLCV with a clear uptrend for MA crossover testing."""
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    close = [start_price + trend * i for i in range(n)]
    return pd.DataFrame(
        {
            "open": [c - 0.5 for c in close],
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [10000.0] * n,
        },
        index=idx,
    )


def _make_sideways_ohlcv(n: int = 300, base_price: float = 100.0) -> pd.DataFrame:
    """Generate sideways OHLCV (no trend)."""
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    np.random.seed(42)
    close = base_price + np.random.randn(n) * 2.0
    return pd.DataFrame(
        {
            "open": [c - 0.1 for c in close],
            "high": [c + 0.5 for c in close],
            "low": [c - 0.5 for c in close],
            "close": close,
            "volume": [10000.0] * n,
        },
        index=idx,
    )


class TestComputeMA:
    def test_sma(self):
        s = pd.Series([1, 2, 3, 4, 5], dtype=float)
        result = compute_ma(s, 3, "sma")
        assert result.iloc[2] == 2.0  # (1+2+3)/3
        assert result.iloc[3] == 3.0
        assert pd.isna(result.iloc[0])

    def test_ema(self):
        s = pd.Series([1, 2, 3, 4, 5], dtype=float)
        result = compute_ma(s, 3, "ema")
        assert not pd.isna(result.iloc[2])

    def test_invalid_ma_type(self):
        s = pd.Series([1, 2, 3], dtype=float)
        with pytest.raises(ValueError):
            compute_ma(s, 3, "wma")


class TestGenerateSignals:
    def test_trending_data_generates_long_signal(self):
        df = _make_trending_ohlcv(300)
        params = MAParams(
            fast_ma_window=10,
            slow_ma_window=50,
            trend_filter_active=False,
            long_only=True,
        )
        signals = generate_signals(df, params)
        # In a clear uptrend, fast MA > slow MA, so position should be 1
        assert (signals["position"] == 1).any()
        # Should have at least one entry signal
        assert (signals["signal"] == 1).any()

    def test_sideways_data_may_not_enter(self):
        df = _make_sideways_ohlcv(300)
        params = MAParams(
            fast_ma_window=10,
            slow_ma_window=50,
            trend_filter_active=False,
            long_only=True,
        )
        signals = generate_signals(df, params)
        # Sideways data may or may not generate signals, but no errors
        assert "position" in signals.columns
        assert "signal" in signals.columns

    def test_insufficient_data_returns_empty(self):
        df = _make_trending_ohlcv(10)
        params = MAParams(fast_ma_window=20, slow_ma_window=100)
        signals = generate_signals(df, params)
        # With insufficient data, returns DataFrame with same index but NaN values
        assert len(signals) == len(df)
        # Position should be NaN or 0 (no valid signals possible)
        assert signals["position"].isna().all() or (signals["position"] == 0).all()

    def test_long_short_mode(self):
        df = _make_trending_ohlcv(300)
        params = MAParams(
            fast_ma_window=10,
            slow_ma_window=50,
            trend_filter_active=False,
            long_only=False,
        )
        signals = generate_signals(df, params)
        # In long/short mode, position can be -1
        # In uptrend, should be +1
        assert (signals["position"] == 1).any()

    def test_trend_filter_blocks_entries(self):
        """With trend filter active and price below 200-SMA, no long entries."""
        df = _make_sideways_ohlcv(300, base_price=50.0)
        params = MAParams(
            fast_ma_window=10,
            slow_ma_window=50,
            trend_filter_active=True,
            trend_filter_window=200,
            long_only=True,
        )
        signals = generate_signals(df, params)
        # If price is below 200-SMA, trend_ok is False, so position stays 0
        trend_ok = df["close"] > df["close"].rolling(200).mean()
        if not trend_ok.all():
            # Some bars where trend filter blocks
            blocked = signals.loc[~trend_ok, "position"]
            assert (blocked == 0).all()

    def test_no_lookahead_bias(self):
        """Signal at time T should only use data up to T."""
        df = _make_trending_ohlcv(300)
        params = MAParams(
            fast_ma_window=20,
            slow_ma_window=100,
            trend_filter_active=False,
        )
        signals = generate_signals(df, params)

        # The position at bar T is determined by MAs up to bar T
        # Changing future data should not change the signal at T
        df_modified = df.copy()
        df_modified.iloc[250:, df_modified.columns.get_loc("close")] *= 10  # distort future

        signals_modified = generate_signals(df_modified, params)

        # Signals up to bar 249 should be identical
        common_idx = signals.index[:250]
        pd.testing.assert_series_equal(
            signals.loc[common_idx, "position"],
            signals_modified.loc[common_idx, "position"],
            check_names=False,
        )

    def test_signal_is_position_diff(self):
        """Signal column should be the diff of position column."""
        df = _make_trending_ohlcv(300)
        params = MAParams(fast_ma_window=10, slow_ma_window=50, trend_filter_active=False)
        signals = generate_signals(df, params)
        expected_signal = signals["position"].diff().fillna(0).astype(int)
        pd.testing.assert_series_equal(signals["signal"], expected_signal, check_names=False)

    def test_sweep_grid_produces_params(self):
        grid = sweep_grid()
        assert len(grid) > 0
        # Check that fast < slow for all
        for p in grid:
            assert p.fast_ma_window < p.slow_ma_window

    def test_position_values_valid(self):
        """Position should only be -1, 0, or +1."""
        df = _make_trending_ohlcv(300)
        for long_only in [True, False]:
            params = MAParams(
                fast_ma_window=10,
                slow_ma_window=50,
                trend_filter_active=False,
                long_only=long_only,
            )
            signals = generate_signals(df, params)
            valid = signals["position"].isin([-1, 0, 1]).all()
            assert valid, f"Invalid position values with long_only={long_only}"
