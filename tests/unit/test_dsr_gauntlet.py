"""DSR gauntlet selection-identity and declared-search regressions."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from validation import gauntlet as gauntlet_module
from validation.search import DeclaredSearch, declared_search


def _stub_other_checks(monkeypatch, oos: pd.Series) -> None:
    monkeypatch.setattr(
        gauntlet_module,
        "run_wfa",
        lambda *args, **kwargs: SimpleNamespace(
            passed=True, failure_reasons=[], oos_returns=oos,
            aggregate_metrics={"oos_sharpe": 0.0}, num_folds=1,
            frac_negative_folds=0.0,
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


def _run(matrix: np.ndarray, search: DeclaredSearch | None, monkeypatch):
    _stub_other_checks(monkeypatch, pd.Series(np.full(60, 0.001) + np.tile([0.0005, -0.0005], 30)))
    return gauntlet_module.run_gauntlet(
        "identity-regression",
        pd.DataFrame({"close": np.arange(len(matrix))}),
        lambda *_a, **_k: {},
        lambda *_a, **_k: {},
        pd.DataFrame({"sharpe": np.zeros(matrix.shape[1]), "parameter": range(matrix.shape[1])}),
        ["parameter"],
        dsr_search=search,
        mc_num_paths=50,
    )


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
    index = pd.RangeIndex(100)
    search = declared_search(
        [{"p": 1}, {"p": 2}, {"p": 3}],
        [pd.Series(matrix[:, i], index=index) for i in range(3)],
        {"p": 2},
        search_scope="three documented daily parameter configurations",
    )

    result = _run(matrix, search, monkeypatch)

    assert result.dsr_result is not None
    assert result.dsr_result.available
    assert result.dsr_result.observed_sharpe == pytest.approx(matrix[:, 1].mean() / matrix[:, 1].std(ddof=1))
    assert result.dsr_result.observed_sharpe != pytest.approx(matrix[:, 0].mean() / matrix[:, 0].std(ddof=1))
    assert result.dsr_result.track_record_length == 100


def test_missing_search_evidence_is_unavailable_and_blocks_pass(monkeypatch) -> None:
    result = _run(np.zeros((10, 2)), None, monkeypatch)

    assert result.dsr_result is not None and result.dsr_result.available is False
    assert result.passed is False
    assert "DSR: DSR unavailable: no declared trial-search evidence was supplied" in result.failure_reasons


def test_zero_volatility_trial_cannot_be_dropped_from_the_search(monkeypatch) -> None:
    rng = np.random.default_rng(3)
    matrix = rng.normal(0.001, 0.01, size=(50, 3))
    matrix[:, 2] = 0.0
    index = pd.RangeIndex(50)
    search = declared_search(
        [{"p": i} for i in range(3)],
        [pd.Series(matrix[:, i], index=index) for i in range(3)],
        {"p": 0},
        search_scope="three trials, one never trades",
    )

    result = _run(matrix, search, monkeypatch)

    assert result.dsr_result.available is False
    assert "[2] have zero return volatility" in (result.dsr_result.unavailable_reason or "")
    assert result.passed is False


def test_declared_search_rejects_ambiguous_or_misaligned_trials() -> None:
    a = pd.Series([0.01, -0.01, 0.02, 0.0], index=pd.RangeIndex(4))
    b = pd.Series([0.01, -0.01, 0.02, 0.0], index=pd.RangeIndex(1, 5))

    duplicate = declared_search([{"p": 1}, {"p": 1}], [a, a], {"p": 1}, search_scope="dup")
    misaligned = declared_search([{"p": 1}, {"p": 2}], [a, b], {"p": 1}, search_scope="shifted")
    missing = declared_search([{"p": 1}, {"p": 2}], [a, a], {"p": 3}, search_scope="absent")

    assert duplicate.selection_error == (
        "the frozen selected parameters match 2 declared trials; expected exactly one"
    )
    assert misaligned.selection_error == "declared trials do not share one observation window"
    assert missing.selected_trial_index is None and "match 0" in (missing.selection_error or "")
