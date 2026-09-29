"""Corrected evidence safety contracts, with real SQLite and a real gauntlet."""
from __future__ import annotations

import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from experiments.artifacts import ArtifactImmutableError, ArtifactKind, ArtifactManager
from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.corrected_evaluations import (
    EvaluationInputs,
    abandon_corrected_evaluation,
    check_current_qualification,
    evaluate_corrected,
    run_current_evaluation,
)
from experiments.models import ExperimentDraft, PromotionStatus
from experiments.registry import ExperimentRegistry
from validation.search import declared_search
from validation.wfa.engine import WFAConfig, WFATier


def _train(data, **kwargs):
    return {"p": 0}


def _test(data, parameters):
    returns = data["returns"]
    downside = returns[returns < 0]
    return {
        "returns": returns, "sharpe": float(returns.mean() / returns.std() * np.sqrt(252)),
        "sortino": float(returns.mean() / downside.std() * np.sqrt(252)),
        "total_return": float((1 + returns).prod() - 1), "max_drawdown": -0.05,
    }


@pytest.fixture
def environment(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    snapshot = replace(build_bb_aapl_1d_default_snapshot(), parameters={"p": 0},
                       cost_model={}, slippage_model={})
    experiment = registry.create(ExperimentDraft(
        label="synthetic correction", snapshot=snapshot,
        promotion_status=PromotionStatus.VALIDATION_PASSED,
    ))
    yield registry, experiment, ArtifactManager(registry.root)
    registry.close()


def _inputs(tmp_path, experiment):
    rng = np.random.default_rng(1729)
    index = pd.date_range("2020-01-01", periods=1000, freq="D")
    matrix = rng.normal(0.002, 0.005, (1000, 10))
    trials = [{"p": p} for p in range(10)]
    returns = [pd.Series(matrix[:, p], index=index) for p in range(10)]
    data = pd.DataFrame({"returns": returns[0]})
    path = tmp_path / "synthetic-source.csv"
    data.to_csv(path)
    sweep = pd.DataFrame({"p": range(10), "sharpe": [series.mean() / series.std() * np.sqrt(252) for series in returns]})
    return EvaluationInputs(
        data=data, train_fn=_train, test_fn=_test, sweep_results=sweep,
        param_columns=["p"], search=declared_search(
            trials, returns, experiment.snapshot.parameters,
            search_scope="All ten synthetic trials, p=0..9; no excluded trials or prior search",
        ), input_files={"synthetic CSV, generated with seed 1729": path},
        caller_config={"cost_model": {}, "slippage_model": {}, "generator_seed": 1729},
        wfa_config=WFAConfig(WFATier.PRIMARY, "3m", "2m", "2m"),
        periods_per_year=252, mc_num_paths=100, mc_block_size=20,
    )


def _historical(artifacts, experiment):
    artifacts.write_json(experiment.uuid, ArtifactKind.VALIDATION_REPORT_JSON, {"passed": True, "old": "untouched"})
    artifacts.write_text(experiment.uuid, ArtifactKind.VALIDATION_VERDICT_TXT, "PASS\n")
    return {kind: artifacts.path(experiment.uuid, kind).read_bytes() for kind in (
        ArtifactKind.METADATA_JSON, ArtifactKind.VALIDATION_REPORT_JSON, ArtifactKind.VALIDATION_VERDICT_TXT,
    )}


def test_real_corrected_gauntlet_preserves_original_and_qualifies(environment, tmp_path):
    registry, experiment, artifacts = environment
    original = _historical(artifacts, experiment)
    assert not check_current_qualification(registry, experiment.uuid, experiment.experiment_hash).qualified
    inputs = _inputs(tmp_path, experiment)
    eid = str(uuid.uuid4())
    path = evaluate_corrected(registry, experiment.uuid, experiment.experiment_hash, evaluation_id=eid, inputs=inputs)
    result = json.loads(path.read_text())
    assert result["verdict"] == "PASS", result
    assert result["report"]["dsr"]["m_raw"] == 10
    assert result["report"]["monte_carlo"]["num_paths"] == 100
    assert check_current_qualification(registry, experiment.uuid, experiment.experiment_hash).qualified
    request = json.loads(artifacts.corrected_evaluation_path(experiment.uuid, eid, "request").read_text())
    assert request["original"]["report_sha256"] == hashlib.sha256(original[ArtifactKind.VALIDATION_REPORT_JSON]).hexdigest()
    assert request["prepared"]["search"]["trials"] == [{"p": p} for p in range(10)]
    assert request["prepared"]["search"]["selected_parameters"] == {"p": 0}
    for kind, content in original.items():
        assert artifacts.path(experiment.uuid, kind).read_bytes() == content
    assert registry.get(experiment.uuid).promotion_status == PromotionStatus.VALIDATION_PASSED
    for retry_id in (eid, str(uuid.uuid4())):
        with pytest.raises(ArtifactImmutableError):
            evaluate_corrected(registry, experiment.uuid, experiment.experiment_hash, evaluation_id=retry_id, inputs=inputs)
    assert check_current_qualification(registry, experiment.uuid, experiment.experiment_hash).qualified


def test_current_canonical_envelope_qualifies_without_historical_correction(environment, tmp_path):
    registry, experiment, artifacts = environment
    payload = run_current_evaluation(experiment, _inputs(tmp_path, experiment))
    artifacts.write_json(experiment.uuid, ArtifactKind.VALIDATION_REPORT_JSON, payload)
    assert check_current_qualification(registry, experiment.uuid, experiment.experiment_hash).qualified
    assert not (artifacts.experiment_dir(experiment.uuid) / "corrected_evaluations").exists()


@pytest.mark.parametrize("damage", [
    "missing_provenance", "bad_mc", "bad_raw_dsr", "bad_sortino", "missing_search",
    "bad_source_commit", "bad_input_hash", "bad_callback_hash", "nonfinite_mc",
])
def test_forged_overall_pass_never_bypasses_subgates(environment, tmp_path, damage):
    registry, experiment, artifacts = environment
    payload = run_current_evaluation(experiment, _inputs(tmp_path, experiment))
    assert payload["gauntlet"]["passed"] is True
    if damage == "missing_provenance":
        del payload["evaluation_provenance"]
    elif damage == "bad_mc":
        payload["gauntlet"]["monte_carlo"]["pct_5_max_dd"] = -0.5
    elif damage == "bad_raw_dsr":
        payload["gauntlet"]["dsr"]["pvalue_m_raw"] = 0.1
    elif damage == "bad_sortino":
        payload["gauntlet"]["wfa"]["oos_sortino"] = 0.9
    elif damage == "bad_source_commit":
        payload["evaluation_provenance"]["corrected_source"]["commit"] = "z" * 40
    elif damage == "bad_input_hash":
        payload["evaluation_provenance"]["prepared"]["inputs"][0]["sha256"] = "z" * 64
    elif damage == "bad_callback_hash":
        payload["evaluation_provenance"]["prepared"]["train"]["source_sha256"] = "0" * 64
    elif damage == "nonfinite_mc":
        payload["gauntlet"]["monte_carlo"]["pct_5_cagr"] = float("nan")
    else:
        del payload["gauntlet"]["declared_search"]
    artifacts.write_json(experiment.uuid, ArtifactKind.VALIDATION_REPORT_JSON, payload)
    assert not check_current_qualification(registry, experiment.uuid, experiment.experiment_hash).qualified


def test_missing_provenance_records_unavailable_not_historical_pass(environment):
    registry, experiment, artifacts = environment
    original = _historical(artifacts, experiment)
    path = evaluate_corrected(registry, experiment.uuid, experiment.experiment_hash, evaluation_id=str(uuid.uuid4()))
    result = json.loads(path.read_text())
    assert result["available"] is False and result["verdict"] == "requiring_re_evaluation"
    assert result["report"] is None
    qualification = check_current_qualification(registry, experiment.uuid, experiment.experiment_hash)
    assert not qualification.qualified and qualification.status == "requiring_re_evaluation"
    assert artifacts.path(experiment.uuid, ArtifactKind.VALIDATION_REPORT_JSON).read_bytes() == original[ArtifactKind.VALIDATION_REPORT_JSON]


@pytest.mark.parametrize("damage", ["selected", "cost", "truncated", "input"])
def test_incomplete_or_different_prerequisites_cannot_run_as_frozen(environment, tmp_path, damage):
    registry, experiment, artifacts = environment
    _historical(artifacts, experiment)
    inputs = _inputs(tmp_path, experiment)
    if damage == "selected":
        inputs = replace(inputs, search=replace(inputs.search, selected_parameters={"p": 1}))
    elif damage == "cost":
        inputs = replace(inputs, caller_config={"cost_model": {"commission": 0}, "slippage_model": {}})
    elif damage == "truncated":
        inputs = replace(inputs, sweep_results=inputs.sweep_results.iloc[:2])
    else:
        inputs = replace(inputs, input_files={"missing": tmp_path / "absent.csv"})
    path = evaluate_corrected(registry, experiment.uuid, experiment.experiment_hash,
                              evaluation_id=str(uuid.uuid4()), inputs=inputs)
    result = json.loads(path.read_text())
    assert result["verdict"] == "requiring_re_evaluation" and result["report"] is None


def test_hash_mismatch_never_writes_evidence(environment):
    registry, experiment, artifacts = environment
    with pytest.raises(ValueError, match="hash"):
        evaluate_corrected(registry, experiment.uuid, "0" * 64, evaluation_id=str(uuid.uuid4()))
    assert not (artifacts.experiment_dir(experiment.uuid) / "corrected_evaluations").exists()


def test_concurrent_request_claims_have_exactly_one_winner(environment):
    _, experiment, artifacts = environment
    def claim(eid):
        try:
            artifacts.claim_corrected_evaluation(experiment.uuid, eid, "a" * 64)
            return eid
        except ArtifactImmutableError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, [str(uuid.uuid4()) for _ in range(8)]))
    winners = [value for value in results if value is not None]
    assert len(winners) == 1
    path = artifacts.corrected_evaluation_path(experiment.uuid, winners[0], "request")
    claim_record = json.loads((path.parent.parent / "requests" / ("a" * 64 + ".json")).read_text())
    assert claim_record["evaluation_id"] == winners[0]
    assert [folder.name for folder in path.parent.parent.iterdir() if folder.name != "requests"] == winners


