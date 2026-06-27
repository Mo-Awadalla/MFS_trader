"""Tests for canonical Momentum v1 signal construction."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.momentum.signal import MomentumParams, generate_signals


def _momentum_frame(
    *,
    n_days: int = 310,
    n_symbols: int = 120,
    start: str = "2023-01-03",
) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=n_days, tz="UTC")
    symbols = tuple(f"S{i:03d}" for i in range(n_symbols))
    fields = ("open", "high", "low", "close", "volume")
    columns = pd.MultiIndex.from_product([symbols, fields], names=["symbol", "field"])
    df = pd.DataFrame(index=idx, columns=columns, dtype=float)

    for i, symbol in enumerate(symbols):
        base = 20.0 + i
        close = np.full(n_days, base)
        momentum_return = ((i - n_symbols / 2) / n_symbols) * 0.40
        close[40:252] = np.linspace(base, base * (1.0 + momentum_return), 212)
        close[252:] = close[251]
        df[(symbol, "close")] = close
        df[(symbol, "open")] = close
        df[(symbol, "high")] = close * 1.01
        df[(symbol, "low")] = close * 0.99
        df[(symbol, "volume")] = 2_000_000.0

    return df


class TestMomentumSignal:
    def test_rebalance_forms_dollar_neutral_top_bottom_quartiles(self) -> None:
        df = _momentum_frame()
        signals = generate_signals(df, MomentumParams())

        weights = signals.xs("weight", axis=1, level="field")
        rebalance_weights = weights.loc["2024-03-01"]

        assert (rebalance_weights > 0).sum() == 30
        assert (rebalance_weights < 0).sum() == 30
        assert rebalance_weights[rebalance_weights > 0].sum() == pytest.approx(1.0)
        assert rebalance_weights[rebalance_weights < 0].sum() == pytest.approx(-1.0)
        assert rebalance_weights.abs().sum() == pytest.approx(2.0)

        long_symbols = set(rebalance_weights[rebalance_weights > 0].index)
        short_symbols = set(rebalance_weights[rebalance_weights < 0].index)
        assert "S119" in long_symbols
        assert "S000" in short_symbols

    def test_uses_prior_data_only(self) -> None:
        df = _momentum_frame()
        params = MomentumParams()
        original = generate_signals(df, params)

        modified = df.copy()
        modified.loc["2024-03-04":, ("S000", "close")] *= 100.0
        changed = generate_signals(modified, params)

        pd.testing.assert_frame_equal(
            original.loc[: "2024-03-01"],
            changed.loc[: "2024-03-01"],
        )

    def test_rebalances_on_first_trading_session_of_month(self) -> None:
        df = _momentum_frame(n_days=330)
        signals = generate_signals(df, MomentumParams())
        rebalances = signals[("portfolio", "is_rebalance")].astype(bool)

        assert bool(rebalances.loc["2024-03-01"])
        assert bool(rebalances.loc["2024-04-01"])
        assert not bool(rebalances.loc["2024-04-02"])

    def test_skips_below_minimum_universe_and_retains_holdings(self) -> None:
        df = _momentum_frame(n_symbols=120, n_days=340)
        symbols_to_break = [f"S{i:03d}" for i in range(80)]
        df.loc["2024-03-04":, [(symbol, "close") for symbol in symbols_to_break]] = np.nan

        signals = generate_signals(df, MomentumParams())

        weights = signals.xs("weight", axis=1, level="field")
        skipped = signals[("portfolio", "rebalance_skipped")]
        reason = signals[("portfolio", "skip_reason")]

        assert bool(skipped.loc["2024-04-01"])
        assert reason.loc["2024-04-01"] == "insufficient_eligible_universe"
        pd.testing.assert_series_equal(
            weights.loc["2024-04-01"],
            weights.loc["2024-03-01"],
            check_names=False,
        )

    def test_validates_multi_symbol_ohlcv_shape(self) -> None:
        bad = pd.DataFrame({"close": [1.0, 2.0]}, index=pd.date_range("2024-01-01", periods=2))

        with pytest.raises(ValueError, match="MultiIndex"):
            generate_signals(bad, MomentumParams())

    def test_requires_complete_ohlcv_fields_for_every_symbol(self) -> None:
        df = _momentum_frame(n_symbols=120)
        incomplete = df.drop(columns=[("S000", "volume")])

        with pytest.raises(ValueError, match="missing fields"):
            generate_signals(incomplete, MomentumParams())
