"""Tests for Deflated Sharpe Ratio."""

from __future__ import annotations

import numpy as np
import pandas as pd

from validation.dsr.engine import (
    compute_dsr,
    estimate_m_cluster,
    estimate_m_eff_corr,
)


class TestEstimateMEffCorr:
    def test_identical_columns_low_m_eff(self):
        """If all strategies return identical results, M_eff should be ~1."""
        returns = np.random.randn(100, 5)
        returns = np.repeat(returns[:, :1], 5, axis=1)  # all identical
        m_eff = estimate_m_eff_corr(returns)
        assert m_eff < 2.0  # effectively 1 independent trial

    def test_independent_columns_high_m_eff(self):
        """If all strategies are independent, M_eff should be ~n_trials."""
        rng = np.random.default_rng(42)
        returns = rng.standard_normal((200, 10))  # 10 independent strategies
        m_eff = estimate_m_eff_corr(returns)
        assert m_eff > 5.0  # close to 10

    def test_single_column(self):
        returns = np.random.randn(100, 1)
        m_eff = estimate_m_eff_corr(returns)
        assert m_eff == 1.0

    def test_dataframe_input(self):
        rng = np.random.default_rng(42)
        df = pd.DataFrame(rng.standard_normal((100, 5)))
        m_eff = estimate_m_eff_corr(df)
        assert m_eff > 1.0


class TestEstimateMCluster:
    def test_clusters_parameter_space(self):
        rng = np.random.default_rng(42)
        param_results = pd.DataFrame(
            {
                "fast_window": rng.integers(5, 50, 50),
                "slow_window": rng.integers(50, 200, 50),
                "sharpe": rng.standard_normal(50),
            }
        )
        m_cluster = estimate_m_cluster(param_results, ["fast_window", "slow_window"])
        assert m_cluster >= 1

    def test_empty_returns_one(self):
        m_cluster = estimate_m_cluster(pd.DataFrame(), ["a"])
        assert m_cluster == 1


class TestComputeDSR:
    def test_high_sharpe_long_track_passes(self):
        """A high Sharpe with long track record and few trials should pass."""
        rng = np.random.default_rng(42)
        # 5 strategies, 500 bars, best Sharpe = 3.0
        returns_matrix = rng.standard_normal((500, 5))
        result = compute_dsr(
            observed_sharpe=3.0,
            returns_matrix=returns_matrix,
            num_trials_raw=5,
            track_record_length=500,
        )
        assert result.dsr_pvalue < 0.10
        assert result.num_trials_eff > 0

    def test_low_sharpe_fails(self):
        """A low Sharpe should fail DSR."""
        rng = np.random.default_rng(42)
        returns_matrix = rng.standard_normal((100, 20))
        result = compute_dsr(
            observed_sharpe=0.1,
            returns_matrix=returns_matrix,
            num_trials_raw=20,
            track_record_length=100,
        )
        assert result.dsr_pvalue > 0.10
        assert not result.passed

    def test_many_trials_inflates_threshold(self):
        """With many trials, even a decent Sharpe should be deflated."""
        rng = np.random.default_rng(42)
        # 500 strategies, mostly noise
        returns_matrix = rng.standard_normal((100, 500))
        result = compute_dsr(
            observed_sharpe=1.5,
            returns_matrix=returns_matrix,
            num_trials_raw=500,
            track_record_length=100,
        )
        # With 500 trials, a Sharpe of 1.5 on 100 bars may not survive
        # M_raw p-value should be more conservative
        assert result.pvalue_m_raw >= result.pvalue_m_eff or result.pvalue_m_raw > 0.05

    def test_pvalue_methods_different(self):
        """All three p-value methods should be computed."""
        rng = np.random.default_rng(42)
        returns_matrix = rng.standard_normal((200, 50))
        result = compute_dsr(
            observed_sharpe=2.0,
            returns_matrix=returns_matrix,
            num_trials_raw=50,
            track_record_length=200,
            num_trials_cluster=30,
        )
        assert result.pvalue_m_raw > 0
        assert result.pvalue_m_eff > 0
        assert result.pvalue_m_cluster > 0

    def test_collapse_under_m_raw_fails(self):
        """If DSR passes with M_eff but fails with M_raw, it should not pass."""
        rng = np.random.default_rng(42)
        # High correlation between strategies (low M_eff) but many raw trials
        base = rng.standard_normal((200, 1))
        returns_matrix = np.repeat(base, 100, axis=1) + rng.standard_normal((200, 100)) * 0.01
        result = compute_dsr(
            observed_sharpe=1.0,
            returns_matrix=returns_matrix,
            num_trials_raw=100,
            track_record_length=200,
        )
        # M_eff is low (correlated), M_raw is high
        # If pval_raw is bad, should fail even if pval_eff is OK
        if result.pvalue_m_raw > 0.10:
            assert not result.passed
