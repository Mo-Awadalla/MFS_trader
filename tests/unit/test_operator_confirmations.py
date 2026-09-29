"""Tests for operator confirmation commands.

The three commands enforce explicit UUID + hash checks so operators cannot
accidentally promote an experiment they did not intend. Lifecycle transitions
go through ``ExperimentRegistry`` which already enforces the matrix.
"""

from __future__ import annotations

import copy
import json

import pytest

from engine.paper_session import build_paper_operator_report
from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.kill_switch import KillSwitchSeverity
from experiments.models import (
    ExperimentDraft,
    PromotionStatus,
)
from experiments.operator_confirmations import (
    ConfirmationResult,
    ConfirmedExperimentError,
    ExperimentHashMismatchError,
    confirm_paper_ops_pass,
    confirm_resume,
    confirm_retire,
    verify_experiment_hash,
)
from experiments.registry import ExperimentRegistry
from tests.qualification import enter_paper_ops
from tests.unit.test_paper_evidence import write_prerequisite_evidence, write_qualified_evidence


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
    enter_paper_ops(registry, uuid)


def _write_passing_paper_report(registry, exp) -> None:
    ArtifactManager(registry.root).write_json(
        exp.uuid,
        ArtifactKind.PAPER_OPERATOR_REPORT_JSON,
        {
            "experiment_uuid": exp.uuid,
            "experiment_hash": exp.experiment_hash,
            "promotion_status": "paper_ops",
            "passed": True,
            "blockers": [],
        },
    )


def _write_paper_ops_pass_evidence(registry, exp, session_id: str = "pass-session") -> str:
    return write_qualified_evidence(registry, exp, session_id)


class TestVerifyExperimentHash:
    def test_returns_experiment_when_hash_matches(self, registry):
        exp = registry.create(_draft("verify"))
        verified = verify_experiment_hash(registry, exp.uuid, exp.experiment_hash)
        assert verified.uuid == exp.uuid

    def test_rejects_when_hash_does_not_match(self, registry):
        exp = registry.create(_draft("verify-mismatch"))
        with pytest.raises(ExperimentHashMismatchError) as excinfo:
            verify_experiment_hash(registry, exp.uuid, expected_hash="0" * 64)
        assert excinfo.value.uuid == exp.uuid


