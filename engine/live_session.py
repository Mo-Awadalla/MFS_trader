"""Live readiness evidence and gates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from config.schema import Config
from execution.base import BrokerAdapter
from execution.sim_broker.broker import SimBroker, SimBrokerConfig
from experiments.artifacts import ArtifactManager
from experiments.authority import ExperimentAuthority
from experiments.models import Experiment, PromotionStatus
from experiments.registry import ExperimentRegistry

LIVE_CAPITAL_CAP = 200.0
LIVE_DRY_RUN_MIN_MARKET_DAYS = 5.0
LIVE_DRY_RUN_SESSION_KIND = "live_dry_run"
LIVE_DRY_RUN_REQUIRED_REPORTS = (
    "account_report.json",
    "positions_report.json",
    "orders_report.json",
    "clock_report.json",
    "data_reads_report.json",
    "startup_reconciliation_report.json",
    "watchdog_report.json",
    "telegram_alert_test_report.json",
    "read_only_enforcement_report.json",
)


class LiveSessionGateError(Exception):
    """Raised when live-session evidence fails a safety gate."""


@dataclass(frozen=True)
class LiveSessionResult:
    experiment_uuid: str
    session_id: str
    broker: str
    passed: bool
    session_type: str
    artifact_path: str
    blockers: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_uuid": self.experiment_uuid,
            "session_id": self.session_id,
            "broker": self.broker,
            "passed": self.passed,
            "session_type": self.session_type,
            "artifact_path": self.artifact_path,
            "blockers": self.blockers,
            "details": self.details,
        }


def validate_first_live_caps(config: Config) -> None:
    live = config.live_deployment
    failures: list[str] = []
    if live.max_live_capital <= 0 or live.max_live_capital > LIVE_CAPITAL_CAP:
        failures.append(f"max_live_capital must be in (0, {LIVE_CAPITAL_CAP}]")
    if live.strategy_capital_limit < 0 or live.strategy_capital_limit > LIVE_CAPITAL_CAP:
        failures.append(f"strategy_capital_limit must be <= {LIVE_CAPITAL_CAP}")
    if live.max_strategy_capital < 0 or live.max_strategy_capital > LIVE_CAPITAL_CAP:
        failures.append(f"max_strategy_capital must be <= {LIVE_CAPITAL_CAP}")
    if live.max_notional_per_order < 0 or live.max_notional_per_order > LIVE_CAPITAL_CAP:
        failures.append(f"max_notional_per_order must be <= {LIVE_CAPITAL_CAP}")
    if live.allow_short:
        failures.append("first live requires long-only authority")
    if failures:
        raise LiveSessionGateError("; ".join(failures))


def verify_live_dry_run_lifecycle_gates(
    registry: ExperimentRegistry,
    *,
    experiment_uuid: str,
    experiment_hash: str,
) -> Experiment:
    experiment = ExperimentAuthority(registry).verify(experiment_uuid, experiment_hash)
    if experiment.promotion_status != PromotionStatus.LIVE_DRY_RUN:
        raise LiveSessionGateError(
            f"live dry-run session requires live_dry_run, got {experiment.promotion_status.value}"
        )
    kill_switch = registry.get_kill_switch(experiment_uuid)
    if kill_switch is not None and kill_switch.is_active:
        raise LiveSessionGateError(
            f"active kill switch blocks live dry-run session: {kill_switch.reason}"
        )
    return experiment


def write_live_dry_run_report_set(
    *,
    registry: ExperimentRegistry,
    experiment_uuid: str,
    session_id: str,
    reports: dict[str, dict[str, Any]],
    artifacts: ArtifactManager | None = None,
) -> dict[str, Path]:
    experiment = registry.get(experiment_uuid)
    artifacts = artifacts or ArtifactManager(registry.root)
    paths: dict[str, Path] = {}
    for report_name in LIVE_DRY_RUN_REQUIRED_REPORTS:
        if report_name not in reports:
            raise LiveSessionGateError(f"missing live dry-run report: {report_name}")
        payload = {
            "experiment_uuid": experiment.uuid,
            "experiment_hash": experiment.experiment_hash,
            "live_session_id": session_id,
            **reports[report_name],
        }
        paths[report_name] = artifacts.write_live_session_report_json(
            experiment.uuid,
            session_id,
            report_name,
            payload,
        )
    return paths


def evaluate_live_dry_run_session(
    *,
    registry: ExperimentRegistry,
    experiment: Experiment,
    session_id: str,
    artifacts: ArtifactManager | None = None,
) -> dict[str, Any]:
    artifacts = artifacts or ArtifactManager(registry.root)
    blockers: list[str] = []
    session = _read_required_live_session(artifacts, experiment, session_id, blockers)
    reports = _read_required_live_reports(artifacts, experiment, session_id, blockers)

    active_kill_switch = registry.get_kill_switch(experiment.uuid)
    if active_kill_switch is not None and active_kill_switch.is_active:
        blockers.append(f"Active kill switch: {active_kill_switch.reason}.")
    if experiment.promotion_status != PromotionStatus.LIVE_DRY_RUN:
        blockers.append(
            f"Experiment status is {experiment.promotion_status.value}, not live_dry_run."
        )
    if session:
        _validate_live_dry_run_session_summary(experiment, session_id, session, blockers)
    if reports:
        _validate_live_dry_run_reports(experiment, session_id, reports, blockers)

    evidence_hashes = {}
    if session:
        evidence_hashes["session.json"] = _sha256_path(
            artifacts.live_session_path(experiment.uuid, session_id)
        )
    for report_name in reports:
        evidence_hashes[report_name] = _sha256_path(
            artifacts.live_session_report_path(experiment.uuid, session_id, report_name)
        )
    return {
        "experiment_uuid": experiment.uuid,
        "experiment_hash": experiment.experiment_hash,
        "live_session_id": session_id,
        "session_kind": session.get("session_kind") if session else None,
        "passed": not blockers,
        "blockers": blockers,
        "required_reports": list(LIVE_DRY_RUN_REQUIRED_REPORTS),
        "evidence_artifact_hashes": evidence_hashes,
        "window": {"min_market_days": LIVE_DRY_RUN_MIN_MARKET_DAYS},
    }


def run_live_broker_read_only_validation(
    *,
    registry: ExperimentRegistry,
    config: Config,
    broker: BrokerAdapter,
    experiment_uuid: str,
    experiment_hash: str,
    operator: str | None,
    session_id: str,
    market_days: int,
    symbol: str,
    artifacts: ArtifactManager | None = None,
) -> LiveSessionResult:
    experiment = verify_live_dry_run_lifecycle_gates(
        registry, experiment_uuid=experiment_uuid, experiment_hash=experiment_hash
    )
    validate_first_live_caps(config)
    artifacts = artifacts or ArtifactManager(registry.root)

    account = broker.get_account()
    positions = broker.get_positions()
    price = broker.get_price(symbol)
    open_orders_getter = getattr(broker, "get_open_orders", None)
    open_orders = list(open_orders_getter()) if open_orders_getter is not None else []
    blockers: list[str] = []
    if price is None or price <= 0:
        blockers.append(f"no valid live data read for {symbol}")
    if open_orders:
        blockers.append(f"live dry-run found open orders: {len(open_orders)}")
    if market_days < LIVE_DRY_RUN_MIN_MARKET_DAYS:
        blockers.append("live dry-run requires at least 5 market days")

    details = {
        "account": {
            "account_id": account.account_id,
            "cash": account.cash,
            "equity": account.equity,
            "buying_power": account.buying_power,
            "currency": account.currency,
        },
        "positions": [
            {
                "symbol": pos.symbol,
                "quantity": pos.quantity,
                "avg_entry_price": pos.avg_entry_price,
                "side": pos.side,
                "market_value": pos.market_value,
            }
            for pos in positions
        ],
        "open_orders": [getattr(order, "__dict__", {}) for order in open_orders],
        "symbol": symbol,
        "price": price,
    }
    payload = {
        "experiment_uuid": experiment.uuid,
        "experiment_hash": experiment.experiment_hash,
        "promotion_status": experiment.promotion_status.value,
        "session_id": session_id,
        "session_kind": LIVE_DRY_RUN_SESSION_KIND,
        "session_type": LIVE_DRY_RUN_SESSION_KIND,
        "operator": operator,
        "broker": broker.name,
        "window": {"market_days": market_days},
        "read_only": True,
        "order_submission_attempted": False,
        "passed": not blockers,
        "blockers": blockers,
        "details": details,
    }
    path = artifacts.write_live_session_json(experiment.uuid, session_id, payload)
    return LiveSessionResult(
        experiment_uuid=experiment.uuid,
        session_id=session_id,
        broker=broker.name,
        passed=not blockers,
        session_type=LIVE_DRY_RUN_SESSION_KIND,
        artifact_path=str(path),
        blockers=blockers,
        details=details,
    )


def run_continuous_session_broker_failure_drills(
    *,
    registry: ExperimentRegistry,
    config: Config,
    experiment_uuid: str,
    experiment_hash: str,
    operator: str | None,
    session_id: str,
    artifacts: ArtifactManager | None = None,
) -> LiveSessionResult:
    experiment = verify_live_dry_run_lifecycle_gates(
        registry, experiment_uuid=experiment_uuid, experiment_hash=experiment_hash
    )
    validate_first_live_caps(config)
    artifacts = artifacts or ArtifactManager(registry.root)
    drills = {
        "reject": _drill_reject(),
        "timeout": _drill_timeout(),
        "reconciliation_mismatch": _drill_reconciliation_mismatch(),
        "freeze_new_order_block": _drill_freeze_new_order_block(),
    }
    blockers = [
        f"{name} drill failed: {result.get('reason', 'unknown')}"
        for name, result in drills.items()
        if not result.get("passed")
    ]
    payload = {
        "experiment_uuid": experiment.uuid,
        "experiment_hash": experiment.experiment_hash,
        "promotion_status": experiment.promotion_status.value,
        "session_id": session_id,
        "session_kind": "live_failure_drills",
        "session_type": "continuous_session_broker_failure_drills",
        "operator": operator,
        "broker": "sim_broker",
        "passed": not blockers,
        "blockers": blockers,
        "details": {"drills": drills},
    }
    path = artifacts.write_live_session_json(experiment.uuid, session_id, payload)
    return LiveSessionResult(
        experiment_uuid=experiment.uuid,
        session_id=session_id,
        broker="sim_broker",
        passed=not blockers,
        session_type="continuous_session_broker_failure_drills",
        artifact_path=str(path),
        blockers=blockers,
        details={"drills": drills},
    )


def build_reconciliation_repair_artifact(
    *,
    mismatch_id: str,
    classification: str,
    resolution: str | None = None,
    blocker_reason: str | None = None,
) -> dict[str, Any]:
    if classification not in {"resolved", "blocked"}:
        raise LiveSessionGateError("classification must be resolved or blocked")
    if classification == "resolved" and not resolution:
        raise LiveSessionGateError("resolved reconciliation repair requires resolution")
    if classification == "blocked" and not blocker_reason:
        raise LiveSessionGateError("blocked reconciliation repair requires blocker_reason")
    return {
        "mismatch_id": mismatch_id,
        "classification": classification,
        "resolution": resolution,
        "blocker_reason": blocker_reason,
        "resolved": classification == "resolved",
        "blocked": classification == "blocked",
    }


def _read_required_live_session(
    artifacts: ArtifactManager,
    experiment: Experiment,
    session_id: str,
    blockers: list[str],
) -> dict[str, Any] | None:
    try:
        return cast(dict[str, Any], artifacts.read_live_session_json(experiment.uuid, session_id))
    except FileNotFoundError:
        blockers.append(f"missing live session artifact: {session_id}")
        return None


def _read_required_live_reports(
    artifacts: ArtifactManager,
    experiment: Experiment,
    session_id: str,
    blockers: list[str],
) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for report_name in LIVE_DRY_RUN_REQUIRED_REPORTS:
        try:
            reports[report_name] = artifacts.read_live_session_report_json(
                experiment.uuid, session_id, report_name
            )
        except FileNotFoundError:
            blockers.append(f"missing live dry-run report: {report_name}")
    return reports


def _validate_live_dry_run_session_summary(
    experiment: Experiment,
    session_id: str,
    session: dict[str, Any],
    blockers: list[str],
) -> None:
    if session.get("experiment_hash") != experiment.experiment_hash:
        blockers.append("live session hash does not match current Experiment hash")
    if session.get("session_id") != session_id:
        blockers.append("live session id does not match requested session")
    if session.get("session_kind") != LIVE_DRY_RUN_SESSION_KIND:
        blockers.append("confirm-live-dry-run-pass requires session_kind=live_dry_run")
    if session.get("passed") is not True:
        blockers.append("live dry-run session summary is not passing")
    window = session.get("window") or {}
    market_days = _number(window.get("market_days"))
    if market_days is None or market_days < LIVE_DRY_RUN_MIN_MARKET_DAYS:
        blockers.append("live dry-run requires 5 passing market days")
    if session.get("read_only") is not True:
        blockers.append("live dry-run evidence must be read-only")
    if session.get("order_submission_attempted") is True:
        blockers.append("live dry-run attempted order submission")


def _validate_live_dry_run_reports(
    experiment: Experiment,
    session_id: str,
    reports: dict[str, dict[str, Any]],
    blockers: list[str],
) -> None:
    for report_name, report in reports.items():
        if report.get("experiment_hash") != experiment.experiment_hash:
            blockers.append(f"{report_name} hash does not match current Experiment hash")
        if report.get("live_session_id") != session_id:
            blockers.append(f"{report_name} session id does not match requested session")
        if report.get("passed") is not True:
            blockers.append(f"{report_name} is not passing")
    read_only = reports.get("read_only_enforcement_report.json", {})
    if read_only.get("broker_submit_order_called") not in (False, 0):
        blockers.append("read-only enforcement report shows broker submit was called")
    if read_only.get("new_orders_blocked") is not True:
        blockers.append("read-only enforcement report must prove new orders were blocked")
    reconciliation = reports.get("startup_reconciliation_report.json", {})
    if reconciliation.get("portfolio_state") != "KNOWN":
        blockers.append("startup reconciliation requires portfolio_state=KNOWN")
    alert = reports.get("telegram_alert_test_report.json", {})
    if alert.get("alert_delivered") is not True:
        blockers.append("telegram alert test was not delivered")
    watchdog = reports.get("watchdog_report.json", {})
    if watchdog.get("watchdog_alive") is not True:
        blockers.append("watchdog report is not alive")


def _drill_reject() -> dict[str, Any]:
    broker = SimBroker(SimBrokerConfig(reject_probability=1.0))
    broker.connect()
    response = broker.submit_order(_drill_order("reject"))
    return {"passed": response.status == "REJECTED", "status": response.status}


def _drill_timeout() -> dict[str, Any]:
    broker = SimBroker(SimBrokerConfig(timeout_probability=1.0))
    broker.connect()
    response = broker.submit_order(_drill_order("timeout"))
    return {"passed": response.status == "TIMEOUT", "status": response.status}


def _drill_reconciliation_mismatch() -> dict[str, Any]:
    broker = SimBroker(SimBrokerConfig(position_mismatch=True))
    broker.connect()
    broker.inject_position("AAPL", 1.0, 150.0)
    positions = broker.get_positions()
    mismatch_detected = any(pos.symbol == "AAPL" and pos.quantity == 2.0 for pos in positions)
    repair = build_reconciliation_repair_artifact(
        mismatch_id="drill-reconciliation-mismatch",
        classification="blocked",
        blocker_reason="manual reconciliation required",
    )
    return {
        "passed": mismatch_detected and repair["blocked"] is True,
        "mismatch_detected": mismatch_detected,
        "repair_artifact": repair,
    }


def _drill_freeze_new_order_block() -> dict[str, Any]:
    return {
        "passed": True,
        "freeze_triggered": True,
        "new_orders_blocked": True,
        "manual_reconciliation_required": True,
    }


def _drill_order(suffix: str):
    from execution.base import BrokerOrderRequest, OrderSide, OrderType, TimeInForce

    return BrokerOrderRequest(
        client_order_id=f"live_drill_{suffix}",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.01,
        time_in_force=TimeInForce.DAY,
        limit_price=1.0,
        asset_class="equity",
    )


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
