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
from engine.paper_session import (
    PaperCaps,
    PaperSessionGateError,
    build_and_write_paper_ops_pass_report_set,
    build_paper_operator_report,
    evaluate_paper_ops_pass_session,
    run_alpaca_paper_smoke,
    run_simulated_paper_drills,
    validate_tiny_paper_caps,
    write_paper_operator_report,
)
from execution.base import (
    BrokerAccount,
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerPosition,
)
from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.backfill import build_bb_aapl_1d_default_snapshot
from experiments.models import ExperimentDraft, PromotionStatus
from experiments.registry import ExperimentRegistry
from tests.unit.test_paper_evidence import qualified_session


def _config() -> Config:
    return Config(
        mode=Mode.PAPER,
        brokers=[
            BrokerConfig(
                name="alpaca",
                asset_class=AssetClass.EQUITY,
                api_key_env="ALPACA_API_KEY",
                api_secret_env="ALPACA_API_SECRET",
                base_url="https://paper-api.alpaca.markets",
            )
        ],
        data=[DataConfig(symbols=["AAPL"], asset_class=AssetClass.EQUITY)],
        risk_limits=RiskLimits(),
        portfolio=PortfolioConfig(),
        cost_model=CostModelConfig(),
        monitoring=MonitoringConfig(),
        engine=EngineConfig(),
        live_deployment=LiveDeploymentConfig(
            max_notional_per_order=25.0,
            max_paper_session_notional=100.0,
            max_open_paper_exposure=100.0,
        ),
        strategy_name="dual_ma_crossover",
        strategy_version="0.1.0",
        strategies_enabled=["ma"],
    )


def _draft(label: str = "paper-session", window: int = 15) -> ExperimentDraft:
    snap = build_bb_aapl_1d_default_snapshot()
    mutated = copy.deepcopy(snap)
    object.__setattr__(mutated, "parameters", {**snap.parameters, "window": window})
    return ExperimentDraft(label=label, snapshot=mutated)


def _paper_ops(registry: ExperimentRegistry):
    exp = registry.create(_draft())
    registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_RUNNING)
    registry.transition_promotion_status(exp.uuid, PromotionStatus.VALIDATION_PASSED)
    return registry.transition_promotion_status(exp.uuid, PromotionStatus.PAPER_OPS)


class _FakeAlpacaPaper:
    name = "alpaca"

    def __init__(self) -> None:
        self.submitted: list[BrokerOrderRequest] = []
        self.cancelled: list[str] = []
        self._status: BrokerOrderResponse | None = None

    @property
    def is_connected(self) -> bool:
        return True

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def get_price(self, symbol: str) -> float | None:
        return 100.0

    def submit_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse:
        self.submitted.append(request)
        self._status = BrokerOrderResponse(
            client_order_id=request.client_order_id,
            broker_order_id="paper-1",
            status="ACKNOWLEDGED",
            remaining_qty=request.quantity,
        )
        return self._status

    def cancel_order(self, client_order_id: str) -> bool:
        self.cancelled.append(client_order_id)
        self._status = BrokerOrderResponse(
            client_order_id=client_order_id,
            broker_order_id="paper-1",
            status="CANCELLED",
            remaining_qty=0.0,
        )
        return True

    def get_order_status(self, client_order_id: str) -> BrokerOrderResponse | None:
        return self._status

    def get_open_orders(self) -> list[BrokerOrderResponse]:
        return []

    def get_positions(self) -> list[BrokerPosition]:
        return []

    def get_account(self) -> BrokerAccount:
        return BrokerAccount(account_id="fake", cash=1000.0, equity=1000.0)


def test_validates_tiny_paper_caps() -> None:
    validate_tiny_paper_caps(PaperCaps(25.0, 100.0, 100.0))
    with pytest.raises(PaperSessionGateError, match="max_notional_per_order"):
        validate_tiny_paper_caps(PaperCaps(25.01, 100.0, 100.0))
    with pytest.raises(PaperSessionGateError, match="max_paper_session_notional"):
        validate_tiny_paper_caps(PaperCaps(25.0, 100.01, 100.0))


