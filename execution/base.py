"""Broker adapter interface — all brokers (real and simulated) implement this.

The sim_broker and real adapters (Alpaca, CCXT) share this interface so the
engine can swap destinations without code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
