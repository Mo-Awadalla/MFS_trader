"""Broker adapter interface — all brokers (real and simulated) implement this.

The sim_broker and real adapters (Alpaca, CCXT) share this interface so the
engine can swap destinations without code changes.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


@dataclass
class BrokerOrderRequest:
    """Request to submit an order to a broker."""

    client_order_id: str  # deterministic, for idempotency
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: float | None = None
    stop_price: float | None = None
    asset_class: str = "equity"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerOrderResponse:
    """Response from broker after order submission."""

    client_order_id: str
    broker_order_id: str | None
    status: str  # ACKNOWLEDGED | REJECTED | TIMEOUT
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    remaining_qty: float = 0.0
    rejection_reason: str | None = None
    timestamp: str | None = None


@dataclass
class BrokerPosition:
    """A position as reported by the broker."""

    symbol: str
    quantity: float
    avg_entry_price: float
    side: str  # long | short | flat
    unrealized_pnl: float | None = None
    market_value: float | None = None


@dataclass
class BrokerAccount:
    """Account state as reported by the broker."""

    account_id: str
    cash: float
    equity: float
    buying_power: float | None = None
    currency: str = "USD"


@dataclass(frozen=True)
class QuoteEvidence:
    """A quote with distinct provider time and local receive time."""

    symbol: str
    price: float
    provider_timestamp: datetime | None
    observed_at: datetime
    source: str

    def validate(
        self,
        *,
        expected_symbol: str,
        now: datetime | None = None,
        max_provider_age: timedelta = timedelta(seconds=30),
        max_local_age: timedelta = timedelta(seconds=5),
    ) -> None:
        now = now or datetime.now(UTC)
        if self.symbol != expected_symbol:
            raise ValueError("quote symbol does not match the outbound order")
        if not math.isfinite(float(self.price)) or self.price <= 0:
            raise ValueError("quote price is missing, nonfinite, or nonpositive")
        if not self.source.strip():
            raise ValueError("quote source is missing")
        if self.provider_timestamp is None:
            raise ValueError("quote has no provider timestamp")
        for label, value in (("provider", self.provider_timestamp), ("local", self.observed_at), ("validation", now)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{label} quote timestamp must be timezone-aware")
        source_age = now.astimezone(UTC) - self.provider_timestamp.astimezone(UTC)
        local_age = now.astimezone(UTC) - self.observed_at.astimezone(UTC)
        if source_age < -timedelta(seconds=2) or source_age > max_provider_age:
            raise ValueError(f"quote provider timestamp is stale or future-dated ({source_age.total_seconds():.3f}s)")
        if local_age < timedelta(0) or local_age > max_local_age:
            raise ValueError(f"quote local observation is stale or future-dated ({local_age.total_seconds():.3f}s)")


@dataclass(frozen=True)
class BrokerOpenOrder:
    client_order_id: str
    symbol: str
    side: str
    remaining_qty: float
    limit_price: float | None = None
    avg_fill_price: float | None = None
    broker_order_id: str | None = None
    status: str = "ACKNOWLEDGED"


@dataclass(frozen=True)
class BrokerOpenOrdersSnapshot:
    """Open-order read with explicit completeness and local observation time."""

    orders: tuple[BrokerOpenOrder, ...]
    observed_at: datetime
    complete: bool
    source: str

    def validate(self, *, now: datetime | None = None, max_age: timedelta = timedelta(seconds=5)) -> None:
        now = now or datetime.now(UTC)
        if not self.complete:
            raise ValueError("broker open-order snapshot is incomplete")
        if not self.source.strip():
            raise ValueError("broker open-order snapshot has no source")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("open-order observation timestamp must be timezone-aware")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("open-order validation timestamp must be timezone-aware")
        age = now.astimezone(UTC) - self.observed_at.astimezone(UTC)
        if age < timedelta(0) or age > max_age:
            raise ValueError(f"broker open-order snapshot is stale or future-dated ({age.total_seconds():.3f}s)")
        ids: set[str] = set()
        for order in self.orders:
            if not order.client_order_id or order.client_order_id in ids:
                raise ValueError("broker open-order snapshot has a missing or duplicate client order id")
            ids.add(order.client_order_id)
            if not order.symbol or order.side not in {"buy", "sell"}:
                raise ValueError(f"broker open order {order.client_order_id} has invalid symbol or side")
            if not math.isfinite(float(order.remaining_qty)) or order.remaining_qty <= 0:
                raise ValueError(f"broker open order {order.client_order_id} has invalid remaining quantity")
            for price in (order.limit_price, order.avg_fill_price):
                if price is not None and (not math.isfinite(float(price)) or price <= 0):
                    raise ValueError(f"broker open order {order.client_order_id} has invalid price")


class BrokerAdapter(ABC):
    """Abstract base for all broker adapters."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def submit_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse: ...

    @abstractmethod
    def cancel_order(self, client_order_id: str) -> bool: ...

    @abstractmethod
    def get_order_status(self, client_order_id: str) -> BrokerOrderResponse | None: ...

    @abstractmethod
    def get_positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    def get_account(self) -> BrokerAccount: ...

    @abstractmethod
    def get_price(self, symbol: str) -> float | None: ...

    def get_quote(self, symbol: str) -> QuoteEvidence | None:
        """Return timestamped quote evidence; legacy floats are not authorization evidence."""
        return None

    def get_open_orders_snapshot(self) -> BrokerOpenOrdersSnapshot:
        """Return a complete broker open-order view or fail closed."""
        raise RuntimeError(f"{self.name} does not provide a complete open-order snapshot")
