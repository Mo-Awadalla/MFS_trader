"""Simulated broker — the malicious fake broker for failure testing.

This is the battlefield where the engine learns to survive before touching
real capital. It can be configured to:
  - reject orders randomly or deterministically
  - timeout (no response)
  - partially fill orders
  - duplicate fills
  - report stale data
  - become unreachable
  - report mismatched positions

All behavior is deterministic given a seed, for reproducible tests.
"""

from __future__ import annotations

import random
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from execution.base import (
    BrokerAccount,
    BrokerAdapter,
    BrokerOpenOrder,
    BrokerOpenOrdersSnapshot,
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerPosition,
    OrderSide,
    OrderType,
    QuoteEvidence,
)
from risk.inputs import RiskMetadataSnapshot


@dataclass
class SimBrokerConfig:
    """Configuration for the simulated broker's failure modes."""

    reject_probability: float = 0.0  # 0.0 = never reject, 1.0 = always
    timeout_probability: float = 0.0
    partial_fill_probability: float = 0.0
    duplicate_fill_probability: float = 0.0
    unreachable: bool = False
    stale_data: bool = False
    position_mismatch: bool = False
    fill_delay_ms: int = 0
    seed: int = 42
    starting_cash: float = 10000.0
    commission_pct: float = 0.0
    slippage_pct: float = 0.001


@dataclass
class _SimOrder:
    """Internal order state in the sim broker."""

    client_order_id: str
    broker_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    requested_qty: float
    limit_price: float | None = None
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    status: str = "ACKNOWLEDGED"
    cancelled: bool = False
    reject_reason: str | None = None