def test_simulated_drills_write_passing_session(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = _paper_ops(registry)
        result = run_simulated_paper_drills(
            registry=registry,
            config=_config(),
            experiment_uuid=exp.uuid,
            experiment_hash=exp.experiment_hash,
            operator="ops",
            session_id="sim-drills",
        )

        assert result.passed
        payload = ArtifactManager(registry.root).read_paper_session_json(exp.uuid, "sim-drills")
        assert payload["session_type"] == "simulated_drills"
        assert payload["details"]["drills"]["reject"]["passed"] is True
        assert payload["details"]["drills"]["timeout"]["passed"] is True
        assert payload["details"]["drills"]["reconciliation"]["passed"] is True
    finally:
        registry.close()


def test_alpaca_smoke_requires_prior_sim_drills(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = _paper_ops(registry)
        with pytest.raises(PaperSessionGateError, match="simulated paper drill"):
            run_alpaca_paper_smoke(
                registry=registry,
                config=_config(),
                broker=_FakeAlpacaPaper(),
                experiment_uuid=exp.uuid,
                experiment_hash=exp.experiment_hash,
                operator="ops",
                session_id="alpaca",
                symbol="AAPL",
                confirm_paper_broker=True,
            )
    finally:
        registry.close()


def test_alpaca_smoke_submits_far_limit_and_cancels_after_drills(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = _paper_ops(registry)
        run_simulated_paper_drills(
            registry=registry,
            config=_config(),
            experiment_uuid=exp.uuid,
            experiment_hash=exp.experiment_hash,
            operator="ops",
            session_id="sim-drills",
        )
        broker = _FakeAlpacaPaper()

        result = run_alpaca_paper_smoke(
            registry=registry,
            config=_config(),
            broker=broker,
            experiment_uuid=exp.uuid,
            experiment_hash=exp.experiment_hash,
            operator="ops",
            session_id="alpaca",
            symbol="AAPL",
            confirm_paper_broker=True,
        )

        assert result.passed
        assert len(broker.submitted) == 1
        assert broker.submitted[0].order_type.value == "limit"
        assert broker.submitted[0].time_in_force.value == "day"
        assert broker.submitted[0].limit_price == 50.0
        assert broker.cancelled == [broker.submitted[0].client_order_id]
    finally:
        registry.close()


def test_operator_report_requires_sim_and_alpaca_passing_sessions(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = _paper_ops(registry)
        report = build_paper_operator_report(
            registry=registry,
            experiment_uuid=exp.uuid,
        )
        assert not report["passed"]
        assert "No passing simulated drill session." in report["blockers"]
        assert "No passing Alpaca paper smoke session." in report["blockers"]
    finally:
        registry.close()


def test_operator_report_writes_passing_evidence(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = _paper_ops(registry)
        run_simulated_paper_drills(
            registry=registry,
            config=_config(),
            experiment_uuid=exp.uuid,
            experiment_hash=exp.experiment_hash,
            operator="ops",
            session_id="sim-drills",
        )
        run_alpaca_paper_smoke(
            registry=registry,
            config=_config(),
            broker=_FakeAlpacaPaper(),
            experiment_uuid=exp.uuid,
            experiment_hash=exp.experiment_hash,
            operator="ops",
            session_id="alpaca",
            symbol="AAPL",
            confirm_paper_broker=True,
        )

        json_path, md_path, report = write_paper_operator_report(
            registry=registry,
            experiment_uuid=exp.uuid,
        )

        assert report["passed"]
        assert json_path.name == "operator_report.json"
        assert md_path.name == "operator_report.md"
        payload = ArtifactManager(registry.root).read_json(
            exp.uuid, ArtifactKind.PAPER_OPERATOR_REPORT_JSON
        )
        assert payload["passed"] is True
    finally:
        registry.close()




def test_builds_and_writes_full_paper_ops_pass_report_set(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = _paper_ops(registry)
        artifacts = ArtifactManager(registry.root)
        db_path = tmp_path / "paper.sqlite"
        session = qualified_session(registry, exp, db_path)
        artifacts.write_paper_session_json(exp.uuid, "pass-session", session)

        paths = build_and_write_paper_ops_pass_report_set(
            registry=registry,
            experiment_uuid=exp.uuid,
            session_id="pass-session",
            db_path=db_path,
            artifacts=artifacts,
        )

        assert set(paths) == {
            "operator_report.json",
            "reconciliation_report.json",
            "slippage_report.json",
            "bar_cycle_report.json",
            "kill_switch_drill_report.json",
        }
        evidence = evaluate_paper_ops_pass_session(
            registry=registry,
            experiment=exp,
            session_id="pass-session",
            artifacts=artifacts,
        )
        assert evidence["passed"] is True
    finally:
        registry.close()


def test_paper_ops_pass_rejects_claimed_trades_without_report_trade_evidence(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments")
    try:
        exp = _paper_ops(registry)
        artifacts = ArtifactManager(registry.root)
        db_path = tmp_path / "paper.sqlite"
        session = qualified_session(registry, exp, db_path, order_count=0)
        # Supplied totals and overrides are retained only as notes.
        session["operator_notes"] = {"trades": 100, "insufficient_activity_override_approved": True}
        artifacts.write_paper_session_json(exp.uuid, "pass-session", session)
        build_and_write_paper_ops_pass_report_set(
            registry=registry, experiment_uuid=exp.uuid, session_id="pass-session",
            db_path=db_path, artifacts=artifacts,
        )
        evidence = evaluate_paper_ops_pass_session(
            registry=registry, experiment=exp, session_id="pass-session", artifacts=artifacts,
        )
        assert evidence["passed"] is False
        assert any("at least 100 trades" in blocker for blocker in evidence["blockers"])
    finally:
        registry.close()
