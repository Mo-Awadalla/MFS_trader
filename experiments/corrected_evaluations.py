"""Immutable, separately versioned numerical evaluations; never lifecycle authority.

This is a trusted research-caller API, not an arbitrary report import API. The
caller supplies complete prepared inputs and reviewed WFA functions; this module
runs the corrected gauntlet itself. Missing evidence is explicitly unavailable.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.hashing import compute_experiment_hash
from experiments.models import Experiment
from experiments.registry import ExperimentRegistry
from experiments.storage import utc_now_iso

SCHEMA_VERSION = "corrected_evaluation_v1"
FORMULAS = {"gauntlet": "gauntlet_report_v2", "mc": "mc_block_bootstrap_v2",
            "dsr": "bailey_lopez_de_prado_eq2_v1"}


@dataclass(frozen=True)
class EvaluationInputs:
    """Complete gauntlet inputs from a reviewed caller, not a supplied verdict.

    input_files maps durable input identities to local source files. All prepared
    numerical inputs are additionally hashed. caller_config must disclose every
    strategy/preparation option, including costs; snapshot is recorded separately.
    The declared search must include FULL parameter dictionaries for every trial.
    """

    data: Any
    train_fn: Callable[..., dict[str, Any]]
    test_fn: Callable[..., dict[str, Any]]
    sweep_results: Any
    param_columns: list[str]
    search: Any
    input_files: dict[str, Path]
    caller_config: dict[str, Any]
    wfa_config: Any
    periods_per_year: float
    mc_num_paths: int = 10000
    mc_block_size: int = 20
    initial_capital: float = 10000.0


@dataclass(frozen=True)
class Qualification:
    qualified: bool
    status: str
    reason: str
    evaluation_id: str | None = None


class CorrectedQualificationError(ValueError):
    """Current numerical evidence does not qualify the Experiment for paper."""


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _source() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--",
             "experiments/corrected_evaluations.py", "experiments/artifacts.py", "validation"],
            cwd=root, check=True, capture_output=True, text=True,
        ).stdout
        clean = not dirty
    except (OSError, subprocess.SubprocessError):
        commit = None
        clean = False
    paths = [Path(__file__), root / "experiments" / "artifacts.py"]
    paths.extend(sorted((root / "validation").rglob("*.py")))
    return {"commit": commit, "working_tree_clean": clean, "files": {
        str(path.relative_to(root)): _file_hash(path) for path in paths
    }, "formulas": FORMULAS}


def _verify_identity(registry: ExperimentRegistry, uuid: str, expected_hash: str) -> Experiment:
    experiment = registry.get(uuid)
    if experiment.experiment_hash != expected_hash:
        raise ValueError("Full original Experiment hash does not match")
    if compute_experiment_hash(experiment.snapshot) != expected_hash:
        raise ValueError("Frozen Experiment snapshot hash does not match")
    return experiment


def _original(artifacts: ArtifactManager, experiment: Experiment) -> dict[str, Any]:
    report = artifacts.path(experiment.uuid, ArtifactKind.VALIDATION_REPORT_JSON)
    verdict = artifacts.path(experiment.uuid, ArtifactKind.VALIDATION_VERDICT_TXT)
    return {
        "uuid": experiment.uuid, "experiment_hash": experiment.experiment_hash,
        "report_identity": str(report.relative_to(artifacts.root)),
        "report_sha256": _file_hash(report) if report.is_file() else None,
        "verdict_sha256": _file_hash(verdict) if verdict.is_file() else None,
        "verdict": verdict.read_text() if verdict.is_file() else None,
        "promotion_status_at_evaluation": experiment.promotion_status.value,
    }


def _frame_identity(frame: Any) -> dict[str, Any]:
    import pandas as pd

    values = pd.util.hash_pandas_object(frame, index=True).to_numpy().tobytes()
    return {"sha256": hashlib.sha256(values).hexdigest(), "shape": list(frame.shape),
            "columns": [str(x) for x in frame.columns],
            "dtypes": [str(x) for x in frame.dtypes]}


def _callback_identity(callback: Callable[..., Any]) -> dict[str, str]:
    path = inspect.getsourcefile(callback)
    if not path:
        raise ValueError("Reviewed caller functions require inspectable source files")
    root = Path(__file__).resolve().parents[1]
    relative = Path(path).resolve().relative_to(root)
    try:
        committed = subprocess.run(
            ["git", "show", f"HEAD:{relative.as_posix()}"], cwd=root,
            check=True, capture_output=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Reviewed caller source must be committed in this checkout") from exc
    digest = _file_hash(Path(path))
    if hashlib.sha256(committed).hexdigest() != digest:
        raise ValueError("Reviewed caller source differs from the recorded source commit")
    return {"function": f"{callback.__module__}.{callback.__qualname__}",
            "source_identity": relative.as_posix(), "source_sha256": digest}


def _prepared(inputs: EvaluationInputs, experiment: Experiment) -> dict[str, Any]:
    import numpy as np

    search = inputs.search
    if search is None or search.selection_error:
        raise ValueError("Complete searched-trial provenance is missing or invalid")
    if search.selected_parameters != experiment.snapshot.parameters:
        raise ValueError("Selected full parameters differ from the frozen Experiment")
    trials = list(search.trial_parameters)
    if not trials or any(set(p) != set(experiment.snapshot.parameters) for p in trials):
        raise ValueError("Every declared trial must disclose all frozen parameter keys")
    if not search.search_scope.strip() or not search.observation_index_sha256:
        raise ValueError("Complete search scope and shared observation identity are required")
    matrix = np.asarray(search.returns_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != len(trials) or not np.isfinite(matrix).all():
        raise ValueError("Complete finite searched-trial return matrix is required")
    if len(inputs.sweep_results) != len(trials):
        raise ValueError("Sweep rows must include every declared trial in declared order")
    selected = search.selected_trial_index
    matches = [i for i, trial in enumerate(trials) if trial == experiment.snapshot.parameters]
    if matches != [selected] or isinstance(selected, bool):
        raise ValueError("Selected column must uniquely match the full frozen parameters")
    if not inputs.param_columns or not set(inputs.param_columns) <= set(experiment.snapshot.parameters):
        raise ValueError("Stability columns must be declared frozen parameter names")
    for row, trial in zip(inputs.sweep_results.to_dict("records"), trials, strict=True):
        if any(row.get(key) != trial[key] for key in inputs.param_columns):
            raise ValueError("Sweep row order/parameters do not match the declared search")
    if not inputs.input_files or any(not identity.strip() for identity in inputs.input_files):
        raise ValueError("Durable input identities and source files are required")
    if not inputs.caller_config:
        raise ValueError("Full caller/preparation configuration is required")
    if inputs.caller_config.get("cost_model") != experiment.snapshot.cost_model:
        raise ValueError("Caller cost configuration must match the frozen Experiment")
    if inputs.caller_config.get("slippage_model") != experiment.snapshot.slippage_model:
        raise ValueError("Caller slippage configuration must match the frozen Experiment")
    if inputs.wfa_config is None:
        raise ValueError("An explicit full WFA configuration is required")
    if not np.isfinite(inputs.periods_per_year) or inputs.periods_per_year <= 0:
        raise ValueError("Explicit positive observation frequency is required")
    return {
        "inputs": [{"identity": identity, "path": str(Path(path).resolve()),
                    "sha256": _file_hash(Path(path))} for identity, path in sorted(inputs.input_files.items())],
        "data": _frame_identity(inputs.data), "sweep": _frame_identity(inputs.sweep_results),
        "search": {"scope": search.search_scope, "trials": trials,
                   "selected_trial_index": selected, "selected_parameters": search.selected_parameters,
                   "observation_index_sha256": search.observation_index_sha256,
                   "returns_shape": list(matrix.shape),
                   "returns_sha256": hashlib.sha256(matrix.tobytes(order="C")).hexdigest()},
        "train": _callback_identity(inputs.train_fn), "test": _callback_identity(inputs.test_fn),
        "configuration": {"caller": inputs.caller_config, "wfa": asdict(inputs.wfa_config),
                          "param_columns": inputs.param_columns,
                          "initial_capital": inputs.initial_capital,
                          "mc_num_paths": inputs.mc_num_paths, "mc_block_size": inputs.mc_block_size,
                          "periods_per_year": inputs.periods_per_year,
                          "seed": experiment.snapshot.random_seed,
                          "ruin_threshold": -0.50, "max_dd_limit": -0.30,
                          "oos_returns_source": "WFA", "dsr_method": "M_eff_corr",
                          "wfa_pass_criteria": {"oos_sharpe_min": 0.8, "oos_sortino_min": 1.0,
                                                "frac_negative_max": 0.5, "max_single_fold_profit_share": 0.60},
                          "mc_pass_criteria": {"prob_ruin_max_exclusive": 0.05, "pct_5_cagr_min_exclusive": 0},
                          "dsr_pass_criteria": {"pvalue_max_exclusive": 0.05, "pvalue_m_raw_max_exclusive": 0.10},
                          "stability": {"plateau_pct": 0.20, "max_drop_from_best": 0.30},
                          "wfa_kwargs": {}},
    }


def _run_gauntlet(experiment: Experiment, inputs: EvaluationInputs) -> dict[str, Any]:
    from validation.gauntlet import run_gauntlet

    return run_gauntlet(
        experiment.snapshot.strategy, inputs.data, inputs.train_fn, inputs.test_fn,
        inputs.sweep_results, inputs.param_columns, dsr_search=inputs.search,
        initial_capital=inputs.initial_capital, ruin_threshold=-0.50, max_dd_limit=-0.30,
        mc_num_paths=inputs.mc_num_paths, mc_block_size=inputs.mc_block_size,
        mc_periods_per_year=inputs.periods_per_year, wfa_config=inputs.wfa_config,
        seed=experiment.snapshot.random_seed,
    ).to_dict()


def run_current_evaluation(experiment: Experiment, inputs: EvaluationInputs) -> dict[str, Any]:
    """Compute fresh validation with full provenance for a NEW Experiment.

    Returns a canonical-report payload without writing any path. Existing
    ArtifactManager create-only publication remains the caller's responsibility.
    This is not a way to replace a historical report: use evaluate_corrected.
    """
    if compute_experiment_hash(experiment.snapshot) != experiment.experiment_hash:
        raise ValueError("Frozen Experiment snapshot hash does not match")
    prepared = _prepared(inputs, experiment)
    source = _source()
    if source["commit"] is None:
        raise ValueError("Corrected source commit is unavailable; run from a reviewed source checkout")
    if not source["working_tree_clean"]:
        raise ValueError("Corrected source is dirty or untracked; commit reviewed source before evaluation")
    report = _run_gauntlet(experiment, inputs)
    if _prepared(inputs, experiment) != prepared or _source() != source:
        raise ValueError("Evaluation inputs or source changed during execution")
    payload = {
        "gauntlet": report,
        "evaluation_provenance": {
            "schema_version": SCHEMA_VERSION, "uuid": experiment.uuid,
            "experiment_hash": experiment.experiment_hash,
            "snapshot": asdict(experiment.snapshot), "prepared": prepared,
            "corrected_source": source,
        },
    }
    _json_bytes(payload)
    return payload


def evaluate_corrected(
    registry: ExperimentRegistry, uuid: str, expected_hash: str, *, evaluation_id: str,
    inputs: EvaluationInputs | None = None, unavailable_reason: str | None = None,
) -> Path:
    """Run the corrected gauntlet and atomically publish a separate evaluation.

    No PASS/report input is accepted. Absent prerequisites produce an immutable
    requiring_re_evaluation result. A claimed ID/request is never reusable, even
    following interruption. No original evidence or lifecycle status is written.
    """
    experiment = _verify_identity(registry, uuid, expected_hash)
    artifacts = ArtifactManager(registry.root)
    original = _original(artifacts, experiment)
    reason = unavailable_reason
    if reason is not None and not reason.strip():
        raise ValueError("An unavailable reason must be meaningful")
    prepared = None
    if reason is None and inputs is not None:
        try:
            prepared = _prepared(inputs, experiment)
            _json_bytes(prepared)
        except (ValueError, TypeError, OSError, AttributeError) as exc:
            reason = f"Missing/invalid evaluation prerequisites: {exc}"
    if inputs is None and reason is None:
        reason = "Complete input and searched-trial provenance was not supplied"
    if not original["report_sha256"]:
        reason = "Original canonical report is unavailable"
    source = _source()
    if source["commit"] is None:
        reason = "Corrected source commit is unavailable; run from a reviewed source checkout"
    elif not source["working_tree_clean"]:
        reason = "Corrected source is dirty or untracked; commit reviewed source before evaluation"
    request = {"schema_version": SCHEMA_VERSION, "original": original,
               "snapshot": asdict(experiment.snapshot), "corrected_source": source,
               "prepared": prepared, "prerequisite_unavailable_reason": reason}
    request_hash = _digest(request)
    artifacts.claim_corrected_evaluation(uuid, evaluation_id, request_hash)
    artifacts.write_corrected_evaluation_json(uuid, evaluation_id, "request", {
        **request, "evaluation_id": evaluation_id, "created_at": datetime.now(UTC).isoformat(),
        "request_sha256": request_hash,
    })
    report = None
    if reason is None and inputs is not None:
        # The workflow, never an imported user verdict, owns gauntlet execution.
        try:
            report = _run_gauntlet(experiment, inputs)
            unavailable = [report.get("monte_carlo"), report.get("dsr")]
            if any(not check or not check.get("available") for check in unavailable):
                reason = "; ".join(report["failure_reasons"])
            _json_bytes(report)
            if _prepared(inputs, experiment) != prepared:
                reason = "Evaluation inputs changed during execution"
            if _original(artifacts, experiment) != original or _source() != request["corrected_source"]:
                reason = "Original evidence or corrected source changed during execution"
        except Exception as exc:
            reason = f"Corrected gauntlet unavailable: {type(exc).__name__}: {exc}"
            report = None
    verdict = "requiring_re_evaluation" if reason else ("PASS" if report and report["passed"] else "FAIL")
    return artifacts.write_corrected_evaluation_json(uuid, evaluation_id, "result", {
        "schema_version": SCHEMA_VERSION, "evaluation_id": evaluation_id,
        "request_sha256": request_hash, "completed_at": utc_now_iso(),
        "available": reason is None, "verdict": verdict, "unavailable_reason": reason,
        "report": report,
    })


def _gate_evidence_valid(report: dict[str, Any], prepared: dict[str, Any], experiment: Experiment) -> bool:
    """Check serialized gate details, not just an asserted overall PASS."""
    _json_bytes(report)  # Reject NaN/Infinity before comparisons.
    wfa, mc, dsr, stability = (report[name] for name in ("wfa", "monte_carlo", "dsr", "stability"))
    search = prepared["search"]
    config = prepared["configuration"]
    return bool(
        report["report_schema_version"] == FORMULAS["gauntlet"]
        and report["strategy_name"] == experiment.snapshot.strategy
        and report["passed"] is True and not report["failure_reasons"]
        and wfa["passed"] is True and wfa["num_folds"] > 0
        and wfa["oos_sharpe"] >= 0.8 and wfa["oos_sortino"] >= 1.0
        and wfa["frac_negative"] <= 0.5 and wfa["max_single_fold_profit_share"] <= 0.60
        and mc["available"] is True and mc["formula_version"] == FORMULAS["mc"]
        and 0 <= mc["prob_ruin"] < 0.05 and mc["pct_5_cagr"] > 0 and mc["pct_5_max_dd"] >= -0.30
        and mc["seed"] == experiment.snapshot.random_seed
        and mc["num_paths"] == config["mc_num_paths"] and mc["block_size"] == config["mc_block_size"]
        and mc["periods_per_year"] == config["periods_per_year"] and mc["observation_count"] > 1
        and dsr["available"] is True and dsr["passed"] is True
        and dsr["formula_version"] == FORMULAS["dsr"] and dsr["sharpe_unit"] == "per_observation"
        and 0 <= dsr["pvalue"] < 0.05 and 0 <= dsr["pvalue_m_raw"] < 0.10
        and dsr["method"] == "M_eff_corr" and 2 <= dsr["m_eff"] <= dsr["m_raw"]
        and dsr["m_raw"] == len(search["trials"])
        and dsr["track_record_length"] == search["returns_shape"][0]
        and dsr["search_scope"] == search["scope"]
        and search["selected_parameters"] == experiment.snapshot.parameters
        and report["declared_search"] == {
            "scope": search["scope"], "selected_trial_index": search["selected_trial_index"],
            "selected_parameters": search["selected_parameters"], "trials": search["trials"],
            "observation_index_sha256": search["observation_index_sha256"],
        }
        and stability["passed"] is True and stability["has_isolated_peak"] is False
        and stability["plateau_within_pct"] >= 0.70
    )


def _is_hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(c in "0123456789abcdef" for c in value)


def _current_callback_matches(callback: dict[str, Any]) -> bool:
    root = Path(__file__).resolve().parents[1]
    relative = Path(callback["source_identity"])
    path = (root / relative).resolve()
    return bool(
        not relative.is_absolute() and path.is_relative_to(root)
        and isinstance(callback["function"], str) and callback["function"]
        and _is_hex(callback["source_sha256"], 64)
        and _file_hash(path) == callback["source_sha256"]
    )


def _provenance_valid(provenance: dict[str, Any], experiment: Experiment) -> bool:
    source = _source()
    prepared = provenance["prepared"]
    return bool(
        provenance["schema_version"] == SCHEMA_VERSION
        and provenance["snapshot"] == json.loads(_json_bytes(asdict(experiment.snapshot)))
        and provenance["corrected_source"]["files"] == source["files"]
        and provenance["corrected_source"]["formulas"] == FORMULAS
        and provenance["corrected_source"]["working_tree_clean"] is True
        and _is_hex(provenance["corrected_source"]["commit"], 40)
        and all(_is_hex(value, 64) for value in provenance["corrected_source"]["files"].values())
        and prepared["inputs"]
        and all(_is_hex(item["sha256"], 64) and isinstance(item["identity"], str)
                and item["identity"].strip() for item in prepared["inputs"])
        and all(_current_callback_matches(prepared[key]) for key in ("train", "test"))
        and all(_is_hex(prepared["search"][key], 64)
                for key in ("returns_sha256", "observation_index_sha256"))
        and prepared["configuration"]["caller"]["cost_model"] == experiment.snapshot.cost_model
        and prepared["configuration"]["caller"]["slippage_model"] == experiment.snapshot.slippage_model
        and prepared["configuration"]["seed"] == experiment.snapshot.random_seed
    )


def _canonical_qualification(artifacts: ArtifactManager, experiment: Experiment) -> Qualification:
    try:
        payload = artifacts.read_json(experiment.uuid, ArtifactKind.VALIDATION_REPORT_JSON)
        provenance = payload["evaluation_provenance"]
        if (provenance["uuid"] == experiment.uuid
                and provenance["experiment_hash"] == experiment.experiment_hash
                and _provenance_valid(provenance, experiment)
                and _gate_evidence_valid(payload["gauntlet"], provenance["prepared"], experiment)):
            return Qualification(True, "PASS", "Current canonical numerical evidence; manual approval and paper gates remain required")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        pass
    return Qualification(False, "requiring_re_evaluation", "Historical PASS alone is insufficient; complete current numerical evidence is required")


def abandon_corrected_evaluation(
    registry: ExperimentRegistry, uuid: str, expected_hash: str, *,
    evaluation_id: str, operator: str, reason: str,
) -> Path:
    """Append an explicit disposition of an interrupted attempt; never erase it.

    Completed results cannot be abandoned to select an older PASS. This does not
    release the claimed request/ID or qualify anything: a new, distinct complete
    evaluation begun after this disposition is still required.
    """
    _verify_identity(registry, uuid, expected_hash)
    if not operator.strip() or not reason.strip():
        raise ValueError("An operator identity and abandonment reason are required")
    artifacts = ArtifactManager(registry.root)
    request_path = artifacts.corrected_evaluation_path(uuid, evaluation_id, "request")
    if not request_path.parent.is_dir():
        raise ValueError("No reserved corrected evaluation attempt exists")
    if artifacts.corrected_evaluation_path(uuid, evaluation_id, "result").exists():
        raise ValueError("Completed evaluations cannot be abandoned")
    return artifacts.write_corrected_evaluation_json(uuid, evaluation_id, "disposition", {
        "schema_version": SCHEMA_VERSION, "uuid": uuid, "experiment_hash": expected_hash,
        "evaluation_id": evaluation_id, "disposition": "abandoned",
        "operator": operator, "reason": reason, "abandoned_at": datetime.now(UTC).isoformat(),
        "observed_request_sha256": _file_hash(request_path) if request_path.is_file() else None,
    })


def check_current_qualification(
    registry: ExperimentRegistry, uuid: str, expected_hash: str,
) -> Qualification:
    """Fail closed on historical-only, stale, interrupted, or unavailable evidence.

    Current numerical qualification is NOT execution parity, paper-ops evidence,
    operator approval, or permission to transition any lifecycle stage.
    """
    experiment = _verify_identity(registry, uuid, expected_hash)
    artifacts = ArtifactManager(registry.root)
    directory = artifacts.experiment_dir(uuid) / "corrected_evaluations" / "v1"
    def blocked(reason: str, eid: str | None = None) -> Qualification:
        return Qualification(False, "requiring_re_evaluation", reason, eid)

    if not directory.exists():
        return _canonical_qualification(artifacts, experiment)
    evaluations = []
    dispositions = []
    try:
        for folder in directory.iterdir():
            if not folder.is_dir() or folder.name == "requests":
                continue
            disposition_path = artifacts.corrected_evaluation_path(uuid, folder.name, "disposition")
            if disposition_path.exists():
                disposition = json.loads(disposition_path.read_text())
                if (disposition["schema_version"] != SCHEMA_VERSION
                        or disposition["uuid"] != uuid
                        or disposition["experiment_hash"] != expected_hash
                        or disposition["evaluation_id"] != folder.name
                        or disposition["disposition"] != "abandoned"
                        or not disposition["operator"].strip() or not disposition["reason"].strip()):
                    return blocked("Invalid interrupted-attempt disposition", folder.name)
                abandoned_at = datetime.fromisoformat(disposition["abandoned_at"])
                if abandoned_at.tzinfo is None:
                    return blocked("Disposition timestamp requires a timezone", folder.name)
                dispositions.append(abandoned_at)
                continue
            request = json.loads(artifacts.corrected_evaluation_path(uuid, folder.name, "request").read_text())
            result = json.loads(artifacts.corrected_evaluation_path(uuid, folder.name, "result").read_text())
            payload = {key: value for key, value in request.items()
                       if key not in {"evaluation_id", "created_at", "request_sha256"}}
            if (request["schema_version"] != SCHEMA_VERSION or result["schema_version"] != SCHEMA_VERSION
                    or request["evaluation_id"] != folder.name or result["evaluation_id"] != folder.name
                    or _digest(payload) != request["request_sha256"]
                    or result["request_sha256"] != request["request_sha256"]):
                return blocked("Corrected evaluation identity/integrity mismatch", folder.name)
            created_at = datetime.fromisoformat(request["created_at"])
            if created_at.tzinfo is None:
                return blocked("Evaluation timestamp requires a timezone", folder.name)
            evaluations.append((created_at, folder.name, request, result))
        if not evaluations:
            return blocked("No completed corrected evaluation exists")
        created_at, eid, request, result = max(evaluations)
        if dispositions and created_at <= max(dispositions):
            return blocked("A new complete evaluation after abandonment is required", eid)
        original = _original(artifacts, experiment)
        for key in ("uuid", "experiment_hash", "report_identity", "report_sha256", "verdict_sha256"):
            if original[key] != request["original"][key]:
                return blocked("Original evidence no longer matches corrected evaluation", eid)
        report = result["report"]
        if not result["available"] or result["verdict"] != "PASS":
            return Qualification(False, result["verdict"], result["unavailable_reason"] or "Corrected gauntlet failed", eid)
        if not _provenance_valid(request, experiment):
            return blocked("Corrected implementation/provenance changed; evaluation is stale", eid)
        if (request["prerequisite_unavailable_reason"]
                or not _gate_evidence_valid(report, request["prepared"], experiment)):
            return blocked("Corrected PASS lacks complete current gauntlet evidence", eid)
        return Qualification(True, "PASS", "Numerical qualification only; manual approval and paper gates remain required", eid)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        return blocked(f"Incomplete or invalid corrected evaluation: {exc}")


def require_current_qualification(
    registry: ExperimentRegistry, uuid: str, expected_hash: str,
) -> Qualification:
    qualification = check_current_qualification(registry, uuid, expected_hash)
    if not qualification.qualified:
        raise CorrectedQualificationError(f"{qualification.status}: {qualification.reason}")
    return qualification
