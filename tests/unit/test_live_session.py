from __future__ import annotations

import copy

import pytest

from config.schema import (
    AssetClass,
    BrokerConfig,
    Config,
    CostModelConfig,
    DataConfig,
    EngineConfig,
    LiveDeploymentConfig,
    Mode,
    MonitoringConfig,
    PortfolioConfig,
    RiskLimits,
)
from engine.live_session import (
    LIVE_DRY_RUN_REQUIRED_REPORTS,
    LiveSessionGateError,
    build_reconciliation_repair_artifact,
    evaluate_live_dry_run_session,
    run_continuous_session_broker_failure_drills,
    validate_first_live_caps,
    write_live_dry_run_report_set,
)
from experiments.artifacts import ArtifactImmutableError, ArtifactManager
from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.models import ExperimentDraft, PromotionStatus
from experiments.registry import ExperimentRegistry


def _config(max_live_capital: float = 200.0) -> Config:
    return Config(
        mode=Mode.LIVE,
        brokers=[
            BrokerConfig(
                name="alpaca",
                asset_class=AssetClass.EQUITY,
                api_key_env="ALPACA_API_KEY",
                api_secret_env="ALPACA_API_SECRET",
                base_url="https://api.alpaca.markets",
                is_paper=False,
            )
        ],
        data=[DataConfig(symbols=["AAPL"], asset_class=AssetClass.EQUITY)],
        risk_limits=RiskLimits(),
        portfolio=PortfolioConfig(),
        cost_model=CostModelConfig(),
        monitoring=MonitoringConfig(),
        engine=EngineConfig(),
        live_deployment=LiveDeploymentConfig(
            authorized=True,
            max_live_capital=max_live_capital,
            strategy_capital_limit=max_live_capital,
            max_strategy_capital=max_live_capital,
            max_notional_per_order=50.0,
            allow_short=False,
            dry_run_mode=False,
            promotion_status="live",
        ),
        strategy_name="dual_ma_crossover",
        strategy_version="0.1.0",
        strategies_enabled=["ma"],
    )


def _draft(label: str = "live-session") -> ExperimentDraft:
    snap = build_bb_aapl_1d_default_snapshot()
    mutated = copy.deepcopy(snap)
    object.__setattr__(mutated, "parameters", {**snap.parameters, "window": 21})
    return ExperimentDraft(label=label, snapshot=mutated)


def _live_dry_run(registry: ExperimentRegistry):
    exp = registry.create(_draft())
    registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_RUNNING)
    registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_PASSED)
    registry.transition_promotion_status(exp.uuid, PromotionStatus.PAPER_OPS)
    return registry.transition_promotion_status(exp.uuid, PromotionStatus.LIVE_DRY_RUN)


def _write_live_evidence(registry: ExperimentRegistry, exp, session_id: str = "live-dry") -> None:
    artifacts = ArtifactManager(registry.root)
    artifacts.write_live_session_json(
        exp.uuid,
        session_id,
        {
            "experiment_uuid": exp.uuid,
            "experiment_hash": exp.experiment_hash,
            "session_id": session_id,
            "session_kind": "live_dry_run",
            "session_type": "live_dry_run",
            "passed": True,
            "read_only": True,
            "order_submission_attempted": False,
            "window": {"market_days": 5},
        },
    )
    reports = {name: {"passed": True} for name in LIVE_DRY_RUN_REQUIRED_REPORTS}
    reports["startup_reconciliation_report.json"]["portfolio_state"] = "KNOWN"
    reports["telegram_alert_test_report.json"]["alert_delivered"] = True
    reports["watchdog_report.json"]["watchdog_alive"] = True
    reports["read_only_enforcement_report.json"].update(
        {"broker_submit_order_called": False, "new_orders_blocked": True}
    )
    write_live_dry_run_report_set(
        registry=registry,
        experiment_uuid=exp.uuid,
        session_id=session_id,
        reports=reports,
    )


def test_validate_first_live_caps_rejects_above_200() -> None:
    validate_first_live_caps(_config(200.0))
    with pytest.raises(LiveSessionGateError, match="max_live_capital"):
        validate_first_live_caps(_config(200.01))


