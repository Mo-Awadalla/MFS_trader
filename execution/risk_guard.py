"""Final outbound risk recheck against fresh broker and metadata evidence."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from execution.base import BrokerAdapter, BrokerOpenOrdersSnapshot, OrderSide, QuoteEvidence
from execution.evidence import merge_pending_orders
from execution.oms import OrderIntent
from portfolio.accounting import AccountRiskState, PortfolioSnapshot
from portfolio.sizing import PortfolioState, TargetPosition
from risk.engine import DrawdownState, RiskEngine
from risk.inputs import RiskMetadataSnapshot
from storage.repository import get_open_orders

RiskMetadataReader = Callable[[Sequence[str]], RiskMetadataSnapshot]
RiskStateReader = Callable[[], tuple[AccountRiskState, datetime]]


class OutboundRiskGuard:
    """Reject an OMS order unless a fresh, complete book still permits it."""

    def __init__(
        self,
        *,
        broker: BrokerAdapter,
        conn: sqlite3.Connection,
        risk_engine: RiskEngine,
        strategy_name: str,
        risk_state_reader: RiskStateReader,
        metadata_reader: RiskMetadataReader,
        allow_short: bool,
        equity_cap: float | None = None,
    ) -> None:
        self._broker = broker
        self._conn = conn
        self._risk = risk_engine
        self._strategy = strategy_name
        self._risk_state_reader = risk_state_reader
        self._metadata_reader = metadata_reader
        self._allow_short = allow_short
        self._equity_cap = equity_cap

    def __call__(
        self,
        intent: OrderIntent,
        quote: QuoteEvidence,
        broker_orders: BrokerOpenOrdersSnapshot,
    ) -> None:
        started = datetime.now(UTC)
        quote.validate(expected_symbol=intent.symbol, max_local_age=timedelta(seconds=5))
        broker_orders.validate(max_age=timedelta(seconds=5))

        account = self._broker.get_account()
        positions = self._broker.get_positions()
        observed_at = datetime.now(UTC)
        pending = merge_pending_orders(broker_orders, get_open_orders(self._conn))
        for order in pending:
            if float(order.get("last_price") or 0.0) <= 0:
                pending_quote = self._broker.get_quote(str(order.get("symbol", "")))
                if pending_quote is None:
                    raise ValueError("fresh quote evidence is unavailable for a pending order")
                pending_quote.validate(expected_symbol=str(order["symbol"]))
                order["last_price"] = pending_quote.price

        snapshot = PortfolioSnapshot.from_broker(
            self._broker.name,
            account,
            positions,
            pending,
            pending_orders_complete=broker_orders.complete,
            pending_orders_observed_at=broker_orders.observed_at,
            pending_orders_source=broker_orders.source,
            observed_at=observed_at,
            external_cash_flow=0.0,
        )
        snapshot.validate(max_age=timedelta(seconds=5))
        if (datetime.now(UTC) - started).total_seconds() > 5.0:
            raise ValueError("final broker truth reads exceeded the five second window")

        account_risk, risk_observed_at = self._risk_state_reader()
        risk_age = datetime.now(UTC) - risk_observed_at.astimezone(UTC)
        if risk_age < timedelta(0) or risk_age > timedelta(seconds=60):
            raise ValueError("durable loss baselines are stale at the outbound boundary")

        current: dict[str, dict[str, Any]] = {}
        for position in positions:
            if position.quantity == 0:
                continue
            if position.market_value is None or position.quantity == 0:
                raise ValueError(f"position {position.symbol} has no current marked value")
            current[position.symbol] = {
                "quantity": position.quantity,
                "qty": position.quantity,
                "side": position.side,
                "mark_price": abs(float(position.market_value) / position.quantity),
            }

        equity = account.equity
        if self._equity_cap is not None:
            equity = min(equity, self._equity_cap)
        state = PortfolioState(
            cash=account.cash,
            equity=equity,
            high_water_mark=max(account_risk.high_water_mark, account.equity),
            positions={
                symbol: {"qty": row["quantity"], "avg_price": row["mark_price"], "side": row["side"]}
                for symbol, row in current.items()
            },
        )
        drawdown = DrawdownState(
            daily_pnl=account.equity - account_risk.daily_baseline - account_risk.daily_external_cash_flow,
            weekly_pnl=account.equity - account_risk.weekly_baseline - account_risk.weekly_external_cash_flow,
            monthly_pnl=account.equity - account_risk.monthly_baseline - account_risk.monthly_external_cash_flow,
            high_water_mark=max(account_risk.high_water_mark, account.equity),
            current_equity=account.equity,
            daily_baseline=account_risk.daily_baseline,
            weekly_baseline=account_risk.weekly_baseline,
            monthly_baseline=account_risk.monthly_baseline,
        )

        current_qty = float(current.get(intent.symbol, {}).get("quantity", 0.0))
        signed_delta = intent.quantity if intent.side == OrderSide.BUY else -intent.quantity
        desired_qty = current_qty + signed_delta
        if not self._allow_short and desired_qty < -1e-9:
            raise ValueError("outbound order would create a short position")
        target = TargetPosition(
            symbol=intent.symbol,
            asset_class=intent.asset_class,
            side="long" if desired_qty > 1e-9 else ("short" if desired_qty < -1e-9 else "flat"),
            target_qty=desired_qty,
            target_notional=abs(desired_qty) * quote.price,
            current_price=quote.price,
        )

        symbols = set(current)
        symbols.update(str(order["symbol"]) for order in pending)
        symbols.add(intent.symbol)
        metadata = self._metadata_reader(sorted(symbols))
        metadata.validate(sorted(symbols))
        evaluation = self._risk.evaluate(
            [target],
            state,
            drawdown,
            strategy_name=self._strategy,
            current_positions=current,
            pending_orders=pending,
            sector_map=metadata.sectors,
            correlation_matrix=metadata.correlations,
        )
        if evaluation.is_rejected:
            reason = "; ".join(evaluation.rejection_reasons) or "risk evaluation rejected the outbound target"
            raise ValueError(f"outbound risk recheck rejected order: {reason}")
        if (
            len(evaluation.adjusted_targets) != 1
            or evaluation.adjusted_targets[0].symbol != intent.symbol
            or abs(evaluation.adjusted_targets[0].target_qty - desired_qty) > 1e-9
        ):
            raise ValueError("outbound risk recheck would reduce or change the requested quantity")
