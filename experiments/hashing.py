"""Canonical experiment hashing — fingerprint of the frozen decision-path snapshot."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from experiments.models import (
    DataVersionSpec,
    DateRangeSpec,
    Experiment,
    ExperimentSnapshot,
    PromotionStatus,
    UniverseSpec,
)

# Fields excluded from experiment_hash (identity, lifecycle, evidence).
HASH_EXCLUDED_TOP_LEVEL = frozenset(
    {
        "uuid",
        "label",
        "experiment_hash",
        "promotion_status",
        "created_at",
        "superseded_by",
        "legacy_artifacts_path",
        "legacy_experiment_id",
    }
)


def _universe_dict(universe: UniverseSpec) -> dict[str, Any]:
    return {
        "symbols": list(universe.symbols),
        "asset_class": universe.asset_class,
        "selection_rule": universe.selection_rule,
        "filters": universe.filters,
    }


def _data_version_dict(data: DataVersionSpec) -> dict[str, Any]:
    return {
        "source": data.source,
        "bar_frequency": data.bar_frequency,
        "data_version": data.data_version,
        "adjustment": data.adjustment,
        "storage_dir": data.storage_dir,
    }


def _date_range_dict(date_range: DateRangeSpec) -> dict[str, Any]:
    return {"start": date_range.start, "end": date_range.end}


def snapshot_to_hash_dict(snapshot: ExperimentSnapshot) -> dict[str, Any]:
    """Build the canonical dict used for experiment_hash (decision-path fields only)."""
    return {
        "strategy": snapshot.strategy,
        "strategy_template_version": snapshot.strategy_template_version,
        "parameters": snapshot.parameters,
        "universe": _universe_dict(snapshot.universe),
        "data_version": _data_version_dict(snapshot.data_version),
        "date_range": _date_range_dict(snapshot.date_range),
        "execution_mode": snapshot.execution_mode,
        "cost_model": snapshot.cost_model,
        "slippage_model": snapshot.slippage_model,
        "risk_profile": snapshot.risk_profile,
        "portfolio_config": snapshot.portfolio_config,
        "paper_thresholds": snapshot.paper_thresholds,
        "git_commit": snapshot.git_commit,
        "config_version": snapshot.config_version,
        "random_seed": snapshot.random_seed,
    }


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, stable scalars."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_json_default)


def compute_experiment_hash(snapshot: ExperimentSnapshot) -> str:
    """SHA-256 of the canonical decision-path snapshot."""
    payload = canonical_json(snapshot_to_hash_dict(snapshot))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot_from_dict(data: dict[str, Any]) -> ExperimentSnapshot:
    """Reconstruct snapshot from metadata JSON."""
    universe_raw = data["universe"]
    data_raw = data["data_version"]
    date_raw = data["date_range"]
    return ExperimentSnapshot(
        strategy=str(data["strategy"]),
        strategy_template_version=str(data["strategy_template_version"]),
        parameters=dict(data["parameters"]),
        universe=UniverseSpec(
            symbols=tuple(universe_raw["symbols"]),
            asset_class=str(universe_raw["asset_class"]),
            selection_rule=universe_raw.get("selection_rule"),
            filters=dict(universe_raw.get("filters", {})),
        ),
        data_version=DataVersionSpec(
            source=str(data_raw["source"]),
            bar_frequency=str(data_raw["bar_frequency"]),
            data_version=str(data_raw["data_version"]),
            adjustment=data_raw.get("adjustment"),
            storage_dir=data_raw.get("storage_dir"),
        ),
        date_range=DateRangeSpec(
            start=date_raw.get("start"),
            end=date_raw.get("end"),
        ),
        execution_mode=str(data["execution_mode"]),
        cost_model=dict(data["cost_model"]),
        slippage_model=dict(data["slippage_model"]),
        risk_profile=dict(data["risk_profile"]),
        portfolio_config=dict(data["portfolio_config"]),
        paper_thresholds=dict(data["paper_thresholds"]),
        git_commit=str(data["git_commit"]),
        config_version=str(data["config_version"]),
        random_seed=int(data["random_seed"]),
    )


def experiment_to_metadata_dict(experiment: Experiment) -> dict[str, Any]:
    """Serialize Experiment to metadata.json (audit artifact)."""
    snap = snapshot_to_hash_dict(experiment.snapshot)
    return {
        "uuid": experiment.uuid,
        "label": experiment.label,
        "experiment_hash": experiment.experiment_hash,
        **snap,
        "promotion_status": experiment.promotion_status.value,
        "created_at": experiment.created_at,
        "superseded_by": experiment.superseded_by,
        "legacy_artifacts_path": experiment.legacy_artifacts_path,
        "legacy_experiment_id": experiment.legacy_experiment_id,
        "suspended_from_status": (
            experiment.suspended_from_status.value
            if experiment.suspended_from_status is not None
            else None
        ),
    }


def experiment_from_metadata_dict(data: dict[str, Any]) -> Experiment:
    """Deserialize Experiment from metadata.json."""
    snapshot = snapshot_from_dict(data)
    suspended_raw = data.get("suspended_from_status")
    return Experiment(
        uuid=str(data["uuid"]),
        label=str(data["label"]),
        experiment_hash=str(data["experiment_hash"]),
        snapshot=snapshot,
        promotion_status=PromotionStatus(str(data["promotion_status"])),
        created_at=str(data["created_at"]),
        superseded_by=data.get("superseded_by"),
        legacy_artifacts_path=data.get("legacy_artifacts_path"),
        legacy_experiment_id=data.get("legacy_experiment_id"),
        suspended_from_status=(
            PromotionStatus(str(suspended_raw)) if suspended_raw else None
        ),
    )


def _json_default(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