def test_concurrent_result_publication_never_overwrites(environment):
    _, experiment, artifacts = environment
    eid = str(uuid.uuid4())
    def publish(value):
        try:
            artifacts.write_corrected_evaluation_json(experiment.uuid, eid, "result", {"value": value})
            return value
        except ArtifactImmutableError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(publish, range(8)))
    winners = [value for value in results if value is not None]
    assert len(winners) == 1
    assert json.loads(artifacts.corrected_evaluation_path(experiment.uuid, eid, "result").read_text()) == {"value": winners[0]}


def test_interrupted_execution_blocks_retries_and_qualification(environment, monkeypatch):
    registry, experiment, artifacts = environment
    _historical(artifacts, experiment)
    eid = str(uuid.uuid4())
    real_write = ArtifactManager.write_corrected_evaluation_json
    def interrupted(self, experiment_uuid, evaluation_id, document, payload):
        if document == "result":
            raise KeyboardInterrupt("synthetic interruption")
        return real_write(self, experiment_uuid, evaluation_id, document, payload)
    with monkeypatch.context() as context:
        context.setattr(ArtifactManager, "write_corrected_evaluation_json", interrupted)
        with pytest.raises(KeyboardInterrupt):
            evaluate_corrected(registry, experiment.uuid, experiment.experiment_hash, evaluation_id=eid)
    assert not artifacts.corrected_evaluation_path(experiment.uuid, eid, "result").exists()
    assert not check_current_qualification(registry, experiment.uuid, experiment.experiment_hash).qualified
    with pytest.raises(ArtifactImmutableError):
        evaluate_corrected(registry, experiment.uuid, experiment.experiment_hash, evaluation_id=eid)


