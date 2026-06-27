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
    suspended_from_status: PromotionStatus | None = None


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


class IllegalPromotionTransitionError(Exception):
    """Raised when a promotion-status transition violates the lifecycle matrix.

    Carries the source and target status so callers can surface the exact
    rule that was violated. Per CONTEXT.md: "Status says where the Experiment
    is. Blockers say why it cannot advance. Events say what happened. Do not
    mix them."
    """

    def __init__(
        self,
        uuid: str,
        source: PromotionStatus,
        target: PromotionStatus,
        reason: str,
    ) -> None:
        self.uuid = uuid
        self.source = source
        self.target = target
        super().__init__(
            f"Illegal promotion transition for {uuid}: {source.value} -> {target.value}: {reason}"
        )


SINGLE_STRATEGY_FIRST_LIVE_BLOCKED = (
    "single_strategy_first_live is enabled and another Experiment is already LIVE"
)


def is_legal_promotion_transition(
    source: PromotionStatus,
    target: PromotionStatus,
) -> bool:
    """Transition matrix for Experiment promotion_status (CONTEXT.md).

    ``superseded`` is reachable from any non-terminal status (operator marks
    a prior experiment as invalidated by a newer one). ``retired`` requires
    operator confirmation and is terminal. ``suspended`` captures the prior
    status into ``suspended_from_status`` so resume restores it.
    """
    if source == target:
        return True  # idempotent transitions are tolerated
    allowed: dict[PromotionStatus, frozenset[PromotionStatus]] = {
        PromotionStatus.RESEARCH: frozenset(
            {
                PromotionStatus.VALIDATION_RUNNING,
                PromotionStatus.RETIRED,
                PromotionStatus.SUPERSEDED,
            }
        ),
        PromotionStatus.VALIDATION_RUNNING: frozenset(
            {
                PromotionStatus.VALIDATION_FAILED,
                PromotionStatus.VALIDATION_PASSED,
                PromotionStatus.RETIRED,
                PromotionStatus.SUPERSEDED,
            }
        ),
        PromotionStatus.VALIDATION_FAILED: frozenset(
            {PromotionStatus.RETIRED, PromotionStatus.SUPERSEDED}
        ),
        PromotionStatus.VALIDATION_PASSED: frozenset(
            {
                PromotionStatus.PAPER_OPS,
                PromotionStatus.RETIRED,
                PromotionStatus.SUPERSEDED,
            }
        ),
        PromotionStatus.PAPER_OPS: frozenset(
            {
                PromotionStatus.LIVE_DRY_RUN,
                PromotionStatus.SUSPENDED,
                PromotionStatus.RETIRED,
                PromotionStatus.SUPERSEDED,
            }
        ),
        PromotionStatus.LIVE_DRY_RUN: frozenset(
            {
                PromotionStatus.LIVE_CANDIDATE,
                PromotionStatus.SUSPENDED,
                PromotionStatus.RETIRED,
                PromotionStatus.SUPERSEDED,
            }
        ),
        PromotionStatus.LIVE_CANDIDATE: frozenset(
            {
                PromotionStatus.LIVE,
                PromotionStatus.SUSPENDED,
                PromotionStatus.RETIRED,
                PromotionStatus.SUPERSEDED,
            }
        ),
        PromotionStatus.LIVE: frozenset(
            {PromotionStatus.SUSPENDED, PromotionStatus.RETIRED}
        ),
        # SUSPENDED may resume into any non-terminal status; the
        # ``suspended_from_status`` match is enforced separately in
        # ``ExperimentRegistry._enforce_transition``.
        PromotionStatus.SUSPENDED: frozenset(
            {
                PromotionStatus.RESEARCH,
                PromotionStatus.VALIDATION_RUNNING,
                PromotionStatus.VALIDATION_FAILED,
                PromotionStatus.VALIDATION_PASSED,
                PromotionStatus.PAPER_OPS,
                PromotionStatus.LIVE_DRY_RUN,
                PromotionStatus.LIVE_CANDIDATE,
                PromotionStatus.LIVE,
                PromotionStatus.RETIRED,
                PromotionStatus.SUPERSEDED,
            }
        ),
        PromotionStatus.RETIRED: frozenset(),  # terminal
        PromotionStatus.SUPERSEDED: frozenset(),  # terminal
    }
    return target in allowed[source]
