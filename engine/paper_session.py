"""Paper broker sessions and operator reports."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from config.schema import Config
from execution.base import (
    BrokerAdapter,
    BrokerOrderRequest,
    BrokerOrderResponse,
    OrderSide,
    OrderType,
    TimeInForce,
)
from execution.sim_broker.broker import SimBroker, SimBrokerConfig
from experiments.artifacts import ArtifactKind, ArtifactManager
from experiments.models import Experiment, PromotionStatus
from experiments.operator_confirmations import verify_experiment_hash
from experiments.registry import ExperimentRegistry
from monitoring.reports import (
    build_operational_report,
    format_operational_report,
)

MAX_ORDER_CAP = 25.0
MAX_SESSION_CAP = 100.0
MAX_OPEN_EXPOSURE_CAP = 100.0

PAPER_OPS_SMOKE_MARKER = "PAPER_OPS_SMOKE_PASSED"
PAPER_OPS_SMOKE_REPORT = "paper_ops_smoke_report.json"
PAPER_OPS_PASS_SESSION_KIND = "paper_ops_pass"
PAPER_OPS_SMOKE_SESSION_KIND = "paper_ops_smoke"
PAPER_OPS_REQUIRED_REPORTS = (
    "operator_report.json",
    "reconciliation_report.json",
    "slippage_report.json",
    "bar_cycle_report.json",
    "kill_switch_drill_report.json",
)
PAPER_OPS_MIN_CALENDAR_DAYS = 30.0
PAPER_OPS_MIN_MARKET_SESSIONS = 20.0
PAPER_OPS_MIN_TRADES = 100.0
PAPER_OPS_BAR_CYCLE_COMPLETION_MIN = 0.995
PAPER_OPS_SLIPPAGE_BLOCKER_THRESHOLD = 2.0
PAPER_OPS_SMOKE_MIN_MARKET_SESSIONS = 5.0
PAPER_OPS_SMOKE_MIN_WALL_CLOCK_DAYS = 7.0
PAPER_OPS_PASS_WINDOW = {
    "min_calendar_days": PAPER_OPS_MIN_CALENDAR_DAYS,
    "min_market_sessions": PAPER_OPS_MIN_MARKET_SESSIONS,
    "min_trades": PAPER_OPS_MIN_TRADES,
    "target_trades": 200,
    "bar_cycle_completion_min": PAPER_OPS_BAR_CYCLE_COMPLETION_MIN,
    "unexplained_missed_cycles_allowed": 0,
    "slippage_warning_threshold": 1.5,
    "slippage_blocker_threshold": PAPER_OPS_SLIPPAGE_BLOCKER_THRESHOLD,
    "reconciliation_unresolved_allowed": 0,
    "portfolio_state_required_at_end": "KNOWN",
}
PAPER_OPS_TERMINAL_ORDER_STATES = {"FILLED", "CANCELLED", "REJECTED", "EXPIRED", "REPLACED"}
PAPER_OPS_OPEN_ORDER_STATES = {"ACKNOWLEDGED", "PARTIALLY_FILLED", "SUBMITTING", "CANCEL_REQUESTED"}


class PaperSessionGateError(Exception):
    """Raised when a paper broker session fails a safety gate."""


@dataclass(frozen=True)
class PaperCaps:
    max_notional_per_order: float
    max_paper_session_notional: float
    max_open_paper_exposure: float

    def to_dict(self) -> dict[str, float]:
        return {
            "max_notional_per_order": self.max_notional_per_order,
            "max_paper_session_notional": self.max_paper_session_notional,
            "max_open_paper_exposure": self.max_open_paper_exposure,
        }


@dataclass(frozen=True)
class PaperSessionResult:
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


def paper_caps_from_config(config: Config) -> PaperCaps:
    live = config.live_deployment
    return PaperCaps(
        max_notional_per_order=live.max_notional_per_order,
        max_paper_session_notional=live.max_paper_session_notional or live.max_paper_notional,
        max_open_paper_exposure=live.max_open_paper_exposure or live.max_strategy_capital,
    )


def validate_tiny_paper_caps(caps: PaperCaps) -> None:
    failures: list[str] = []
    if caps.max_notional_per_order <= 0 or caps.max_notional_per_order > MAX_ORDER_CAP:
        failures.append(f"max_notional_per_order must be in (0, {MAX_ORDER_CAP}]")
    if caps.max_paper_session_notional <= 0 or caps.max_paper_session_notional > MAX_SESSION_CAP:
        failures.append(f"max_paper_session_notional must be in (0, {MAX_SESSION_CAP}]")
    if caps.max_open_paper_exposure <= 0 or caps.max_open_paper_exposure > MAX_OPEN_EXPOSURE_CAP:
        failures.append(f"max_open_paper_exposure must be in (0, {MAX_OPEN_EXPOSURE_CAP}]")
    if caps.max_notional_per_order > caps.max_paper_session_notional:
        failures.append("max_notional_per_order cannot exceed max_paper_session_notional")
    if caps.max_notional_per_order > caps.max_open_paper_exposure:
        failures.append("max_notional_per_order cannot exceed max_open_paper_exposure")
    if failures:
        raise PaperSessionGateError("; ".join(failures))


def verify_paper_lifecycle_gates(
    registry: ExperimentRegistry,
    *,
    experiment_uuid: str,
    experiment_hash: str,
) -> Experiment:
    experiment = verify_experiment_hash(registry, experiment_uuid, experiment_hash)
    if experiment.promotion_status != PromotionStatus.PAPER_OPS:
        raise PaperSessionGateError(
            f"paper broker session requires paper_ops, got {experiment.promotion_status.value}"
        )
    kill_switch = registry.get_kill_switch(experiment_uuid)
    if kill_switch is not None and kill_switch.is_active:
        raise PaperSessionGateError(
            f"active kill switch blocks paper broker session: {kill_switch.reason}"
        )
    return experiment


def has_passing_sim_drill(artifacts: ArtifactManager, experiment_uuid: str) -> bool:
    return any(
        session.get("passed") is True
        and session.get("session_type") == "simulated_drills"
        for session in artifacts.list_paper_sessions(experiment_uuid)
    )


def has_passing_alpaca_smoke(artifacts: ArtifactManager, experiment_uuid: str) -> bool:
    return any(
        session.get("passed") is True
        and session.get("session_type") == "alpaca_paper_smoke"
        for session in artifacts.list_paper_sessions(experiment_uuid)
    )


def write_paper_ops_pass_report_set(
    *,
    registry: ExperimentRegistry,
    experiment_uuid: str,
    session_id: str,
    reports: dict[str, dict[str, Any]],
    artifacts: ArtifactManager | None = None,
) -> dict[str, Path]:
    """Write immutable report evidence for one full Paper Ops Pass session.

    This helper is intentionally small: real paper-loop code can build the
    reports from broker/runtime state, while this function enforces the
    per-session immutable artifact layout used by the promotion gate.
    """
    experiment = registry.get(experiment_uuid)
    if experiment is None:
        raise PaperSessionGateError(f"Experiment not found: {experiment_uuid}")
    artifacts = artifacts or ArtifactManager(registry.root)
    paths: dict[str, Path] = {}
    for report_name in PAPER_OPS_REQUIRED_REPORTS:
        if report_name not in reports:
            raise PaperSessionGateError(f"missing paper ops report: {report_name}")
        payload = {
            "experiment_uuid": experiment.uuid,
            "experiment_hash": experiment.experiment_hash,
            "paper_session_id": session_id,
            **reports[report_name],
        }
        paths[report_name] = artifacts.write_paper_session_report_json(
            experiment.uuid,
            session_id,
            report_name,
            payload,
        )
    return paths


def build_paper_ops_smoke_report(
    *,
    registry: ExperimentRegistry,
    experiment_uuid: str,
    session_id: str,
    artifacts: ArtifactManager | None = None,
) -> dict[str, Any]:
    """Build non-promoting Paper Ops Smoke evidence for one paper session."""
    experiment = registry.get(experiment_uuid)
    if experiment is None:
        raise PaperSessionGateError(f"Experiment not found: {experiment_uuid}")
    artifacts = artifacts or ArtifactManager(registry.root)
    session = cast(dict[str, Any], artifacts.read_paper_session_json(experiment.uuid, session_id))
    window = session.get("window") or {}
    bar_cycle = session.get("bar_cycle_report") or {}
    blockers: list[str] = []
    if session.get("session_kind") != PAPER_OPS_SMOKE_SESSION_KIND:
        blockers.append("Paper Ops Smoke requires session_kind=paper_ops_smoke.")
    if session.get("passed") is not True:
        blockers.append("Paper Ops Smoke session summary is not passing.")
    _require_min(window, "market_sessions", PAPER_OPS_SMOKE_MIN_MARKET_SESSIONS, blockers)
    _require_min(window, "calendar_days", PAPER_OPS_SMOKE_MIN_WALL_CLOCK_DAYS, blockers)
    unexplained = _number(bar_cycle.get("unexplained_missed_cycles"), default=0.0)
    if unexplained is not None and unexplained > 0:
        blockers.append("Paper Ops Smoke has unexplained missed cycles.")
    unplanned = _number(window.get("unplanned_interruptions"), default=0.0)
    if unplanned is not None and unplanned > 0:
        blockers.append("Paper Ops Smoke has unplanned interruptions.")
    drill = session.get("kill_switch_drill") or {}
    if drill.get("kill_switch_drill_evidence_exists") is not True:
        blockers.append("Paper Ops Smoke kill-switch drill evidence missing.")
    if drill.get("new_orders_blocked") is not True:
        blockers.append("Paper Ops Smoke kill-switch drill did not prove blocked new orders.")
    return {
        "experiment_uuid": experiment.uuid,
        "experiment_hash": experiment.experiment_hash,
        "paper_session_id": session_id,
        "session_kind": session.get("session_kind"),
        "status": PAPER_OPS_SMOKE_MARKER if not blockers else "PAPER_OPS_SMOKE_BLOCKED",
        "passed": not blockers,
        "blockers": blockers,
        "promotion_unlocked": False,
        "window": {
            "market_sessions": window.get("market_sessions"),
            "calendar_days": window.get("calendar_days"),
            "min_market_sessions": PAPER_OPS_SMOKE_MIN_MARKET_SESSIONS,
            "min_wall_clock_days": PAPER_OPS_SMOKE_MIN_WALL_CLOCK_DAYS,
            "unplanned_interruptions": window.get("unplanned_interruptions", 0),
        },
        "bar_cycle_report": bar_cycle,
    }


def write_paper_ops_smoke_report(
    *,
    registry: ExperimentRegistry,
    experiment_uuid: str,
    session_id: str,
    artifacts: ArtifactManager | None = None,
) -> Path:
    artifacts = artifacts or ArtifactManager(registry.root)
    report = build_paper_ops_smoke_report(
        registry=registry,
        experiment_uuid=experiment_uuid,
        session_id=session_id,
        artifacts=artifacts,
    )
    return artifacts.write_paper_session_report_json(
        experiment_uuid,
        session_id,
        PAPER_OPS_SMOKE_REPORT,
        report,
    )


def build_paper_ops_pass_report_set(
    *,
    registry: ExperimentRegistry,
    experiment_uuid: str,
    session_id: str,
    db_path: str | Path,
    artifacts: ArtifactManager | None = None,
) -> dict[str, dict[str, Any]]:
    """Build the five required Paper Ops Pass reports from session + DB evidence."""
    experiment = registry.get(experiment_uuid)
    if experiment is None:
        raise PaperSessionGateError(f"Experiment not found: {experiment_uuid}")
    artifacts = artifacts or ArtifactManager(registry.root)
    session = cast(dict[str, Any], artifacts.read_paper_session_json(experiment.uuid, session_id))
    db = Path(db_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        orders = _db_rows(conn, "SELECT * FROM orders_live ORDER BY created_at, client_order_id")
        events = _db_rows(conn, "SELECT * FROM events ORDER BY id")
        positions = _db_rows(conn, "SELECT * FROM positions_live ORDER BY strategy, symbol")
        operational = build_operational_report(conn).to_dict()
    finally:
        conn.close()

    reports = {
        "operator_report.json": _build_pass_operator_report(
            experiment=experiment,
            session=session,
            orders=orders,
            positions=positions,
            operational=operational,
            active_kill_switch=registry.get_kill_switch(experiment.uuid),
        ),
        "reconciliation_report.json": _build_pass_reconciliation_report(
            session=session,
            orders=orders,
            events=events,
        ),
        "slippage_report.json": _build_pass_slippage_report(session=session, orders=orders),
        "bar_cycle_report.json": _build_pass_bar_cycle_report(session=session),
        "kill_switch_drill_report.json": _build_pass_kill_switch_drill_report(
            session=session,
            events=events,
        ),
    }
    return reports


def build_and_write_paper_ops_pass_report_set(
    *,
    registry: ExperimentRegistry,
    experiment_uuid: str,
    session_id: str,
    db_path: str | Path,
    artifacts: ArtifactManager | None = None,
) -> dict[str, Path]:
    """Build and persist immutable Paper Ops Pass reports for one session."""
    artifacts = artifacts or ArtifactManager(registry.root)
    reports = build_paper_ops_pass_report_set(
        registry=registry,
        experiment_uuid=experiment_uuid,
        session_id=session_id,
        db_path=db_path,
        artifacts=artifacts,
    )
    return write_paper_ops_pass_report_set(
        registry=registry,
        experiment_uuid=experiment_uuid,
        session_id=session_id,
        reports=reports,
        artifacts=artifacts,
    )


def evaluate_paper_ops_pass_session(
    *,
    registry: ExperimentRegistry,
    experiment: Experiment,
    session_id: str,
    artifacts: ArtifactManager | None = None,
) -> dict[str, Any]:
    artifacts = artifacts or ArtifactManager(registry.root)
    blockers: list[str] = []
    session = _read_required_session(artifacts, experiment, session_id, blockers)
    reports = _read_required_reports(artifacts, experiment, session_id, blockers)

    active_kill_switch = registry.get_kill_switch(experiment.uuid)
    if active_kill_switch is not None and active_kill_switch.is_active:
        blockers.append(f"Active kill switch: {active_kill_switch.reason}.")

    if experiment.promotion_status != PromotionStatus.PAPER_OPS:
        blockers.append(
            f"Experiment status is {experiment.promotion_status.value}, not paper_ops."
        )

    if session:
        _validate_pass_session_summary(experiment, session_id, session, blockers)
    if reports:
        _validate_pass_reports(experiment, session_id, session or {}, reports, blockers)

    evidence_hashes = {}
    if session:
        evidence_hashes["session.json"] = _sha256_path(
            artifacts.paper_session_path(experiment.uuid, session_id)
        )
    for report_name in reports:
        evidence_hashes[report_name] = _sha256_path(
            artifacts.paper_session_report_path(
                experiment.uuid,
                session_id,
                report_name,
            )
        )

    return {
        "experiment_uuid": experiment.uuid,
        "experiment_hash": experiment.experiment_hash,
        "paper_session_id": session_id,
        "session_kind": session.get("session_kind") if session else None,
        "passed": not blockers,
        "blockers": blockers,
        "required_reports": list(PAPER_OPS_REQUIRED_REPORTS),
        "evidence_artifact_hashes": evidence_hashes,
        "window": PAPER_OPS_PASS_WINDOW,
    }


def run_simulated_paper_drills(
    *,
    registry: ExperimentRegistry,
    config: Config,
    experiment_uuid: str,
    experiment_hash: str,
    operator: str | None,
    session_id: str,
    artifacts: ArtifactManager | None = None,
) -> PaperSessionResult:
    experiment = verify_paper_lifecycle_gates(
        registry, experiment_uuid=experiment_uuid, experiment_hash=experiment_hash
    )
    caps = paper_caps_from_config(config)
    validate_tiny_paper_caps(caps)
    artifacts = artifacts or ArtifactManager(registry.root)

    drills = {
        "reject": _drill_reject(),
        "timeout": _drill_timeout(),
        "reconciliation": _drill_reconciliation(),
    }
    blockers = [
        f"{name} drill failed: {result.get('reason', 'unknown')}"
        for name, result in drills.items()
        if not result.get("passed")
    ]
    payload = _base_session_payload(
        experiment,
        session_id=session_id,
        operator=operator,
        broker="sim_broker",
        session_type="simulated_drills",
        caps=caps,
        passed=not blockers,
        blockers=blockers,
        details={"drills": drills},
    )
    path = artifacts.write_paper_session_json(experiment_uuid, session_id, payload)
    return PaperSessionResult(
        experiment_uuid=experiment_uuid,
        session_id=session_id,
        broker="sim_broker",
        passed=not blockers,
        session_type="simulated_drills",
        artifact_path=str(path),
        blockers=blockers,
        details={"drills": drills},
    )


def run_alpaca_paper_smoke(
    *,
    registry: ExperimentRegistry,
    config: Config,
    broker: BrokerAdapter,
    experiment_uuid: str,
    experiment_hash: str,
    operator: str | None,
    session_id: str,
    symbol: str,
    confirm_paper_broker: bool,
    artifacts: ArtifactManager | None = None,
) -> PaperSessionResult:
    experiment = verify_paper_lifecycle_gates(
        registry, experiment_uuid=experiment_uuid, experiment_hash=experiment_hash
    )
    if not confirm_paper_broker:
        raise PaperSessionGateError("--confirm-paper-broker is required for alpaca_paper")
    caps = paper_caps_from_config(config)
    validate_tiny_paper_caps(caps)
    artifacts = artifacts or ArtifactManager(registry.root)
    if not has_passing_sim_drill(artifacts, experiment_uuid):
        raise PaperSessionGateError("passing simulated paper drill evidence is required")

    price = broker.get_price(symbol)
    if price is None or price <= 0:
        raise PaperSessionGateError(f"no valid broker price for {symbol}")
    qty = round(caps.max_notional_per_order / price, 6)
    if qty <= 0:
        raise PaperSessionGateError("calculated paper order quantity is zero")
    limit_price = round(price * 0.5, 2)
    client_order_id = _client_order_id(experiment_uuid, session_id, symbol)

    before_open = _orders_to_dicts(_get_open_orders(broker))
    before_positions = _positions_to_dicts(broker.get_positions())
    response = broker.submit_order(
        BrokerOrderRequest(
            client_order_id=client_order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=qty,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            asset_class="equity",
        )
    )
    cancel_ok = False
    post_cancel_status: BrokerOrderResponse | None = None
    if response.status not in {"REJECTED", "TIMEOUT", "FILLED"}:
        cancel_ok = broker.cancel_order(client_order_id)
        post_cancel_status = broker.get_order_status(client_order_id)
    after_open = _orders_to_dicts(_get_open_orders(broker))
    after_positions = _positions_to_dicts(broker.get_positions())

    blockers = _alpaca_smoke_blockers(
        response=response,
        cancel_ok=cancel_ok,
        post_cancel_status=post_cancel_status,
        before_positions=before_positions,
        after_positions=after_positions,
        after_open=after_open,
    )
    details = {
        "symbol": symbol,
        "price": price,
        "limit_price": limit_price,
        "qty": qty,
        "client_order_id": client_order_id,
        "submit_response": _order_response_to_dict(response),
        "cancel_ok": cancel_ok,
        "post_cancel_status": _order_response_to_dict(post_cancel_status),
        "open_orders_before": before_open,
        "open_orders_after": after_open,
        "positions_before": before_positions,
        "positions_after": after_positions,
    }
    payload = _base_session_payload(
        experiment,
        session_id=session_id,
        operator=operator,
        broker=broker.name,
        session_type="alpaca_paper_smoke",
        caps=caps,
        passed=not blockers,
        blockers=blockers,
        details=details,
    )
    path = artifacts.write_paper_session_json(experiment_uuid, session_id, payload)
    return PaperSessionResult(
        experiment_uuid=experiment_uuid,
        session_id=session_id,
        broker=broker.name,
        passed=not blockers,
        session_type="alpaca_paper_smoke",
        artifact_path=str(path),
        blockers=blockers,
        details=details,
    )


def build_paper_operator_report(
    *,
    registry: ExperimentRegistry,
    experiment_uuid: str,
    db_path: str | Path | None = None,
    artifacts: ArtifactManager | None = None,
) -> dict[str, Any]:
    experiment = registry.get(experiment_uuid)
    artifacts = artifacts or ArtifactManager(registry.root)
    sessions = artifacts.list_paper_sessions(experiment_uuid)
    operational = build_operational_report(db_path).to_dict() if db_path is not None else None
    blockers = _paper_operator_blockers(
        experiment=experiment,
        sessions=sessions,
        operational=operational,
        active_kill_switch=registry.get_kill_switch(experiment_uuid),
    )
    return {
        "experiment_uuid": experiment_uuid,
        "experiment_hash": experiment.experiment_hash,
        "promotion_status": experiment.promotion_status.value,
        "passed": not blockers,
        "blockers": blockers,
        "sessions": sessions,
        "operational_report": operational,
    }


def write_paper_operator_report(
    *,
    registry: ExperimentRegistry,
    experiment_uuid: str,
    db_path: str | Path | None = None,
    artifacts: ArtifactManager | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    artifacts = artifacts or ArtifactManager(registry.root)
    report = build_paper_operator_report(
        registry=registry,
        experiment_uuid=experiment_uuid,
        db_path=db_path,
        artifacts=artifacts,
    )
    json_path = artifacts.write_json(
        experiment_uuid,
        ArtifactKind.PAPER_OPERATOR_REPORT_JSON,
        report,
    )
    md_path = artifacts.write_text(
        experiment_uuid,
        ArtifactKind.PAPER_OPERATOR_REPORT_MD,
        format_paper_operator_report(report),
    )
    return json_path, md_path, report


def format_paper_operator_report(report: dict[str, Any]) -> str:
    status = "PASS" if report.get("passed") else "BLOCKED"
    lines = [
        "# Paper Operator Report",
        "",
        f"Status: {status}",
        f"Experiment: `{report['experiment_uuid']}`",
        f"Promotion status: `{report['promotion_status']}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = report.get("blockers") or []
    lines.extend(f"- {blocker}" for blocker in blockers) if blockers else lines.append("- None.")
    lines.extend(["", "## Sessions", ""])
    for session in report.get("sessions") or []:
        lines.append(
            f"- `{session.get('session_id')}` {session.get('session_type')} "
            f"{'PASS' if session.get('passed') else 'BLOCKED'}"
        )
    operational = report.get("operational_report")
    if operational is not None:
        lines.extend(["", "## Engine Operational Report", ""])
        lines.append(format_operational_report(_OperationalReportShim(operational)))
    return "\n".join(lines) + "\n"


def _drill_reject() -> dict[str, Any]:
    broker = SimBroker(SimBrokerConfig(reject_probability=1.0))
    broker.connect()
    response = broker.submit_order(_drill_order("reject"))
    return {
        "passed": response.status == "REJECTED",
        "status": response.status,
        "reason": response.rejection_reason,
    }


def _drill_timeout() -> dict[str, Any]:
    broker = SimBroker(SimBrokerConfig(timeout_probability=1.0))
    broker.connect()
    response = broker.submit_order(_drill_order("timeout"))
    return {"passed": response.status == "TIMEOUT", "status": response.status}


def _drill_reconciliation() -> dict[str, Any]:
    broker = SimBroker(SimBrokerConfig(position_mismatch=True))
    broker.connect()
    broker.inject_position("AAPL", 1.0, 150.0)
    positions = broker.get_positions()
    mismatch_detected = any(pos.symbol == "AAPL" and pos.quantity == 2.0 for pos in positions)
    return {
        "passed": mismatch_detected,
        "mismatch_detected": mismatch_detected,
        "positions": _positions_to_dicts(positions),
    }


def _drill_order(suffix: str) -> BrokerOrderRequest:
    return BrokerOrderRequest(
        client_order_id=f"paper_drill_{suffix}",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=0.01,
        time_in_force=TimeInForce.DAY,
        limit_price=1.0,
        asset_class="equity",
    )


def _base_session_payload(
    experiment: Experiment,
    *,
    session_id: str,
    operator: str | None,
    broker: str,
    session_type: str,
    caps: PaperCaps,
    passed: bool,
    blockers: list[str],
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "experiment_uuid": experiment.uuid,
        "experiment_hash": experiment.experiment_hash,
        "promotion_status": experiment.promotion_status.value,
        "session_id": session_id,
        "session_kind": _session_kind_for_type(session_type),
        "session_type": session_type,
        "operator": operator,
        "broker": broker,
        "caps": caps.to_dict(),
        "lifecycle_gates": {
            "status_is_paper_ops": experiment.promotion_status == PromotionStatus.PAPER_OPS,
            "hash_verified": True,
            "kill_switch_clear": True,
        },
        "passed": passed,
        "blockers": blockers,
        "details": details,
    }


def _client_order_id(experiment_uuid: str, session_id: str, symbol: str) -> str:
    digest = hashlib.sha256(f"{experiment_uuid}:{session_id}:{symbol}".encode()).hexdigest()[:10]
    return f"paper_{symbol}_{digest}"


def _get_open_orders(broker: BrokerAdapter) -> list[BrokerOrderResponse]:
    getter = getattr(broker, "get_open_orders", None)
    if getter is None:
        return []
    return list(getter())


def _orders_to_dicts(orders: list[BrokerOrderResponse]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for order in orders:
        payload = _order_response_to_dict(order)
        if payload is not None:
            converted.append(payload)
    return converted


def _positions_to_dicts(positions: Any) -> list[dict[str, Any]]:
    return [
        {
            "symbol": pos.symbol,
            "quantity": pos.quantity,
            "avg_entry_price": pos.avg_entry_price,
            "side": pos.side,
            "market_value": pos.market_value,
        }
        for pos in positions
    ]


def _order_response_to_dict(order: BrokerOrderResponse | None) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "client_order_id": order.client_order_id,
        "broker_order_id": order.broker_order_id,
        "status": order.status,
        "filled_qty": order.filled_qty,
        "avg_fill_price": order.avg_fill_price,
        "remaining_qty": order.remaining_qty,
        "rejection_reason": order.rejection_reason,
    }


def _alpaca_smoke_blockers(
    *,
    response: BrokerOrderResponse,
    cancel_ok: bool,
    post_cancel_status: BrokerOrderResponse | None,
    before_positions: list[dict[str, Any]],
    after_positions: list[dict[str, Any]],
    after_open: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if response.status in {"REJECTED", "TIMEOUT"}:
        blockers.append(f"paper order did not acknowledge: {response.status}")
    if response.status == "FILLED" or response.filled_qty > 0:
        blockers.append("far-limit paper order filled unexpectedly")
    if response.status not in {"REJECTED", "TIMEOUT", "FILLED"} and not cancel_ok:
        blockers.append("paper order cancel failed")
    if post_cancel_status is not None and post_cancel_status.status not in {"CANCELLED", "CANCEL_REQUESTED"}:
        blockers.append(f"unexpected post-cancel status: {post_cancel_status.status}")
    if before_positions != after_positions:
        blockers.append("broker positions changed during paper smoke")
    if after_open:
        blockers.append(f"open orders remain after paper smoke: {len(after_open)}")
    return blockers


def _paper_operator_blockers(
    *,
    experiment: Experiment,
    sessions: list[dict[str, Any]],
    operational: dict[str, Any] | None,
    active_kill_switch: Any,
) -> list[str]:
    blockers: list[str] = []
    if experiment.promotion_status != PromotionStatus.PAPER_OPS:
        blockers.append(f"Experiment status is {experiment.promotion_status.value}, not paper_ops.")
    if active_kill_switch is not None and active_kill_switch.is_active:
        blockers.append(f"Active kill switch: {active_kill_switch.reason}.")
    if not any(s.get("passed") is True and s.get("session_type") == "simulated_drills" for s in sessions):
        blockers.append("No passing simulated drill session.")
    if not any(s.get("passed") is True and s.get("session_type") == "alpaca_paper_smoke" for s in sessions):
        blockers.append("No passing Alpaca paper smoke session.")
    failed_sessions = [s for s in sessions if s.get("passed") is not True]
    if failed_sessions:
        blockers.append(f"Failed paper sessions present: {len(failed_sessions)}.")
    if operational is not None and not operational.get("passed", False):
        blockers.extend(f"Operational report: {b}" for b in operational.get("blockers", []))
    return blockers


def _build_pass_operator_report(
    *,
    experiment: Experiment,
    session: dict[str, Any],
    orders: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    operational: dict[str, Any],
    active_kill_switch: Any,
) -> dict[str, Any]:
    blockers: list[str] = []
    portfolio_state = str(session.get("portfolio_state") or _portfolio_state_from_orders(orders))
    if experiment.promotion_status != PromotionStatus.PAPER_OPS:
        blockers.append(f"Experiment status is {experiment.promotion_status.value}, not paper_ops.")
    if active_kill_switch is not None and active_kill_switch.is_active:
        blockers.append(f"Active kill switch: {active_kill_switch.reason}.")
    if portfolio_state != "KNOWN":
        blockers.append(f"portfolio_state is {portfolio_state}, not KNOWN.")
    if session.get("passed") is not True:
        blockers.append("Paper session summary is not passing.")
    if operational.get("passed") is not True:
        blockers.extend(f"Operational report: {b}" for b in operational.get("blockers", []))
    return {
        "passed": not blockers,
        "blockers": blockers,
        "portfolio_state": portfolio_state,
        "active_blockers": blockers,
        "operational_report": operational,
        "orders_total": len(orders),
        "positions_total": len(positions),
    }


def _build_pass_reconciliation_report(
    *,
    session: dict[str, Any],
    orders: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers: list[str] = []
    unresolved_orders = [
        row for row in orders
        if row.get("order_state") == "UNKNOWN"
        or row.get("reconciliation_status") in {"MISMATCHED", "UNRESOLVED"}
    ]
    open_orders = [row for row in orders if row.get("order_state") in PAPER_OPS_OPEN_ORDER_STATES]
    mismatch_events = [event for event in events if event.get("event_type") == "RECONCILIATION_MISMATCH"]
    if unresolved_orders:
        blockers.append(f"Unresolved order reconciliation rows: {len(unresolved_orders)}.")
    if mismatch_events:
        blockers.append(f"Reconciliation mismatch events recorded: {len(mismatch_events)}.")
    portfolio_state = str(session.get("portfolio_state") or _portfolio_state_from_orders(orders))
    if portfolio_state != "KNOWN":
        blockers.append(f"portfolio_state is {portfolio_state}, not KNOWN.")
    return {
        "passed": not blockers,
        "blockers": blockers,
        "portfolio_state": portfolio_state,
        "unresolved_count": len(unresolved_orders) + len(mismatch_events),
        "open_order_count": len(open_orders),
        "order_lifecycle": [_order_lifecycle_row(row) for row in orders],
    }


def _build_pass_slippage_report(
    *,
    session: dict[str, Any],
    orders: list[dict[str, Any]],
) -> dict[str, Any]:
    samples = list(session.get("slippage_samples") or [])
    filled_orders = [
        row for row in orders
        if float(row.get("filled_qty") or 0.0) > 0 and row.get("avg_fill_price") is not None
    ]
    blocker_threshold = float(
        session.get("slippage_blocker_threshold")
        or PAPER_OPS_SLIPPAGE_BLOCKER_THRESHOLD
    )
    warning_threshold = float(session.get("slippage_warning_threshold") or 1.5)
    blockers: list[str] = []
    ratios: list[float] = []
    actual_values: list[float] = []
    expected_values: list[float] = []
    for sample in samples:
        actual = _number(sample.get("actual_slippage_bps"))
        expected = _number(sample.get("expected_slippage_bps"))
        if actual is None or expected is None or expected <= 0:
            blockers.append("Slippage sample missing positive expected/actual bps.")
            continue
        actual_values.append(actual)
        expected_values.append(expected)
        ratios.append(actual / expected)
    if filled_orders and not samples:
        blockers.append("Filled orders exist but no explicit slippage samples were recorded.")
    ratio = max(ratios) if ratios else None
    blocker_triggered = ratio is not None and ratio >= blocker_threshold
    if blocker_triggered:
        blockers.append("Slippage blocker threshold exceeded.")
    return {
        "passed": not blockers,
        "blockers": blockers,
        "slippage_unit": "basis_points",
        "warning_threshold": warning_threshold,
        "blocker_threshold": blocker_threshold,
        "sample_size": len(samples),
        "filled_order_count": len(filled_orders),
        "trade_count": max(len(samples), len(filled_orders)),
        "expected_slippage_bps": _mean(expected_values),
        "actual_slippage_bps": _mean(actual_values),
        "actual_vs_expected_ratio": ratio,
        "p95_actual_slippage_bps": _percentile(actual_values, 0.95),
        "blocker_triggered": blocker_triggered,
        "samples": samples,
    }


def _build_pass_bar_cycle_report(session: dict[str, Any]) -> dict[str, Any]:
    report = dict(session.get("bar_cycle_report") or {})
    cycles = list(session.get("bar_cycles") or [])
    blockers: list[str] = list(report.get("blockers") or [])
    completion = _number(report.get("bar_cycle_completion"))
    unexplained = _number(report.get("unexplained_missed_cycles"), default=0.0)
    if not cycles:
        blockers.append("No bar-cycle records were persisted.")
    if completion is None or completion < PAPER_OPS_BAR_CYCLE_COMPLETION_MIN:
        blockers.append("Bar-cycle completion is below 99.5%.")
    if unexplained is not None and unexplained > 0:
        blockers.append("Unexplained missed cycles were recorded.")
    report.update({
        "passed": not blockers,
        "blockers": blockers,
        "cycles": cycles,
    })
    return report


def _build_pass_kill_switch_drill_report(
    *,
    session: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    drill = dict(session.get("kill_switch_drill") or {})
    kill_events = [
        event for event in events
        if str(event.get("event_type") or "").startswith("KILL_SWITCH")
        or event.get("event_type") in {"ENGINE_HALTED", "PORTFOLIO_STATE_BLOCK_NEW_ORDERS"}
    ]
    evidence_exists = bool(drill.get("kill_switch_drill_evidence_exists") or kill_events)
    new_orders_blocked = bool(drill.get("new_orders_blocked"))
    blockers: list[str] = list(drill.get("blockers") or [])
    if not evidence_exists:
        blockers.append("Kill-switch drill evidence missing.")
    if not new_orders_blocked:
        blockers.append("Kill-switch drill did not prove new orders were blocked.")
    return {
        "passed": not blockers,
        "blockers": blockers,
        "kill_switch_drill_evidence_exists": evidence_exists,
        "new_orders_blocked": new_orders_blocked,
        "events_considered": len(kill_events),
        "drill": drill,
    }


def _portfolio_state_from_orders(orders: list[dict[str, Any]]) -> str:
    if any(row.get("order_state") == "UNKNOWN" for row in orders):
        return "UNKNOWN"
    if any(row.get("reconciliation_status") in {"MISMATCHED", "UNRESOLVED"} for row in orders):
        return "UNKNOWN"
    if any(row.get("order_state") in PAPER_OPS_OPEN_ORDER_STATES for row in orders):
        return "PARTIAL"
    return "KNOWN"


def _order_lifecycle_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "client_order_id": row.get("client_order_id"),
        "broker_order_id": row.get("broker_order_id"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "requested_qty": row.get("requested_qty"),
        "filled_qty": row.get("filled_qty"),
        "remaining_qty": row.get("remaining_qty"),
        "avg_fill_price": row.get("avg_fill_price"),
        "order_state": row.get("order_state"),
        "reconciliation_status": row.get("reconciliation_status"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "terminal": row.get("order_state") in PAPER_OPS_TERMINAL_ORDER_STATES,
    }


def _db_rows(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql).fetchall()]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[index]


def _session_kind_for_type(session_type: str) -> str:
    if session_type in {"simulated_drills", "alpaca_paper_smoke", "paper_run"}:
        return PAPER_OPS_SMOKE_SESSION_KIND
    return session_type


def _read_required_session(
    artifacts: ArtifactManager,
    experiment: Experiment,
    session_id: str,
    blockers: list[str],
) -> dict[str, Any] | None:
    try:
        return cast(
            dict[str, Any],
            artifacts.read_paper_session_json(experiment.uuid, session_id),
        )
    except FileNotFoundError:
        blockers.append(f"missing paper session artifact: {session_id}")
        return None


def _read_required_reports(
    artifacts: ArtifactManager,
    experiment: Experiment,
    session_id: str,
    blockers: list[str],
) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for report_name in PAPER_OPS_REQUIRED_REPORTS:
        try:
            reports[report_name] = artifacts.read_paper_session_report_json(
                experiment.uuid,
                session_id,
                report_name,
            )
        except FileNotFoundError:
            blockers.append(f"missing paper session report: {report_name}")
    return reports


def _validate_pass_session_summary(
    experiment: Experiment,
    session_id: str,
    session: dict[str, Any],
    blockers: list[str],
) -> None:
    if session.get("experiment_hash") != experiment.experiment_hash:
        blockers.append("paper session hash does not match current Experiment hash")
    if session.get("session_id") != session_id:
        blockers.append("paper session id does not match requested session")
    if session.get("session_kind") != PAPER_OPS_PASS_SESSION_KIND:
        blockers.append("confirm-paper-ops-pass requires session_kind=paper_ops_pass")
    if session.get("passed") is not True:
        blockers.append("paper ops pass session summary is not passing")

    window = session.get("window") or {}
    _require_min(window, "calendar_days", PAPER_OPS_MIN_CALENDAR_DAYS, blockers)
    _require_min(window, "market_sessions", PAPER_OPS_MIN_MARKET_SESSIONS, blockers)
    trades = _number(window.get("trades"))
    has_override = bool(window.get("insufficient_activity_override_approved"))
    if trades is None:
        blockers.append("paper ops pass window missing trades")
    elif trades < PAPER_OPS_MIN_TRADES and not has_override:
        blockers.append(
            "paper ops pass requires at least 100 trades or an explicit "
            "operator-approved insufficient-activity override"
        )


def _validate_pass_reports(
    experiment: Experiment,
    session_id: str,
    session: dict[str, Any],
    reports: dict[str, dict[str, Any]],
    blockers: list[str],
) -> None:
    for report_name, report in reports.items():
        if report.get("experiment_hash") != experiment.experiment_hash:
            blockers.append(f"{report_name} hash does not match current Experiment hash")
        if report.get("paper_session_id") != session_id:
            blockers.append(f"{report_name} session id does not match requested session")
        if report.get("passed") is not True:
            blockers.append(f"{report_name} is not passing")

    operator = reports.get("operator_report.json", {})
    if operator.get("portfolio_state") != "KNOWN":
        blockers.append("paper operator report requires portfolio_state=KNOWN")
    if operator.get("active_blockers"):
        blockers.append("paper operator report has active blockers")

    reconciliation = reports.get("reconciliation_report.json", {})
    unresolved_count = _number(reconciliation.get("unresolved_count"), default=0.0)
    if unresolved_count is not None and unresolved_count > 0:
        blockers.append("reconciliation report has unresolved mismatches")
    if reconciliation.get("portfolio_state") not in {None, "KNOWN"}:
        blockers.append("reconciliation report portfolio_state is not KNOWN")

    slippage = reports.get("slippage_report.json", {})
    report_trade_count = _number(
        slippage.get("trade_count"),
        default=_number(operator.get("orders_total"), default=0.0),
    )
    insufficient_activity_override = bool(
        (session.get("window") or {}).get("insufficient_activity_override_approved")
    )
    if (
        report_trade_count is not None
        and report_trade_count < PAPER_OPS_MIN_TRADES
        and not insufficient_activity_override
    ):
        blockers.append("paper ops pass reports do not prove at least 100 trades")
    ratio = _number(slippage.get("actual_vs_expected_ratio"))
    blocker_threshold = _number(
        slippage.get("blocker_threshold"),
        default=PAPER_OPS_SLIPPAGE_BLOCKER_THRESHOLD,
    )
    if ratio is not None and blocker_threshold is not None and ratio >= blocker_threshold:
        blockers.append("slippage blocker threshold exceeded")
    if slippage.get("blocker_triggered") is True:
        blockers.append("slippage report triggered blocker")

    bar_cycle = reports.get("bar_cycle_report.json", {})
    completion = _number(bar_cycle.get("bar_cycle_completion"))
    if completion is None:
        blockers.append("bar-cycle report missing completion ratio")
    elif completion < PAPER_OPS_BAR_CYCLE_COMPLETION_MIN:
        blockers.append("bar-cycle completion below 99.5%")
    unexplained_missed = _number(
        bar_cycle.get("unexplained_missed_cycles"),
        default=0.0,
    )
    if unexplained_missed is not None and unexplained_missed > 0:
        blockers.append("bar-cycle report has unexplained missed cycles")

    kill = reports.get("kill_switch_drill_report.json", {})
    if kill.get("kill_switch_drill_evidence_exists") is not True:
        blockers.append("kill-switch drill evidence missing")
    if kill.get("new_orders_blocked") is False:
        blockers.append("kill-switch drill did not block new orders")


def _require_min(
    payload: dict[str, Any],
    key: str,
    minimum: float,
    blockers: list[str],
) -> None:
    value = _number(payload.get(key))
    if value is None:
        blockers.append(f"paper ops pass window missing {key}")
    elif value < minimum:
        blockers.append(f"paper ops pass requires {key} >= {minimum:g}")


def _number(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _OperationalReportShim:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.__dict__.update(payload)
