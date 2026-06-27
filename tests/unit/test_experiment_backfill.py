"""Tests for archived experiment backfill."""

from __future__ import annotations

import json

from experiments.backfill import (
    ARCHIVED_TEMPLATE_VERSION,
    BB_AAPL_1D_DEFAULT_LABEL,
    BB_AAPL_1D_DEFAULT_LEGACY_PATH,
    BB_AAPL_1D_DEFAULT_UUID,
    backfill_bb_aapl_1d_default,
    build_bb_aapl_1d_default_experiment,
)
from experiments.models import PromotionStatus
from experiments.registry import ExperimentRegistry


class TestBBBackfill:
    def test_backfill_registers_archived_experiment(self, tmp_path):
        registry = ExperimentRegistry(tmp_path / "experiments")
        try:
            experiment = backfill_bb_aapl_1d_default(
                registry, repo_root=tmp_path, verify_legacy=False
            )
            assert experiment.uuid == BB_AAPL_1D_DEFAULT_UUID
            assert experiment.label == BB_AAPL_1D_DEFAULT_LABEL
            assert experiment.promotion_status == PromotionStatus.VALIDATION_FAILED
            assert experiment.snapshot.strategy_template_version == ARCHIVED_TEMPLATE_VERSION
            assert experiment.legacy_artifacts_path == BB_AAPL_1D_DEFAULT_LEGACY_PATH

            meta = json.loads(
                (registry.root / experiment.uuid / "metadata.json").read_text(encoding="utf-8")
            )
            assert meta["experiment_hash"] == experiment.experiment_hash
            assert meta["promotion_status"] == "validation_failed"
        finally:
            registry.close()

    def test_backfill_idempotent(self, tmp_path):
        registry = ExperimentRegistry(tmp_path / "experiments")
        try:
            first = backfill_bb_aapl_1d_default(registry, verify_legacy=False)
            second = backfill_bb_aapl_1d_default(registry, verify_legacy=False)
            assert first.uuid == second.uuid
            assert len(registry.list_experiments()) == 1
        finally:
            registry.close()

    def test_backfill_does_not_mutate_legacy_artifacts(self, tmp_path):
        legacy_dir = tmp_path / BB_AAPL_1D_DEFAULT_LEGACY_PATH
        legacy_dir.mkdir(parents=True)
        original = {
            "experiment_id": BB_AAPL_1D_DEFAULT_LABEL,
            "promotion_status": "validation_failed",
            "strategy": "bollinger_bands",
            "data_source": "alpaca",
        }
        experiment_json = legacy_dir / "experiment.json"
        experiment_json.write_text(json.dumps(original, indent=2), encoding="utf-8")
        before = experiment_json.read_text(encoding="utf-8")

        registry = ExperimentRegistry(tmp_path / "experiments")
        try:
            backfill_bb_aapl_1d_default(registry, repo_root=tmp_path, verify_legacy=True)
            assert experiment_json.read_text(encoding="utf-8") == before
        finally:
            registry.close()

    def test_frozen_archived_hash_constant(self):
        """Guard: archived snapshot hash must not drift silently."""
        experiment = build_bb_aapl_1d_default_experiment()
        assert experiment.experiment_hash == (
            "532553bf2a648957b31eb04c48d4ee9b4bd48006052a84aa006012230c074262"
        )
