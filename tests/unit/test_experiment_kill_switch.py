"""Tests for Experiment-scoped kill switches.

Per CONTEXT.md the keys are:
- SOFT blocks new orders; ``promotion_status`` is unchanged.
- HARD/CATASTROPHIC also transitions the Experiment to ``SUSPENDED``.
- Two Experiments sharing the same Strategy template are independent.
- Clearing the kill switch does NOT auto-resume — operator must run
  ``resume_experiment`` separately after the postmortem.
"""

from __future__ import annotations

import copy

import pytest

from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.models import (
    ExperimentDraft,
    PromotionStatus,
)
from experiments.registry import ExperimentRegistry


@pytest.fixture
def registry(tmp_path):
    reg = ExperimentRegistry(tmp_path / "experiments")
    yield reg
    reg.close()


def _draft(label: str = "test-bb", window: int = 15) -> ExperimentDraft:
    snap = build_bb_aapl_1d_default_snapshot()
    mutated = copy.deepcopy(snap)
    object.__setattr__(mutated, "parameters", {**snap.parameters, "window": window})
    return ExperimentDraft(label=label, snapshot=mutated)


def _walk_to_paper_ops(registry, uuid) -> None:
    registry.transition_promotion_status(uuid, PromotionStatus.VALIDATION_RUNNING)
    registry.transition_promotion_status(uuid, PromotionStatus.VALIDATION_PASSED)
    registry.transition_promotion_status(uuid, PromotionStatus.PAPER_OPS)


class TestExperimentKillSwitch:
    def test_soft_kill_blocks_without_suspending(self, registry):
        from experiments.kill_switch import KillSwitchSeverity

        exp = registry.create(_draft("soft"))
        _walk_to_paper_ops(registry, exp.uuid)
        experiment, state = registry.set_kill_switch(
            exp.uuid, KillSwitchSeverity.SOFT, "elevated reconciliation rate"
        )
        assert state.is_active
        assert state.is_soft
        assert not state.is_hard
        # SOFT does not change lifecycle stage.
        assert experiment.promotion_status == PromotionStatus.PAPER_OPS
        assert registry.is_soft_killed(exp.uuid) is True
        assert registry.is_hard_killed(exp.uuid) is False

    def test_hard_kill_suspends_experiment(self, registry):
        from experiments.kill_switch import KillSwitchSeverity

        exp = registry.create(_draft("hard"))
        _walk_to_paper_ops(registry, exp.uuid)
        experiment, state = registry.set_kill_switch(
            exp.uuid, KillSwitchSeverity.HARD, "max daily loss breach"
        )
        assert state.is_hard
        assert experiment.promotion_status == PromotionStatus.SUSPENDED
        assert experiment.suspended_from_status == PromotionStatus.PAPER_OPS
        assert registry.is_hard_killed(exp.uuid) is True

    def test_catastrophic_kill_marks_catastrophic(self, registry):
        from experiments.kill_switch import KillSwitchSeverity

        exp = registry.create(_draft("cat"))
        _walk_to_paper_ops(registry, exp.uuid)
        experiment, state = registry.set_kill_switch(
            exp.uuid,
            KillSwitchSeverity.CATASTROPHIC,
            "broker state UNKNOWN after disconnect",
        )
        assert state.is_catastrophic
        assert experiment.promotion_status == PromotionStatus.SUSPENDED
        assert experiment.suspended_from_status == PromotionStatus.PAPER_OPS

    def test_two_experiments_are_independent(self, registry):
        from experiments.kill_switch import KillSwitchSeverity

        a = registry.create(_draft("a", window=15))
        b = registry.create(_draft("b", window=20))
        _walk_to_paper_ops(registry, a.uuid)
        _walk_to_paper_ops(registry, b.uuid)
        registry.set_kill_switch(a.uuid, KillSwitchSeverity.SOFT, "drift")
        assert registry.is_soft_killed(a.uuid) is True
        assert registry.is_soft_killed(b.uuid) is False
        assert registry.is_hard_killed(b.uuid) is False

    def test_clear_does_not_auto_resume(self, registry):
        from experiments.kill_switch import KillSwitchSeverity

        exp = registry.create(_draft("clear"))
        _walk_to_paper_ops(registry, exp.uuid)
        registry.set_kill_switch(exp.uuid, KillSwitchSeverity.HARD, "drawdown")
        # Experiment still suspended after clearing the kill switch.
        registry.clear_kill_switch(exp.uuid, cleared_by="operator")
        reloaded = registry.get(exp.uuid)
        assert reloaded.promotion_status == PromotionStatus.SUSPENDED
        assert reloaded.suspended_from_status == PromotionStatus.PAPER_OPS
        assert registry.is_hard_killed(exp.uuid) is False

    def test_resume_restores_prior_status_and_clears_block(self, registry):
        from experiments.kill_switch import KillSwitchSeverity

        exp = registry.create(_draft("resume"))
        _walk_to_paper_ops(registry, exp.uuid)
        registry.set_kill_switch(exp.uuid, KillSwitchSeverity.HARD, "soft bleed")
        registry.clear_kill_switch(exp.uuid, cleared_by="operator")
        resumed = registry.resume_experiment(exp.uuid)
        assert resumed.promotion_status == PromotionStatus.PAPER_OPS
        assert resumed.suspended_from_status is None  # cleared on resume

    def test_setting_kill_switch_replaces_prior_active(self, registry):
        from experiments.kill_switch import KillSwitchSeverity

        exp = registry.create(_draft("escalate"))
        _walk_to_paper_ops(registry, exp.uuid)
        registry.set_kill_switch(exp.uuid, KillSwitchSeverity.SOFT, "first warning")
        escalated, state = registry.set_kill_switch(
            exp.uuid, KillSwitchSeverity.HARD, "escalated"
        )
        assert state.severity == KillSwitchSeverity.HARD
        assert escalated.promotion_status == PromotionStatus.SUSPENDED

    def test_clearing_unknown_kill_switch_raises(self, registry):
        from experiments.kill_switch import KillSwitchError

        exp = registry.create(_draft("never-set"))
        with pytest.raises(KillSwitchError):
            registry.clear_kill_switch(exp.uuid)

    def test_list_active_kill_switches(self, registry):
        from experiments.kill_switch import KillSwitchSeverity

        a = registry.create(_draft("la-1", window=15))
        b = registry.create(_draft("la-2", window=20))
        _walk_to_paper_ops(registry, a.uuid)
        _walk_to_paper_ops(registry, b.uuid)
        registry.set_kill_switch(a.uuid, KillSwitchSeverity.SOFT, "watch")
        registry.set_kill_switch(b.uuid, KillSwitchSeverity.HARD, "halt")
        actives = registry.list_active_kill_switches()
        active_uuids = {state.experiment_uuid for state in actives}
        assert active_uuids == {a.uuid, b.uuid}

    def test_kill_switch_state_serializes(self, registry):
        from experiments.kill_switch import KillSwitchSeverity

        exp = registry.create(_draft("ser"))
        _walk_to_paper_ops(registry, exp.uuid)
        _, state = registry.set_kill_switch(
            exp.uuid, KillSwitchSeverity.SOFT, "test", set_by="ops"
        )
        payload = state.to_dict()
        assert payload["severity"] == "soft"
        assert payload["reason"] == "test"
        assert payload["is_active"] is True
        assert payload["set_by"] == "ops"
