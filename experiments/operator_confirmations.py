"""Operator confirm commands — explicit promotion gates.

Per CONTEXT.md advancement rules are *hybrid*: the system evaluates readiness,
but the operator must explicitly confirm each lifecycle transition into live
stages and out of suspended/retired states. These helpers enforce:

- **No "run latest".** Every command requires an explicit experiment UUID
  AND the recorded ``experiment_hash`` so an operator cannot accidentally
  promote an experiment they did not intend. A mismatch raises
  ``ExperimentHashMismatchError``.
- **Lifecycle matrix.** Transitions are routed through ``ExperimentRegistry``;
  the matrix from CONTEXT.md is enforced.
- **Audit trail.** Kill switches, if active, are cleared on resume only after
  the lifecycle transition succeeds; the operator's identity is recorded.

The three commands are:

- ``confirm_paper_ops_pass``  — ``paper_ops → live_dry_run``
- ``confirm_resume``           — ``suspended → suspended_from_status`` and
                                 clears the active kill switch.
- ``confirm_retire``           — any non-terminal stage → ``retired``
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from experiments.artifacts import ArtifactManager
from experiments.models import (
    Experiment,
    ExperimentNotFoundError,
    PromotionStatus,
)
from experiments.registry import ExperimentRegistry
from experiments.storage import utc_now_iso


class ExperimentHashMismatchError(Exception):
    """Raised when the operator-supplied hash does not match the registry's."""

    def __init__(self, uuid: str, expected: str, actual: str) -> None:
        self.uuid = uuid
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Experiment {uuid} hash mismatch: operator supplied {expected[:16]}... "
            f"but registry has {actual[:16]}..."
        )


class ConfirmedExperimentError(Exception):
    """Raised when the experiment is not in a state that accepts this command."""


@dataclass(frozen=True)
class ConfirmationResult:
    """Outcome of a successful operator confirmation."""

    experiment: Experiment
    transition: str  # "paper_ops -> live_dry_run", "suspended -> X", "* -> retired"
    operator: str | None
    cleared_kill_switch: bool = False
    paper_session_id: str | None = None
    confirmation_artifact_path: str | None = None
    evidence_artifact_hashes: dict[str, str] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "experiment_uuid": self.experiment.uuid,
            "experiment_hash": self.experiment.experiment_hash,
            "promotion_status": self.experiment.promotion_status.value,
            "transition": self.transition,
            "operator": self.operator,
            "cleared_kill_switch": self.cleared_kill_switch,
            "paper_session_id": self.paper_session_id,
            "confirmation_artifact_path": self.confirmation_artifact_path,
            "evidence_artifact_hashes": self.evidence_artifact_hashes,
        }


def verify_experiment_hash(
    registry: ExperimentRegistry,
    uuid: str,
    expected_hash: str,
) -> Experiment:
    """Fetch the experiment and confirm the operator-supplied hash matches.

    Rejects ambiguous prefix matches — operators must supply the full
    ``experiment_hash`` to avoid silently promoting a re-fingerprinted
    snapshot.
    """
    experiment = registry.get(uuid)
    if experiment is None:
        raise ExperimentNotFoundError(f"Experiment not found: {uuid}")
    if experiment.experiment_hash != expected_hash:
        raise ExperimentHashMismatchError(
            uuid, expected=expected_hash, actual=experiment.experiment_hash
        )
    return experiment


def confirm_paper_ops_pass(
    registry: ExperimentRegistry,
    uuid: str,
    expected_hash: str,
    *,
    paper_session_id: str,
    operator: str | None = None,
) -> ConfirmationResult:
    """Operator confirmation: ``paper_ops → live_dry_run``.

    Per CONTEXT.md the system may *recommend* graduation from paper ops; only
    the operator promotes. This command is the gate.
    """
    experiment = verify_experiment_hash(registry, uuid, expected_hash)
    if experiment.promotion_status != PromotionStatus.PAPER_OPS:
        raise ConfirmedExperimentError(
            f"confirm-paper-ops-pass requires PAPER_OPS, "
            f"got {experiment.promotion_status.value}"
        )
    evidence = _verify_paper_ops_evidence(registry, experiment, paper_session_id)
    confirmation_path = _write_paper_ops_confirmation(
        registry,
        experiment,
        paper_session_id=paper_session_id,
        operator=operator,
        evidence=evidence,
    )
    updated = registry.transition_promotion_status(
        uuid, PromotionStatus.LIVE_DRY_RUN
    )
    return ConfirmationResult(
        experiment=updated,
        transition="paper_ops -> live_dry_run",
        operator=operator,
        paper_session_id=paper_session_id,
        confirmation_artifact_path=str(confirmation_path),
            evidence_artifact_hashes=cast(
                dict[str, str],
                evidence["evidence_artifact_hashes"],
            ),
    )