def test_evaluates_passing_live_dry_run_session(tmp_path) -> None:
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = _live_dry_run(registry)
        _write_live_evidence(registry, exp)

        result = evaluate_live_dry_run_session(
            registry=registry,
            experiment=exp,
            session_id="live-dry",
        )

        assert result["passed"] is True
        assert set(result["required_reports"]) == set(LIVE_DRY_RUN_REQUIRED_REPORTS)
        assert "session.json" in result["evidence_artifact_hashes"]
    finally:
        registry.close()


def test_live_dry_run_blocks_when_submit_was_called(tmp_path) -> None:
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = _live_dry_run(registry)
        artifacts = ArtifactManager(registry.root)
        artifacts.write_live_session_json(
            exp.uuid,
            "bad-live",
            {
                "experiment_uuid": exp.uuid,
                "experiment_hash": exp.experiment_hash,
                "session_id": "bad-live",
                "session_kind": "live_dry_run",
                "session_type": "live_dry_run",
                "passed": True,
                "read_only": True,
                "order_submission_attempted": False,
                "window": {"market_days": 5},
            },
        )
        reports = {name: {"passed": True} for name in LIVE_DRY_RUN_REQUIRED_REPORTS}
        reports["startup_reconciliation_report.json"]["portfolio_state"] = "KNOWN"
        reports["telegram_alert_test_report.json"]["alert_delivered"] = True
        reports["watchdog_report.json"]["watchdog_alive"] = True
        reports["read_only_enforcement_report.json"].update(
            {"broker_submit_order_called": True, "new_orders_blocked": False}
        )
        write_live_dry_run_report_set(
            registry=registry,
            experiment_uuid=exp.uuid,
            session_id="bad-live",
            reports=reports,
        )

        result = evaluate_live_dry_run_session(
            registry=registry,
            experiment=exp,
            session_id="bad-live",
        )

        assert result["passed"] is False
        assert any("broker submit was called" in b for b in result["blockers"])
    finally:
        registry.close()


def test_continuous_session_broker_failure_drills_write_passing_artifact(tmp_path) -> None:
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = _live_dry_run(registry)
        result = run_continuous_session_broker_failure_drills(
            registry=registry,
            config=_config(),
            experiment_uuid=exp.uuid,
            experiment_hash=exp.experiment_hash,
            operator="ops",
            session_id="failure-drills",
        )

        assert result.passed
        payload = ArtifactManager(registry.root).read_live_session_json(
            exp.uuid, "failure-drills"
        )
        assert payload["details"]["drills"]["freeze_new_order_block"]["new_orders_blocked"] is True
    finally:
        registry.close()


def test_reconciliation_repair_artifact_requires_resolved_or_blocked() -> None:
    resolved = build_reconciliation_repair_artifact(
        mismatch_id="m1",
        classification="resolved",
        resolution="broker/local state reconciled to KNOWN",
    )
    blocked = build_reconciliation_repair_artifact(
        mismatch_id="m2",
        classification="blocked",
        blocker_reason="manual broker investigation required",
    )
    assert resolved["resolved"] is True
    assert blocked["blocked"] is True
    with pytest.raises(LiveSessionGateError):
        build_reconciliation_repair_artifact(mismatch_id="m3", classification="resolved")


def test_live_session_artifacts_are_immutable_and_report_paths_are_scoped(tmp_path) -> None:
    artifacts = ArtifactManager(tmp_path / "experiments")
    experiment_uuid = "119131fa-0f67-48d7-ab87-f20d81c70c1f"

    session_path = artifacts.write_live_session_json(
        experiment_uuid,
        "live-dry",
        {"passed": True},
    )
    report_path = artifacts.write_live_session_report_json(
        experiment_uuid,
        "live-dry",
        "account_report.json",
        {"passed": True},
    )

    assert session_path == (
        tmp_path / "experiments" / experiment_uuid / "live" / "sessions" / "live-dry" / "session.json"
    )
    assert report_path.parent == session_path.parent
    assert artifacts.read_live_session_json(experiment_uuid, "live-dry") == {"passed": True}
    assert artifacts.read_live_session_report_json(
        experiment_uuid, "live-dry", "account_report.json"
    ) == {"passed": True}
    with pytest.raises(ArtifactImmutableError):
        artifacts.write_live_session_json(experiment_uuid, "live-dry", {"passed": False})
    with pytest.raises(ArtifactImmutableError):
        artifacts.write_live_session_report_json(
            experiment_uuid,
            "live-dry",
            "account_report.json",
            {"passed": False},
        )
