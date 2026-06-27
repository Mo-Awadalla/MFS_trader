"""Tests for canonical Pairs v1 signal lifecycle."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.pairs.signal import PairsParams, generate_signals


def _pairs_signal_panel(n_days: int = 300, n_symbols: int = 4) -> pd.DataFrame:
    idx = pd.bdate_range("2023-01-03", periods=n_days, tz="UTC")
    symbols = tuple(f"S{i:03d}" for i in range(n_symbols))
    fields = ("open", "high", "low", "close", "volume")
    columns = pd.MultiIndex.from_product([symbols, fields], names=["symbol", "field"])
    df = pd.DataFrame(index=idx, columns=columns, dtype=float)

    rng = np.random.default_rng(7)
    log_base = np.log(50.0) + np.cumsum(rng.normal(0.0, 0.01, n_days))
    base = np.exp(log_base)
    stationary = rng.normal(0.0, 0.002, n_days)
    spike_ts = pd.Timestamp("2023-12-29", tz="UTC")
    if spike_ts in idx:
        spike_pos = idx.get_loc(spike_ts)
        if not isinstance(spike_pos, int):
            raise AssertionError("expected unique spike timestamp")
        stationary[spike_pos] = 0.004

    for i, symbol in enumerate(symbols):
        if symbol == "S000":
            close = base
        elif symbol == "S001":
            close = np.exp(log_base + 0.04 + stationary)
        else:
            independent = np.log(30.0 + i) + np.cumsum(rng.normal(0.0, 0.02 + i * 0.005, n_days))
            close = np.exp(independent)
        volume = np.full(n_days, 2_000_000.0 - i * 100_000.0)
        df[(symbol, "open")] = close
        df[(symbol, "high")] = close * 1.01
        df[(symbol, "low")] = close * 0.99
        df[(symbol, "close")] = close
        df[(symbol, "volume")] = volume
    return df


def _fast_params() -> PairsParams:
    return PairsParams(
        candidate_pool_size=4,
        formation_window_days=252,
        liquidity_lookback_days=20,
        min_history_days=60,
        min_eligible_universe=2,
        min_median_dollar_volume=1.0,
        max_active_pairs=1,
    )


class TestPairsSignal:
    def test_monthly_refit_enters_cointegrated_pair_and_exits_on_mean_reversion(self) -> None:
        df = _pairs_signal_panel()
        signals = generate_signals(df, _fast_params())

        weights = signals.xs("weight", axis=1, level="field")
        active_count = signals[("portfolio", "active_pair_count")]
        entries = signals[("portfolio", "entry_count")]
        exits = signals[("portfolio", "exit_count")]

        assert bool(signals.loc["2024-01-01", ("portfolio", "is_rebalance")])
        assert entries.loc["2024-01-01"] == 1
        assert active_count.loc["2024-01-01"] == 1
        assert weights.loc["2024-01-01"].abs().sum() == pytest.approx(2.0)
        assert weights.loc["2024-01-01"].sum() == pytest.approx(0.0, abs=0.05)
        assert exits.loc["2024-01-03"] == 1
        assert active_count.loc["2024-01-03"] == 0
        assert weights.loc["2024-01-03"].abs().sum() == pytest.approx(0.0)

    def test_uses_prior_data_only(self) -> None:
        df = _pairs_signal_panel()
        params = _fast_params()
        original = generate_signals(df, params)

        modified = df.copy()
        modified.loc["2024-01-02":, ("S000", "close")] *= 5.0
        changed = generate_signals(modified, params)

        pd.testing.assert_frame_equal(
            original.loc[: "2024-01-01"],
            changed.loc[: "2024-01-01"],
        )

    def test_short_history_skips_without_preparing_positions(self) -> None:
        df = _pairs_signal_panel(n_days=70)
        signals = generate_signals(df, _fast_params())

        weights = signals.xs("weight", axis=1, level="field")
        skipped = signals[("portfolio", "rebalance_skipped")]

        assert skipped.any()
        assert weights.abs().sum().sum() == pytest.approx(0.0)
