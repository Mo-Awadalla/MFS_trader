"""Frozen Experiment models — identity, snapshot, and lifecycle status."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PromotionStatus(StrEnum):
    """Experiment lifecycle stage (CONTEXT.md vocabulary)."""

    RESEARCH = "research"
    VALIDATION_RUNNING = "validation_running"
    VALIDATION_FAILED = "validation_failed"
    VALIDATION_PASSED = "validation_passed"
    PAPER_OPS = "paper_ops"
    LIVE_DRY_RUN = "live_dry_run"
    LIVE_CANDIDATE = "live_candidate"
    LIVE = "live"
    SUSPENDED = "suspended"
    RETIRED = "retired"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class UniverseSpec:
    symbols: tuple[str, ...]
    asset_class: str
    selection_rule: str | None = None
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DataVersionSpec:
    source: str
    bar_frequency: str
    data_version: str
    adjustment: str | None = None
    storage_dir: str | None = None


@dataclass(frozen=True)
class DateRangeSpec:
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True)
class ExperimentSnapshot:
    """Decision-path fields frozen at Experiment creation. Included in experiment_hash."""

    strategy: str
    strategy_template_version: str
    parameters: dict[str, Any]
    universe: UniverseSpec
    data_version: DataVersionSpec
    date_range: DateRangeSpec
    execution_mode: str
    cost_model: dict[str, Any]
    slippage_model: dict[str, Any]
    risk_profile: dict[str, Any]
    portfolio_config: dict[str, Any]
    paper_thresholds: dict[str, Any]
    git_commit: str
    config_version: str
    random_seed: int


@dataclass(frozen=True)
class ExperimentDraft:
    """Input to create a new Experiment."""

    label: str
    snapshot: ExperimentSnapshot
    uuid: str | None = None
    promotion_status: PromotionStatus = PromotionStatus.RESEARCH
    legacy_artifacts_path: str | None = None
    legacy_experiment_id: str | None = None


@dataclass(frozen=True)
class Experiment:
    """Immutable Experiment record (snapshot frozen; status transitions are lifecycle only)."""

    uuid: str
    label: str
    experiment_hash: str
    snapshot: ExperimentSnapshot
    promotion_status: PromotionStatus
    created_at: str
    superseded_by: str | None = None
    legacy_artifacts_path: str | None = None
    legacy_experiment_id: str | None = None


class DuplicateExperimentError(Exception):
    """Raised when an experiment with the same hash already exists."""

    def __init__(self, experiment_hash: str, existing_uuid: str) -> None:
        self.experiment_hash = experiment_hash
        self.existing_uuid = existing_uuid
        super().__init__(
            f"Experiment hash {experiment_hash[:16]}... already registered as {existing_uuid}"
        )


class ImmutableExperimentError(Exception):
    """Raised when a mutation would change frozen snapshot fields."""


class ExperimentNotFoundError(Exception):
    """Raised when an experiment UUID is not in the registry."""
