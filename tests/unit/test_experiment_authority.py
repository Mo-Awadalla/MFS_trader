from __future__ import annotations

import copy

import pytest

from experiments.authority import ExperimentAuthority
from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.kill_switch import KillSwitchSeverity
from experiments.models import ExperimentDraft, PromotionStatus
from experiments.operator_confirmations import ExperimentHashMismatchError
from experiments.registry import ExperimentRegistry


def _draft() -> ExperimentDraft:
    snapshot = copy.deepcopy(build_bb_aapl_1d_default_snapshot())
    object.__setattr__(snapshot, "parameters", {**snapshot.parameters, "window": 17})
    return ExperimentDraft(label="authority-test", snapshot=snapshot)


@pytest.fixture
def authority(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    yield registry, ExperimentAuthority(registry)
    registry.close()


def test_authority_verifies_identity_before_transition(authority) -> None:
    registry, subject = authority
    experiment = registry.create(_draft())

    with pytest.raises(ExperimentHashMismatchError, match="hash mismatch"):
        subject.transition(
            experiment.uuid,
            "0" * 64,
            PromotionStatus.VALIDATION_RUNNING,
        )

    updated = subject.transition(
        experiment.uuid,
        experiment.experiment_hash,
        PromotionStatus.VALIDATION_RUNNING,
    )
    assert updated.promotion_status == PromotionStatus.VALIDATION_RUNNING


def test_authority_preserves_kill_switch_semantics(authority) -> None:
    registry, subject = authority
    experiment = registry.create(_draft())

    _, state = subject.set_kill_switch(
        experiment.uuid,
        KillSwitchSeverity.SOFT,
        "operator test",
    )

    assert state.is_active
    assert subject.get_kill_switch(experiment.uuid) == state
    assert registry.get(experiment.uuid).promotion_status == PromotionStatus.RESEARCH
