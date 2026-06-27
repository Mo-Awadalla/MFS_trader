"""Tests for the Bollinger Bands mean-reversion signal generator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.bb.signal import (
    BBParams,
    compact_sweep_grid,
    compute_bollinger_bands,
    default_params,
    diagnose_signals,
    generate_signals,
    params_from_dict,
    params_to_dict,
    sweep_grid,
    width_filter_mask,
)


def _make_mean_reverting_ohlcv(n: int = 400, base_price: float = 100.0) -> pd.DataFrame:
    """Oscillating series to exercise mean-reversion entries."""
    idx = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    close = base_price + 10.0 * np.sin(np.linspace(0, 20 * np.pi, n))
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": [10000.0] * n,
        },
        index=idx,
    )


class TestBollingerBands:
    def test_compute_bands(self):
        close = pd.Series([100.0, 101.0, 99.0, 102.0, 98.0, 100.0, 101.0, 99.0, 100.0, 101.0])
        middle, upper, lower, width = compute_bollinger_bands(close, window=5, std_mult=2.0)
        assert middle.iloc[-1] == pytest.approx(close.tail(5).mean())
        assert upper.iloc[-1] > middle.iloc[-1]
        assert lower.iloc[-1] < middle.iloc[-1]
        assert width.iloc[-1] > 0

    def test_width_filter_none(self):
        close = pd.Series(np.linspace(100, 110, 300))
        _, _, _, width = compute_bollinger_bands(close, 20, 2.0)
        mask = width_filter_mask(width, BBParams(width_mode="none"))
        assert mask.all()

    def test_mean_reversion_generates_entries(self):
        df = _make_mean_reverting_ohlcv()
        params = BBParams(window=10, std_mult=1.5, width_mode="none", width_lookback=30)
        signals = generate_signals(df, params)
        assert (signals["position"] == 1).any()
        assert (signals["signal"] == 1).any()

    def test_insufficient_data_returns_empty_shape(self):
        df = _make_mean_reverting_ohlcv(20)
        params = default_params()
        signals = generate_signals(df, params)
        assert len(signals) == len(df)
        assert signals["position"].isna().all() or (signals["position"] == 0).all()

    def test_no_lookahead_bias(self):
        df = _make_mean_reverting_ohlcv()
        params = BBParams(window=15, std_mult=2.0, width_mode="none", width_lookback=30)
        signals = generate_signals(df, params)

        df_modified = df.copy()
        df_modified.iloc[250:, df_modified.columns.get_loc("close")] *= 2.0
        signals_modified = generate_signals(df_modified, params)

        common_idx = signals.index[:250]
        pd.testing.assert_series_equal(
            signals.loc[common_idx, "position"],
            signals_modified.loc[common_idx, "position"],
            check_names=False,
        )

    def test_signal_is_position_diff(self):
        df = _make_mean_reverting_ohlcv()
        params = BBParams(window=10, std_mult=1.5, width_mode="none", width_lookback=30)
        signals = generate_signals(df, params)
        expected = signals["position"].diff().fillna(0).astype(int)
        pd.testing.assert_series_equal(signals["signal"], expected, check_names=False)

    def test_long_only_positions(self):
        df = _make_mean_reverting_ohlcv()
        signals = generate_signals(df, BBParams(window=10, std_mult=1.5, width_mode="none", width_lookback=30))
        assert signals["position"].isin([0, 1]).all()

    def test_breakout_not_implemented(self):
        df = _make_mean_reverting_ohlcv()
        with pytest.raises(NotImplementedError):
            generate_signals(df, BBParams(mean_reversion=False))

    def test_sweep_grid_sizes(self):
        grid = sweep_grid()
        assert len(grid) == 9 * 7 * 3
        windows = {p.window for p in grid}
        assert min(windows) == 10
        assert max(windows) == 50

    def test_compact_sweep_grid(self):
        assert len(compact_sweep_grid()) == 3

    def test_params_roundtrip(self):
        params = default_params()
        assert params_from_dict(params_to_dict(params)) == params

    def test_diagnose_signals_counts_filter_rejections(self):
        df = _make_mean_reverting_ohlcv(400)
        params = BBParams(window=10, std_mult=1.5, width_mode="normal", width_lookback=60)
        diag = diagnose_signals(df, params)
        assert diag["raw_entry_events"] >= diag["filtered_entry_events"]
        rejected = diag.get("rejected_by_reason", {}).get("width_filter", 0)
        assert rejected == diag["raw_entry_events"] - diag["filtered_entry_events"]

    def test_exits_fire_after_entry(self):
        """Exit crosses must reduce position — prior ffill bug held forever."""
        df = _make_mean_reverting_ohlcv(400)
        params = BBParams(window=10, std_mult=1.5, width_mode="none", width_lookback=30)
        signals = generate_signals(df, params)
        assert (signals["exit_signals"] if "exit_signals" in signals else (signals["signal"] == -1)).any() or (
            signals["signal"] == -1
        ).any()
        assert (signals["signal"] == -1).any()
