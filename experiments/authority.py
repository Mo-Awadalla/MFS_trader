"""Fail-closed Experiment authority facade.

This module is the narrow seam for runtime and operator entry points. The
Registry remains the semantic authority and ArtifactManager remains the
filesystem authority; this facade composes them without merging ownership.
"""

from __future__ import annotations

from experiments.kill_switch import KillSwitchSeverity, KillSwitchState
from experiments.models import Experiment, PromotionStatus
from experiments.operator_confirmations import (
    ConfirmationResult,
    confirm_paper_ops_pass,
    confirm_resume,
    confirm_retire,
    verify_experiment_hash,
)
from experiments.registry import ExperimentRegistry


class ExperimentAuthority:
    """Small, fail-closed operation surface over Experiment authorities."""

    def __init__(self, registry: ExperimentRegistry) -> None:
        self._registry = registry

    def get(self, experiment_uuid: str) -> Experiment:
        return self._registry.get(experiment_uuid)

    def verify(self, experiment_uuid: str, expected_hash: str) -> Experiment:
        """Require both the full UUID and canonical Experiment Hash."""

        return verify_experiment_hash(self._registry, experiment_uuid, expected_hash)

    def transition(
        self,
        experiment_uuid: str,
        expected_hash: str,
        new_status: PromotionStatus,
        *,
        superseded_by: str | None = None,
    ) -> Experiment:
        self.verify(experiment_uuid, expected_hash)
        return self._registry.transition_promotion_status(
            experiment_uuid,
            new_status,
            superseded_by=superseded_by,
        )

    def get_kill_switch(self, experiment_uuid: str) -> KillSwitchState | None:
        return self._registry.get_kill_switch(experiment_uuid)

    def set_kill_switch(
        self,
        experiment_uuid: str,
        severity: KillSwitchSeverity,
        reason: str,
        *,
        set_by: str | None = None,
    ) -> tuple[Experiment, KillSwitchState]:
        return self._registry.set_kill_switch(
            experiment_uuid,
            severity,
            reason,
            set_by=set_by,
        )

    def clear_kill_switch(
        self,
        experiment_uuid: str,
        *,
        cleared_by: str | None = None,
    ) -> KillSwitchState:
        return self._registry.clear_kill_switch(
            experiment_uuid,
            cleared_by=cleared_by,
        )

    def confirm_paper_ops_pass(
        self,
        experiment_uuid: str,
        expected_hash: str,
        *,
        paper_session_id: str,
        operator: str | None = None,
    ) -> ConfirmationResult:
        return confirm_paper_ops_pass(
            self._registry,
            experiment_uuid,
            expected_hash,
            paper_session_id=paper_session_id,
            operator=operator,
        )

    def confirm_resume(
        self,
        experiment_uuid: str,
        expected_hash: str,
        *,
        operator: str | None = None,
    ) -> ConfirmationResult:
        return confirm_resume(
            self._registry,
            experiment_uuid,
            expected_hash,
            operator=operator,
        )

    def confirm_retire(
        self,
        experiment_uuid: str,
        expected_hash: str,
        *,
        operator: str | None = None,
    ) -> ConfirmationResult:
        return confirm_retire(
            self._registry,
            experiment_uuid,
            expected_hash,
            operator=operator,
        )


__all__ = ["ExperimentAuthority"]
