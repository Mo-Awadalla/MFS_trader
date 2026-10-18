from __future__ import annotations

from datetime import UTC, datetime

import pytest

from engine.paper_evidence import execution_version
from experiments.artifacts import ArtifactManager
from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.kill_switch import KillSwitchSeverity
from experiments.lifecycle import RuntimeObservationStatus
from experiments.models import (
    ExperimentDraft,
    IllegalPromotionTransitionError,
    PromotionStatus,
)
from experiments.registry import ExperimentRegistry


@pytest.fixture
def registry(tmp_path):
    value = ExperimentRegistry(tmp_path / "experiments")
    yield value
    value.close()


def _experiment(registry, status=PromotionStatus.VALIDATION_PASSED):
    return registry.create(
        ExperimentDraft(
            label="lifecycle-view-test",
            snapshot=build_bb_aapl_1d_default_snapshot(),
            promotion_status=status,
        )
    )


def test_assessment_keeps_science_separate_from_historical_promotion(registry):
    experiment = _experiment(registry)

    assessment = registry.inspect_lifecycle(experiment.uuid)

    assert assessment.experiment.promotion_status is PromotionStatus.VALIDATION_PASSED
    assert assessment.qualification.qualified is False
    assert assessment.qualification.status == "requiring_re_evaluation"
    assert assessment.runtime.status is RuntimeObservationStatus.UNOBSERVED
    assert registry.get(experiment.uuid).promotion_status is PromotionStatus.VALIDATION_PASSED


def test_stale_paper_execution_evidence_is_not_reported_as_completed(registry):
    experiment = _experiment(registry)
    payload = {
        "experiment_uuid": experiment.uuid,
        "experiment_hash": experiment.experiment_hash,
        "session_id": "stale-session",
        "session_type": "paper_run",
        "identity": {
            "experiment_uuid": experiment.uuid,
            "experiment_hash": experiment.experiment_hash,
            "session_id": "stale-session",
            "code_version": "0" * 64,
        },
        "observations": {"observed_until": datetime.now(UTC).isoformat()},
        "passed": True,
        "halted": False,
        "errors": [],
    }
    ArtifactManager(registry.root).write_paper_session_json(
        experiment.uuid, "stale-session", payload,
    )

    assessment = registry.inspect_lifecycle(experiment.uuid)

    assert assessment.runtime.status is RuntimeObservationStatus.STALE_SESSION
    assert assessment.experiment.promotion_status is PromotionStatus.VALIDATION_PASSED


def test_clean_paper_session_is_reported_without_advancing_lifecycle(registry):
    experiment = _experiment(registry)
    payload = {
        "experiment_uuid": experiment.uuid,
        "experiment_hash": experiment.experiment_hash,
        "session_id": "clean-session",
        "session_type": "paper_run",
        "identity": {
            "experiment_uuid": experiment.uuid,
            "experiment_hash": experiment.experiment_hash,
            "session_id": "clean-session",
            "code_version": execution_version(),
        },
        "observations": {"observed_until": datetime.now(UTC).isoformat()},
        "passed": True,
        "halted": False,
        "errors": [],
    }
    ArtifactManager(registry.root).write_paper_session_json(
        experiment.uuid, "clean-session", payload,
    )

    assessment = registry.inspect_lifecycle(experiment.uuid)

    assert assessment.runtime.status is RuntimeObservationStatus.LAST_SESSION_COMPLETED
    assert assessment.runtime.session_id == "clean-session"
    assert assessment.experiment.promotion_status is PromotionStatus.VALIDATION_PASSED


def test_malformed_paper_session_identity_is_invalid_evidence(registry):
    experiment = _experiment(registry)
    payload = {
        "experiment_uuid": experiment.uuid,
        "experiment_hash": experiment.experiment_hash,
        "session_id": None,
        "session_type": "paper_run",
        "identity": {},
        "observations": {"observed_until": datetime.now(UTC).isoformat()},
        "passed": True,
        "halted": False,
        "errors": [],
    }
    ArtifactManager(registry.root).write_paper_session_json(
        experiment.uuid, "malformed-session", payload,
    )

    assessment = registry.inspect_lifecycle(experiment.uuid)

    assert assessment.runtime.status is RuntimeObservationStatus.INVALID_EVIDENCE


def test_failed_or_halted_runtime_observation_stays_separate(registry):
    experiment = _experiment(registry)
    payload = {
        "experiment_uuid": experiment.uuid,
        "experiment_hash": experiment.experiment_hash,
        "session_id": "blocked-session",
        "session_type": "paper_run",
        "identity": {
            "experiment_uuid": experiment.uuid,
            "experiment_hash": experiment.experiment_hash,
            "session_id": "blocked-session",
            "code_version": execution_version(),
        },
        "observations": {"observed_until": datetime.now(UTC).isoformat()},
        "passed": False,
        "halted": True,
        "errors": ["fresh data overdue"],
        "halt_reason": "fresh data overdue",
    }
    ArtifactManager(registry.root).write_paper_session_json(
        experiment.uuid, "blocked-session", payload,
    )

    assessment = registry.inspect_lifecycle(experiment.uuid)

    assert assessment.runtime.status is RuntimeObservationStatus.LAST_SESSION_BLOCKED
    assert "fresh data overdue" in assessment.runtime.reason
    assert assessment.experiment.promotion_status is PromotionStatus.VALIDATION_PASSED


def test_kill_switch_halts_runtime_without_becoming_scientific_failure(registry):
    experiment = _experiment(registry)
    registry.set_kill_switch(experiment.uuid, KillSwitchSeverity.SOFT, "operator pause")

    assessment = registry.inspect_lifecycle(experiment.uuid)

    assert assessment.runtime.status is RuntimeObservationStatus.KILL_SWITCH_ACTIVE
    assert assessment.qualification.qualified is False
    assert assessment.experiment.promotion_status is PromotionStatus.VALIDATION_PASSED


def test_hard_halt_requires_explicit_recovery_and_restores_saved_stage(registry):
    experiment = _experiment(registry, PromotionStatus.LIVE_DRY_RUN)
    registry.set_kill_switch(experiment.uuid, KillSwitchSeverity.HARD, "unknown broker state")

    halted = registry.inspect_lifecycle(experiment.uuid)
    assert halted.experiment.promotion_status is PromotionStatus.SUSPENDED
    assert halted.runtime.status is RuntimeObservationStatus.RECOVERY_REQUIRED

    registry.clear_kill_switch(experiment.uuid, cleared_by="operator")
    still_suspended = registry.inspect_lifecycle(experiment.uuid)
    assert still_suspended.experiment.promotion_status is PromotionStatus.SUSPENDED
    assert still_suspended.runtime.status is RuntimeObservationStatus.RECOVERY_REQUIRED

    resumed = registry.resume_experiment(experiment.uuid)
    assert resumed.promotion_status is PromotionStatus.LIVE_DRY_RUN
    assert registry.inspect_lifecycle(experiment.uuid).runtime.status is RuntimeObservationStatus.UNOBSERVED


def test_failed_validation_is_terminal_and_cannot_be_promoted(registry):
    experiment = _experiment(registry, PromotionStatus.RESEARCH)
    registry.transition_promotion_status(experiment.uuid, PromotionStatus.VALIDATION_RUNNING)
    registry.transition_promotion_status(experiment.uuid, PromotionStatus.VALIDATION_FAILED)

    with pytest.raises(IllegalPromotionTransitionError):
        registry.transition_promotion_status(experiment.uuid, PromotionStatus.VALIDATION_PASSED)