def test_interrupted_atomic_write_exposes_no_partial_result(environment, monkeypatch):
    import experiments.artifacts as module

    _, experiment, artifacts = environment
    eid = str(uuid.uuid4())
    def interrupted(*args):
        raise OSError("synthetic fsync failure")
    monkeypatch.setattr(module.os, "fsync", interrupted)
    with pytest.raises(OSError, match="fsync"):
        artifacts.write_corrected_evaluation_json(experiment.uuid, eid, "result", {"value": "complete"})
    path = artifacts.corrected_evaluation_path(experiment.uuid, eid, "result")
    assert not path.exists() and list(path.parent.iterdir()) == []


def test_new_unavailable_attempt_cannot_select_older_pass(environment, tmp_path):
    registry, experiment, artifacts = environment
    _historical(artifacts, experiment)
    evaluate_corrected(registry, experiment.uuid, experiment.experiment_hash,
                       evaluation_id=str(uuid.uuid4()), inputs=_inputs(tmp_path, experiment))
    eid = str(uuid.uuid4())
    evaluate_corrected(registry, experiment.uuid, experiment.experiment_hash,
                       evaluation_id=eid, unavailable_reason="Newly discovered missing exploratory trials")
    result = check_current_qualification(registry, experiment.uuid, experiment.experiment_hash)
    assert not result.qualified and result.evaluation_id == eid
    assert result.status == "requiring_re_evaluation"


