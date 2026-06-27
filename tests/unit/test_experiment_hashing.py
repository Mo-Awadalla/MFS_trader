"""Tests for canonical experiment hashing."""

from __future__ import annotations

import copy

from experiments.backfill import (
    build_bb_aapl_1d_default_experiment,
    build_bb_aapl_1d_default_snapshot,
)
from experiments.hashing import (
    HASH_EXCLUDED_TOP_LEVEL,
    canonical_json,
    compute_experiment_hash,
    experiment_from_metadata_dict,
    experiment_to_metadata_dict,
    snapshot_to_hash_dict,
)
from experiments.models import PromotionStatus


class TestExperimentHashing:
    def test_hash_is_deterministic(self):
        snap = build_bb_aapl_1d_default_snapshot()
        assert compute_experiment_hash(snap) == compute_experiment_hash(snap)

    def test_hash_changes_when_parameters_change(self):
        snap = build_bb_aapl_1d_default_snapshot()
        h1 = compute_experiment_hash(snap)
        mutated = copy.deepcopy(snap)
        object.__setattr__(mutated, "parameters", {**snap.parameters, "window": 21})
        h2 = compute_experiment_hash(mutated)
        assert h1 != h2

    def test_hash_changes_when_template_version_changes(self):
        snap = build_bb_aapl_1d_default_snapshot()
        h1 = compute_experiment_hash(snap)
        mutated = copy.deepcopy(snap)
        object.__setattr__(mutated, "strategy_template_version", "bollinger_bands:v2")
        h2 = compute_experiment_hash(mutated)
        assert h1 != h2

    def test_canonical_json_sorted_keys(self):
        payload = snapshot_to_hash_dict(build_bb_aapl_1d_default_snapshot())
        assert canonical_json(payload) == canonical_json(dict(reversed(list(payload.items()))))

    def test_metadata_roundtrip_preserves_hash(self):
        experiment = build_bb_aapl_1d_default_experiment()
        meta = experiment_to_metadata_dict(experiment)
        restored = experiment_from_metadata_dict(meta)
        assert restored.experiment_hash == experiment.experiment_hash
        assert compute_experiment_hash(restored.snapshot) == experiment.experiment_hash

    def test_hash_excludes_lifecycle_fields(self):
        assert "uuid" in HASH_EXCLUDED_TOP_LEVEL
        assert "promotion_status" in HASH_EXCLUDED_TOP_LEVEL
        assert "created_at" in HASH_EXCLUDED_TOP_LEVEL

    def test_promotion_status_not_in_hash_dict(self):
        snap_dict = snapshot_to_hash_dict(build_bb_aapl_1d_default_snapshot())
        assert "promotion_status" not in snap_dict
        assert "uuid" not in snap_dict

    def test_hash_includes_decision_path_fields(self):
        snap_dict = snapshot_to_hash_dict(build_bb_aapl_1d_default_snapshot())
        for key in (
            "strategy",
            "strategy_template_version",
            "parameters",
            "universe",
            "data_version",
            "date_range",
            "execution_mode",
            "cost_model",
            "slippage_model",
            "risk_profile",
            "portfolio_config",
            "paper_thresholds",
            "git_commit",
            "config_version",
            "random_seed",
        ):
            assert key in snap_dict

    def test_experiment_hash_matches_metadata_field(self):
        experiment = build_bb_aapl_1d_default_experiment()
        meta = experiment_to_metadata_dict(experiment)
        assert meta["experiment_hash"] == compute_experiment_hash(experiment.snapshot)
        assert meta["promotion_status"] == PromotionStatus.VALIDATION_FAILED.value
