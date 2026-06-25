"""Tests for parameter stability analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd

from validation.stability.engine import (
    analyze_stability,
    check_wfa_consistency,
)


def _make_sweep_results(
    n: int = 100, stable: bool = True, seed: int = 42
) -> pd.DataFrame:
    """Generate parameter sweep results.

    If stable=True, creates a smooth plateau.
    If stable=False, creates an isolated peak.
    """
    rng = np.random.default_rng(seed)
    fast = np.repeat(np.arange(5, 15), 10)[:n]
    slow = np.tile(np.arange(50, 60), 10)[:n]

    if stable:
        # Smooth plateau: Sharpe is a smooth function of params
        sharpe = 1.5 - 0.01 * (fast - 10) ** 2 - 0.01 * (slow - 55) ** 2
        sharpe += rng.normal(0, 0.05, n)
    else:
        # Isolated peak: one point is much better than all neighbors
        sharpe = rng.normal(0.5, 0.1, n)
        sharpe[0] = 3.0  # isolated peak

    return pd.DataFrame(
        {
            "fast_window": fast,
            "slow_window": slow,
            "sharpe": sharpe,
        }
    )


class TestAnalyzeStability:
    def test_stable_plateau_passes(self):
        results = _make_sweep_results(100, stable=True)
        result = analyze_stability(results, ["fast_window", "slow_window"])
        assert result.passed
        assert not result.has_isolated_peak
        assert result.plateau_within_pct > 0.7

    def test_isolated_peak_detected(self):
        results = _make_sweep_results(100, stable=False)
        result = analyze_stability(results, ["fast_window", "slow_window"])
        assert result.has_isolated_peak
        assert not result.passed

    def test_best_params_extracted(self):
        results = _make_sweep_results(100, stable=True)
        result = analyze_stability(results, ["fast_window", "slow_window"])
        assert "fast_window" in result.best_params
        assert "slow_window" in result.best_params
        assert result.best_sharpe > 0

    def test_sensitivity_computed(self):
        results = _make_sweep_results(100, stable=True)
        result = analyze_stability(results, ["fast_window", "slow_window"])
        assert "fast_window" in result.param_sensitivity
        assert "slow_window" in result.param_sensitivity

    def test_empty_results_fails(self):
        result = analyze_stability(pd.DataFrame(), ["a", "b"])
        assert not result.passed
        assert "empty_results" in result.failure_reasons

    def test_plateau_with_negative_sharpe_fails(self):
        """If the plateau region straddles positive and negative, it's unstable."""
        # Create results where the top 20% include negative Sharpes
        # by having a large spread near the top
        rng = np.random.default_rng(42)
        n = 100
        fast = np.repeat(np.arange(5, 15), 10)[:n]
        slow = np.tile(np.arange(50, 60), 10)[:n]
        # Bimodal: some positive, some negative, close in rank
        sharpe = rng.normal(0.0, 0.3, n)
        sharpe[:5] = 1.0  # a few good
        sharpe[5:15] = -0.5  # rest of "top" region is negative
        results = pd.DataFrame({"fast_window": fast, "slow_window": slow, "sharpe": sharpe})
        result = analyze_stability(results, ["fast_window", "slow_window"], plateau_pct=0.20)
        # Plateau includes the mix of positive and negative
        assert result.plateau_sharpe_range[0] < 0 or not result.passed


class TestWFAConsistency:
    def test_consistent_folds_pass(self):
        folds = [
            {"fitted_params": {"fast_window": 10, "slow_window": 50}, "sharpe": 1.5},
            {"fitted_params": {"fast_window": 10, "slow_window": 50}, "sharpe": 1.3},
            {"fitted_params": {"fast_window": 10, "slow_window": 50}, "sharpe": 1.4},
        ]
        result = check_wfa_consistency(folds, ["fast_window", "slow_window"])
        assert result["consistent"]

    def test_inconsistent_folds_fail(self):
        folds = [
            {"fitted_params": {"fast_window": 5, "slow_window": 50}, "sharpe": 1.5},
            {"fitted_params": {"fast_window": 40, "slow_window": 100}, "sharpe": 1.3},
            {"fitted_params": {"fast_window": 20, "slow_window": 200}, "sharpe": 1.4},
        ]
        result = check_wfa_consistency(folds, ["fast_window", "slow_window"])
        assert not result["consistent"]

    def test_empty_folds_fail(self):
        result = check_wfa_consistency([], ["fast_window"])
        assert not result["consistent"]
