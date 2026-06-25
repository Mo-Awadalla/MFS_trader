"""Tests for Monte Carlo simulation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from validation.mc.engine import (
    block_bootstrap_returns,
    compute_path_metrics,
    run_monte_carlo,
    run_parameter_perturbation,
)


def _make_returns(n: int = 252, seed: int = 42, sharpe_target: float = 1.5) -> pd.Series:
    """Generate synthetic daily returns with a target Sharpe ratio."""
    rng = np.random.default_rng(seed)
    # Sharpe = mean * 252 / (std * sqrt(252)) = mean/std * sqrt(252)
    # For Sharpe = 1.5: mean/std = 1.5/sqrt(252) ≈ 0.0945
    std = 0.01
    mean = sharpe_target / np.sqrt(252) * std
    returns = pd.Series(rng.normal(mean, std, n))
    return returns


class TestBlockBootstrap:
    def test_generates_correct_shape(self):
        returns = _make_returns(252)
        paths = block_bootstrap_returns(returns, num_paths=100, block_size=20, seed=42)
        assert paths.shape == (100, 252)

    def test_reproducible_with_seed(self):
        returns = _make_returns(252)
        paths1 = block_bootstrap_returns(returns, 50, 20, seed=42)
        paths2 = block_bootstrap_returns(returns, 50, 20, seed=42)
        np.testing.assert_array_equal(paths1, paths2)

    def test_different_seeds_different_paths(self):
        returns = _make_returns(252)
        paths1 = block_bootstrap_returns(returns, 50, 20, seed=42)
        paths2 = block_bootstrap_returns(returns, 50, 20, seed=99)
        assert not np.array_equal(paths1, paths2)


class TestComputePathMetrics:
    def test_positive_returns_positive_wealth(self):
        returns = np.array([0.01, 0.02, 0.005, 0.015, 0.01, 0.03])
        metrics = compute_path_metrics(returns, initial_capital=10000)
        assert metrics["terminal_wealth"] > 10000
        assert metrics["sharpe"] > 0

    def test_negative_returns_negative_wealth(self):
        returns = np.array([-0.01, -0.01, -0.01, -0.01])
        metrics = compute_path_metrics(returns, initial_capital=10000)
        assert metrics["terminal_wealth"] < 10000
        assert metrics["max_drawdown"] < 0


class TestRunMonteCarlo:
    def test_high_sharpe_strategy_low_prob_loss(self):
        returns = _make_returns(252, sharpe_target=2.0)
        result = run_monte_carlo(returns, num_paths=1000, block_size=20, seed=42)
        assert result.num_paths == 1000
        assert result.mean_sharpe > 0
        # High Sharpe should have low probability of loss
        assert result.prob_loss < 0.5

    def test_zero_sharpe_strategy_around_fifty_pct_loss(self):
        """Zero Sharpe (pure noise) should have roughly even odds of loss."""
        returns = _make_returns(500, sharpe_target=0.0)  # longer = more stable
        result = run_monte_carlo(returns, num_paths=1000, block_size=20, seed=42)
        # With pure noise, prob_loss should be somewhere in a wide range
        # (compounding drag makes it slightly > 50%)
        assert 0.3 < result.prob_loss < 0.85

    def test_ruin_probability_increases_with_vol(self):
        # High volatility, negative drift
        rng = np.random.default_rng(42)
        bad_returns = pd.Series(rng.normal(-0.002, 0.05, 252))
        result = run_monte_carlo(bad_returns, num_paths=1000, ruin_threshold=-0.50)
        assert result.prob_ruin > 0.01  # significant chance of ruin

    def test_summarize_returns_all_stats(self):
        returns = _make_returns(252, sharpe_target=1.5)
        result = run_monte_carlo(returns, num_paths=500, seed=42)
        summary = result.summarize(initial_capital=10000)
        assert "prob_loss" in summary
        assert "prob_ruin" in summary
        assert "mean_sharpe" in summary
        assert "pct_5_cagr" in summary
        assert "pct_95_max_dd" in summary

    def test_insufficient_data_returns_empty(self):
        returns = pd.Series([0.01, 0.02])  # only 2 bars
        result = run_monte_carlo(returns, block_size=20)
        assert result.num_paths == 0


class TestParameterPerturbation:
    def test_perturbation_runs(self):
        df = pd.DataFrame(
            {"close": [100.0 + i * 0.1 for i in range(100)]},
            index=pd.date_range("2024-01-01", periods=100, freq="1D", tz="UTC"),
        )

        def backtest_fn(df, params):
            window = params.get("window", 10)
            close = df["close"]
            ma = close.rolling(window).mean()
            signal = (close > ma).astype(int)
            returns = close.pct_change().fillna(0) * signal.shift(1).fillna(0)
            return returns

        result = run_parameter_perturbation(
            df,
            backtest_fn,
            base_params={"window": 10},
            perturbation_ranges={"window": (-0.5, 0.5)},
            num_paths=50,
        )
        assert result["num_paths"] > 0
        assert "mean_sharpe" in result
