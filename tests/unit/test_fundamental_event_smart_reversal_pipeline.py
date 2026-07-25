"""Tests for FundamentalEventSmartReversal scout diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config.schema import CostModelConfig
from research.fundamental_event_smart_reversal_pipeline import _return_components, run_scout
from scripts.run_fundamental_event_smart_reversal_scout import _inclusive_end_timestamp
from strategies.fundamental_event_smart_reversal.signal import (
    FundamentalEventSmartReversalParams,
)


def _panel(n_days: int = 90, n_symbols: int = 12) -> pd.DataFrame:
    index = pd.bdate_range("2023-01-03", periods=n_days, tz="UTC")
    symbols = ("SPY",) + tuple(f"S{i:02d}" for i in range(n_symbols))
    fields = ("open", "high", "low", "close", "volume", "fundamental_event")
    frame = pd.DataFrame(
        index=index,
        columns=pd.MultiIndex.from_product([symbols, fields], names=["symbol", "field"]),
        dtype=float,
    )
    rng = np.random.default_rng(7)
    market = rng.normal(0.0004, 0.01, n_days)
    for i, symbol in enumerate(symbols):
        if symbol == "SPY":
            returns = market
        else:
            noise = rng.normal(0.0, 0.015, n_days)
            returns = 0.3 * market + noise
        close = (100.0 + i) * np.cumprod(1.0 + returns)
        frame[(symbol, "open")] = close
        frame[(symbol, "high")] = close * 1.01
        frame[(symbol, "low")] = close * 0.99
        frame[(symbol, "close")] = close
        frame[(symbol, "volume")] = 2_000_000.0
        frame[(symbol, "fundamental_event")] = 0.0
    frame.loc[index[45], ("S00", "fundamental_event")] = 1.0
    return frame


def test_scout_reports_gross_cost_turnover_event_and_spy_utility() -> None:
    params = FundamentalEventSmartReversalParams(
        liquidity_lookback_days=5,
        min_history_days=20,
        min_price=1.0,
        min_median_dollar_volume=0.0,
        min_eligible_symbols=10,
        max_symbol_weight=0.5,
    )
    report = run_scout(_panel(), params=params, initial_capital=10_000.0)

    assert report.strategy_name == "fundamental_event_smart_reversal"
    assert report.analysis_start is not None
    assert "sharpe" in report.gross_metrics
    assert "sharpe" in report.default_net_metrics
    assert "sharpe" in report.spy_metrics
    assert "sharpe" in report.spy_plus_20pct_overlay_metrics
    assert report.turnover["mean_daily_gross"] >= 0.0
    assert report.event_diagnostics["filing_flagged_symbol_sessions"] == 1
    assert report.event_diagnostics["event_vetoed_symbol_days"] >= 1
    assert report.overlay_diagnostics == {
        "strategy_return_scale": 0.1,
        "strategy_overlay_gross": 0.2,
        "total_portfolio_gross": 1.2,
        "total_portfolio_net": 1.0,
    }
    assert set(report.cost_sensitivity_bps) == {"0.0", "0.5", "1.0", "2.0", "5.0", "10.0"}
    assert "gross_total_return_positive" in report.scout_gates


def test_no_event_comparator_is_diagnostic_only() -> None:
    params = FundamentalEventSmartReversalParams(
        liquidity_lookback_days=5,
        min_history_days=20,
        min_price=1.0,
        min_median_dollar_volume=0.0,
        min_eligible_symbols=10,
        max_symbol_weight=0.5,
    )
    report = run_scout(_panel(), params=params)

    assert report.no_event_comparator["promotion_eligible"] is False
    assert report.no_event_comparator["label"] == "diagnostic_only"


def test_return_components_trade_against_drifted_weights_and_use_adv_impact() -> None:
    index = pd.bdate_range("2024-01-02", periods=3, tz="UTC")
    panel = pd.DataFrame(
        {
            ("A", "close"): [100.0, 110.0, 110.0],
            ("A", "volume"): [1_000.0, 1_000.0, 1_000.0],
        },
        index=index,
    )
    panel.columns = pd.MultiIndex.from_tuples(panel.columns, names=["symbol", "field"])
    signals = pd.DataFrame({("A", "weight"): [0.5, 0.5, 0.5]}, index=index)
    signals.columns = pd.MultiIndex.from_tuples(signals.columns, names=["symbol", "field"])
    zero_cost = {
        "slippage_fixed_pct": 0.0,
        "commission_pct": 0.0,
        "sec_fee_per_dollar_sold": 0.0,
        "finra_taf_per_share_sold": 0.0,
        "borrow_cost_annual_pct": 0.0,
    }

    no_cost = _return_components(
        panel,
        signals,
        CostModelConfig(slippage_variable_coeff=0.0, **zero_cost),
        10_000.0,
    )
    assert np.isclose(no_cost["daily_turnover"].iloc[2], 0.5 * 1.1 / 1.05 - 0.5)

    with_impact = _return_components(
        panel,
        signals,
        CostModelConfig(slippage_variable_coeff=0.5, **zero_cost),
        10_000.0,
    )
    assert np.isclose(with_impact["trading_cost"].iloc[1], 0.0125)


def test_date_only_end_bound_includes_the_full_requested_day() -> None:
    assert _inclusive_end_timestamp("2026-07-02") == "2026-07-02 23:59:59.999999999"
    assert _inclusive_end_timestamp(None) is None
