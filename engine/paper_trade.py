"""Tiny MA paper trading shakedown."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from config.schema import AssetClass, Config
from data.pipeline import load_bars
from engine.paper_dry_run import _find_data_config, _normalize_bars
from execution.base import OrderSide, OrderType, TimeInForce
from execution.oms import OMS, OrderIntent
from monitoring.reports import build_operational_report
from monitoring.watchdog import HeartbeatWatchdog, WatchdogConfig
from portfolio.sizing import PortfolioState, compute_position_delta, compute_target_positions
from risk.engine import DrawdownState, RiskDecision, RiskEngine
from storage.event_logger import EventLogger
from storage.repository import get_engine_state, get_order, set_engine_state
from storage.schema import init_db
from strategies.ma.signal import MAParams, generate_signals


@dataclass(frozen=True)
class PaperTradeResult:
    passed: bool
    db_path: str
    report_path: str
    json_path: str
    client_order_id: str | None
    submitted: bool
    duplicate_skipped: bool
    order_state: str | None
    broker_status: str | None
    open_orders_before: list[dict[str, Any]]
    open_orders_after: list[dict[str, Any]]
    positions_before: list[dict[str, Any]]
    positions_after: list[dict[str, Any]]
    watchdog: dict[str, Any]
    operational_report: dict[str, Any]
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "blockers": self.blockers,
            "db_path": self.db_path,
            "report_path": self.report_path,
            "json_path": self.json_path,
            "client_order_id": self.client_order_id,
            "submitted": self.submitted,
            "duplicate_skipped": self.duplicate_skipped,
            "order_state": self.order_state,
            "broker_status": self.broker_status,
            "open_orders_before": self.open_orders_before,
            "open_orders_after": self.open_orders_after,
            "positions_before": self.positions_before,
            "positions_after": self.positions_after,
            "watchdog": self.watchdog,
            "operational_report": self.operational_report,
        }


def run_ma_paper_trade_once(
    *,
    config: Config,
    broker: Any,
    symbol: str = "AAPL",
    frequency: str = "1d",
    source: str = "alpaca",
    out_dir: str | Path = "runs/ma_paper_trade",
    bars: pd.DataFrame | None = None,
    fast_window: int = 20,
    slow_window: int = 100,
    trend_filter_active: bool = True,
) -> PaperTradeResult:
    """Submit at most one tiny MA paper order."""

    _validate_submit_gate(config, symbol)
    strategy = config.strategy_name or "dual_ma_crossover"
    data_config = _find_data_config(config, symbol)
    if data_config.asset_class != AssetClass.EQUITY:
        raise ValueError("MA paper trading shakedown is equities-only")

    if bars is None:
        bars = load_bars(data_config.storage_dir, symbol, frequency, source=source)
    bars = _normalize_bars(bars, symbol)
    if bars.empty:
        raise ValueError("No bars available for paper trade")

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / "paper_trade.sqlite"
    report_path = output / "paper_trade_report.md"
    json_path = output / "paper_trade_report.json"

    conn = init_db(db_path)
    logger = EventLogger(conn, environment="paper")
    oms = OMS(broker, conn, logger, environment="paper")
    bar_ts = str(bars.index[-1])
    cycle_id = f"paper-trade-{symbol}-{bar_ts}"

    try:
        if get_engine_state(conn, "halted") == "true":
            reason = get_engine_state(conn, "halt_reason") or "unknown"
            logger.log("ENGINE_HALTED", severity="CRITICAL", cycle_id=cycle_id, message=f"Paper trade blocked: {reason}")
            return _finish_result(conn, db_path, report_path, json_path, None, False, False, None, None, [], [], [], [], [])

        logger.log("ENGINE_HEARTBEAT", cycle_id=cycle_id, bar_timestamp=bar_ts, message=f"Processing bar {bar_ts}")
        account = broker.get_account()
        positions_before = _positions_to_dicts(broker.get_positions())
        open_orders_before = _orders_to_dicts(broker.get_open_orders())
        latest_price = broker.get_price(symbol)
        if latest_price is None or latest_price <= 0:
            raise ValueError(f"No latest price available for {symbol}")

        last_close = float(bars["close"].iloc[-1])
        if last_close > 0:
            ratio = float(latest_price) / last_close
            if ratio < 0.5 or ratio > 1.5:
                raise ValueError(
                    f"Latest broker price {latest_price:.4f} is inconsistent with last stored close {last_close:.4f}"
                )

        signals = generate_signals(
            bars,
            MAParams(
                fast_ma_window=fast_window,
                slow_ma_window=slow_window,
                trend_filter_active=trend_filter_active,
                long_only=True,
            ),
        )
        exposure = float(signals.iloc[-1].get("position", 0.0) or 0.0)
        if exposure < 0 and not config.live_deployment.allow_short:
            exposure = 0.0

        state = PortfolioState(
            cash=account.cash,
            equity=min(account.equity, _strategy_capital(config)),
            high_water_mark=min(account.equity, _strategy_capital(config)),
            positions=_portfolio_positions(positions_before),
        )
        targets = compute_target_positions(
            {symbol: exposure},
            {symbol: float(latest_price)},
            state,
            config.portfolio,
            asset_classes={symbol: data_config.asset_class.value},
        )
        risk = RiskEngine(config.risk_limits).evaluate(
            targets,
            state,
            DrawdownState(high_water_mark=state.equity, current_equity=state.equity),
            strategy_name=strategy,
            current_positions=state.positions,
        )
        risk_target = risk.adjusted_targets[0] if risk.adjusted_targets else targets[0]
        current_qty = _current_qty(symbol, positions_before)
        delta = compute_position_delta(
            risk_target,
            current_qty,
            execution_mode=config.portfolio.execution_mode,
            min_notional_delta=config.portfolio.min_notional_delta,
            min_qty_delta=config.portfolio.min_qty_delta,
            min_pct_position_delta=config.portfolio.min_pct_position_delta,
        )
        logger.log(
            _risk_event(risk.final_decision),
            severity="INFO" if risk.final_decision == RiskDecision.APPROVED else "WARN",
            strategy=strategy,
            symbol=symbol,
            cycle_id=cycle_id,
            bar_timestamp=bar_ts,
            message=f"Risk decision: {risk.final_decision.value}",
            details={"reasons": risk.rejection_reasons + risk.reduction_reasons},
        )

        client_order_id: str | None = None
        duplicate_skipped = False
        broker_status = None
        if delta["action"] != "hold" and risk.final_decision != RiskDecision.REJECTED:
            side = OrderSide.BUY if delta["delta_qty"] > 0 else OrderSide.SELL
            if side == OrderSide.SELL and not config.live_deployment.allow_short and current_qty <= 0:
                raise ValueError("Short/opening sell blocked by paper shakedown config")

            order_type, limit_price = _order_type_and_limit(config, side, float(latest_price))
            notional_cap = min(
                config.live_deployment.max_paper_notional,
                config.live_deployment.max_notional_per_order or config.live_deployment.max_paper_notional,
                _remaining_strategy_capital(config, positions_before),
                abs(float(delta["delta_notional"])),
            )
            if notional_cap >= config.portfolio.min_notional_delta:
                qty = notional_cap / (limit_price or float(latest_price))
                intent = OrderIntent(
                    strategy=strategy,
                    symbol=symbol,
                    asset_class=data_config.asset_class.value,
                    side=side,
                    order_type=order_type,
                    quantity=float(qty),
                    time_in_force=TimeInForce.DAY,
                    limit_price=limit_price,
                    bar_timestamp=bar_ts,
                    correlation_id=cycle_id,
                    client_order_namespace=hashlib.sha256(str(db_path.resolve()).encode()).hexdigest()[:8],
                    version=config.strategy_version,
                )
                before_count = _order_count(conn)
                client_order_id = oms.create_and_submit(intent)
                duplicate_skipped = client_order_id is not None and _order_count(conn) == before_count
                if client_order_id is not None:
                    status = broker.get_order_status(client_order_id)
                    if status is not None:
                        broker_status = status.status
                        logger.log(
                            "BROKER_STATUS_CHECK",
                            strategy=strategy,
                            symbol=symbol,
                            client_order_id=client_order_id,
                            broker_order_id=status.broker_order_id,
                            order_state=status.status,
                            filled_qty=status.filled_qty,
                            remaining_qty=status.remaining_qty,
                            avg_fill_price=status.avg_fill_price,
                            message=f"Broker status {status.status}",
                        )
                        if (
                            config.live_deployment.paper_cancel_open_order_after_submit
                            and status.status in {"ACKNOWLEDGED", "PARTIALLY_FILLED"}
                        ):
                            cancelled = oms.cancel_order(client_order_id)
                            logger.log(
                                "ORDER_CANCEL_STATUS",
                                strategy=strategy,
                                symbol=symbol,
                                client_order_id=client_order_id,
                                message=f"Cancel requested: {cancelled}",
                                details={"cancelled": cancelled},
                            )
                            post_cancel_status = broker.get_order_status(client_order_id)
                            if post_cancel_status is not None:
                                broker_status = post_cancel_status.status
                                logger.log(
                                    "BROKER_STATUS_CHECK",
                                    strategy=strategy,
                                    symbol=symbol,
                                    client_order_id=client_order_id,
                                    broker_order_id=post_cancel_status.broker_order_id,
                                    order_state=post_cancel_status.status,
                                    filled_qty=post_cancel_status.filled_qty,
                                    remaining_qty=post_cancel_status.remaining_qty,
                                    avg_fill_price=post_cancel_status.avg_fill_price,
                                    message=f"Broker status {post_cancel_status.status}",
                                )
        logger.log("ENGINE_HEARTBEAT", cycle_id=cycle_id, bar_timestamp=bar_ts, message=f"Bar {bar_ts} complete - cycle 1")

        positions_after = _positions_to_dicts(broker.get_positions())
        open_orders_after = _orders_to_dicts(broker.get_open_orders())
        order_state = None
        if client_order_id:
            order = get_order(conn, client_order_id)
            order_state = order["order_state"] if order else None
        result = _finish_result(
            conn,
            db_path,
            report_path,
            json_path,
            client_order_id,
            client_order_id is not None and not duplicate_skipped,
            duplicate_skipped,
            order_state,
            broker_status,
            open_orders_before,
            open_orders_after,
            positions_before,
            positions_after,
            _paper_blockers(client_order_id, order_state, broker_status, _order_count(conn) > 0),
        )
        return result
    finally:
        conn.close()


def halt_paper_trading(db_path: str | Path, reason: str = "manual_halt") -> None:
    conn = init_db(db_path)
    try:
        set_engine_state(conn, "halted", "true")
        set_engine_state(conn, "halt_reason", reason)
        EventLogger(conn, environment="paper").log("ENGINE_HALTED", severity="CRITICAL", message=f"Engine halted: {reason}")
    finally:
        conn.close()


def _validate_submit_gate(config: Config, symbol: str) -> None:
    if symbol != "AAPL":
        raise ValueError("Phase 3.6 paper trading is AAPL-only")
    live = config.live_deployment
    if not live.paper_submit_enabled:
        raise ValueError("paper_submit_enabled must be true before paper submits")
    if live.max_paper_notional <= 0:
        raise ValueError("max_paper_notional must be explicitly set before paper submits")
    if live.max_notional_per_order <= 0:
        raise ValueError("max_notional_per_order must be explicitly set before paper submits")
    if _strategy_capital(config) <= 0:
        raise ValueError("max_strategy_capital or strategy_capital_limit must be explicitly set before paper submits")
    if config.risk_limits.max_open_positions != 1:
        raise ValueError("paper shakedown requires max_open_positions = 1")
    if config.portfolio.execution_mode != "signal_transition":
        raise ValueError("paper shakedown requires execution_mode = signal_transition")


def _finish_result(
    conn: sqlite3.Connection,
    db_path: Path,
    report_path: Path,
    json_path: Path,
    client_order_id: str | None,
    submitted: bool,
    duplicate_skipped: bool,
    order_state: str | None,
    broker_status: str | None,
    open_orders_before: list[dict[str, Any]],
    open_orders_after: list[dict[str, Any]],
    positions_before: list[dict[str, Any]],
    positions_after: list[dict[str, Any]],
    blockers: list[str],
) -> PaperTradeResult:
    operational = build_operational_report(conn).to_dict()
    watchdog = HeartbeatWatchdog(WatchdogConfig(db_path=str(db_path))).check_heartbeat()
    all_blockers = list(blockers)
    if not operational.get("passed"):
        all_blockers.extend(f"Operational report: {b}" for b in operational.get("blockers", []))
    if not watchdog.get("alive"):
        all_blockers.append(f"Watchdog heartbeat not alive: {watchdog.get('error') or watchdog.get('alerts')}")
    result = PaperTradeResult(
        passed=not all_blockers,
        db_path=str(db_path),
        report_path=str(report_path),
        json_path=str(json_path),
        client_order_id=client_order_id,
        submitted=submitted,
        duplicate_skipped=duplicate_skipped,
        order_state=order_state,
        broker_status=broker_status,
        open_orders_before=open_orders_before,
        open_orders_after=open_orders_after,
        positions_before=positions_before,
        positions_after=positions_after,
        watchdog=watchdog,
        operational_report=operational,
        blockers=all_blockers,
    )
    _write_reports(result, report_path, json_path)
    return result


def _write_reports(result: PaperTradeResult, report_path: Path, json_path: Path) -> None:
    json_path.write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")
    lines = [
        "# MA Paper Trade Report",
        "",
        f"Status: {'PASS' if result.passed else 'BLOCKED'}",
        f"Client order id: `{result.client_order_id or 'n/a'}`",
        f"Submitted this run: {result.submitted}",
        f"Duplicate skipped: {result.duplicate_skipped}",
        f"Order state: {result.order_state or 'n/a'}",
        f"Broker status: {result.broker_status or 'n/a'}",
        f"Open orders before/after: {len(result.open_orders_before)}/{len(result.open_orders_after)}",
        f"Positions before/after: {len(result.positions_before)}/{len(result.positions_after)}",
        f"Watchdog alive: {result.watchdog.get('alive')}",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- {blocker}" for blocker in result.blockers) if result.blockers else lines.append("- None.")
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _paper_blockers(
    client_order_id: str | None,
    order_state: str | None,
    broker_status: str | None,
    has_known_order: bool,
) -> list[str]:
    blockers: list[str] = []
    if client_order_id is None:
        if not has_known_order:
            blockers.append("No paper order id was produced.")
        return blockers
    if order_state not in {"ACKNOWLEDGED", "FILLED", "PARTIALLY_FILLED", "CANCELLED"}:
        blockers.append(f"Unexpected local order state: {order_state}")
    if broker_status not in {"ACKNOWLEDGED", "FILLED", "PARTIALLY_FILLED", "CANCELLED"}:
        blockers.append(f"Unexpected broker status: {broker_status}")
    return blockers


def _risk_event(decision: RiskDecision) -> str:
    if decision == RiskDecision.REJECTED:
        return "RISK_CHECK_BLOCKED"
    if decision == RiskDecision.REDUCED:
        return "RISK_CHECK_REDUCED"
    return "RISK_CHECK_PASSED"


def _order_type_and_limit(config: Config, side: OrderSide, price: float) -> tuple[OrderType, float | None]:
    if config.live_deployment.paper_order_type == "market":
        return OrderType.MARKET, None
    offset = config.live_deployment.paper_limit_offset_pct
    limit = price * (1 + offset) if side == OrderSide.BUY else price * (1 - offset)
    return OrderType.LIMIT, round(limit, 2)


def _strategy_capital(config: Config) -> float:
    return config.live_deployment.max_strategy_capital or config.live_deployment.strategy_capital_limit


def _remaining_strategy_capital(config: Config, positions: list[dict[str, Any]]) -> float:
    used = sum(abs(float(p.get("market_value") or 0.0)) for p in positions)
    return max(0.0, _strategy_capital(config) - used)


def _order_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM orders_live").fetchone()[0])


def _positions_to_dicts(positions: list[Any]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "symbol": p.symbol,
                "quantity": p.quantity,
                "avg_entry_price": p.avg_entry_price,
                "side": p.side,
                "unrealized_pnl": p.unrealized_pnl,
                "market_value": p.market_value,
            }
            for p in positions
        ],
        key=lambda row: row["symbol"],
    )


def _orders_to_dicts(orders: list[Any]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "client_order_id": o.client_order_id,
                "broker_order_id": o.broker_order_id,
                "status": o.status,
                "filled_qty": o.filled_qty,
                "remaining_qty": o.remaining_qty,
                "rejection_reason": o.rejection_reason,
            }
            for o in orders
        ],
        key=lambda row: row["client_order_id"],
    )


def _current_qty(symbol: str, positions: list[dict[str, Any]]) -> float:
    for position in positions:
        if position["symbol"] == symbol:
            return float(position["quantity"])
    return 0.0


def _portfolio_positions(positions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        p["symbol"]: {
            "qty": float(p["quantity"]),
            "avg_price": float(p["avg_entry_price"]),
            "side": p["side"],
        }
        for p in positions
        if abs(float(p["quantity"])) > 1e-9
    }