def confirm_resume(
    registry: ExperimentRegistry,
    uuid: str,
    expected_hash: str,
    *,
    operator: str | None = None,
) -> ConfirmationResult:
    """Operator confirmation: resume from ``SUSPENDED`` to
    ``suspended_from_status`` and clear the active kill switch.

    Per CONTEXT.md resume never auto-restores trading authority; this command
    is the explicit operator confirmation. After this, advancement to live
    stages still requires the deployment checklist + the same operator
    confirmation discipline.
    """
    experiment = verify_experiment_hash(registry, uuid, expected_hash)
    if experiment.promotion_status != PromotionStatus.SUSPENDED:
        raise ConfirmedExperimentError(
            f"confirm-resume requires SUSPENDED, "
            f"got {experiment.promotion_status.value}"
        )
    updated = registry.resume_experiment(uuid)
    cleared = False
    if registry.get_kill_switch(uuid) is not None:
        registry.clear_kill_switch(uuid, cleared_by=operator)
        cleared = True
    return ConfirmationResult(
        experiment=updated,
        transition=f"suspended -> {updated.promotion_status.value}",
        operator=operator,
        cleared_kill_switch=cleared,
    )


def confirm_retire(
    registry: ExperimentRegistry,
    uuid: str,
    expected_hash: str,
    *,
    operator: str | None = None,
) -> ConfirmationResult:
    """Operator confirmation: terminal retirement from any non-terminal stage.

    Re-evaluation after retirement creates a *new* Experiment.
    """
    experiment = verify_experiment_hash(registry, uuid, expected_hash)
    if experiment.promotion_status in {PromotionStatus.RETIRED, PromotionStatus.SUPERSEDED}:
        raise ConfirmedExperimentError(
            f"confirm-retire requires non-terminal status, "
            f"got {experiment.promotion_status.value}"
        )
    updated = registry.retire_experiment(uuid)
    return ConfirmationResult(
        experiment=updated,
        transition=f"{experiment.promotion_status.value} -> retired",
        operator=operator,
    )


def _verify_paper_ops_evidence(
    registry: ExperimentRegistry,
    experiment: Experiment,
    paper_session_id: str,
) -> dict[str, Any]:
    from engine.paper_session import evaluate_paper_ops_pass_session

    evidence = evaluate_paper_ops_pass_session(
        registry=registry,
        experiment=experiment,
        session_id=paper_session_id,
    )
    if evidence.get("passed") is not True:
        blockers = evidence.get("blockers") or []
        raise ConfirmedExperimentError(
            "confirm-paper-ops-pass requires a passing immutable 30-day "
            "paper_ops_pass session: " + "; ".join(str(b) for b in blockers)
        )
    return evidence


def _write_paper_ops_confirmation(
    registry: ExperimentRegistry,
    experiment: Experiment,
    *,
    paper_session_id: str,
    operator: str | None,
    evidence: dict[str, Any],
) -> Path:
    artifacts = ArtifactManager(registry.root)
    payload = {
        "confirmation_type": "paper_ops_pass",
        "confirmed_by": operator,
        "confirmed_at_utc": utc_now_iso(),
        "experiment_id": experiment.uuid,
        "experiment_uuid": experiment.uuid,
        "experiment_hash": experiment.experiment_hash,
        "paper_session_id": paper_session_id,
        "evidence_artifact_hashes": evidence["evidence_artifact_hashes"],
        "result": "confirmed",
        "next_allowed_status": PromotionStatus.LIVE_DRY_RUN.value,
    }
    return artifacts.write_paper_session_report_json(
        experiment.uuid,
        paper_session_id,
        "paper_ops_pass_confirmation.json",
        payload,
    )
