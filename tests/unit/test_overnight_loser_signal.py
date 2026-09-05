"""Tests for overnight loser v1 signal construction and cost model."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config.schema import CostModelConfig
from research.cross_sectional_pipeline import backtest_cross_sectional, build_returns_matrix
from research.overnight_loser_cost import (
    BASE_COMMISSION_PCT,
    BASE_SLIPPAGE_PCT,
    overnight_loser_cost_config,
)
from strategies.overnight_loser.signal import (
    TEMPLATE_VERSION,
    OvernightLoserParams,
    generate_signals,
    params_from_dict,
    params_to_dict,
    universe_symbols,
)

GAP_DAY = "2024-02-13"  # bar index 30 of the fixture


def _panel(*, n_days: int = 40, n_symbols: int = 10) -> pd.DataFrame:
    """Flat panel at 100 with known overnight gaps on GAP_DAY.

    S000 opens -10%, S001 -8%, S002 -5%, S003 -3%; S008 +5%, S009 +10%;
    everything else gaps 0%.
    """
    idx = pd.bdate_range("2024-01-02", periods=n_days, tz="UTC")
    symbols = tuple(f"S{i:03d}" for i in range(n_symbols))
    fields = ("open", "high", "low", "close", "volume")
    columns = pd.MultiIndex.from_product([symbols, fields], names=["symbol", "field"])
    df = pd.DataFrame(index=idx, columns=columns, dtype=float)
    for symbol in symbols:
        df[(symbol, "open")] = 100.0
        df[(symbol, "high")] = 101.0
        df[(symbol, "low")] = 99.0
        df[(symbol, "close")] = 100.0
        df[(symbol, "volume")] = 2_000_000.0
    gaps = {"S000": 90.0, "S001": 92.0, "S002": 95.0, "S003": 97.0, "S008": 105.0, "S009": 110.0}
    for symbol, open_price in gaps.items():
        if symbol in symbols:
            df.loc[GAP_DAY, (symbol, "open")] = open_price
    return df


class TestOvernightLoserSignal:
    def test_buys_worst_overnight_losers_equal_weight(self) -> None:
        signals = generate_signals(_panel(), OvernightLoserParams())
        weights = signals.xs("weight", axis=1, level="field").loc[GAP_DAY]
        trades = signals.xs("trade", axis=1, level="field").loc[GAP_DAY]

        long_symbols = set(weights[weights > 0].index)
        assert long_symbols == {"S000", "S001", "S002", "S003"}
        assert weights[weights > 0].tolist() == pytest.approx([0.25] * 4)
        assert weights.sum() == pytest.approx(1.0)
        assert (weights < 0).sum() == 0  # long-only v1
        pd.testing.assert_series_equal(trades, weights, check_names=False)

    def test_long_short_variant_is_dollar_neutral(self) -> None:
        params = OvernightLoserParams(
            num_long_positions=2,
            num_short_positions=2,
            short_gross=1.0,
        )
        signals = generate_signals(_panel(), params)
        weights = signals.xs("weight", axis=1, level="field").loc[GAP_DAY]

        assert set(weights[weights > 0].index) == {"S000", "S001"}
        assert set(weights[weights < 0].index) == {"S008", "S009"}
        assert weights.sum() == pytest.approx(0.0)
        assert weights.abs().sum() == pytest.approx(2.0)

    def test_flat_before_warmup(self) -> None:
        params = OvernightLoserParams()
        signals = generate_signals(_panel(), params)
        weights = signals.xs("weight", axis=1, level="field")
        skip_reason = signals[("portfolio", "skip_reason")]

        warmup = max(params.min_history_days, params.liquidity_lookback_days)
        assert weights.iloc[:warmup].abs().sum().sum() == 0
        assert (skip_reason.iloc[:warmup] == "insufficient_history").all()
        assert weights.iloc[warmup:].abs().sum(axis=1).min() == pytest.approx(1.0)

    def test_signal_uses_same_bar_open_but_not_same_bar_close(self) -> None:
        params = OvernightLoserParams()
        original = generate_signals(_panel(), params)

        modified = _panel()
        modified.loc[GAP_DAY, ("S005", "close")] = 10.0  # same-bar close must not matter
        changed = generate_signals(modified, params)
        pd.testing.assert_series_equal(
            original.xs("weight", axis=1, level="field").loc[GAP_DAY],
            changed.xs("weight", axis=1, level="field").loc[GAP_DAY],
        )

        gapped = _panel()
        gapped.loc[GAP_DAY, ("S005", "open")] = 80.0  # same-bar open must matter
        regenerated = generate_signals(gapped, params)
        weights = regenerated.xs("weight", axis=1, level="field").loc[GAP_DAY]
        assert weights["S005"] == pytest.approx(0.25)

    def test_skips_when_universe_smaller_than_position_count(self) -> None:
        df = _panel(n_symbols=3)
        signals = generate_signals(df, OvernightLoserParams(num_long_positions=4))
        weights = signals.xs("weight", axis=1, level="field")
        skip_reason = signals[("portfolio", "skip_reason")]

        assert weights.abs().sum().sum() == 0
        assert (skip_reason.iloc[20:] == "insufficient_eligible_universe").all()

    def test_params_roundtrip(self) -> None:
        params = OvernightLoserParams(num_short_positions=2, short_gross=1.0, delay_bps=2.0)
        assert params_from_dict(params_to_dict(params)) == params

    def test_unknown_universe_raises(self) -> None:
        with pytest.raises(KeyError, match="unknown overnight_loser universe"):
            universe_symbols("nonexistent")

    def test_sector_spdr_universe_has_twelve_tickers(self) -> None:
        assert len(universe_symbols("sector_spdrs")) == 12


class TestOvernightLoserCosts:
    def test_spread_and_delay_fold_into_slippage(self) -> None:
        params = OvernightLoserParams(spread_bps=3.0, delay_bps=2.0)
        cost = overnight_loser_cost_config(params)
        assert cost.slippage_fixed_pct == pytest.approx(BASE_SLIPPAGE_PCT + 0.0003 + 0.0002)
        assert cost.commission_pct == pytest.approx(BASE_COMMISSION_PCT)

    def test_zero_spread_and_delay_keeps_base_costs(self) -> None:
        params = OvernightLoserParams(spread_bps=0.0, delay_bps=0.0)
        cost = overnight_loser_cost_config(params)
        assert cost.slippage_fixed_pct == pytest.approx(BASE_SLIPPAGE_PCT)


class TestEntryOnOpenBacktest:
    def test_open_to_close_returns_and_round_trip_costs(self) -> None:
        params = OvernightLoserParams()
        cost = overnight_loser_cost_config(params)
        result = backtest_cross_sectional(
            _panel(),
            params,
            strategy_name="overnight_loser",
            generate_signals=generate_signals,
            params_to_dict=params_to_dict,
            cost_config=cost,
            initial_capital=10_000.0,
            entry_on_open=True,
            template_version=TEMPLATE_VERSION,
        )

        expected_gross = 0.25 * sum(
            100.0 / open_price - 1.0 for open_price in (90.0, 92.0, 95.0, 97.0)
        )
        buy_pct = cost.slippage_fixed_pct + cost.commission_pct
        sell_pct = buy_pct + cost.sec_fee_per_dollar_sold + 0.0001
        expected_net = expected_gross - 1.0 * (buy_pct + sell_pct)
        assert result.returns.loc[GAP_DAY] == pytest.approx(expected_net)

    def test_zero_cost_gap_free_days_earn_nothing_gross(self) -> None:
        zero_cost = CostModelConfig(
            slippage_fixed_pct=0.0,
            slippage_variable_coeff=0.0,
            commission_pct=0.0,
            sec_fee_per_dollar_sold=0.0,
            finra_taf_per_share_sold=0.0,
            borrow_cost_annual_pct=0.0,
        )
        result = backtest_cross_sectional(
            _panel(),
            OvernightLoserParams(),
            strategy_name="overnight_loser",
            generate_signals=generate_signals,
            params_to_dict=params_to_dict,
            cost_config=zero_cost,
            initial_capital=10_000.0,
            entry_on_open=True,
            template_version=TEMPLATE_VERSION,
        )
        # Open == close on gap-free days so gross return is zero; the only
        # residual is the house-convention 1 bp TAF sell approximation on
        # invested days (matching trade_costs in cross_sectional_pipeline).
        gap_free = result.returns.drop(pd.Timestamp(GAP_DAY, tz="UTC"))
        warmup_days = gap_free.iloc[:20]
        invested_days = gap_free.iloc[20:]
        assert np.allclose(warmup_days, 0.0)
        assert np.allclose(invested_days, -0.0001)

    def test_round_trip_costs_follow_open_to_close_weights_not_signal_deltas(self) -> None:
        params = OvernightLoserParams()
        cost = overnight_loser_cost_config(params)

        def zero_trade_signals(df: pd.DataFrame, signal_params: OvernightLoserParams) -> pd.DataFrame:
            signals = generate_signals(df, signal_params)
            signals.loc[:, pd.IndexSlice[:, "trade"]] = 0.0
            return signals

        result = backtest_cross_sectional(
            _panel(),
            params,
            strategy_name="overnight_loser",
            generate_signals=zero_trade_signals,
            params_to_dict=params_to_dict,
            cost_config=cost,
            entry_on_open=True,
            template_version=TEMPLATE_VERSION,
        )

        buy_pct = cost.slippage_fixed_pct + cost.commission_pct
        sell_pct = buy_pct + cost.sec_fee_per_dollar_sold + 0.0001
        assert result.returns.loc[GAP_DAY] == pytest.approx(
            0.25 * sum(100.0 / open_price - 1.0 for open_price in (90.0, 92.0, 95.0, 97.0))
            - buy_pct
            - sell_pct
        )

    def test_returns_matrix_uses_open_to_close_execution_when_requested(self) -> None:
        params = OvernightLoserParams()
        result = backtest_cross_sectional(
            _panel(),
            params,
            strategy_name="overnight_loser",
            generate_signals=generate_signals,
            params_to_dict=params_to_dict,
            cost_config=overnight_loser_cost_config(params),
            entry_on_open=True,
            template_version=TEMPLATE_VERSION,
        )

        matrix = build_returns_matrix(
            _panel(),
            params,
            strategy_name="overnight_loser",
            generate_signals=generate_signals,
            params_to_dict=params_to_dict,
            cost_config=overnight_loser_cost_config(params),
            entry_on_open=True,
            template_version=TEMPLATE_VERSION,
        )

        assert matrix[:, 0] == pytest.approx(result.returns.to_numpy())
