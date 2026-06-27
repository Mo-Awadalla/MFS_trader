"""Tests for portfolio-level research over Experiment outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.models import PromotionStatus
from experiments.registry import ExperimentRegistry
from research.csmr_experiment import build_csmr_experiment_draft
from research.portfolio_research import (
    ExperimentOutput,
    combine_experiment_returns,
    equal_weight_allocation,
    exposure_report,
    performance_attribution,
    run_portfolio_research,
    strategy_correlation,
    write_portfolio_artifact,
)
from strategies.csmr.signal import CSMRParams


def _output(uuid: str, returns: list[float]) -> ExperimentOutput:
    idx = pd.bdate_range("2024-01-02", periods=len(returns), tz="UTC")
    return ExperimentOutput(
        experiment_uuid=uuid,
        label=uuid,
        strategy="test_strategy",
        promotion_status="validation_passed",
        metrics={"sharpe": 1.0},
        returns=pd.Series(returns, index=idx),
        max_gross_exposure_pct=2.0,
        max_net_exposure_pct=0.1,
    )


def test_combines_experiment_returns_with_equal_allocation() -> None:
    outputs = [_output("a", [0.01, 0.02]), _output("b", [0.03, -0.01])]
    allocation = equal_weight_allocation(outputs)

    combined = combine_experiment_returns(outputs, allocation)

    assert allocation == {"a": 0.5, "b": 0.5}
    assert combined.iloc[0] == 0.02
    assert combined.iloc[1] == 0.005


def test_correlation_exposure_and_attribution() -> None:
    outputs = [_output("a", [0.01, 0.02, 0.03]), _output("b", [0.03, 0.02, 0.01])]
    allocation = {"a": 0.25, "b": 0.75}

    corr = strategy_correlation(outputs)
    exposure = exposure_report(outputs, allocation)
    attribution = performance_attribution(outputs, allocation)

    assert corr["status"] == "ok"
    assert corr["max_abs_correlation"] == pytest.approx(1.0)
    assert exposure["weighted_max_gross_exposure_pct"] == 2.0
    assert attribution["by_experiment"]["a"]["total_return_contribution"] == 0.015


def test_portfolio_research_loads_validated_experiment_outputs(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "experiments")
    artifacts = ArtifactManager(registry.root)
    try:
        df = _panel()
        experiment = registry.create(
            build_csmr_experiment_draft(
                df,
                label="validated-csmr",
                params=CSMRParams(min_eligible_symbols=2),
                data_source="synthetic",
            )
        )
        registry.transition_promotion_status(experiment.uuid, PromotionStatus.VALIDATION_RUNNING)
        registry.transition_promotion_status(experiment.uuid, PromotionStatus.VALIDATION_PASSED)
        artifacts.write_json(
            experiment.uuid,
            ArtifactKind.VALIDATION_REPORT_JSON,
            {
                "research": {"metrics": {"sharpe": 1.0, "total_return": 0.03}},
                "gauntlet": {"passed": True, "failure_reasons": []},
            },
        )
        artifacts.write_json(
            experiment.uuid,
            ArtifactKind.DIAGNOSTICS_SIGNALS_JSON,
            {
                "returns": [
                    {"timestamp": "2024-01-02 00:00:00+00:00", "return": 0.01},
                    {"timestamp": "2024-01-03 00:00:00+00:00", "return": 0.02},
                ]
            },
        )

        report = run_portfolio_research(registry, artifacts)
        artifact_path = write_portfolio_artifact(report, tmp_path / "portfolio" / "report.json")

        assert report.experiment_uuids == (experiment.uuid,)
        assert report.allocation == {experiment.uuid: 1.0}
        assert report.metrics["total_return"] > 0
        assert artifact_path.exists()
    finally:
        registry.close()


def _panel() -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-02", periods=90, tz="UTC")
    symbols = ("S000", "S001")
    columns = pd.MultiIndex.from_product(
        [symbols, ("open", "high", "low", "close", "volume")],
        names=["symbol", "field"],
    )
    df = pd.DataFrame(index=idx, columns=columns, dtype=float)
    for i, symbol in enumerate(symbols):
        close = pd.Series(20.0 + i, index=idx)
        df[(symbol, "open")] = close
        df[(symbol, "high")] = close * 1.01
        df[(symbol, "low")] = close * 0.99
        df[(symbol, "close")] = close
        df[(symbol, "volume")] = 2_000_000.0
    return df
