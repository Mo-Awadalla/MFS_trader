"""Read-only backfill of archived experiments into the registry."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from config.schema import CostModelConfig, PortfolioConfig, RiskLimits
from experiments.hashing import compute_experiment_hash
from experiments.models import (
    DataVersionSpec,
    DateRangeSpec,
    Experiment,
    ExperimentSnapshot,
    PromotionStatus,
    UniverseSpec,
)
from experiments.registry import ExperimentRegistry
from research.bb_defaults import default_cost_config

# Stable identity for the archived Alpaca BB validation (pre-registry).
BB_AAPL_1D_DEFAULT_UUID = str(
    uuid.uuid5(uuid.NAMESPACE_URL, "mfs-trader:experiment:BB-AAPL-1D-Default")
)
BB_AAPL_1D_DEFAULT_LABEL = "BB-AAPL-1D-Default"
BB_AAPL_1D_DEFAULT_LEGACY_PATH = "runs/bb_aapl_validation_alpaca"

# Frozen snapshot constants matching the archived Alpaca validation run.
ARCHIVED_TEMPLATE_VERSION = "bollinger_bands:v1"
ARCHIVED_GIT_COMMIT = "c5795471193a320598c1db4d3c10d599dd7e98d8"
ARCHIVED_CONFIG_VERSION = "research.toml@0.1.0"
ARCHIVED_RANDOM_SEED = 42
ARCHIVED_CREATED_AT = "2026-06-26T12:00:00Z"
ARCHIVED_DATA_VERSION = "alpaca:AAPL:1d@1486"
ARCHIVED_PARAMETERS: dict[str, Any] = {
    "window": 20,
    "std_mult": 2.0,
    "width_percentile_low": 25,
    "width_percentile_high": 75,
    "width_mode": "normal",
    "width_lookback": 252,
    "long_only": True,
    "mean_reversion": True,
}
ARCHIVED_PAPER_THRESHOLDS: dict[str, Any] = {
    "min_calendar_days": 30,
    "min_trades": 100,
    "target_trades": 200,
}


def _slippage_from_cost(cost: CostModelConfig) -> dict[str, Any]:
    return {
        "slippage_fixed_pct": cost.slippage_fixed_pct,
        "slippage_variable_coeff": cost.slippage_variable_coeff,
    }


def _cost_without_slippage(cost: CostModelConfig) -> dict[str, Any]:
    full = asdict(cost)
    full.pop("slippage_fixed_pct", None)
    full.pop("slippage_variable_coeff", None)
    return full


def build_bb_aapl_1d_default_snapshot() -> ExperimentSnapshot:
    """Frozen decision-path snapshot for the archived BB-AAPL-1D-Default experiment."""
    cost = default_cost_config()
    risk = RiskLimits()
    portfolio = PortfolioConfig()
    return ExperimentSnapshot(
        strategy="bollinger_bands",
        strategy_template_version=ARCHIVED_TEMPLATE_VERSION,
        parameters=dict(ARCHIVED_PARAMETERS),
        universe=UniverseSpec(
            symbols=("AAPL",),
            asset_class="equity",
            selection_rule=None,
            filters={"min_volume": 1_000_000.0, "price_floor": 5.0},
        ),
        data_version=DataVersionSpec(
            source="alpaca",
            bar_frequency="1d",
            data_version=ARCHIVED_DATA_VERSION,
            adjustment="split_dividend",
            storage_dir="data/parquet/equity",
        ),
        date_range=DateRangeSpec(start="2020-01-01", end=None),
        execution_mode="next_bar_open",
        cost_model=_cost_without_slippage(cost),
        slippage_model=_slippage_from_cost(cost),
        risk_profile=asdict(risk),
        portfolio_config=asdict(portfolio),
        paper_thresholds=dict(ARCHIVED_PAPER_THRESHOLDS),
        git_commit=ARCHIVED_GIT_COMMIT,
        config_version=ARCHIVED_CONFIG_VERSION,
        random_seed=ARCHIVED_RANDOM_SEED,
    )


def build_bb_aapl_1d_default_experiment() -> Experiment:
    """Construct the archived Experiment record (does not write to disk)."""
    snapshot = build_bb_aapl_1d_default_snapshot()
    return Experiment(
        uuid=BB_AAPL_1D_DEFAULT_UUID,
        label=BB_AAPL_1D_DEFAULT_LABEL,
        experiment_hash=compute_experiment_hash(snapshot),
        snapshot=snapshot,
        promotion_status=PromotionStatus.VALIDATION_FAILED,
        created_at=ARCHIVED_CREATED_AT,
        legacy_artifacts_path=BB_AAPL_1D_DEFAULT_LEGACY_PATH,
        legacy_experiment_id=BB_AAPL_1D_DEFAULT_LABEL,
    )


def _load_archived_verdict(legacy_path: Path) -> dict[str, Any] | None:
    experiment_json = legacy_path / "experiment.json"
    if not experiment_json.exists():
        return None
    return json.loads(experiment_json.read_text(encoding="utf-8"))


def backfill_bb_aapl_1d_default(
    registry: ExperimentRegistry,
    *,
    repo_root: Path | None = None,
    verify_legacy: bool = True,
) -> Experiment:
    """Import archived BB-AAPL-1D-Default into the registry without mutating legacy artifacts."""
    experiment = build_bb_aapl_1d_default_experiment()

    if verify_legacy:
        root = repo_root or Path.cwd()
        legacy = root / BB_AAPL_1D_DEFAULT_LEGACY_PATH
        archived = _load_archived_verdict(legacy)
        if archived is not None:
            assert archived["promotion_status"] == "validation_failed"
            assert archived.get("experiment_id") == BB_AAPL_1D_DEFAULT_LABEL
            assert archived["strategy"] == "bollinger_bands"
            assert archived["data_source"] == "alpaca"

    return registry.import_existing(experiment)
