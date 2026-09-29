"""Historical status alone must never admit a current broker-paper action."""
from __future__ import annotations

import pandas as pd
import pytest

from config.loader import load_config
from engine import cli
from engine.paper_run import PaperRunConfig, PaperRunLoop
from engine.paper_session import build_paper_operator_report
from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.corrected_evaluations import CorrectedQualificationError
from experiments.models import ExperimentDraft, PromotionStatus
from experiments.registry import ExperimentRegistry


@pytest.fixture
def historical(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    experiment = registry.create(ExperimentDraft(
        label="temporary historical admission fixture",
        snapshot=build_bb_aapl_1d_default_snapshot(),
        promotion_status=PromotionStatus.VALIDATION_PASSED,
    ))
    ArtifactManager(registry.root).write_json(
        experiment.uuid, ArtifactKind.VALIDATION_REPORT_JSON, {"passed": True},
    )
    yield registry, experiment
    registry.close()


@pytest.mark.parametrize("enforce_matrix", [True, False])
def test_historical_pass_cannot_transition_to_current_paper(historical, enforce_matrix):
    registry, experiment = historical
    before = (registry.root / experiment.uuid / "metadata.json").read_bytes()
    with pytest.raises(CorrectedQualificationError):
        registry.transition_promotion_status(
            experiment.uuid, PromotionStatus.PAPER_OPS, enforce_matrix=enforce_matrix,
        )
    assert (registry.root / experiment.uuid / "metadata.json").read_bytes() == before
    assert registry.get(experiment.uuid).promotion_status == PromotionStatus.VALIDATION_PASSED


def test_bypass_matrix_cannot_skip_current_evidence(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        experiment = registry.create(ExperimentDraft(label="research", snapshot=build_bb_aapl_1d_default_snapshot()))
        with pytest.raises(CorrectedQualificationError):
            registry.transition_promotion_status(experiment.uuid, PromotionStatus.PAPER_OPS, enforce_matrix=False)
        assert registry.get(experiment.uuid).promotion_status == PromotionStatus.RESEARCH
    finally:
        registry.close()


def _historical_paper(registry):
    # Importing recorded lifecycle history remains possible. It conveys no
    # current execution authority, which is what the following tests exercise.
    return registry.create(ExperimentDraft(
        label="historical paper", snapshot=build_bb_aapl_1d_default_snapshot(),
        promotion_status=PromotionStatus.PAPER_OPS,
    ))


def test_historical_paper_resume_is_not_current_admission(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        experiment = _historical_paper(registry)
        registry.suspend_experiment(experiment.uuid)
        with pytest.raises(CorrectedQualificationError):
            registry.resume_experiment(experiment.uuid)
        assert registry.get(experiment.uuid).promotion_status == PromotionStatus.SUSPENDED
    finally:
        registry.close()


def test_loop_refuses_historical_paper_before_broker_or_ledger(tmp_path):
    class Broker:
        name = "alpaca"
        is_connected = False
        connections = 0

        def connect(self):
            self.connections += 1
            raise AssertionError("historical evidence reached broker")

    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        experiment = _historical_paper(registry)
        broker = Broker()
        db = tmp_path / "must-not-exist.sqlite"
        loop = PaperRunLoop(
            config=load_config("builtin:paper_shakedown", load_env=False), broker=broker,
            strategy_fn=lambda frame, params: {}, strategy_name="test",
            run_config=PaperRunConfig(
                experiment_uuid=experiment.uuid, experiment_hash=experiment.experiment_hash,
                experiment_root=registry.root, session_id="historical-refusal", max_cycles=1,
            ),
        )
        state = loop.run(pd.DataFrame(), db)
        assert state.halted and state.halt_reason.startswith("requiring_re_evaluation:")
        assert broker.connections == 0
        assert not db.exists()
    finally:
        registry.close()


def test_cli_refuses_historical_paper_before_credentials(tmp_path, monkeypatch):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        experiment = _historical_paper(registry)

        def forbidden(*args, **kwargs):
            raise AssertionError("historical evidence reached credentials or broker")

        monkeypatch.setattr(cli, "get_broker_creds", forbidden)
        monkeypatch.setattr(cli, "AlpacaAdapter", forbidden)
        rc = cli.main([
            "--config", "builtin:paper_shakedown", "paper-run",
            "--experiment-root", str(registry.root), "--experiment-uuid", experiment.uuid,
            "--experiment-hash", experiment.experiment_hash, "--broker", "alpaca_paper",
            "--confirm-paper-broker", "--session-id", "historical-refusal",
            "--out-dir", str(tmp_path / "output"), "--max-cycles", "1",
        ])
        assert rc == 1
        assert not (tmp_path / "output").exists()
    finally:
        registry.close()


def test_operator_report_separates_historical_status_from_qualification(historical):
    registry, experiment = historical
    report = build_paper_operator_report(registry=registry, experiment_uuid=experiment.uuid)
    assert report["promotion_status"] == "validation_passed"
    assert report["numerical_qualification"]["qualified"] is False
    assert report["numerical_qualification"]["status"] == "requiring_re_evaluation"
    assert report["broker_paper_qualified"] is False
    assert report["promotion_unlocked"] is False
