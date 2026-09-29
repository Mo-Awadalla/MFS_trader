"""Synthetic numerical evidence for temporary lifecycle/operational test registries.

These prescribed net-return streams are test fixtures, not backtests of the named
production strategy and never evidence for a real Experiment.
"""
from __future__ import annotations

from numbers import Real

import numpy as np
import pandas as pd

from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.corrected_evaluations import EvaluationInputs, run_current_evaluation
from experiments.models import Experiment, PromotionStatus
from experiments.registry import ExperimentRegistry
from validation.search import declared_search
from validation.wfa.engine import WFAConfig, WFATier


def _train(data: pd.DataFrame) -> dict:
    return {}


def _evaluate(data: pd.DataFrame, parameters: dict) -> dict:
    returns = data["returns"]
    downside = np.minimum(returns, 0.0)
    equity = (1.0 + returns).cumprod()
    peaks = equity.cummax().clip(lower=1.0)
    return {
        "returns": returns,
        "sharpe": float(returns.mean() / returns.std() * np.sqrt(252)),
        "sortino": float(returns.mean() / downside.std() * np.sqrt(252)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "max_drawdown": float((equity / peaks - 1.0).min()),
    }


def publish_synthetic_qualification(registry: ExperimentRegistry, experiment: Experiment) -> None:
    """Compute and publish current evidence in a temporary test registry only."""
    params = experiment.snapshot.parameters
    key = next(k for k, v in params.items() if isinstance(v, Real) and not isinstance(v, bool))
    trials = [{**params, key: params[key] + offset} for offset in range(10)]
    index = pd.date_range("2020-01-01", periods=1000, freq="D")
    matrix = np.random.default_rng(1729).normal(0.002, 0.005, (1000, 10))
    returns = [pd.Series(matrix[:, i], index=index) for i in range(10)]
    data = pd.DataFrame(matrix, index=index, columns=["returns", *[f"trial_{i}" for i in range(1, 10)]])
    path = registry.root / f"synthetic-input-{experiment.uuid}.csv"
    data.to_csv(path)
    sweep = pd.DataFrame([
        {**trial, "sharpe": float(series.mean() / series.std() * np.sqrt(252))}
        for trial, series in zip(trials, returns, strict=True)
    ])
    inputs = EvaluationInputs(
        data=data, train_fn=_train, test_fn=_evaluate, sweep_results=sweep,
        param_columns=[key], search=declared_search(
            trials, returns, params,
            search_scope="All ten prescribed synthetic net-return fixture trials; no production strategy claim",
        ), input_files={"synthetic full return matrix, seed 1729": path},
        caller_config={
            "cost_model": experiment.snapshot.cost_model,
            "slippage_model": experiment.snapshot.slippage_model,
            "synthetic_prescribed_net_returns": True,
            "generator_seed": 1729,
        },
        wfa_config=WFAConfig(WFATier.PRIMARY, "3m", "2m", "2m"),
        periods_per_year=252, mc_num_paths=100, mc_block_size=20,
    )
    payload = run_current_evaluation(experiment, inputs)
    assert payload["gauntlet"]["passed"], payload["gauntlet"]["failure_reasons"]
    ArtifactManager(registry.root).write_json(
        experiment.uuid, ArtifactKind.VALIDATION_REPORT_JSON, payload,
    )


def enter_paper_ops(registry: ExperimentRegistry, uuid: str) -> Experiment:
    """Prepare actual current numerical evidence before a test's paper admission."""
    publish_synthetic_qualification(registry, registry.get(uuid))
    return registry.transition_promotion_status(uuid, PromotionStatus.PAPER_OPS)
