"""Tests for walk-forward analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from validation.wfa.engine import (
    PRESETS,
    WFATier,
    generate_expanding_folds,
    generate_folds,
    parse_window,
    run_wfa,
)


def _make_ohlcv(n_days: int = 800, start: str = "2022-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n_days, freq="1D", tz="UTC")
    np.random.seed(42)
    close = 100.0 * np.cumprod(1 + np.random.randn(n_days) * 0.01)
    return pd.DataFrame(
        {
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": [10000.0] * n_days,
        },
        index=idx,
    )


class TestParseWindow:
    def test_months(self):
        delta = parse_window("18m", pd.Timestamp("2022-01-01", tz="UTC"))
        assert delta is not None
        assert delta.days > 500  # ~18 months

    def test_days(self):
        delta = parse_window("30d", pd.Timestamp("2022-01-01", tz="UTC"))
        assert delta is not None
        assert delta.days == 30

    def test_expanding_returns_none(self):
        delta = parse_window("expanding", pd.Timestamp("2022-01-01", tz="UTC"))
        assert delta is None

    def test_invalid_unit(self):
        with pytest.raises(ValueError):
            parse_window("5x", pd.Timestamp("2022-01-01", tz="UTC"))


class TestGenerateFolds:
    def test_primary_folds(self):
        df = _make_ohlcv(800)
        config = PRESETS[WFATier.PRIMARY]
        folds = generate_folds(df, config)
        assert len(folds) > 0
        # Each fold: (train_start, train_end, test_start, test_end)
        # train_end == test_start (train ends where test begins)
        for ts, te, vs, ve in folds:
            assert ts <= te <= vs < ve

    def test_robustness_folds_more_numerous(self):
        df = _make_ohlcv(800)
        primary = generate_folds(df, PRESETS[WFATier.PRIMARY])
        robustness = generate_folds(df, PRESETS[WFATier.ROBUSTNESS])
        # Robustness should have more folds (smaller step)
        assert len(robustness) >= len(primary)

    def test_expanding_folds(self):
        df = _make_ohlcv(800)
        folds = generate_expanding_folds(df, test_window="6m", step="3m")
        assert len(folds) > 0
        # Expanding: train_start is always data start
        data_start = df.index[0]
        for ts, _te, _vs, _ve in folds:
            assert ts == data_start  # expanding always starts at inception

    def test_short_data_no_folds(self):
        df = _make_ohlcv(10)
        config = PRESETS[WFATier.PRIMARY]
        folds = generate_folds(df, config)
        assert len(folds) == 0  # not enough data for 18m train


class TestRunWFA:
    def test_wfa_runs_with_simple_strategy(self):
        df = _make_ohlcv(800)

        # Simple strategy: buy and hold (always return +1 position)
        def train_fn(train_df, **kwargs):
            return {"position": 1}

        def test_fn(test_df, params):
            close = test_df["close"]
            returns = close.pct_change().fillna(0)
            sharpe = float(returns.mean() * 252 / (returns.std() * np.sqrt(252))) if returns.std() > 0 else 0
            return {
                "sharpe": sharpe,
                "sortino": sharpe,
                "total_return": float((close.iloc[-1] / close.iloc[0]) - 1),
                "max_drawdown": float(((close / close.cummax()) - 1).min()),
                "returns": returns,
            }

        result = run_wfa(df, train_fn, test_fn, PRESETS[WFATier.PRIMARY])
        assert result.num_folds > 0
        assert "oos_sharpe" in result.aggregate_metrics
        assert "num_folds" in result.aggregate_metrics

    def test_wfa_handles_fold_errors(self):
        df = _make_ohlcv(800)

        def train_fn(train_df, **kwargs):
            return {}

        def test_fn(test_df, params):
            raise ValueError("intentional error")

        result = run_wfa(df, train_fn, test_fn)
        assert len(result.failure_reasons) > 0
        assert any("error" in r for r in result.failure_reasons)

    def test_wfa_pass_criteria(self):
        """A strategy with consistently positive returns should pass WFA."""
        df = _make_ohlcv(1200)  # enough for multiple folds

        def train_fn(train_df, **kwargs):
            return {}

        def test_fn(test_df, params):
            close = test_df["close"]
            returns = close.pct_change().fillna(0)
            # Artificially boost Sharpe to pass criteria
            returns = returns + 0.001
            sharpe = float(returns.mean() * 252 / (returns.std() * np.sqrt(252)))
            sortino = sharpe * 1.2
            return {
                "sharpe": max(sharpe, 1.5),
                "sortino": max(sortino, 1.5),
                "total_return": 0.05,
                "max_drawdown": -0.05,
                "returns": returns,
            }

        result = run_wfa(df, train_fn, test_fn)
        assert result.num_folds > 1  # multiple folds needed for profit-share check
        assert result.passed
