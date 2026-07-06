"""Tests for intraday / swing-trading validation helpers."""

from __future__ import annotations

import pandas as pd

from validation.intraday import (
    IntradayValidationConfig,
    annualization_factor,
    estimate_bars_per_session,
    evaluate_intraday_constraints,
    intraday_performance_metrics,
)


def _intraday_index(days: int = 80, bars_per_day: int = 13) -> pd.DatetimeIndex:
    sessions = pd.bdate_range("2024-01-02", periods=days, tz="UTC")
    stamps = []
    for session in sessions:
        start = session + pd.Timedelta(hours=14, minutes=30)
        stamps.extend(start + pd.Timedelta(minutes=30 * i) for i in range(bars_per_day))
    return pd.DatetimeIndex(stamps)


def test_estimates_bars_per_session_and_annualization():
    idx = _intraday_index(days=10, bars_per_day=13)

    assert estimate_bars_per_session(idx) == 13
    assert annualization_factor(idx) == 252 * 13


def test_intraday_performance_metrics_uses_bar_annualization():
    idx = _intraday_index(days=80, bars_per_day=13)
    returns = pd.Series(0.0001, index=idx)
    equity = (1.0 + returns).cumprod() * 10000.0

    metrics = intraday_performance_metrics(
        returns,
        equity,
        initial_capital=10000.0,
        bars_per_session=13,
    )

    assert metrics["annualization_factor"] == 252 * 13
    assert metrics["final_equity"] > 10000.0
    assert metrics["total_bars"] == len(idx)


def test_intraday_constraints_pass_for_flat_by_close_active_strategy():
    idx = _intraday_index(days=80, bars_per_day=13)
    returns = pd.Series(0.0, index=idx)
    positions = pd.Series(0.0, index=idx)
    rows = []
    for session in pd.Index(idx.normalize()).unique():
        day_idx = idx[idx.normalize() == session]
        entry = day_idx[1]
        exit_ = day_idx[4]
        positions.loc[entry:exit_] = 1.0
        positions.loc[exit_] = 0.0
        returns.loc[day_idx[2:4]] = 0.001
        rows.append({"timestamp": entry, "weight_delta": 1.0, "pnl": 5.0})
        rows.append({"timestamp": exit_, "weight_delta": -1.0, "pnl": 2.0})
    trades = pd.DataFrame(rows)

    result = evaluate_intraday_constraints(
        returns=returns,
        trades=trades,
        positions=positions,
        config=IntradayValidationConfig(
            bars_per_session=13,
            min_trades=100,
            min_trading_sessions=60,
            max_holding_period_bars=4,
            require_flat_by_session_close=True,
            max_single_session_profit_share=0.05,
            max_exposure_fraction=0.40,
        ),
    )

    assert result.passed
    assert result.metrics["flat_by_session_close"] is True
    assert result.metrics["trade_count"] == 160


def test_intraday_constraints_fail_for_hidden_overnight_and_concentration():
    idx = _intraday_index(days=80, bars_per_day=13)
    returns = pd.Series(0.0, index=idx)
    first_day = idx.normalize()[0]
    returns.loc[idx.normalize() == first_day] = 0.01
    positions = pd.Series(1.0, index=idx)
    trades = pd.DataFrame(
        [{"timestamp": idx[0], "weight_delta": 1.0, "pnl": -1.0} for _ in range(5)]
    )

    result = evaluate_intraday_constraints(
        returns=returns,
        trades=trades,
        positions=positions,
        config=IntradayValidationConfig(
            bars_per_session=13,
            min_trades=100,
            min_trading_sessions=60,
            max_holding_period_bars=6,
            require_flat_by_session_close=True,
            max_single_session_profit_share=0.20,
            max_exposure_fraction=0.80,
        ),
    )

    assert not result.passed
    assert "trade_count 5 < 100" in result.failures
    assert "not_flat_by_session_close" in result.failures
    assert any("single session contributes" in failure for failure in result.failures)
    assert any("max_holding_period_bars" in failure for failure in result.failures)