class TestConfirmPaperOpsPass:
    def test_promotes_to_live_dry_run(self, registry):
        exp = registry.create(_draft("promote"))
        _walk_to_paper_ops(registry, exp.uuid)
        session_id = _write_paper_ops_pass_evidence(registry, exp)
        report = build_paper_operator_report(registry=registry, experiment_uuid=exp.uuid)
        assert report["broker_paper_qualified"] is True
        result = confirm_paper_ops_pass(
            registry,
            exp.uuid,
            exp.experiment_hash,
            paper_session_id=session_id,
            operator="ops",
        )
        assert isinstance(result, ConfirmationResult)
        assert result.transition == "paper_ops -> live_dry_run"
        assert result.experiment.promotion_status == PromotionStatus.LIVE_DRY_RUN
        assert result.operator == "ops"
        assert result.paper_session_id == session_id
        assert result.confirmation_artifact_path is not None
        confirmation = ArtifactManager(registry.root).read_paper_session_report_json(
            exp.uuid,
            session_id,
            "paper_ops_pass_confirmation.json",
        )
        assert confirmation["result"] == "confirmed"

        assert "prerequisites/sim-drills/session.json" in confirmation["evidence_artifact_hashes"]
        assert "prerequisites/broker-smoke/session.json" in confirmation["evidence_artifact_hashes"]

    @pytest.mark.parametrize("missing", ["simulated_drills", "alpaca_paper_smoke"])
    def test_full_pass_without_each_prerequisite_cannot_report_or_confirm(self, registry, missing):
        exp = registry.create(_draft("missing-prerequisite"))
        _walk_to_paper_ops(registry, exp.uuid)
        session_id = write_qualified_evidence(registry, exp, missing_prerequisite=missing)
        # A retained, unbound operator PASS cannot fill the missing prerequisite.
        _write_passing_paper_report(registry, exp)
        artifacts = ArtifactManager(registry.root)
        metadata = artifacts.experiment_dir(exp.uuid) / "metadata.json"
        original = metadata.read_bytes()
        report = build_paper_operator_report(registry=registry, experiment_uuid=exp.uuid)
        assert report["broker_paper_qualified"] is False
        assert report["broker_paper_qualification"][0]["passed"] is False
        with pytest.raises(ConfirmedExperimentError):
            confirm_paper_ops_pass(registry, exp.uuid, exp.experiment_hash, paper_session_id=session_id)
        assert registry.get(exp.uuid).promotion_status == PromotionStatus.PAPER_OPS
        assert metadata.read_bytes() == original
        assert not artifacts.paper_session_report_path(
            exp.uuid, session_id, "paper_ops_pass_confirmation.json",
        ).exists()

    @pytest.mark.parametrize("prerequisite,mutation", [
        ("sim-drills", "experiment_uuid"),
        ("sim-drills", "experiment_hash"),
        ("sim-drills", "environment"),
        ("sim-drills", "missing"),
        ("sim-drills", "truthy"),
        ("sim-drills", "nonfinite"),
        ("sim-drills", "inconsistent"),
        ("broker-smoke", "experiment_uuid"),
        ("broker-smoke", "experiment_hash"),
        ("broker-smoke", "environment"),
        ("broker-smoke", "missing"),
        ("broker-smoke", "truthy"),
        ("broker-smoke", "nonfinite"),
        ("broker-smoke", "inconsistent"),
        ("broker-smoke", "unbound"),
        ("broker-smoke", "report"),
    ])
    def test_invalid_prerequisite_cannot_report_or_confirm(self, registry, prerequisite, mutation):
        exp = registry.create(_draft("invalid-prerequisite"))
        _walk_to_paper_ops(registry, exp.uuid)
        session_id = write_qualified_evidence(registry, exp)
        artifacts = ArtifactManager(registry.root)
        path = artifacts.paper_session_path(exp.uuid, prerequisite)
        session = json.loads(path.read_text())
        simulated = prerequisite == "sim-drills"
        if mutation in {"experiment_uuid", "experiment_hash"}:
            session[mutation] = "wrong"
        elif mutation == "environment":
            if simulated:
                session["broker"] = "alpaca"
            else:
                session["identity"]["broker_environment"] = "sim_broker"
        elif mutation == "missing":
            if simulated:
                del session["details"]["drills"]["timeout"]
            else:
                session["observations"]["drill_events"] = []
        elif mutation == "truthy":
            if simulated:
                session["details"]["drills"]["reject"]["passed"] = "true"
            else:
                session["passed"] = 1
        elif mutation == "nonfinite":
            if simulated:
                session["details"]["drills"]["reconciliation"]["positions"][0]["quantity"] = float("nan")
            else:
                session["observations"]["cycles"][0]["untrusted_extra"] = float("inf")
        elif mutation == "inconsistent":
            if simulated:
                session["details"]["drills"]["timeout"]["status"] = "FILLED"
            else:
                session["window"]["market_sessions"] += 1
        elif mutation == "unbound":
            del session["observations"]
        else:
            report_path = artifacts.paper_session_report_path(
                exp.uuid, prerequisite, "paper_ops_smoke_report.json",
            )
            report_path.write_text(json.dumps({"passed": True}))
        # Deliberately corrupt only temporary synthetic imported artifacts.
        path.write_text(json.dumps(session))
        metadata = artifacts.experiment_dir(exp.uuid) / "metadata.json"
        original = metadata.read_bytes()
        report = build_paper_operator_report(registry=registry, experiment_uuid=exp.uuid)
        assert report["broker_paper_qualified"] is False
        with pytest.raises(ConfirmedExperimentError):
            confirm_paper_ops_pass(registry, exp.uuid, exp.experiment_hash, paper_session_id=session_id)
        assert registry.get(exp.uuid).promotion_status == PromotionStatus.PAPER_OPS
        assert metadata.read_bytes() == original

    @pytest.mark.parametrize("environment,account", [
        ("sim_broker", "fake-paper-account-never-exported"),
        ("alpaca_paper", "another-synthetic-account"),
    ])
    def test_consistent_smoke_from_wrong_environment_or_account_cannot_qualify(
        self, registry, environment, account,
    ):
        exp = registry.create(_draft("unrelated-smoke"))
        _walk_to_paper_ops(registry, exp.uuid)
        session_id = write_qualified_evidence(
            registry, exp, missing_prerequisite="alpaca_paper_smoke",
        )
        # This is internally consistent observed smoke, not merely a bad digest.
        write_prerequisite_evidence(
            registry, exp, missing="simulated_drills",
            smoke_environment=environment, smoke_account=account,
        )
        metadata = ArtifactManager(registry.root).experiment_dir(exp.uuid) / "metadata.json"
        original = metadata.read_bytes()
        report = build_paper_operator_report(registry=registry, experiment_uuid=exp.uuid)
        assert report["broker_paper_qualified"] is False
        with pytest.raises(ConfirmedExperimentError):
            confirm_paper_ops_pass(registry, exp.uuid, exp.experiment_hash, paper_session_id=session_id)
        assert metadata.read_bytes() == original
        assert registry.get(exp.uuid).promotion_status == PromotionStatus.PAPER_OPS

    def test_rejects_when_not_in_paper_ops(self, registry):
        exp = registry.create(_draft("not-po"))
        registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_RUNNING)
        with pytest.raises(ConfirmedExperimentError, match="PAPER_OPS"):
            confirm_paper_ops_pass(
                registry,
                exp.uuid,
                exp.experiment_hash,
                paper_session_id="pass-session",
            )

    def test_rejects_when_hash_wrong(self, registry):
        exp = registry.create(_draft("wrong-hash"))
        _walk_to_paper_ops(registry, exp.uuid)
        _write_paper_ops_pass_evidence(registry, exp)
        with pytest.raises(ExperimentHashMismatchError):
            confirm_paper_ops_pass(
                registry,
                exp.uuid,
                expected_hash="x" * 64,
                paper_session_id="pass-session",
            )

    def test_rejects_without_paper_ops_pass_session(self, registry):
        exp = registry.create(_draft("missing-paper-report"))
        _walk_to_paper_ops(registry, exp.uuid)
        with pytest.raises(ConfirmedExperimentError, match="paper_ops_pass session"):
            confirm_paper_ops_pass(
                registry,
                exp.uuid,
                exp.experiment_hash,
                paper_session_id="missing-session",
            )

    def test_rejects_smoke_evidence_as_paper_ops_pass(self, registry):
        exp = registry.create(_draft("smoke-is-not-pass"))
        _walk_to_paper_ops(registry, exp.uuid)
        ArtifactManager(registry.root).write_paper_session_json(
            exp.uuid,
            "smoke-session",
            {
                "experiment_uuid": exp.uuid,
                "experiment_hash": exp.experiment_hash,
                "session_id": "smoke-session",
                "session_kind": "paper_ops_smoke",
                "session_type": "alpaca_paper_smoke",
                "passed": True,
            },
        )
        with pytest.raises(ConfirmedExperimentError, match="session_kind=paper_ops_pass"):
            confirm_paper_ops_pass(
                registry,
                exp.uuid,
                exp.experiment_hash,
                paper_session_id="smoke-session",
            )