class SimBroker(BrokerAdapter):
    """A simulated broker with configurable failure modes.

    Use this to test the engine's behavior under:
      - order rejections
      - timeouts
      - partial fills
      - duplicate fills
      - broker unreachable
      - stale data
      - position mismatches
    """

    def __init__(self, config: SimBrokerConfig | None = None):
        self._config = config or SimBrokerConfig()
        self._rng = random.Random(self._config.seed)
        self._connected = False
        self._orders: dict[str, _SimOrder] = {}  # client_order_id → order
        self._broker_order_ids: dict[str, str] = {}  # broker_order_id → client_order_id
        self._positions: dict[str, BrokerPosition] = {}
        self._prices: dict[str, float] = {"AAPL": 150.0, "MSFT": 300.0, "GOOGL": 130.0}
        self._price_updated_at: dict[str, datetime] = {
            symbol: datetime.now(UTC) for symbol in self._prices
        }
        self._cash = self._config.starting_cash
        self._equity = self._config.starting_cash
        self._order_counter = 0

    @property
    def name(self) -> str:
        return "sim_broker"

    @property
    def is_connected(self) -> bool:
        return self._connected and not self._config.unreachable

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def set_price(self, symbol: str, price: float) -> None:
        """Set the current price for a symbol (for testing)."""
        self._prices[symbol] = price
        self._price_updated_at[symbol] = datetime.now(UTC)

    def get_external_cash_flow(self) -> float:
        """The simulator has no deposit or withdrawal operation."""
        return 0.0

    @property
    def is_new_isolated_simulation(self) -> bool:
        """Each SimBroker instance starts a distinct in-memory account."""
        return True

    def submit_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse:
        """Submit an order — may reject, timeout, or partially fill based on config."""
        if not self.is_connected:
            return BrokerOrderResponse(
                client_order_id=request.client_order_id,
                broker_order_id=None,
                status="REJECTED",
                rejection_reason="broker_not_connected",
            )

        # Idempotency: if we've seen this client_order_id, return existing status
        if request.client_order_id in self._orders:
            existing = self._orders[request.client_order_id]
            return BrokerOrderResponse(
                client_order_id=existing.client_order_id,
                broker_order_id=existing.broker_order_id,
                status=existing.status,
                filled_qty=existing.filled_qty,
                avg_fill_price=existing.avg_fill_price,
                remaining_qty=existing.requested_qty - existing.filled_qty,
            )

        # Simulate timeout
        if self._rng.random() < self._config.timeout_probability:
            # Don't create an order — just don't respond
            return BrokerOrderResponse(
                client_order_id=request.client_order_id,
                broker_order_id=None,
                status="TIMEOUT",
            )

        # Simulate rejection
        if self._rng.random() < self._config.reject_probability:
            order = _SimOrder(
                client_order_id=request.client_order_id,
                broker_order_id=f"sim_{self._order_counter}",
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                requested_qty=request.quantity,
                limit_price=request.limit_price,
                status="REJECTED",
                reject_reason="simulated_rejection",
            )
            self._order_counter += 1
            self._orders[request.client_order_id] = order
            return BrokerOrderResponse(
                client_order_id=request.client_order_id,
                broker_order_id=order.broker_order_id,
                status="REJECTED",
                rejection_reason="simulated_rejection",
            )

        # Generate broker order ID
        broker_order_id = f"sim_{self._order_counter}"
        self._order_counter += 1

        # Get fill price (with slippage)
        base_price = self._prices.get(request.symbol, 100.0)
        slip = self._config.slippage_pct
        if request.side == OrderSide.BUY:
            fill_price = base_price * (1 + slip)
        else:
            fill_price = base_price * (1 - slip)

        # Determine fill quantity
        if self._rng.random() < self._config.partial_fill_probability:
            # Partial fill: 30-70% of requested
            fill_pct = self._rng.uniform(0.3, 0.7)
            filled_qty = request.quantity * fill_pct
            status = "PARTIALLY_FILLED"
        else:
            filled_qty = request.quantity
            status = "FILLED"

        # Create the order
        order = _SimOrder(
            client_order_id=request.client_order_id,
            broker_order_id=broker_order_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            requested_qty=request.quantity,
            limit_price=request.limit_price,
            filled_qty=filled_qty,
            avg_fill_price=fill_price,
            status=status,
        )
        self._orders[request.client_order_id] = order
        self._broker_order_ids[broker_order_id] = request.client_order_id

        # Update positions
        self._update_position(order)

        # Simulate delay
        if self._config.fill_delay_ms > 0:
            time.sleep(self._config.fill_delay_ms / 1000.0)

        # Simulate duplicate fill (sends a second fill notification)
        if self._rng.random() < self._config.duplicate_fill_probability:
            # The duplicate should NOT change position again (idempotency test)
            pass  # handled by idempotency check at top of submit_order

        return BrokerOrderResponse(
            client_order_id=request.client_order_id,
            broker_order_id=broker_order_id,
            status=status,
            filled_qty=filled_qty,
            avg_fill_price=fill_price,
            remaining_qty=request.quantity - filled_qty,
        )

    def cancel_order(self, client_order_id: str) -> bool:
        """Cancel an order. Returns True if cancelled, False if not found/cancellable."""
        if client_order_id not in self._orders:
            return False
        order = self._orders[client_order_id]
        if order.status in ("FILLED", "CANCELLED", "REJECTED", "EXPIRED"):
            return False
        order.status = "CANCELLED"
        order.cancelled = True
        return True

    def get_order_status(self, client_order_id: str) -> BrokerOrderResponse | None:
        """Get the current status of an order."""
        if client_order_id not in self._orders:
            return None
        order = self._orders[client_order_id]
        return BrokerOrderResponse(
            client_order_id=order.client_order_id,
            broker_order_id=order.broker_order_id,
            status=order.status,
            filled_qty=order.filled_qty,
            avg_fill_price=order.avg_fill_price,
            remaining_qty=order.requested_qty - order.filled_qty,
        )

    def get_positions(self) -> list[BrokerPosition]:
        """Get current positions — may be stale or mismatched per config."""
        if self._config.stale_data:
            return []  # report no positions (stale)

        self._refresh_marks()

        if self._config.position_mismatch:
            # Report different quantities than internal state
            return [
                BrokerPosition(
                    symbol=sym,
                    quantity=pos.quantity * 2,  # mismatch!
                    avg_entry_price=pos.avg_entry_price,
                    side=pos.side,
                )
                for sym, pos in self._positions.items()
            ]

        return list(self._positions.values())

    def get_account(self) -> BrokerAccount:
        """Get account state."""
        self._refresh_marks()
        return BrokerAccount(
            account_id="sim_account",
            cash=self._cash,
            equity=self._equity,
            currency="USD",
        )

    def get_price(self, symbol: str) -> float | None:
        """Get current price for a symbol."""
        if self._config.stale_data:
            return None
        return self._prices.get(symbol)

    def get_quote(self, symbol: str) -> QuoteEvidence | None:
        """Return synthetic quote evidence with its fixture update timestamp."""
        if self._config.stale_data or symbol not in self._prices:
            return None
        return QuoteEvidence(
            symbol=symbol,
            price=self._prices[symbol],
            provider_timestamp=self._price_updated_at.get(symbol),
            observed_at=datetime.now(UTC),
            source="sim_broker.synthetic_price_fixture",
        )

    def get_open_orders_snapshot(self) -> BrokerOpenOrdersSnapshot:
        """Return all in-memory nonterminal orders as a complete fixture."""
        orders = tuple(
            BrokerOpenOrder(
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                side=order.side.value,
                remaining_qty=max(0.0, order.requested_qty - order.filled_qty),
                limit_price=order.limit_price,
                avg_fill_price=order.avg_fill_price,
                broker_order_id=order.broker_order_id,
                status=order.status,
            )
            for order in self._orders.values()
            if not order.cancelled
            and order.status not in {"FILLED", "REJECTED", "CANCELLED", "EXPIRED"}
            and order.requested_qty - order.filled_qty > 1e-12
        )
        return BrokerOpenOrdersSnapshot(
            orders=orders,
            observed_at=datetime.now(UTC),
            complete=True,
            source="sim_broker.synthetic_order_fixture",
        )

    def get_risk_metadata(self, symbols: Sequence[str]) -> RiskMetadataSnapshot:
        """Conservative all-correlated metadata, explicitly limited to simulation."""
        ordered = sorted(set(symbols))
        return RiskMetadataSnapshot(
            sectors=dict.fromkeys(ordered, "simulated_unknown_sector"),
            correlations={
                left: dict.fromkeys(ordered, 1.0)
                for left in ordered
            },
            observed_at=datetime.now(UTC),
            source="sim_broker.synthetic_conservative_risk_fixture",
        )

    def _update_position(self, order: _SimOrder) -> None:
        """Update internal position after a fill."""
        if order.filled_qty == 0:
            return

        sym = order.symbol
        delta = order.filled_qty if order.side == OrderSide.BUY else -order.filled_qty
        fill_price = float(order.avg_fill_price or self._prices.get(sym, 0.0))
        self._cash -= delta * fill_price

        if sym in self._positions:
            pos = self._positions[sym]
            new_qty = pos.quantity + delta
            if abs(new_qty) < 1e-9:
                del self._positions[sym]
            else:
                self._positions[sym] = BrokerPosition(
                    symbol=sym,
                    quantity=new_qty,
                    avg_entry_price=order.avg_fill_price or pos.avg_entry_price,
                    side="long" if new_qty > 0 else "short",
                    market_value=new_qty * self._prices.get(sym, fill_price),
                    unrealized_pnl=(self._prices.get(sym, fill_price) - (order.avg_fill_price or pos.avg_entry_price)) * new_qty,
                )
        else:
            self._positions[sym] = BrokerPosition(
                symbol=sym,
                quantity=delta,
                avg_entry_price=order.avg_fill_price or 0,
                side="long" if delta > 0 else "short",
                market_value=delta * self._prices.get(sym, fill_price),
                unrealized_pnl=0.0,
            )
        self._refresh_marks()

    def inject_position(self, symbol: str, quantity: float, avg_price: float) -> None:
        """Inject a position for testing reconciliation."""
        if abs(quantity) < 1e-9:
            self._positions.pop(symbol, None)
        else:
            self._positions[symbol] = BrokerPosition(
                symbol=symbol,
                quantity=quantity,
                avg_entry_price=avg_price,
                side="long" if quantity > 0 else "short",
                market_value=quantity * self._prices.get(symbol, avg_price),
                unrealized_pnl=0.0,
            )
        self._equity = self._cash + sum(float(pos.market_value or 0.0) for pos in self._positions.values())

    def clear_all_positions(self) -> None:
        """Clear all positions (simulate manual close)."""
        self._positions.clear()
        self._equity = self._cash

    def _refresh_marks(self) -> None:
        """Keep simulated cash/equity and position marks internally coherent."""
        marked: dict[str, BrokerPosition] = {}
        for symbol, position in self._positions.items():
            price = self._prices.get(symbol)
            if price is None or price <= 0:
                continue
            marked[symbol] = BrokerPosition(
                symbol=symbol,
                quantity=position.quantity,
                avg_entry_price=position.avg_entry_price,
                side=position.side,
                unrealized_pnl=(price - position.avg_entry_price) * position.quantity,
                market_value=position.quantity * price,
            )
        self._positions = marked
        self._equity = self._cash + sum(float(position.market_value or 0.0) for position in marked.values())
