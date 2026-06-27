"""Tests for ExperimentRegistry — create, query, duplicates, lifecycle."""

from __future__ import annotations

import copy

import pytest

from experiments.backfill import (
    build_bb_aapl_1d_default_experiment,
    build_bb_aapl_1d_default_snapshot,
)
from experiments.hashing import compute_experiment_hash
from experiments.models import (
    DuplicateExperimentError,
    Experiment,
    ExperimentDraft,
    ImmutableExperimentError,
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


class TestExperimentRegistry:
    def test_create_writes_metadata_and_index(self, registry):
        experiment = registry.create(_draft())
        meta_path = registry.root / experiment.uuid / "metadata.json"
        assert meta_path.exists()
        assert registry.get(experiment.uuid).label == "test-bb"

    def test_duplicate_hash_rejected(self, registry):
        registry.create(_draft("first"))
        with pytest.raises(DuplicateExperimentError):
            registry.create(_draft("second-same-snapshot"))

    def test_different_snapshots_get_different_hashes(self, registry):
        a = registry.create(_draft("a"))
        snap = build_bb_aapl_1d_default_snapshot()
        object.__setattr__(snap, "random_seed", 99)
        b = registry.create(ExperimentDraft(label="b", snapshot=snap))
        assert a.experiment_hash != b.experiment_hash

    def test_import_existing_is_idempotent(self, registry):
        archived = build_bb_aapl_1d_default_experiment()
        first = registry.import_existing(archived)
        second = registry.import_existing(archived)
        assert first.uuid == second.uuid
        assert len(registry.list_experiments()) == 1

    def test_uuid_collision_with_different_hash_raises(self, registry):
        archived = build_bb_aapl_1d_default_experiment()
        registry.import_existing(archived)
        snap = build_bb_aapl_1d_default_snapshot()
        object.__setattr__(snap, "random_seed", 7)
        bad = Experiment(
            uuid=archived.uuid,
            label=archived.label,
            experiment_hash=compute_experiment_hash(snap),
            snapshot=snap,
            promotion_status=PromotionStatus.RESEARCH,
            created_at=archived.created_at,
        )
        with pytest.raises(ImmutableExperimentError):
            registry.import_existing(bad)

    def test_list_by_strategy(self, registry):
        registry.import_existing(build_bb_aapl_1d_default_experiment())
        results = registry.list_experiments(strategy="bollinger_bands")
        assert len(results) == 1

    def test_list_validation_failures(self, registry):
        registry.import_existing(build_bb_aapl_1d_default_experiment())
        failed = registry.list_experiments(promotion_status=PromotionStatus.VALIDATION_FAILED)
        assert len(failed) == 1
        passed = registry.list_experiments(promotion_status=PromotionStatus.VALIDATION_PASSED)
        assert len(passed) == 0

    def test_list_by_template_version(self, registry):
        registry.import_existing(build_bb_aapl_1d_default_experiment())
        v1 = registry.list_experiments(strategy_template_version="bollinger_bands:v1")
        v2 = registry.list_experiments(strategy_template_version="bollinger_bands:v2")
        assert len(v1) == 1
        assert len(v2) == 0

    def test_list_by_data_source(self, registry):
        registry.import_existing(build_bb_aapl_1d_default_experiment())
        alpaca = registry.list_experiments(data_source="alpaca")
        yahoo = registry.list_experiments(data_source="yahoo")
        assert len(alpaca) == 1
        assert len(yahoo) == 0

    def test_promotion_status_transition(self, registry):
        exp = registry.create(_draft())
        registry.transition_promotion_status(
            exp.uuid, PromotionStatus.VALIDATION_RUNNING
        )
        updated = registry.transition_promotion_status(
            exp.uuid, PromotionStatus.VALIDATION_FAILED
        )
        assert updated.promotion_status == PromotionStatus.VALIDATION_FAILED
        assert registry.get(exp.uuid).promotion_status == PromotionStatus.VALIDATION_FAILED

    def test_illegal_promotion_transition_rejected(self, registry):
        from experiments.models import IllegalPromotionTransitionError

        exp = registry.create(_draft())
        with pytest.raises(IllegalPromotionTransitionError):
            registry.transition_promotion_status(
                exp.uuid, PromotionStatus.LIVE  # cannot shortcut research -> live
            )

    def test_suspended_from_status_preserved_on_resume(self, registry):
        exp = registry.create(_draft())
        registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_RUNNING)
        registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_PASSED)
        registry.transition_promotion_status(exp.uuid, PromotionStatus.PAPER_OPS)
        suspended = registry.suspend_experiment(exp.uuid)
        assert suspended.promotion_status == PromotionStatus.SUSPENDED
        assert suspended.suspended_from_status == PromotionStatus.PAPER_OPS
        resumed = registry.resume_experiment(exp.uuid)
        assert resumed.promotion_status == PromotionStatus.PAPER_OPS

    def test_resume_rejected_when_target_does_not_match_suspended_from(self, registry):
        from experiments.models import IllegalPromotionTransitionError

        exp = registry.create(_draft())
        registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_RUNNING)
        registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_PASSED)
        registry.transition_promotion_status(exp.uuid, PromotionStatus.PAPER_OPS)
        registry.suspend_experiment(exp.uuid)
        with pytest.raises(IllegalPromotionTransitionError):
            # Cannot resume directly into LIVE_DRY_RUN — must resume into PAPER_OPS.
            registry.transition_promotion_status(
                exp.uuid, PromotionStatus.LIVE_DRY_RUN
            )

    def test_single_strategy_first_live_blocks_seconds_live_entry(self, registry):
        from experiments.models import IllegalPromotionTransitionError

        first = registry.create(_draft("first", window=15))
        second = registry.create(_draft("second-different", window=20))
        for exp in (first, second):
            registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_RUNNING)
            registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_PASSED)
            registry.transition_promotion_status(exp.uuid, PromotionStatus.PAPER_OPS)
            registry.transition_promotion_status(exp.uuid, PromotionStatus.LIVE_DRY_RUN)
            registry.transition_promotion_status(exp.uuid, PromotionStatus.LIVE_CANDIDATE)
        registry.transition_promotion_status(first.uuid, PromotionStatus.LIVE)
        with pytest.raises(IllegalPromotionTransitionError, match="single_strategy_first_live"):
            registry.transition_promotion_status(second.uuid, PromotionStatus.LIVE)

    def test_terminal_status_rejects_further_transition(self, registry):
        from experiments.models import IllegalPromotionTransitionError

        exp = registry.create(_draft())
        registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_RUNNING)
        registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_FAILED)
        with pytest.raises(IllegalPromotionTransitionError):
            registry.transition_promotion_status(
                exp.uuid, PromotionStatus.VALIDATION_PASSED
            )

    def test_get_by_label_and_legacy_id(self, registry):
        archived = registry.import_existing(build_bb_aapl_1d_default_experiment())
        assert registry.get_by_label(archived.label) is not None
        assert registry.get_by_legacy_id("BB-AAPL-1D-Default") is not None

    def test_snapshot_immutable_after_create(self, registry):
        exp = registry.create(_draft())
        original_hash = exp.experiment_hash
        reloaded = registry.get(exp.uuid)
        assert reloaded.experiment_hash == original_hash
        assert reloaded.snapshot.parameters == exp.snapshot.parameters