class TestConfirmResume:
    def test_resumes_to_suspended_from_status(self, registry):
        exp = registry.create(_draft("resume"))
        _walk_to_paper_ops(registry, exp.uuid)
        registry.suspend_experiment(exp.uuid)
        result = confirm_resume(
            registry, exp.uuid, exp.experiment_hash, operator="ops"
        )
        assert result.experiment.promotion_status == PromotionStatus.PAPER_OPS
        assert result.transition == "suspended -> paper_ops"
        # Resume after suspension clears the captured suspended_from_status.
        assert result.experiment.suspended_from_status is None

    def test_rejects_when_not_suspended(self, registry):
        exp = registry.create(_draft("not-susp"))
        _walk_to_paper_ops(registry, exp.uuid)
        with pytest.raises(ConfirmedExperimentError, match="SUSPENDED"):
            confirm_resume(registry, exp.uuid, exp.experiment_hash)

    def test_clears_active_kill_switch_on_resume(self, registry):
        exp = registry.create(_draft("with-ks"))
        _walk_to_paper_ops(registry, exp.uuid)
        registry.set_kill_switch(
            exp.uuid, KillSwitchSeverity.HARD, "postmortem required"
        )
        assert registry.is_hard_killed(exp.uuid)
        result = confirm_resume(registry, exp.uuid, exp.experiment_hash)
        assert result.cleared_kill_switch is True
        assert registry.is_hard_killed(exp.uuid) is False


class TestConfirmRetire:
    def test_retires_from_non_terminal(self, registry):
        exp = registry.create(_draft("retire"))
        _walk_to_paper_ops(registry, exp.uuid)
        result = confirm_retire(registry, exp.uuid, exp.experiment_hash)
        assert result.experiment.promotion_status == PromotionStatus.RETIRED
        assert result.transition.endswith("-> retired")

    def test_rejects_when_already_retired(self, registry):
        exp = registry.create(_draft("already-retired"))
        _walk_to_paper_ops(registry, exp.uuid)
        confirm_retire(registry, exp.uuid, exp.experiment_hash)
        with pytest.raises(ConfirmedExperimentError, match="non-terminal"):
            confirm_retire(registry, exp.uuid, exp.experiment_hash)

    def test_rejects_when_hash_wrong(self, registry):
        exp = registry.create(_draft("bad-hash"))
        _walk_to_paper_ops(registry, exp.uuid)
        with pytest.raises(ExperimentHashMismatchError):
            confirm_retire(registry, exp.uuid, expected_hash="x" * 64)


class TestConfirmationResultSerializes:
    def test_to_dict_is_serializable(self, registry):
        exp = registry.create(_draft("serialize"))
        _walk_to_paper_ops(registry, exp.uuid)
        session_id = _write_paper_ops_pass_evidence(registry, exp)
        result = confirm_paper_ops_pass(
            registry,
            exp.uuid,
            exp.experiment_hash,
            paper_session_id=session_id,
        )
        payload = result.to_dict()
        assert payload["transition"] == "paper_ops -> live_dry_run"
        assert payload["experiment_hash"] == exp.experiment_hash
        assert payload["promotion_status"] == "live_dry_run"
        assert payload["paper_session_id"] == session_id
