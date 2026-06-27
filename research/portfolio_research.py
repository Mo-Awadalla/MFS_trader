"""Portfolio-level research over validated Experiment outputs."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.models import Experiment, PromotionStatus
from experiments.registry import ExperimentRegistry


@dataclass(frozen=True)
class ExperimentOutput:
    """Validation output consumed by portfolio research."""

    experiment_uuid: str
    label: str
    strategy: str
    promotion_status: str
    metrics: dict[str, float]
    returns: pd.Series
    max_gross_exposure_pct: float
    max_net_exposure_pct: float
    report: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioResearchReport:
    """Portfolio-level research artifact assembled from Experiment evidence."""

    experiment_uuids: tuple[str, ...]
    allocation: dict[str, float]
    metrics: dict[str, float]
    correlation: dict[str, Any]
    exposure: dict[str, Any]
    attribution: dict[str, Any]
    skipped_experiments: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_uuids": list(self.experiment_uuids),
            "allocation": self.allocation,
            "metrics": self.metrics,
            "correlation": self.correlation,
            "exposure": self.exposure,
            "attribution": self.attribution,
            "skipped_experiments": self.skipped_experiments,
        }


def load_experiment_outputs(
    registry: ExperimentRegistry,
    artifacts: ArtifactManager,
    *,
    promotion_status: PromotionStatus = PromotionStatus.VALIDATION_PASSED,
) -> tuple[list[ExperimentOutput], dict[str, str]]:
    """Load portfolio-consumable outputs from Experiments in one lifecycle status."""
    outputs: list[ExperimentOutput] = []
    skipped: dict[str, str] = {}
    for experiment in registry.list_experiments(promotion_status=promotion_status):
        output = load_experiment_output(experiment, artifacts)
        if output is None:
            skipped[experiment.uuid] = "missing_returns_diagnostics"
            continue
        outputs.append(output)
    return outputs, skipped


def load_experiment_output(
    experiment: Experiment,
    artifacts: ArtifactManager,
) -> ExperimentOutput | None:
    """Load one Experiment output, returning None when returns evidence is absent."""
    report = artifacts.read_json(experiment.uuid, ArtifactKind.VALIDATION_REPORT_JSON)
    diagnostics: dict[str, Any] = {}
    if artifacts.exists(experiment.uuid, ArtifactKind.DIAGNOSTICS_SIGNALS_JSON):
        diagnostics = artifacts.read_json(experiment.uuid, ArtifactKind.DIAGNOSTICS_SIGNALS_JSON)
    returns = _returns_from_diagnostics(diagnostics)
    if returns.empty:
        return None
    risk = experiment.snapshot.risk_profile
    return ExperimentOutput(
        experiment_uuid=experiment.uuid,
        label=experiment.label,
        strategy=experiment.snapshot.strategy,
        promotion_status=str(experiment.promotion_status),
        metrics={str(k): float(v) for k, v in report.get("research", {}).get("metrics", {}).items()},
        returns=returns,
        max_gross_exposure_pct=float(risk.get("max_gross_exposure_pct", 0.0)),
        max_net_exposure_pct=float(risk.get("max_net_exposure_pct", 0.0)),
        report=report,
    )


def equal_weight_allocation(outputs: list[ExperimentOutput]) -> dict[str, float]:
    """Allocate capital equally across portfolio inputs."""
    if not outputs:
        return {}
    weight = 1.0 / len(outputs)
    return {output.experiment_uuid: weight for output in outputs}


def combine_experiment_returns(
    outputs: list[ExperimentOutput],
    allocation: dict[str, float] | None = None,
) -> pd.Series:
    """Combine Experiment return series according to capital weights."""
    if not outputs:
        return pd.Series(dtype=float)
    allocation = allocation or equal_weight_allocation(outputs)
    frame = pd.concat(
        [output.returns.rename(output.experiment_uuid) for output in outputs],
        axis=1,
    ).fillna(0.0)
    weighted = frame.mul(pd.Series(allocation), axis=1)
    return weighted.sum(axis=1).rename("portfolio_return")


def strategy_correlation(outputs: list[ExperimentOutput]) -> dict[str, Any]:
    """Compute cross-Experiment return correlations."""
    if len(outputs) < 2:
        return {"matrix": {}, "max_abs_correlation": 0.0, "status": "insufficient_experiments"}
    frame = pd.concat(
        [output.returns.rename(output.experiment_uuid) for output in outputs],
        axis=1,
    ).fillna(0.0)
    corr = frame.corr().fillna(0.0)
    max_abs = 0.0
    for row in corr.index:
        for col in corr.columns:
            if row == col:
                continue
            max_abs = max(max_abs, abs(float(corr.loc[row, col])))
    return {
        "matrix": {
            str(row): {str(col): float(corr.loc[row, col]) for col in corr.columns}
            for row in corr.index
        },
        "max_abs_correlation": max_abs,
        "status": "ok",
    }


def exposure_report(outputs: list[ExperimentOutput], allocation: dict[str, float]) -> dict[str, Any]:
    """Report portfolio-level exposure implied by Experiment risk profiles."""
    gross = sum(allocation.get(output.experiment_uuid, 0.0) * output.max_gross_exposure_pct for output in outputs)
    net = sum(abs(allocation.get(output.experiment_uuid, 0.0) * output.max_net_exposure_pct) for output in outputs)
    return {
        "weighted_max_gross_exposure_pct": gross,
        "weighted_abs_max_net_exposure_pct": net,
        "by_experiment": {
            output.experiment_uuid: {
                "strategy": output.strategy,
                "capital_weight": allocation.get(output.experiment_uuid, 0.0),
                "max_gross_exposure_pct": output.max_gross_exposure_pct,
                "max_net_exposure_pct": output.max_net_exposure_pct,
            }
            for output in outputs
        },
    }


def performance_attribution(
    outputs: list[ExperimentOutput],
    allocation: dict[str, float],
) -> dict[str, Any]:
    """Attribute portfolio return contribution by Experiment."""
    contributions: dict[str, Any] = {}
    total = 0.0
    for output in outputs:
        weight = allocation.get(output.experiment_uuid, 0.0)
        contribution = float((output.returns * weight).sum())
        total += contribution
        contributions[output.experiment_uuid] = {
            "strategy": output.strategy,
            "capital_weight": weight,
            "total_return_contribution": contribution,
        }
    return {
        "total_return_contribution": total,
        "by_experiment": contributions,
    }


def run_portfolio_research(
    registry: ExperimentRegistry,
    artifacts: ArtifactManager,
    *,
    promotion_status: PromotionStatus = PromotionStatus.VALIDATION_PASSED,
) -> PortfolioResearchReport:
    """Build a portfolio research report from existing Experiment outputs."""
    outputs, skipped = load_experiment_outputs(
        registry,
        artifacts,
        promotion_status=promotion_status,
    )
    allocation = equal_weight_allocation(outputs)
    portfolio_returns = combine_experiment_returns(outputs, allocation)
    metrics = _portfolio_metrics(portfolio_returns)
    return PortfolioResearchReport(
        experiment_uuids=tuple(output.experiment_uuid for output in outputs),
        allocation=allocation,
        metrics=metrics,
        correlation=strategy_correlation(outputs),
        exposure=exposure_report(outputs, allocation),
        attribution=performance_attribution(outputs, allocation),
        skipped_experiments=skipped,
    )


def write_portfolio_artifact(report: PortfolioResearchReport, path: str | Path) -> Path:
    """Write a portfolio research artifact atomically."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    fd, name = tempfile.mkstemp(prefix=".portfolio-", suffix=".tmp", dir=target.parent)
    tmp_path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)
    return target


def _returns_from_diagnostics(diagnostics: dict[str, Any]) -> pd.Series:
    rows = diagnostics.get("returns", [])
    if not rows:
        return pd.Series(dtype=float)
    index = [pd.Timestamp(row["timestamp"]) for row in rows]
    values = [float(row["return"]) for row in rows]
    return pd.Series(values, index=pd.DatetimeIndex(index)).sort_index()


def _portfolio_metrics(returns: pd.Series) -> dict[str, float]:
    if returns.empty:
        return {
            "total_return": 0.0,
            "ann_volatility": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
        }
    equity = (1.0 + returns).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    ann_vol = float(returns.std() * (252**0.5)) if len(returns) > 1 else 0.0
    sharpe = float((returns.mean() / returns.std()) * (252**0.5)) if returns.std() > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0
    return {
        "total_return": total_return,
        "ann_volatility": ann_vol,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
    }
