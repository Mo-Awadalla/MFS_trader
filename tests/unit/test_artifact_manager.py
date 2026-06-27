"""Tests for ArtifactManager — canonical Experiment evidence persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from experiments.artifacts import (
    ArtifactExistsError,
    ArtifactFormatError,
    ArtifactImmutableError,
    ArtifactKind,
    ArtifactManager,
    InvalidExperimentUUIDError,
    UnknownArtifactKindError,
)


class TestArtifactManager:
    def test_returns_canonical_paths_without_creating_directories(self, tmp_path: Path) -> None:
        manager = ArtifactManager(tmp_path / "experiments")
        exp_uuid = "fd42a55c-abc4-59f3-abd3-c70c0380482b"

        assert manager.experiment_dir(exp_uuid) == tmp_path / "experiments" / exp_uuid
        assert (
            manager.path(exp_uuid, ArtifactKind.VALIDATION_REPORT_JSON)
            == tmp_path / "experiments" / exp_uuid / "validation" / "report.json"
        )
        assert not (tmp_path / "experiments").exists()

    def test_accepts_exact_kind_strings_and_rejects_unknown_kinds(self, tmp_path: Path) -> None:
        manager = ArtifactManager(tmp_path / "experiments")
        exp_uuid = "fd42a55c-abc4-59f3-abd3-c70c0380482b"

        assert manager.path(exp_uuid, "run_log").name == "run.log"
        with pytest.raises(UnknownArtifactKindError):
            manager.path(exp_uuid, "validation-report-json")

    def test_writes_and_reads_json_artifacts(self, tmp_path: Path) -> None:
        manager = ArtifactManager(tmp_path / "experiments")
        exp_uuid = "fd42a55c-abc4-59f3-abd3-c70c0380482b"

        path = manager.write_json(
            exp_uuid,
            ArtifactKind.VALIDATION_REPORT_JSON,
            {"status": "failed", "metrics": {"sharpe": -0.1}},
        )

        assert path == tmp_path / "experiments" / exp_uuid / "validation" / "report.json"
        assert manager.exists(exp_uuid, ArtifactKind.VALIDATION_REPORT_JSON)
        assert manager.read_json(exp_uuid, ArtifactKind.VALIDATION_REPORT_JSON) == {
            "metrics": {"sharpe": -0.1},
            "status": "failed",
        }

    def test_writes_text_artifacts(self, tmp_path: Path) -> None:
        manager = ArtifactManager(tmp_path / "experiments")
        exp_uuid = "fd42a55c-abc4-59f3-abd3-c70c0380482b"

        path = manager.write_text(
            exp_uuid,
            ArtifactKind.VALIDATION_VERDICT_TXT,
            "FAIL\n",
        )

        assert path == tmp_path / "experiments" / exp_uuid / "validation" / "verdict.txt"
        assert path.read_text(encoding="utf-8") == "FAIL\n"

    def test_enforces_format_by_kind(self, tmp_path: Path) -> None:
        manager = ArtifactManager(tmp_path / "experiments")
        exp_uuid = "fd42a55c-abc4-59f3-abd3-c70c0380482b"

        with pytest.raises(ArtifactFormatError):
            manager.write_text(exp_uuid, ArtifactKind.VALIDATION_REPORT_JSON, "{}")
        with pytest.raises(ArtifactFormatError):
            manager.write_json(exp_uuid, ArtifactKind.RUN_LOG, {"message": "started"})
        with pytest.raises(ArtifactFormatError):
            manager.read_json(exp_uuid, ArtifactKind.RUN_LOG)

    def test_immutable_evidence_cannot_be_overwritten(self, tmp_path: Path) -> None:
        manager = ArtifactManager(tmp_path / "experiments")
        exp_uuid = "fd42a55c-abc4-59f3-abd3-c70c0380482b"

        manager.write_json(exp_uuid, ArtifactKind.REPLAY_ATTRIBUTION_JSON, {"run": 1})

        with pytest.raises(ArtifactImmutableError):
            manager.write_json(
                exp_uuid,
                ArtifactKind.REPLAY_ATTRIBUTION_JSON,
                {"run": 2},
                overwrite=True,
            )
        assert manager.read_json(exp_uuid, ArtifactKind.REPLAY_ATTRIBUTION_JSON) == {"run": 1}

    def test_metadata_json_may_be_overwritten_explicitly(self, tmp_path: Path) -> None:
        manager = ArtifactManager(tmp_path / "experiments")
        exp_uuid = "fd42a55c-abc4-59f3-abd3-c70c0380482b"

        manager.write_json(exp_uuid, ArtifactKind.METADATA_JSON, {"status": "research"})
        manager.write_json(
            exp_uuid,
            ArtifactKind.METADATA_JSON,
            {"status": "validation_failed"},
            overwrite=True,
        )

        assert manager.read_json(exp_uuid, ArtifactKind.METADATA_JSON) == {
            "status": "validation_failed"
        }

    def test_metadata_json_requires_explicit_overwrite(self, tmp_path: Path) -> None:
        manager = ArtifactManager(tmp_path / "experiments")
        exp_uuid = "fd42a55c-abc4-59f3-abd3-c70c0380482b"

        manager.write_json(exp_uuid, ArtifactKind.METADATA_JSON, {"status": "research"})

        with pytest.raises(ArtifactExistsError):
            manager.write_json(exp_uuid, ArtifactKind.METADATA_JSON, {"status": "paper_ops"})

    def test_rejects_non_canonical_experiment_uuid(self, tmp_path: Path) -> None:
        manager = ArtifactManager(tmp_path / "experiments")

        with pytest.raises(InvalidExperimentUUIDError):
            manager.path("../outside", ArtifactKind.METADATA_JSON)

        with pytest.raises(InvalidExperimentUUIDError):
            manager.path(
                "FD42A55C-ABC4-59F3-ABD3-C70C0380482B",
                ArtifactKind.METADATA_JSON,
            )
