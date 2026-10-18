"""Read-only Experiment lifecycle assessment across independent state axes.

``promotion_status`` remains the persisted lifecycle authority. Numerical
qualification is read from the corrected-evaluation verifier, while runtime
observation comes from the active kill switch and immutable paper-session
evidence. This module never advances lifecycle state or authorizes trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from engine.paper_evidence import execution_version
from experiments.artifacts import ArtifactManager
from experiments.corrected_evaluations import Qualification, check_current_qualification
from experiments.models import Experiment, PromotionStatus

if TYPE_CHECKING:
    from experiments.registry import ExperimentRegistry


class RuntimeObservationStatus(StrEnum):
    """What the latest stored operational evidence says, not a live health claim."""

    UNOBSERVED = "unobserved"
    LAST_SESSION_COMPLETED = "last_session_completed"
    LAST_SESSION_BLOCKED = "last_session_blocked"
    STALE_SESSION = "stale_session"
    INVALID_EVIDENCE = "invalid_evidence"
    KILL_SWITCH_ACTIVE = "kill_switch_active"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass(frozen=True)
class RuntimeObservation:
    status: RuntimeObservationStatus
    session_id: str | None = None
    observed_until: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ExperimentLifecycleAssessment:
    """Current lifecycle stage plus independent science/runtime observations.

    A completed paper session is operational evidence only. It is not a
    numerical qualification or a promotion decision.
    """

    experiment: Experiment
    qualification: Qualification
    runtime: RuntimeObservation


def assess_experiment_lifecycle(
    registry: ExperimentRegistry,
    experiment_uuid: str,
) -> ExperimentLifecycleAssessment:
    """Read current evidence without changing the Experiment or its artifacts."""
    experiment = registry.get(experiment_uuid)
    qualification = check_current_qualification(
        registry, experiment.uuid, experiment.experiment_hash,
    )
    runtime = _runtime_observation(registry, experiment)
    return ExperimentLifecycleAssessment(
        experiment=experiment,
        qualification=qualification,
        runtime=runtime,
    )


def _runtime_observation(
    registry: ExperimentRegistry,
    experiment: Experiment,
) -> RuntimeObservation:
    if experiment.promotion_status == PromotionStatus.SUSPENDED:
        return RuntimeObservation(
            RuntimeObservationStatus.RECOVERY_REQUIRED,
            reason="Experiment is suspended; explicit operator recovery is required",
        )

    kill_switch = registry.get_kill_switch(experiment.uuid)
    if kill_switch is not None and kill_switch.is_active:
        return RuntimeObservation(
            RuntimeObservationStatus.KILL_SWITCH_ACTIVE,
            reason=f"{kill_switch.severity.value}: {kill_switch.reason}",
        )

    try:
        sessions = ArtifactManager(registry.root).list_paper_sessions(experiment.uuid)
    except (OSError, ValueError, TypeError) as exc:
        return RuntimeObservation(
            RuntimeObservationStatus.INVALID_EVIDENCE,
            reason=f"Cannot read paper-session evidence: {exc}",
        )

    if not isinstance(sessions, list) or any(not isinstance(session, dict) for session in sessions):
        return RuntimeObservation(
            RuntimeObservationStatus.INVALID_EVIDENCE,
            reason="Paper-session evidence must be a list of JSON objects",
        )

    candidates = [session for session in sessions if session.get("session_type") == "paper_run"]
    if not candidates:
        return RuntimeObservation(RuntimeObservationStatus.UNOBSERVED)

    try:
        latest = max(candidates, key=lambda session: _observed_at(session))
        observed_at = _observed_at(latest)
        session_id = latest["session_id"]
        identity = latest["identity"]
        if (
            not isinstance(session_id, str)
            or not session_id
            or not isinstance(identity, dict)
            or latest.get("experiment_uuid") != experiment.uuid
            or latest.get("experiment_hash") != experiment.experiment_hash
            or identity.get("experiment_uuid") != experiment.uuid
            or identity.get("experiment_hash") != experiment.experiment_hash
            or identity.get("session_id") != session_id
        ):
            return RuntimeObservation(
                RuntimeObservationStatus.INVALID_EVIDENCE,
                str(session_id), observed_at.isoformat(),
                "Paper-session identity does not match the frozen Experiment",
            )
        if identity.get("code_version") != execution_version():
            return RuntimeObservation(
                RuntimeObservationStatus.STALE_SESSION,
                str(session_id), observed_at.isoformat(),
                "Execution source differs from the paper-session observation",
            )
        if latest.get("halted") is True or latest.get("errors") or latest.get("passed") is not True:
            return RuntimeObservation(
                RuntimeObservationStatus.LAST_SESSION_BLOCKED,
                str(session_id), observed_at.isoformat(),
                str(latest.get("halt_reason") or latest.get("blockers") or "Paper session did not complete cleanly"),
            )
        return RuntimeObservation(
            RuntimeObservationStatus.LAST_SESSION_COMPLETED,
            str(session_id), observed_at.isoformat(),
            "Latest stored paper session completed; this does not establish current health or qualification",
        )
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError, OSError) as exc:
        return RuntimeObservation(
            RuntimeObservationStatus.INVALID_EVIDENCE,
            reason=f"Paper-session evidence is incomplete or invalid: {exc}",
        )


def _observed_at(session: dict[str, Any]) -> datetime:
    observations = session["observations"]
    value = observations["observed_until"]
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("paper-session timestamp requires a timezone")
    return parsed.astimezone(UTC)
