"""Integration tests for VS-ICSM registry and vectorized research plumbing."""

from __future__ import annotations

import pandas as pd

from research.vs_icsm_experiment import build_vs_icsm_experiment_draft
from research.vs_icsm_pipeline import backtest_vs_icsm
from strategies.registry import get_strategy, strategy_template_version
from strategies.vs_icsm.signal import VSICSMParams
from strategies.vs_icsm.strategy import TEMPLATE_VERSION, VolatilityStandardizedICSMStrategy
from tests.unit.test_vs_icsm_signal import vs_icsm_panel


def test_vs_icsm_is_registered_canonical_v1() -> None:
    strategy = get_strategy("volatility_standardized_intraday_momentum")

    assert isinstance(strategy, VolatilityStandardizedICSMStrategy)
    assert strategy.metadata()["hypothesis"] == "volatility_standardized_intraday_order_flow_persistence"
    assert strategy.metadata()["long_only"] is True
    assert strategy.metadata()["dollar_neutral"] is False
    assert strategy.metadata()["bar_frequency"] == "1h"
    assert (
        strategy_template_version("volatility_standardized_intraday_momentum")
        == f"volatility_standardized_intraday_momentum:{TEMPLATE_VERSION}"
    )


def test_vs_icsm_backtest_is_deterministic() -> None:
    df = vs_icsm_panel(n_days=95, n_symbols=25)
    params = VSICSMParams(
        universe_size=25,
        transition_buffer_rank=25,
        liquidity_lookback_sessions=20,
        min_history_sessions=20,
        min_eligible_symbols=15,
    )

    first = backtest_vs_icsm(df, params)
    second = backtest_vs_icsm(df, params)

    pd.testing.assert_series_equal(first.returns, second.returns)
    pd.testing.assert_frame_equal(first.weights, second.weights)
    assert first.rebalance_count == len(df)
    assert first.trade_count > 0


def test_vs_icsm_experiment_draft_captures_frozen_execution_spec() -> None:
    df = vs_icsm_panel(n_days=70, n_symbols=20)
    params = VSICSMParams(
        universe_size=20,
        transition_buffer_rank=20,
        liquidity_lookback_sessions=20,
        min_history_sessions=20,
        min_eligible_symbols=15,
    )

    draft = build_vs_icsm_experiment_draft(
        df,
        label="VS-ICSM-v1-synthetic",
        params=params,
        data_source="synthetic",
        git_commit="test",
    )

    assert draft.snapshot.strategy == "volatility_standardized_intraday_momentum"
    assert draft.snapshot.strategy_template_version.endswith(":v1")
    assert draft.snapshot.parameters["momentum_lookback_bars"] == 6
    assert draft.snapshot.parameters["volatility_lookback_bars"] == 13
    assert draft.snapshot.universe.selection_rule == "monthly_top_200_by_trailing_60_session_median_dollar_volume"
    assert draft.snapshot.execution_mode == "limit_only_day_orders_signal_at_hourly_close_execute_next_bar_open"
    assert draft.snapshot.slippage_model["slippage_fixed_pct"] == 0.0004
