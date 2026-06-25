"""MA paper dry-run.

Read real broker/account state and live quote, run MA sizing/risk logic, log
the would-be order, and never submit anything to the broker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from config.schema import AssetClass, Config
from data.pipeline import load_bars
from execution.base import BrokerAccount, BrokerOrderResponse, BrokerPosition
from monitoring.reports import build_operational_report
from monitoring.watchdog import HeartbeatWatchdog, WatchdogConfig
from portfolio.sizing import PortfolioState, compute_position_delta, compute_target_positions
from risk.engine import DrawdownState, RiskDecision, RiskEngine
from storage.event_logger import EventLogger
from storage.schema import init_db
from strategies.ma.signal import MAParams, generate_signals


class ReadOnlyBroker(Protocol):
    @property
    def name(self) -> str: ...

    def get_account(self) -> BrokerAccount: ...

    def get_positions(self) -> list[BrokerPosition]: ...

    def get_open_orders(self) -> list[BrokerOrderResponse]: ...

    def get_price(self, symbol: str) -> float | None: ...


@dataclass(frozen=True)
class PaperDryRunDecision:
    mode: str
    symbol: str
    strategy: str
    bar_timestamp: str
    signal: float
    target_position: float
    current_position: float
    proposed_delta: float
    risk_decision: str
    would_submit_order: bool
    order_side: str | None
    order_qty: float
    order_type: str
    estimated_notional: float
    reason_if_blocked: str | None
    broker_open_orders_before: list[dict[str, Any]]
    broker_open_orders_after: list[dict[str, Any]]
    broker_positions_before: list[dict[str, Any]]
    broker_positions_after: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "bar_timestamp": self.bar_timestamp,
            "signal": self.signal,
            "target_position": self.target_position,
            "current_position": self.current_position,
            "proposed_delta": self.proposed_delta,
            "risk_decision": self.risk_decision,
            "would_submit_order": self.would_submit_order,
            "order_side": self.order_side,
            "order_qty": self.order_qty,
            "order_type": self.order_type,
            "estimated_notional": self.estimated_notional,
            "reason_if_blocked": self.reason_if_blocked,
            "broker_open_orders_before": self.broker_open_orders_before,
            "broker_open_orders_after": self.broker_open_orders_after,
            "broker_positions_before": self.broker_positions_before,
            "broker_positions_after": self.broker_positions_after,
        }


@dataclass(frozen=True)
class PaperDryRunResult:
    decision: PaperDryRunDecision
    db_path: str
    report_path: str
    json_path: str
    operational_report: dict[str, Any]
    watchdog: dict[str, Any]
    alerts_testable: bool
    blockers: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "blockers": self.blockers,
            "decision": self.decision.to_dict(),
            "db_path": self.db_path,
            "report_path": self.report_path,
            "json_path": self.json_path,
            "operational_report": self.operational_report,
            "watchdog": self.watchdog,
            "alerts_testable": self.alerts_testable,
        }


def run_ma_paper_dry_run(
    *,
    config: Config,
    broker: ReadOnlyBroker,
    symbol: str = "AAPL",
    frequency: str = "1d",
    source: str = "alpaca",
    out_dir: str | Path = "runs/ma_paper_dry_run",
    bars: pd.DataFrame | None = None,
    fast_window: int = 20,
    slow_window: int = 100,
    trend_filter_active: bool = True,
) -> PaperDryRunResult:
    """Run one read-only MA dry-run cycle against paper broker state."""

    strategy = config.strategy_name or "dual_ma_crossover"
    data_config = _find_data_config(config, symbol)
    if data_config.asset_class != AssetClass.EQUITY:
        raise ValueError("MA paper dry-run is equities-only")
    if symbol != "AAPL":
        raise ValueError("Phase 3.5 MA paper dry-run is AAPL-only")

    if bars is None:
        bars = load_bars(data_config.storage_dir, symbol, frequency, source=source)
    bars = _normalize_bars(bars, symbol)
    if bars.empty:
        raise ValueError("No bars available for dry-run")

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / "paper_dry_run.sqlite"
    report_path = output / "paper_dry_run_report.md"
    json_path = output / "paper_dry_run_report.json"
    if db_path.exists():
        db_path.unlink()

    conn = init_db(db_path)
    logger = EventLogger(conn, environment="paper_dry_run")
    cycle_id = f"dryrun-{symbol}-{len(bars)}"
    bar_ts = str(bars.index[-1])

    try:
        logger.log(
            "ENGINE_HEARTBEAT",
            strategy=strategy,
            symbol=symbol,
            asset_class=data_config.asset_class.value,
            broker=broker.name,
            cycle_id=cycle_id,
            bar_timestamp=bar_ts,
            message=f"Processing bar {bar_ts}",
            source="engine.paper_dry_run",
        )

        account = broker.get_account()
        positions_before = _positions_to_dicts(broker.get_positions())
        open_orders_before = _orders_to_dicts(broker.get_open_orders())
        latest_price = broker.get_price(symbol)
        if latest_price is None or latest_price <= 0:
            raise ValueError(f"No latest price available for {symbol}")
        last_close = float(bars["close"].iloc[-1])
        if last_close > 0:
            price_ratio = float(latest_price) / last_close
            if price_ratio < 0.5 or price_ratio > 1.5:
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
        latest_signal = signals.iloc[-1]
        exposure = float(latest_signal.get("position", 0.0) or 0.0)
        signal_value = float(latest_signal.get("signal", 0.0) or 0.0)
        current_qty = _current_qty(symbol, positions_before)
        state = PortfolioState(
            cash=account.cash,
            equity=account.equity,
            high_water_mark=account.equity,
            positions=_portfolio_positions(positions_before),
        )

        targets = compute_target_positions(
            {symbol: exposure},
            {symbol: float(latest_price)},
            state,
            config.portfolio,
            asset_classes={symbol: data_config.asset_class.value},
        )
        target = targets[0]
        risk = RiskEngine(config.risk_limits).evaluate(
            targets,
            state,
            DrawdownState(high_water_mark=account.equity, current_equity=account.equity),
            strategy_name=strategy,
            current_positions=state.positions,
        )
        risk_target = risk.adjusted_targets[0] if risk.adjusted_targets else target
        delta = compute_position_delta(
            risk_target,
            current_qty,
            execution_mode=config.portfolio.execution_mode,
            min_notional_delta=config.portfolio.min_notional_delta,
            min_qty_delta=config.portfolio.min_qty_delta,
            min_pct_position_delta=config.portfolio.min_pct_position_delta,
        )

        blocked_reason = _blocked_reason(risk.final_decision, risk.rejection_reasons, delta)
        would_submit = delta["action"] != "hold" and risk.final_decision != RiskDecision.REJECTED
        order_qty = abs(float(delta["delta_qty"])) if would_submit else 0.0
        order_side = str(delta["action"]) if would_submit else None
        estimated_notional = abs(float(delta["delta_qty"])) * float(latest_price)

        logger.log(
            "SIGNAL_GENERATED",
            strategy=strategy,
            symbol=symbol,
            asset_class=data_config.asset_class.value,
            broker=broker.name,
            account_id=account.account_id,
            cycle_id=cycle_id,
            bar_timestamp=bar_ts,
            message=f"MA signal {signal_value} target exposure {exposure}",
            details={
                "signal": signal_value,
                "target_position": exposure,
                "latest_price": latest_price,
                "fast_window": fast_window,
                "slow_window": slow_window,
                "trend_filter_active": trend_filter_active,
            },
            source="engine.paper_dry_run",
        )
        _log_risk(logger, risk, strategy, symbol, data_config.asset_class.value, broker.name, account.account_id, cycle_id, bar_ts)
        logger.log(
            "ORDER_DRY_RUN",
            strategy=strategy,
            symbol=symbol,
            asset_class=data_config.asset_class.value,
            broker=broker.name,
            account_id=account.account_id,
            cycle_id=cycle_id,
            bar_timestamp=bar_ts,
            side=order_side,
            order_type="market",
            requested_qty=order_qty,
            notional=estimated_notional,
            currency=account.currency,
            message="Dry-run order evaluated; broker submit disabled",
            details={
                "would_submit_order": would_submit,
                "proposed_delta": float(delta["delta_qty"]),
                "risk_decision": risk.final_decision.value,
                "reason_if_blocked": blocked_reason,
            },
            source="engine.paper_dry_run",
        )
        logger.log(
            "ALERT_TEST",
            strategy=strategy,
            symbol=symbol,
            cycle_id=cycle_id,
            bar_timestamp=bar_ts,
            message="Dry-run alert path is log-testable; external alert dispatch disabled",
            details={"telegram_configured": bool(config.monitoring.telegram_alerts)},
            source="engine.paper_dry_run",
        )
        logger.log(
            "ENGINE_HEARTBEAT",
            strategy=strategy,
            symbol=symbol,
            asset_class=data_config.asset_class.value,
            broker=broker.name,
            cycle_id=cycle_id,
            bar_timestamp=bar_ts,
            message=f"Bar {bar_ts} complete - cycle 1",
            source="engine.paper_dry_run",
        )

        positions_after = _positions_to_dicts(broker.get_positions())
        open_orders_after = _orders_to_dicts(broker.get_open_orders())
        decision = PaperDryRunDecision(
            mode="paper_dry_run",
            symbol=symbol,
            strategy=strategy,
            bar_timestamp=bar_ts,
            signal=signal_value,
            target_position=exposure,
            current_position=current_qty,
            proposed_delta=float(delta["delta_qty"]),
            risk_decision=risk.final_decision.value,
            would_submit_order=would_submit,
            order_side=order_side,
            order_qty=order_qty,
            order_type="market",
            estimated_notional=estimated_notional,
            reason_if_blocked=blocked_reason,
            broker_open_orders_before=open_orders_before,
            broker_open_orders_after=open_orders_after,
            broker_positions_before=positions_before,
            broker_positions_after=positions_after,
        )

        operational = build_operational_report(conn)
        watchdog = HeartbeatWatchdog(
            WatchdogConfig(
                heartbeat_timeout_seconds=config.monitoring.watchdog_heartbeat_timeout_seconds,
                db_path=str(db_path),
            )
        ).check_heartbeat()
        blockers = _dry_run_blockers(decision, operational.to_dict(), watchdog)
        result = PaperDryRunResult(
            decision=decision,
            db_path=str(db_path),
            report_path=str(report_path),
            json_path=str(json_path),
            operational_report=operational.to_dict(),
            watchdog=watchdog,
            alerts_testable=True,
            blockers=blockers,
        )
        _write_reports(result, report_path, json_path)
        return result
    finally:
        conn.close()


def _log_risk(
    logger: EventLogger,
    risk: Any,
    strategy: str,
    symbol: str,
    asset_class: str,
    broker: str,
    account_id: str,
    cycle_id: str,
    bar_ts: str,
) -> None:
    event_type = {
        RiskDecision.APPROVED: "RISK_CHECK_PASSED",
        RiskDecision.REDUCED: "RISK_CHECK_REDUCED",
        RiskDecision.REJECTED: "RISK_CHECK_BLOCKED",
    }[risk.final_decision]
    logger.log(
        event_type,
        severity="WARN" if risk.final_decision != RiskDecision.APPROVED else "INFO",
        strategy=strategy,
        symbol=symbol,
        asset_class=asset_class,
        broker=broker,
        account_id=account_id,
        cycle_id=cycle_id,
        bar_timestamp=bar_ts,
        message=f"Risk decision {risk.final_decision.value}",
        details={
            "decisions": [
                {
                    "check_name": d.check_name,
                    "decision": d.decision.value,
                    "message": d.message,
                    "details": d.details,
                }
                for d in risk.decisions
            ],
            "rejection_reasons": risk.rejection_reasons,
            "reduction_reasons": risk.reduction_reasons,
        },
        source="engine.paper_dry_run",
    )


def _write_reports(result: PaperDryRunResult, report_path: Path, json_path: Path) -> None:
    json_path.write_text(json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8")
    d = result.decision
    status = "PASS" if result.passed else "BLOCKED"
    lines = [
        "# MA Paper Dry-Run Report",
        "",
        f"Status: {status}",
        f"Mode: `{d.mode}`",
        f"Symbol: `{d.symbol}`",
        f"Strategy: `{d.strategy}`",
        f"Bar timestamp: `{d.bar_timestamp}`",
        "",
        "## Decision",
        "",
        f"- Signal: {d.signal}",
        f"- Target position: {d.target_position}",
        f"- Current position: {d.current_position}",
        f"- Proposed delta: {d.proposed_delta}",
        f"- Risk decision: {d.risk_decision}",
        f"- Would submit order: {d.would_submit_order}",
        f"- Order side: {d.order_side or 'n/a'}",
        f"- Order qty: {d.order_qty}",
        f"- Order type: {d.order_type}",
        f"- Estimated notional: {d.estimated_notional:.2f}",
        f"- Reason if blocked: {d.reason_if_blocked or 'n/a'}",
        "",
        "## Broker State",
        "",
        f"- Open orders before/after: {len(d.broker_open_orders_before)}/{len(d.broker_open_orders_after)}",
        f"- Positions before/after: {len(d.broker_positions_before)}/{len(d.broker_positions_after)}",
        "",
        "## Gate Checks",
        "",
        f"- Broker open orders unchanged: {d.broker_open_orders_before == d.broker_open_orders_after}",
        f"- Broker positions unchanged: {d.broker_positions_before == d.broker_positions_after}",
        f"- Operational report pass: {result.operational_report.get('passed')}",
        f"- Watchdog heartbeat alive: {result.watchdog.get('alive')}",
        f"- Alerts testable: {result.alerts_testable}",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- {blocker}" for blocker in result.blockers) if result.blockers else lines.append("- None.")
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def _blocked_reason(risk_decision: RiskDecision, rejection_reasons: list[str], delta: dict[str, float]) -> str | None:
    if risk_decision == RiskDecision.REJECTED:
        return "; ".join(rejection_reasons) or "risk rejected"
    if delta["action"] == "hold":
        return "no meaningful target delta"
    return None


def _dry_run_blockers(
    decision: PaperDryRunDecision,
    operational: dict[str, Any],
    watchdog: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if decision.broker_positions_before != decision.broker_positions_after:
        blockers.append("Broker positions changed during dry-run.")
    if decision.broker_open_orders_before != decision.broker_open_orders_after:
        blockers.append("Broker open orders changed during dry-run.")
    if not operational.get("passed"):
        blockers.extend(f"Operational report: {b}" for b in operational.get("blockers", []))
    if not watchdog.get("alive"):
        blockers.append(f"Watchdog heartbeat not alive: {watchdog.get('error') or watchdog.get('alerts')}")
    return blockers


def _find_data_config(config: Config, symbol: str):
    for data_config in config.data:
        if symbol in data_config.symbols:
            return data_config
    raise ValueError(f"Symbol {symbol} is not configured in data sources")


def _normalize_bars(bars: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if isinstance(bars.index, pd.MultiIndex):
        if "symbol" in bars.index.names:
            bars = bars.xs(symbol, level="symbol")
        else:
            bars = bars.droplevel(0)
    return bars.sort_index()


def _positions_to_dicts(positions: list[BrokerPosition]) -> list[dict[str, Any]]:
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


def _orders_to_dicts(orders: list[BrokerOrderResponse]) -> list[dict[str, Any]]:
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
