"""Regression coverage for the Monte Carlo drawdown gate."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import validation.gauntlet as gauntlet
from validation.mc.engine import MCResult


def test_gauntlet_rejects_adverse_signed_drawdown_tail(monkeypatch) -> None:
    oos_returns = pd.Series([0.01] * 20)
    wfa_result = SimpleNamespace(
        passed=True, failure_reasons=[], oos_returns=oos_returns, folds=[],
        aggregate_metrics={}, num_folds=1, frac_negative_folds=0.0,
    )
    mc_result = MCResult(num_paths=100, block_size=20, seed=42)
    mc_result.terminal_wealth = np.full(100, 11_000.0)
    mc_result.sharpes = np.full(100, 1.0)
    mc_result.sortinos = np.full(100, 1.0)
    mc_result.max_drawdowns = np.array([-0.40] * 10 + [-0.10] * 90)
    mc_result.cagrs = np.full(100, 0.10)
    mc_result.summarize(initial_capital=10_000.0)
    monkeypatch.setattr(gauntlet, "run_wfa", lambda *_args, **_kwargs: wfa_result)
    monkeypatch.setattr(gauntlet, "run_monte_carlo", lambda *_args, **_kwargs: mc_result)

    result = gauntlet.run_gauntlet(
        strategy_name="test", df=pd.DataFrame(), train_fn=lambda **_: {},
        test_fn=lambda **_: {}, sweep_results=pd.DataFrame(), param_columns=[],
    )

    assert "MC: adverse 5th pct max DD = -0.400 < -0.3" in result.failure_reasons
    assert "pct_95_max_dd" not in result.to_dict()["monte_carlo"]
    assert result.to_dict()["monte_carlo"]["pct_5_max_dd"] == -0.40


def test_gauntlet_fails_closed_when_oos_returns_are_non_finite(monkeypatch) -> None:
    oos_returns = pd.Series([0.01] * 19 + [np.nan])
    wfa_result = SimpleNamespace(
        passed=True, failure_reasons=[], oos_returns=oos_returns, folds=[],
        aggregate_metrics={}, num_folds=1, frac_negative_folds=0.0,
    )
    monkeypatch.setattr(gauntlet, "run_wfa", lambda *_args, **_kwargs: wfa_result)

    result = gauntlet.run_gauntlet(
        strategy_name="test", df=pd.DataFrame(), train_fn=lambda **_: {},
        test_fn=lambda **_: {}, sweep_results=pd.DataFrame(), param_columns=[],
        mc_num_paths=50,
    )
    mc = result.to_dict()["monte_carlo"]

    assert result.passed is False
    assert "MC unavailable: Monte Carlo returns must all be finite (NaN/inf present)" in result.failure_reasons
    assert mc["available"] is False
    assert "prob_ruin" not in mc and "pct_5_max_dd" not in mc


@pytest.mark.parametrize("limit", [np.nan, np.inf, -np.inf, 0.1, -1.1])
def test_invalid_drawdown_gate_cannot_disable_comparison(monkeypatch, limit):
    def unexpected_wfa(*args, **kwargs):
        raise AssertionError("invalid gate configuration reached evaluation")

    monkeypatch.setattr(gauntlet, "run_wfa", unexpected_wfa)
    with pytest.raises(ValueError):
        gauntlet.run_gauntlet(
            strategy_name="test", df=pd.DataFrame(), train_fn=lambda **_: {},
            test_fn=lambda **_: {}, sweep_results=pd.DataFrame(), param_columns=[],
            max_dd_limit=limit,
        )
