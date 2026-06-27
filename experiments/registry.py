"""Experiment registry — create, query, and lifecycle transitions."""

from __future__ import annotations

import uuid
from pathlib import Path

from experiments.hashing import compute_experiment_hash
from experiments.kill_switch import (
    ExperimentKillSwitchStore,
    KillSwitchSeverity,
    KillSwitchState,
)
from experiments.models import (
    DuplicateExperimentError,
    Experiment,
    ExperimentDraft,
    ExperimentNotFoundError,
    IllegalPromotionTransitionError,
    ImmutableExperimentError,
    PromotionStatus,
    is_legal_promotion_transition,
)
from experiments.storage import ExperimentStore, utc_now_iso


class ExperimentRegistry:
    """Single source of truth for frozen Experiments."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        single_strategy_first_live: bool = True,
    ) -> None:
        self.store = ExperimentStore(root)
        self.single_strategy_first_live = single_strategy_first_live
        self.kill_switches = ExperimentKillSwitchStore(self.store._conn)

    @property
    def root(self) -> Path:
        return self.store.root

    def create(self, draft: ExperimentDraft) -> Experiment:
        """Register a new Experiment. Rejects duplicate hashes."""
        experiment_hash = compute_experiment_hash(draft.snapshot)
        existing = self.store.get_by_hash(experiment_hash)
        if existing is not None:
            raise DuplicateExperimentError(experiment_hash, existing.uuid)

        exp_uuid = draft.uuid or str(uuid.uuid4())
        if self.store.get_by_uuid(exp_uuid) is not None:
            raise ImmutableExperimentError(f"UUID {exp_uuid} already registered")

        experiment = Experiment(
            uuid=exp_uuid,
            label=draft.label,
            experiment_hash=experiment_hash,
            snapshot=draft.snapshot,
            promotion_status=draft.promotion_status,
            created_at=utc_now_iso(),
            legacy_artifacts_path=draft.legacy_artifacts_path,
            legacy_experiment_id=draft.legacy_experiment_id,
        )
        metadata_path = self.store.write_metadata(experiment)
        self.store.insert_index(experiment, metadata_path)
        return experiment

    def import_existing(self, experiment: Experiment) -> Experiment:
        """Idempotent import for backfill — same uuid+hash returns existing."""
        by_hash = self.store.get_by_hash(experiment.experiment_hash)
        if by_hash is not None:
            if by_hash.uuid != experiment.uuid:
                raise DuplicateExperimentError(experiment.experiment_hash, by_hash.uuid)
            return by_hash

        existing = self.store.get_by_uuid(experiment.uuid)
        if existing is not None:
            if existing.experiment_hash != experiment.experiment_hash:
                raise ImmutableExperimentError(
                    f"UUID {experiment.uuid} exists with different hash"
                )
            return existing

        metadata_path = self.store.write_metadata(experiment)
        self.store.insert_index(experiment, metadata_path)
        return experiment

    def get(self, uuid: str) -> Experiment:
        experiment = self.store.get_by_uuid(uuid)
        if experiment is None:
            raise ExperimentNotFoundError(f"Experiment not found: {uuid}")
        return experiment

    def get_by_hash(self, experiment_hash: str) -> Experiment | None:
        return self.store.get_by_hash(experiment_hash)

    def get_by_label(self, label: str) -> Experiment | None:
        uuids = self.store.list_uuids(label=label)
        if not uuids:
            return None
        return self.get(uuids[0])

    def get_by_legacy_id(self, legacy_experiment_id: str) -> Experiment | None:
        for exp in self.list_experiments():
            if exp.legacy_experiment_id == legacy_experiment_id:
                return exp
        return None

    def list_experiments(
        self,
        *,
        strategy: str | None = None,
        promotion_status: PromotionStatus | None = None,
        strategy_template_version: str | None = None,
        data_source: str | None = None,
        label: str | None = None,
    ) -> list[Experiment]:
        uuids = self.store.list_uuids(
            strategy=strategy,
            promotion_status=promotion_status,
            strategy_template_version=strategy_template_version,
            data_source=data_source,
            label=label,
        )
        return [self.get(uid) for uid in uuids]

    def transition_promotion_status(
        self,
        uuid: str,
        new_status: PromotionStatus,
        *,
        superseded_by: str | None = None,
        enforce_matrix: bool = True,
    ) -> Experiment:
        """Update lifecycle status (not part of experiment_hash).

        Enforces the CONTEXT.md transition matrix by default. Callers that
        need to replay an existing lifecycle (e.g. backfill) may pass
        ``enforce_matrix=False`` — this is an audit-only escape hatch, not a
        way to skip the rules in production code paths.

        When transitioning *to* ``SUSPENDED``, the source status is captured
        into ``suspended_from_status`` so ``resume_experiment`` can restore
        it. When transitioning *from* ``SUSPENDED``, the target must equal
        the recorded ``suspended_from_status`` (a.k.a. resume) unless the
        target is terminal (``RETIRED``/``SUPERSEDED``).

        When ``single_strategy_first_live`` is enabled, transitioning any
        experiment to ``LIVE`` or ``LIVE_DRY_RUN`` is blocked while another
        experiment is already in ``LIVE``.
        """
        experiment = self.get(uuid)
        source_status = experiment.promotion_status
        suspended_from = experiment.suspended_from_status

        if enforce_matrix:
            self._enforce_transition(
                experiment,
                source_status,
                new_status,
                suspended_from,
            )
            self._enforce_single_strategy_first_live(experiment, new_status)

        if new_status == PromotionStatus.SUSPENDED:
            captured_source = source_status
        elif source_status == PromotionStatus.SUSPENDED:
            # Resuming clears the snapshot — once back in a non-suspended
            # stage, suspended_from_status is no longer needed.
            captured_source = None
        else:
            captured_source = suspended_from

        updated = Experiment(
            uuid=experiment.uuid,
            label=experiment.label,
            experiment_hash=experiment.experiment_hash,
            snapshot=experiment.snapshot,
            promotion_status=new_status,
            created_at=experiment.created_at,
            superseded_by=superseded_by or experiment.superseded_by,
            legacy_artifacts_path=experiment.legacy_artifacts_path,
            legacy_experiment_id=experiment.legacy_experiment_id,
            suspended_from_status=captured_source,
        )
        self.store.write_metadata(updated)
        self.store.update_index_status(
            uuid,
            promotion_status=new_status,
            superseded_by=superseded_by,
            suspended_from_status=captured_source,
        )
        return updated

    def mark_superseded(self, uuid: str, superseded_by_uuid: str) -> Experiment:
        return self.transition_promotion_status(
            uuid,
            PromotionStatus.SUPERSEDED,
            superseded_by=superseded_by_uuid,
        )

    def suspend_experiment(self, uuid: str) -> Experiment:
        """Transition an Experiment to ``SUSPENDED`` and snapshot the prior
        status. Resume via ``resume_experiment`` restores to that prior status.
        """
        return self.transition_promotion_status(uuid, PromotionStatus.SUSPENDED)

    def resume_experiment(self, uuid: str) -> Experiment:
        """Resume an Experiment from ``SUSPENDED`` to its ``suspended_from_status``.

        Per CONTEXT.md this is the explicit operator confirmation step — never
        an automatic restoration of trading authority. Resume is rejected if
        ``suspended_from_status`` is missing or if the resume target is itself
        suspended/live-of-suspended.
        """
        experiment = self.get(uuid)
        if experiment.promotion_status != PromotionStatus.SUSPENDED:
            raise IllegalPromotionTransitionError(
                experiment.uuid,
                experiment.promotion_status,
                experiment.promotion_status,
                "resume is only permitted from SUSPENDED",
            )
        if experiment.suspended_from_status is None:
            raise IllegalPromotionTransitionError(
                experiment.uuid,
                experiment.promotion_status,
                PromotionStatus.RESEARCH,
                "suspended_from_status is not recorded; cannot resume",
            )
        return self.transition_promotion_status(
            uuid, experiment.suspended_from_status
        )

    def retire_experiment(self, uuid: str) -> Experiment:
        """Operator-confirmed terminal retirement. Re-evaluation requires a
        new Experiment.
        """
        return self.transition_promotion_status(uuid, PromotionStatus.RETIRED)

    # ------------------------------------------------------------------
    # Experiment-scoped kill switches
    # ------------------------------------------------------------------

    def set_kill_switch(
        self,
        uuid: str,
        severity: KillSwitchSeverity,
        reason: str,
        *,
        set_by: str | None = None,
    ) -> tuple[Experiment, KillSwitchState]:
        """Activate the kill switch for one Experiment.

        Per CONTEXT.md:
        - SOFT blocks new orders but leaves ``promotion_status`` unchanged.
        - HARD / CATASTROPHIC also transitions the Experiment to SUSPENDED
          (capturing ``suspended_from_status``).

        Two Experiments sharing the same Strategy template are controlled
        independently — this method only affects the named UUID.
        """
        state = self.kill_switches.set(
            uuid, severity, reason, set_by=set_by
        )
        experiment = self.get(uuid)
        if severity in {KillSwitchSeverity.HARD, KillSwitchSeverity.CATASTROPHIC}:
            if experiment.promotion_status != PromotionStatus.SUSPENDED:
                experiment = self.suspend_experiment(uuid)
        return experiment, state

    def get_kill_switch(self, uuid: str) -> KillSwitchState | None:
        """Read the current kill switch state (active or cleared)."""
        return self.kill_switches.get(uuid)

    def is_soft_killed(self, uuid: str) -> bool:
        state = self.kill_switches.get_active(uuid)
        return state is not None and state.is_soft

    def is_hard_killed(self, uuid: str) -> bool:
        state = self.kill_switches.get_active(uuid)
        return state is not None and state.is_hard

    def clear_kill_switch(
        self,
        uuid: str,
        *,
        cleared_by: str | None = None,
    ) -> KillSwitchState:
        """Clear (acknowledge) the active kill switch.

        Per CONTEXT.md, resume from SUSPENDED requires explicit operator
        confirmation — clearing the kill switch does NOT auto-resume. The
        caller must invoke ``resume_experiment`` separately after the
        postmortem is approved.
        """
        return self.kill_switches.clear(uuid, cleared_by=cleared_by)

    def list_active_kill_switches(self) -> list[KillSwitchState]:
        """Return all experiments whose kill switch is currently active."""
        return self.kill_switches.list_active()

    def _enforce_transition(
        self,
        experiment: Experiment,
        source: PromotionStatus,
        target: PromotionStatus,
        suspended_from: PromotionStatus | None,
    ) -> None:
        if not is_legal_promotion_transition(source, target):
            raise IllegalPromotionTransitionError(
                experiment.uuid, source, target, "transition not in lifecycle matrix"
            )
        # Resume target must match suspended_from_status unless target is
        # terminal (RETIRED/SUPERSEDED) — those are legal audit outcomes.
        if source == PromotionStatus.SUSPENDED and target not in {
            PromotionStatus.RETIRED,
            PromotionStatus.SUPERSEDED,
        }:
            if suspended_from is None or target != suspended_from:
                raise IllegalPromotionTransitionError(
                    experiment.uuid,
                    source,
                    target,
                    f"resume target must match suspended_from_status={suspended_from}",
                )

    def _enforce_single_strategy_first_live(
        self,
        experiment: Experiment,
        target: PromotionStatus,
    ) -> None:
        if not self.single_strategy_first_live:
            return
        if target not in {PromotionStatus.LIVE, PromotionStatus.LIVE_DRY_RUN}:
            return
        # Allow the experiment that is already LIVE to move within live tiers
        # (e.g. LIVE -> SUSPENDED). The guard is about *another* experiment
        # attempting to enter LIVE/LIVE_DRY_RUN while one is already LIVE.
        live_now = self.list_experiments(promotion_status=PromotionStatus.LIVE)
        for other in live_now:
            if other.uuid != experiment.uuid:
                raise IllegalPromotionTransitionError(
                    experiment.uuid,
                    experiment.promotion_status,
                    target,
                    "single_strategy_first_live is enabled and another Experiment "
                    f"({other.uuid}) is already LIVE",
                )

    def close(self) -> None:
        self.store.close()
