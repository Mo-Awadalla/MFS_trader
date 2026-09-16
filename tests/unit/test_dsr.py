"""Regression tests for Bailey--López de Prado Eq. (2) DSR."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from validation.dsr.engine import (
    compute_dsr,
    estimate_m_cluster,
    estimate_m_eff_corr,
    expected_max_sharpe,
)


class TestEstimateMEffCorr:
    def test_identical_columns_low_m_eff(self):
        returns = np.random.default_rng(1).standard_normal((100, 1))
        assert estimate_m_eff_corr(np.repeat(returns, 5, axis=1)) < 2.0

    def test_independent_columns_high_m_eff(self):
        assert estimate_m_eff_corr(np.random.default_rng(42).standard_normal((200, 10))) > 5.0

    def test_dataframe_input(self):
        assert estimate_m_eff_corr(pd.DataFrame(np.random.default_rng(42).standard_normal((100, 5)))) > 1.0


class TestEstimateMCluster:
    def test_clusters_parameter_space(self):
        rng = np.random.default_rng(42)
        results = pd.DataFrame({"fast": rng.integers(5, 50, 50), "slow": rng.integers(50, 200, 50), "sharpe": rng.normal(size=50)})
        assert estimate_m_cluster(results, ["fast", "slow"]) >= 1


class TestBaileyLopezDePradoEquationTwo:
    def test_paper_worked_example(self):
        result = compute_dsr(
            observed_sharpe=2.5 / math.sqrt(250.0), trial_sharpe_variance=0.5 / 250.0,
            num_trials_raw=100, track_record_length=1250, selected_return_skewness=-3.0,
            selected_return_kurtosis=10.0,
            search_scope="Paper numerical example: 100 independent treasury-seasonality trials",
            method="M_raw",
        )
        assert result.available
        assert result.expected_max_sharpe == pytest.approx(0.1132, abs=5e-5)
        assert result.dsr_confidence == pytest.approx(0.9004, abs=5e-5)
        assert result.dsr_pvalue == pytest.approx(1.0 - 0.9004, abs=5e-5)
        assert not result.passed
        assert "<= 0.9500" in result.failure_reasons[0]

    def test_more_trials_reduce_confidence(self):
        shared = {"observed_sharpe": 2.5 / math.sqrt(250.0), "trial_sharpe_variance": 0.5 / 250.0, "track_record_length": 1250, "selected_return_skewness": -3.0, "selected_return_kurtosis": 10.0, "search_scope": "Same documented daily trial family", "method": "M_raw"}
        fewer = compute_dsr(num_trials_raw=46, **shared)
        more = compute_dsr(num_trials_raw=100, **shared)
        assert fewer.dsr_confidence == pytest.approx(0.9505, abs=5e-5)
        assert more.dsr_confidence < fewer.dsr_confidence
        assert more.expected_max_sharpe > fewer.expected_max_sharpe

    def test_selected_returns_calculate_moments_in_per_observation_units(self):
        rng = np.random.default_rng(7)
        selected = rng.standard_t(df=7, size=250) * 0.01 + 0.0008
        trials = rng.standard_normal((250, 4)) * 0.01
        trial_sharpes = trials.mean(axis=0) / trials.std(axis=0, ddof=1)
        result = compute_dsr(selected_returns=selected, trial_sharpe_variance=float(np.var(trial_sharpes, ddof=1)), returns_matrix=trials, num_trials_raw=4, search_scope="Four daily parameter configurations evaluated over the same 250 bars")
        assert result.available
        assert result.track_record_length == len(selected)
        assert result.observed_sharpe == pytest.approx(selected.mean() / selected.std(ddof=1))
        assert result.selected_return_kurtosis == pytest.approx(stats.kurtosis(selected, fisher=False, bias=False))

    @pytest.mark.parametrize(("kwargs", "scope", "reason"), [
        ({"num_trials_raw": 1, "trial_sharpe_variance": 0.0}, "one trial", "at least two"),
        ({"num_trials_raw": 2}, "two trials", "trial_sharpe_variance"),
        ({"num_trials_raw": 2, "trial_sharpe_variance": 0.01}, None, "search_scope"),
    ])
    def test_missing_trial_evidence_is_unavailable(self, kwargs, scope, reason):
        result = compute_dsr(selected_returns=np.array([0.01, -0.02, 0.03, 0.01, 0.02]), search_scope=scope, **kwargs)
        assert not result.available
        assert not result.passed
        assert reason in result.unavailable_reason

    def test_matrix_must_cover_the_declared_search_scope(self):
        result = compute_dsr(selected_returns=np.array([0.01, -0.02, 0.03, 0.01, 0.02]), trial_sharpe_variance=0.01, returns_matrix=np.ones((5, 2)) * 0.01, num_trials_raw=3, search_scope="Three daily parameter configurations")
        assert not result.available
        assert "cover exactly" in result.unavailable_reason

    def test_raw_method_remains_available_when_effective_trials_are_near_one(self):
        selected = np.array([0.01, -0.02, 0.03, 0.01, 0.02])
        matrix = np.repeat(selected[:, None], 3, axis=1)
        result = compute_dsr(selected_returns=selected, trial_sharpe_variance=0.01, returns_matrix=matrix, num_trials_raw=3, search_scope="Three fully correlated daily parameter configurations", method="M_raw")
        assert result.available
        assert result.num_trials_eff < 2.0
        assert result.pvalue_m_eff is None

    def test_effective_method_with_no_selection_benchmark_is_unavailable(self):
        selected = np.array([0.01, -0.02, 0.03, 0.01, 0.02])
        result = compute_dsr(selected_returns=selected, trial_sharpe_variance=0.01, returns_matrix=np.repeat(selected[:, None], 3, axis=1), num_trials_raw=3, search_scope="Three fully correlated daily parameter configurations")
        assert not result.available
        assert "below two" in result.unavailable_reason

    def test_mismatched_observed_sharpe_cannot_be_mixed_with_selected_returns(self):
        result = compute_dsr(observed_sharpe=2.5, selected_returns=np.array([0.01, -0.02, 0.03, 0.01, 0.02]), trial_sharpe_variance=0.01, num_trials_raw=2, search_scope="Two daily parameter configurations", method="M_raw")
        assert not result.available
        assert "must match" in result.unavailable_reason

    def test_expected_max_rejects_invalid_trial_counts(self):
        with pytest.raises(ValueError, match="at least 2"):
            expected_max_sharpe(0.01, 1)

    def test_extreme_tail_uses_survival_function(self):
        result = compute_dsr(observed_sharpe=0.12, trial_sharpe_variance=0.001, num_trials_raw=2, track_record_length=10_000, selected_return_skewness=0.0, selected_return_kurtosis=3.0, search_scope="two documented daily trial configurations", method="M_raw")
        assert 0.0 < result.dsr_pvalue < 1e-16

    @pytest.mark.parametrize(("variance", "skewness", "kurtosis", "reason"), [
        (-0.01, 0.0, 3.0, "variance"), (float("nan"), 0.0, 3.0, "variance"),
        (0.01, 100.0, 1.0, "denominator"), (0.01, 0.0, 0.0, "ordinary"),
    ])
    def test_invalid_eq2_inputs_are_unavailable(self, variance, skewness, kurtosis, reason):
        result = compute_dsr(observed_sharpe=0.5, trial_sharpe_variance=variance, num_trials_raw=2, track_record_length=100, selected_return_skewness=skewness, selected_return_kurtosis=kurtosis, search_scope="two documented daily trial configurations", method="M_raw")
        assert not result.available
        assert reason in result.unavailable_reason
