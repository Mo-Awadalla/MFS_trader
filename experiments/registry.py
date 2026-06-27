"""Experiment registry — create, query, and lifecycle transitions."""

from __future__ import annotations

import uuid
from pathlib import Path

from experiments.hashing import compute_experiment_hash
from experiments.models import (
    DuplicateExperimentError,
    Experiment,
    ExperimentDraft,
    ExperimentNotFoundError,
    ImmutableExperimentError,
    PromotionStatus,
)
from experiments.storage import ExperimentStore, utc_now_iso


class ExperimentRegistry:
    """Single source of truth for frozen Experiments."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.store = ExperimentStore(root)

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
    ) -> Experiment:
        """Update lifecycle status (not part of experiment_hash)."""
        experiment = self.get(uuid)
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
        )
        self.store.write_metadata(updated)
        self.store.update_index_status(
            uuid,
            promotion_status=new_status,
            superseded_by=superseded_by,
        )
        return updated

    def mark_superseded(self, uuid: str, superseded_by_uuid: str) -> Experiment:
        return self.transition_promotion_status(
            uuid,
            PromotionStatus.SUPERSEDED,
            superseded_by=superseded_by_uuid,
        )

    def close(self) -> None:
        self.store.close()
