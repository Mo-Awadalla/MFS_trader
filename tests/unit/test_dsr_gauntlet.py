"""DSR gauntlet selection-identity regressions."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from validation import gauntlet as gauntlet_module


def test_dsr_rejects_non_integer_selected_trial_index() -> None:
    matrix = np.zeros((4, 2))
    assert gauntlet_module._dsr_input_error(matrix, 2, 1.0, "two daily trials") == (
        "dsr_selected_trial_index must be a non-boolean integer"
    )
    assert gauntlet_module._dsr_input_error(matrix, 2, True, "two daily trials") == (
        "dsr_selected_trial_index must be a non-boolean integer"
    )


def test_dsr_uses_explicit_selected_trial_not_matrix_winner(monkeypatch) -> None:
    """A lower-Sharpe frozen candidate must not be replaced by the matrix winner."""
    rng = np.random.default_rng(42)
    matrix = rng.normal(0.0, 0.01, size=(100, 3))
    matrix[:, 0] += 0.0020
    matrix[:, 1] += 0.0005
    selected_sharpe = float(matrix[:, 1].mean() / matrix[:, 1].std(ddof=1) * np.sqrt(252.0))

    monkeypatch.setattr(
        gauntlet_module,
        "run_wfa",
        lambda *args, **kwargs: SimpleNamespace(
            passed=True, failure_reasons=[], oos_returns=pd.Series(matrix[:, 1]),
            aggregate_metrics={"oos_sharpe": 0.0}, num_folds=1,
            frac_negative_folds=0.0,
        ),
    )
    monkeypatch.setattr(
        gauntlet_module,
        "run_monte_carlo",
        lambda *args, **kwargs: SimpleNamespace(
            prob_loss=0.0, prob_ruin=0.0, pct_5_cagr=0.1,
            pct_5_max_dd=-0.1, mean_sharpe=0.0,
        ),
    )
    monkeypatch.setattr(
        gauntlet_module,
        "analyze_stability",
        lambda *args, **kwargs: SimpleNamespace(
            passed=True, failure_reasons=[], has_isolated_peak=False,
            plateau_within_pct=0.2,
        ),
    )

    result = gauntlet_module.run_gauntlet(
        "identity-regression", pd.DataFrame({"close": np.arange(len(matrix))}),
        lambda *_args, **_kwargs: {}, lambda *_args, **_kwargs: {},
        pd.DataFrame({"sharpe": [2.0, selected_sharpe, 0.0], "parameter": [1, 2, 3]}),
        ["parameter"], best_sharpe=selected_sharpe, returns_matrix=matrix,
        dsr_selected_trial_index=1, dsr_selected_returns=matrix[:, 1],
        dsr_search_scope="three documented daily parameter configurations",
        dsr_sharpe_annualization_factor=252.0,
    )

    assert result.dsr_result is not None
    assert result.dsr_result.available
    assert result.dsr_result.observed_sharpe == pytest.approx(matrix[:, 1].mean() / matrix[:, 1].std(ddof=1))
    assert result.dsr_result.observed_sharpe != pytest.approx(matrix[:, 0].mean() / matrix[:, 0].std(ddof=1))
