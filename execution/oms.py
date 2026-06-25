"""Order Management System (OMS) — ties state machine, broker, and storage together.

Responsibilities:
  - Create order intents (with deterministic client_order_id)
  - Submit to broker (only after DB intent write succeeds)
  - Track order state transitions
  - Handle timeouts via reconciliation (not blind retry)
  - Update positions after fills
  - Log every event

Critical rules:
  - DB intent write fails → block order (no broker submit)
  - DB write fails after broker ACK → freeze new orders
  - Timeout → reconcile by client_order_id, never retry blindly
  - Rejected order → no position change
  - Same client_order_id → idempotent (no duplicate)
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

import structlog

from execution.base import (
    BrokerAdapter,
    BrokerOrderRequest,
    BrokerOrderResponse,
    OrderSide,
    OrderType,
    TimeInForce,
)
from execution.order_state_machine import (
    IllegalTransitionError,
    OrderState,
    ReconciliationStatus,
    is_transition_allowed,
    reconcile_timeout,
    validate_transition,
)
from storage.event_logger import EventLogger, utc_now_iso
from storage.repository import (
    get_order,
    update_order_state,
    upsert_order,
    upsert_position,
)

log = structlog.get_logger(__name__)


@dataclass
class OrderIntent:
    """An intent to place an order — created before broker submission."""

    strategy: str
    symbol: str
    asset_class: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: float | None = None
    stop_price: float | None = None
    bar_timestamp: str | None = None
    correlation_id: str | None = None
    client_order_namespace: str = ""
    version: str = "0.0.0"


class OMS:
    """Order Management System — orchestrates order lifecycle.

    Flow:
        1. create_intent() → deterministic client_order_id
        2. log intent to DB (must succeed)
        3. submit_to_broker() → broker response
        4. update state + position
        5. log every transition
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        conn: sqlite3.Connection,
        event_logger: EventLogger,
        environment: str = "paper",
    ):
        self._broker = broker
        self._conn = conn
        self._logger = event_logger
        self._environment = environment
        self._frozen = False  # freeze new orders on DB failure

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def freeze(self, reason: str) -> None:
        """Freeze new order submission (after DB failure, etc.)."""
        self._frozen = True
        self._logger.log("ENGINE_HALTED", severity="CRITICAL", message=f"OMS frozen: {reason}")

    def unfreeze(self) -> None:
        """Manually unfreeze the OMS."""
        self._frozen = False

    def generate_client_order_id(
        self,
        strategy: str,
        symbol: str,
        bar_timestamp: str,
        target_hash: str,
        namespace: str = "",
    ) -> str:
        """Generate a deterministic client_order_id.

        Format: {strategy}_{symbol}_{timestamp}_{hash}
        Deterministic = same inputs always produce same ID = idempotency.
        """
        raw = f"{strategy}_{symbol}_{namespace}_{bar_timestamp}_{target_hash}"
        hash_suffix = hashlib.sha256(raw.encode()).hexdigest()[:8]
        safe_symbol = symbol.replace("/", "_")
        safe_strategy = "".join(ch for ch in strategy if ch.isalnum())[:12] or "strategy"
        safe_ts = "".join(ch for ch in bar_timestamp if ch.isdigit())[:14] or "ts"
        ns = "".join(ch for ch in namespace if ch.isalnum())[:8]
        parts = [safe_strategy, safe_symbol, safe_ts]
        if ns:
            parts.append(ns)
        parts.append(hash_suffix)
        return "_".join(parts)

    def create_and_submit(self, intent: OrderIntent) -> str | None:
        """Create an order intent, log to DB, and submit to broker.

        Returns client_order_id if successful, None if blocked/frozen.
        """
        if self._frozen:
            self._logger.log(
                "ORDER_INTENT",
                severity="WARN",
                strategy=intent.strategy,
                symbol=intent.symbol,
                order_state=OrderState.BLOCKED_BY_RISK.value,
                message="OMS frozen — order blocked",
            )
            return None

        # Generate deterministic client_order_id
        target_hash = hashlib.sha256(
            f"{intent.side}:{intent.quantity}:{intent.limit_price}:{intent.stop_price}".encode()
        ).hexdigest()[:8]
        bar_ts = intent.bar_timestamp or utc_now_iso()
        client_order_id = self.generate_client_order_id(
            intent.strategy,
            intent.symbol,
            bar_ts,
            target_hash,
            namespace=intent.client_order_namespace,
        )

        # Check if order already exists (idempotency)
        existing = get_order(self._conn, client_order_id)
        if existing is not None:
            self._logger.log(
                "ORDER_INTENT",
                strategy=intent.strategy,
                symbol=intent.symbol,
                client_order_id=client_order_id,
                message="Order already exists — idempotent skip",
            )
            return client_order_id

        # 1. Log INTENT to DB (must succeed before broker submit)
        try:
            self._log_intent(client_order_id, intent, OrderState.INTENDED)
        except Exception as e:
            self._logger.log(
                "DB_WRITE_FAILED",
                severity="CRITICAL",
                strategy=intent.strategy,
                symbol=intent.symbol,
                exception=str(e),
                message="DB intent write failed — blocking order",
            )
            self.freeze("db_intent_write_failed")
            return None

        # 2. Submit to broker
        request = BrokerOrderRequest(
            client_order_id=client_order_id,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            time_in_force=intent.time_in_force,
            limit_price=intent.limit_price,
            stop_price=intent.stop_price,
            asset_class=intent.asset_class,
        )

        try:
            response = self._broker.submit_order(request)
        except Exception as e:
            self._logger.log(
                "BROKER_TIMEOUT",
                severity="ERROR",
                strategy=intent.strategy,
                symbol=intent.symbol,
                client_order_id=client_order_id,
                exception=str(e),
                message="Broker submit threw exception",
            )
            self._update_order_state(client_order_id, OrderState.TIMEOUT, intent)
            return client_order_id

        # 3. Process response
        self._process_broker_response(client_order_id, response, intent)

        return client_order_id

    def _log_intent(self, client_order_id: str, intent: OrderIntent, state: OrderState) -> None:
        """Log the order intent to DB (orders_live + events)."""
        import math as _math
        now = utc_now_iso()
        qty_raw = intent.quantity
        qty = 0.0 if qty_raw is None or _math.isnan(float(qty_raw)) else float(qty_raw)
        order_row = {
            "client_order_id": client_order_id,
            "broker_order_id": None,
            "broker": self._broker.name,
            "account_id": None,
            "environment": self._environment,
            "strategy": intent.strategy,
            "symbol": intent.symbol,
            "asset_class": intent.asset_class,
            "side": intent.side.value,
            "order_type": intent.order_type.value,
            "time_in_force": intent.time_in_force.value,
            "limit_price": intent.limit_price,
            "stop_price": intent.stop_price,
            "requested_qty": qty,
            "filled_qty": 0.0,
            "remaining_qty": qty,
            "avg_fill_price": None,
            "notional": None,
            "currency": "USD",
            "order_state": state.value,
            "reconciliation_status": ReconciliationStatus.NOT_CHECKED.value,
            "created_at": now,
            "updated_at": now,
            "bar_timestamp": intent.bar_timestamp,
            "correlation_id": intent.correlation_id,
            "version": intent.version,
        }
        upsert_order(self._conn, order_row)

        self._logger.log(
            "ORDER_INTENT",
            strategy=intent.strategy,
            symbol=intent.symbol,
            client_order_id=client_order_id,
            order_state=state.value,
            side=intent.side.value,
            order_type=intent.order_type.value,
            requested_qty=intent.quantity,
            bar_timestamp=intent.bar_timestamp,
        )

    def _process_broker_response(
        self,
        client_order_id: str,
        response: BrokerOrderResponse,
        intent: OrderIntent,
    ) -> None:
        """Process the broker's response and update state."""
        # Transition through SUBMITTING first (intent was already logged as INTENDED)
        existing = get_order(self._conn, client_order_id)
        if existing and existing["order_state"] == OrderState.INTENDED.value:
            self._update_order_state(client_order_id, OrderState.SUBMITTING, intent)

        if response.status == "TIMEOUT":
            self._update_order_state(client_order_id, OrderState.TIMEOUT, intent)
            self._logger.log(
                "BROKER_TIMEOUT",
                severity="ERROR",
                strategy=intent.strategy,
                symbol=intent.symbol,
                client_order_id=client_order_id,
                message="Broker timeout — will reconcile on next cycle",
            )
            return

        if response.status == "REJECTED":
            self._update_order_state(
                client_order_id,
                OrderState.REJECTED,
                intent,
                broker_order_id=response.broker_order_id,
            )
            self._logger.log(
                "BROKER_REJECT",
                severity="WARN",
                strategy=intent.strategy,
                symbol=intent.symbol,
                client_order_id=client_order_id,
                message=f"Rejected: {response.rejection_reason}",
            )
            return

        # ACKNOWLEDGED or FILLED or PARTIALLY_FILLED
        if response.status == "FILLED":
            new_state = OrderState.FILLED
        elif response.status == "PARTIALLY_FILLED":
            new_state = OrderState.PARTIALLY_FILLED
        else:
            new_state = OrderState.ACKNOWLEDGED

        self._update_order_state(
            client_order_id,
            new_state,
            intent,
            broker_order_id=response.broker_order_id,
            filled_qty=response.filled_qty,
            avg_fill_price=response.avg_fill_price,
            remaining_qty=response.remaining_qty,
        )

        # Update position if filled
        if response.filled_qty > 0:
            self._update_position(intent, response)

        self._logger.log(
            "BROKER_ACK" if new_state == OrderState.ACKNOWLEDGED else "ORDER_FILLED",
            strategy=intent.strategy,
            symbol=intent.symbol,
            client_order_id=client_order_id,
            broker_order_id=response.broker_order_id,
            order_state=new_state.value,
            filled_qty=response.filled_qty,
            avg_fill_price=response.avg_fill_price,
        )

    def _update_order_state(
        self,
        client_order_id: str,
        new_state: OrderState,
        intent: OrderIntent,
        *,
        broker_order_id: str | None = None,
        filled_qty: float | None = None,
        avg_fill_price: float | None = None,
        remaining_qty: float | None = None,
    ) -> None:
        """Update order state in DB, validating transitions."""
        existing = get_order(self._conn, client_order_id)
        if existing is None:
            log.error("order_not_found", client_order_id=client_order_id)
            return

        old_state = OrderState(existing["order_state"])
        try:
            validate_transition(old_state, new_state)
        except IllegalTransitionError as e:
            log.error("illegal_transition", error=str(e), client_order_id=client_order_id)
            self._logger.log(
                "EXCEPTION_HARD",
                severity="ERROR",
                strategy=intent.strategy,
                symbol=intent.symbol,
                client_order_id=client_order_id,
                exception=str(e),
                message=f"Illegal transition: {old_state} → {new_state}",
            )
            return

        update_order_state(
            self._conn,
            client_order_id,
            new_state.value,
            filled_qty=filled_qty,
            remaining_qty=remaining_qty,
            avg_fill_price=avg_fill_price,
            broker_order_id=broker_order_id,
        )

    def _update_position(self, intent: OrderIntent, response: BrokerOrderResponse) -> None:
        """Update position after a fill."""
        delta = response.filled_qty if intent.side == OrderSide.BUY else -response.filled_qty

        from storage.repository import get_positions

        positions = get_positions(self._conn, strategy=intent.strategy)
        existing = next((p for p in positions if p["symbol"] == intent.symbol), None)

        if existing:
            new_qty = existing["quantity"] + delta
            if abs(new_qty) < 1e-9:
                new_qty = 0.0
        else:
            new_qty = delta

        side = "long" if new_qty > 0 else ("short" if new_qty < 0 else "flat")
        upsert_position(
            self._conn,
            {
                "environment": self._environment,
                "strategy": intent.strategy,
                "symbol": intent.symbol,
                "asset_class": intent.asset_class,
                "broker": self._broker.name,
                "side": side,
                "quantity": new_qty,
                "avg_entry_price": response.avg_fill_price,
                "realized_pnl": 0.0,
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            },
        )

    def reconcile_timeout(self, client_order_id: str, intent: OrderIntent) -> OrderState:
        """Reconcile a timed-out order by querying the broker.

        Does NOT retry blindly. Queries broker status and updates state.
        """
        broker_response = self._broker.get_order_status(client_order_id)

        if broker_response is None:
            # Broker has no record of this order
            new_state = OrderState.UNKNOWN
            self._logger.log(
                "ORDER_UNKNOWN",
                severity="CRITICAL",
                strategy=intent.strategy,
                symbol=intent.symbol,
                client_order_id=client_order_id,
                message="Broker has no record — manual review required",
            )
        else:
            new_state = reconcile_timeout(
                broker_status=broker_response.status,
                broker_filled_qty=broker_response.filled_qty,
                requested_qty=intent.quantity,
            )

        self._update_order_state(
            client_order_id,
            new_state,
            intent,
            filled_qty=broker_response.filled_qty if broker_response else 0,
            avg_fill_price=broker_response.avg_fill_price if broker_response else None,
        )

        return new_state

    def cancel_order(self, client_order_id: str) -> bool:
        """Request cancellation of an open order."""
        existing = get_order(self._conn, client_order_id)
        if existing is None:
            return False

        old_state = OrderState(existing["order_state"])
        if not is_transition_allowed(old_state, OrderState.CANCEL_REQUESTED):
            return False

        intent = OrderIntent(
            strategy=existing["strategy"],
            symbol=existing["symbol"],
            asset_class=existing["asset_class"],
            side=OrderSide(existing["side"]),
            order_type=OrderType(existing["order_type"]),
            quantity=existing["requested_qty"],
        )
        self._update_order_state(client_order_id, OrderState.CANCEL_REQUESTED, intent)
        success = self._broker.cancel_order(client_order_id)
        if success:
            self._update_order_state(
                client_order_id,
                OrderState.CANCELLED,
                intent,
            )
            self._logger.log(
                "ORDER_CANCELLED",
                strategy=existing["strategy"],
                symbol=existing["symbol"],
                client_order_id=client_order_id,
            )
        return success