def test_changed_original_bytes_invalidate_corrected_qualification(environment, tmp_path):
    registry, experiment, artifacts = environment
    _historical(artifacts, experiment)
    evaluate_corrected(registry, experiment.uuid, experiment.experiment_hash,
                       evaluation_id=str(uuid.uuid4()), inputs=_inputs(tmp_path, experiment))
    # Simulate corruption outside ArtifactManager in temporary storage only.
    artifacts.path(experiment.uuid, ArtifactKind.VALIDATION_REPORT_JSON).write_text('{"passed": false}')
    assert not check_current_qualification(registry, experiment.uuid, experiment.experiment_hash).qualified


def test_explicit_abandonment_preserves_attempt_and_requires_new_complete_evidence(environment, tmp_path):
    registry, experiment, artifacts = environment
    _historical(artifacts, experiment)
    inputs = _inputs(tmp_path, experiment)
    original_id = str(uuid.uuid4())
    evaluate_corrected(registry, experiment.uuid, experiment.experiment_hash,
                       evaluation_id=original_id, inputs=inputs)
    interrupted_id = str(uuid.uuid4())
    artifacts.claim_corrected_evaluation(experiment.uuid, interrupted_id, "b" * 64)
    assert not check_current_qualification(registry, experiment.uuid, experiment.experiment_hash).qualified
    disposition = abandon_corrected_evaluation(
        registry, experiment.uuid, experiment.experiment_hash, evaluation_id=interrupted_id,
        operator="synthetic operator", reason="Process interrupted before request publication",
    )
    disposition_bytes = disposition.read_bytes()
    assert not check_current_qualification(registry, experiment.uuid, experiment.experiment_hash).qualified
    with pytest.raises(ArtifactImmutableError):
        artifacts.claim_corrected_evaluation(experiment.uuid, interrupted_id, "c" * 64)
    with pytest.raises(ValueError, match="Completed"):
        abandon_corrected_evaluation(
            registry, experiment.uuid, experiment.experiment_hash, evaluation_id=original_id,
            operator="synthetic operator", reason="Must not abandon completed evidence",
        )
    successor = str(uuid.uuid4())
    evaluate_corrected(registry, experiment.uuid, experiment.experiment_hash,
                       evaluation_id=successor, inputs=replace(inputs, mc_num_paths=101))
    qualified = check_current_qualification(registry, experiment.uuid, experiment.experiment_hash)
    assert qualified.qualified and qualified.evaluation_id == successor
    assert disposition.read_bytes() == disposition_bytes
    assert disposition.parent.is_dir()
