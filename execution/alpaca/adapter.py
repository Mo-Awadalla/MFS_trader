"""Alpaca broker adapter — US equities via Alpaca Markets REST API v2.

Implements the BrokerAdapter interface. Maps Alpaca's API responses into
our internal order state machine and position model.

Alpaca-specific behavior handled here:
  - client_order_id passed through to Alpaca for idempotency
  - order status mapping (new/filled/partially_filled/canceled/replaced/...)
  - position side derivation (qty > 0 = long, qty < 0 = short)
  - paper vs live URL selection
  - rate limit handling (429 → retry with backoff)
  - error code mapping to REJECTED/TIMEOUT/UNKNOWN
"""

from __future__ import annotations

import time
from typing import Any

import requests
import structlog

from execution.base import (
    BrokerAccount,
    BrokerAdapter,
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerPosition,
)

log = structlog.get_logger(__name__)

# Alpaca order status → our internal status string
ALPACA_STATUS_MAP: dict[str, str] = {
    "new": "ACKNOWLEDGED",
    "accepted": "ACKNOWLEDGED",
    "accepted_for_bidding": "ACKNOWLEDGED",
    "pending_new": "ACKNOWLEDGED",
    "replaced": "ACKNOWLEDGED",
    "partially_filled": "PARTIALLY_FILLED",
    "filled": "FILLED",
    "done_for_day": "ACKNOWLEDGED",
    "canceled": "CANCELLED",
    "cancelled": "CANCELLED",
    "pending_cancel": "CANCEL_REQUESTED",
    "pending_replace": "ACKNOWLEDGED",
    "rejected": "REJECTED",
    "stopped": "FILLED",
    "stopped_out": "CANCELLED",
    "calculated": "ACKNOWLEDGED",
    "expired": "EXPIRED",
}

# Our internal TIF → Alpaca TIF
TIF_MAP: dict[str, str] = {
    "day": "day",
    "gtc": "gtc",
    "ioc": "ioc",
    "fok": "fok",
    "opg": "opg",
    "cls": "cls",
}

# Our order type → Alpaca order type
ORDER_TYPE_MAP: dict[str, str] = {
    "market": "market",
    "limit": "limit",
    "stop": "stop",
    "stop_limit": "stop_limit",
}

DEFAULT_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 0.5  # seconds


class AlpacaAdapter(BrokerAdapter):
    """Alpaca Markets broker adapter for US equities.

    Args:
        api_key: Alpaca API key (from env var).
        api_secret: Alpaca API secret (from env var).
        base_url: Trading API base URL (paper or live).
        data_url: Market data API base URL.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://paper-api.alpaca.markets",
        data_url: str = "https://data.alpaca.markets",
    ):
        self._api_key = api_key
        self._api_secret = api_secret
        self._base_url = base_url.rstrip("/")
        self._data_url = data_url.rstrip("/")
        self._connected = False
        self._session: requests.Session | None = None

    @property
    def name(self) -> str:
        return "alpaca"

    @property
    def is_connected(self) -> bool:
        return self._connected and self._session is not None

    def connect(self) -> None:
        """Initialize HTTP session and verify credentials."""
        self._session = requests.Session()
        self._session.headers.update(
            {
                "APCA-API-KEY-ID": self._api_key,
                "APCA-API-SECRET-KEY": self._api_secret,
                "Content-Type": "application/json",
            }
        )
        # Verify connection by fetching account
        try:
            resp = self._request("GET", "/v2/account")
            if resp.status_code == 200:
                self._connected = True
                log.info("alpaca_connected", base_url=self._base_url)
            else:
                log.error("alpaca_connect_failed", status=resp.status_code, body=resp.text)
                self._connected = False
        except Exception as e:
            log.error("alpaca_connect_error", error=str(e))
            self._connected = False

    def disconnect(self) -> None:
        if self._session:
            self._session.close()
            self._session = None
        self._connected = False

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """Make an HTTP request to the Alpaca API with retry logic."""
        url = f"{self._base_url}{path}"
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)

        for attempt in range(MAX_RETRIES):
            try:
                resp = self._session.request(method, url, **kwargs)
                # Retry on 429 (rate limit)
                if resp.status_code == 429 and attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF * (2 ** attempt)
                    log.warning("alpaca_rate_limited", retry=attempt + 1, wait=wait)
                    time.sleep(wait)
                    continue
                return resp
            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF * (2 ** attempt)
                    log.warning("alpaca_timeout", retry=attempt + 1, wait=wait)
                    time.sleep(wait)
                    continue
                raise
            except requests.exceptions.ConnectionError:
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF * (2 ** attempt)
                    log.warning("alpaca_connection_error", retry=attempt + 1, wait=wait)
                    time.sleep(wait)
                    continue
                raise
        # Should not reach here, but return last response
        return resp  # type: ignore[return-value]

    def submit_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse:
        """Submit an order to Alpaca."""
        if not self.is_connected:
            return BrokerOrderResponse(
                client_order_id=request.client_order_id,
                broker_order_id=None,
                status="REJECTED",
                rejection_reason="not_connected",
            )

        payload: dict[str, Any] = {
            "symbol": request.symbol,
            "qty": str(request.quantity),
            "side": request.side.value,
            "type": ORDER_TYPE_MAP.get(request.order_type.value, "market"),
            "time_in_force": TIF_MAP.get(request.time_in_force.value, "day"),
            "client_order_id": request.client_order_id,
        }

        if request.limit_price is not None:
            payload["limit_price"] = str(request.limit_price)
        if request.stop_price is not None:
            payload["stop_price"] = str(request.stop_price)

        try:
            resp = self._request("POST", "/v2/orders", json=payload)
        except Exception as e:
            log.error("alpaca_submit_error", error=str(e), symbol=request.symbol)
            return BrokerOrderResponse(
                client_order_id=request.client_order_id,
                broker_order_id=None,
                status="TIMEOUT",
                rejection_reason=str(e),
            )

        if resp.status_code in (200, 201):
            data = resp.json()
            return self._parse_order_response(data, request.client_order_id)
        else:
            error_body = resp.text
            log.warning(
                "alpaca_order_rejected",
                status=resp.status_code,
                body=error_body,
                symbol=request.symbol,
            )
            return BrokerOrderResponse(
                client_order_id=request.client_order_id,
                broker_order_id=None,
                status="REJECTED",
                rejection_reason=f"HTTP {resp.status_code}: {error_body}",
            )

    def cancel_order(self, client_order_id: str) -> bool:
        """Cancel an order by client_order_id.

        First looks up the order to get the broker's order_id,
        then cancels by that broker-assigned ID.
        """
        if not self.is_connected:
            return False

        try:
            # First get the order to find the broker's order ID
            status = self.get_order_status(client_order_id)
            if status is None or status.broker_order_id is None:
                log.warning("alpaca_cancel_not_found", client_order_id=client_order_id)
                return False

            # Cancel by broker-assigned order ID
            resp = self._request("DELETE", f"/v2/orders/{status.broker_order_id}")
            if resp.status_code in (200, 204):
                log.info("alpaca_cancel_ok", client_order_id=client_order_id, broker_order_id=status.broker_order_id)
                return True
            else:
                log.warning("alpaca_cancel_failed", status=resp.status_code, body=resp.text)
                return False
        except Exception as e:
            log.error("alpaca_cancel_error", error=str(e), client_order_id=client_order_id)
            return False

    def get_order_status(self, client_order_id: str) -> BrokerOrderResponse | None:
        """Get order status by client_order_id."""
        if not self.is_connected:
            return None

        try:
            resp = self._request(
                "GET", f"/v2/orders:by_client_order_id?client_order_id={client_order_id}"
            )
        except Exception as e:
            log.error("alpaca_status_error", error=str(e), client_order_id=client_order_id)
            return None

        if resp.status_code == 200:
            data = resp.json()
            return self._parse_order_response(data, client_order_id)
        elif resp.status_code == 404:
            return None  # order not found
        else:
            log.warning("alpaca_status_failed", status=resp.status_code)
            return None

    def get_positions(self) -> list[BrokerPosition]:
        """Fetch all open positions from Alpaca."""
        if not self.is_connected:
            return []

        try:
            resp = self._request("GET", "/v2/positions")
            if resp.status_code == 200:
                positions = resp.json()
                return [self._parse_position(p) for p in positions]
            else:
                log.warning("alpaca_positions_failed", status=resp.status_code)
                return []
        except Exception as e:
            log.error("alpaca_positions_error", error=str(e))
            return []

    def get_account(self) -> BrokerAccount:
        """Fetch account state from Alpaca."""
        if not self.is_connected:
            return BrokerAccount(account_id="unknown", cash=0, equity=0)

        try:
            resp = self._request("GET", "/v2/account")
            if resp.status_code == 200:
                data = resp.json()
                return BrokerAccount(
                    account_id=data.get("id", "unknown"),
                    cash=float(data.get("cash", 0)),
                    equity=float(data.get("equity", 0)),
                    buying_power=float(data.get("buying_power", 0)) if data.get("buying_power") else None,
                    currency="USD",
                )
            else:
                log.warning("alpaca_account_failed", status=resp.status_code)
                return BrokerAccount(account_id="unknown", cash=0, equity=0)
        except Exception as e:
            log.error("alpaca_account_error", error=str(e))
            return BrokerAccount(account_id="unknown", cash=0, equity=0)

    def get_price(self, symbol: str) -> float | None:
        """Get latest price for a symbol from Alpaca data API."""
        if not self.is_connected or not self._session:
            return None

        try:
            url = f"{self._data_url}/v2/stocks/{symbol}/quotes/latest"
            resp = self._session.get(url, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                quote = data.get("quote", data)  # handle both wrapped and unwrapped
                # Alpaca uses 'bp' (bid price) and 'ap' (ask price)
                bid = float(quote.get("bp", quote.get("bid_price", 0)))
                ask = float(quote.get("ap", quote.get("ask_price", 0)))
                if bid > 0 and ask > 0:
                    return (bid + ask) / 2
                elif ask > 0:
                    return ask
                elif bid > 0:
                    return bid
                return None
            else:
                log.warning("alpaca_price_failed", symbol=symbol, status=resp.status_code)
                return None
        except Exception as e:
            log.error("alpaca_price_error", symbol=symbol, error=str(e))
            return None

    def _parse_order_response(self, data: dict[str, Any], client_order_id: str) -> BrokerOrderResponse:
        """Parse Alpaca order JSON into BrokerOrderResponse."""
        alpaca_status = data.get("status", "new")
        internal_status = ALPACA_STATUS_MAP.get(alpaca_status, "UNKNOWN")

        filled_qty = float(data.get("filled_qty", 0))
        avg_fill_price = data.get("filled_avg_price")
        if avg_fill_price is not None:
            avg_fill_price = float(avg_fill_price)

        qty = float(data.get("qty", 0))
        remaining = qty - filled_qty

        return BrokerOrderResponse(
            client_order_id=client_order_id,
            broker_order_id=data.get("id"),
            status=internal_status,
            filled_qty=filled_qty,
            avg_fill_price=avg_fill_price,
            remaining_qty=remaining,
            rejection_reason=data.get("reject_reason"),
            timestamp=data.get("submitted_at"),
        )

    def _parse_position(self, data: dict[str, Any]) -> BrokerPosition:
        """Parse Alpaca position JSON into BrokerPosition."""
        qty = float(data.get("qty", 0))
        side = "long" if qty > 0 else ("short" if qty < 0 else "flat")
        avg_price = float(data.get("avg_entry_price", 0))
        unrealized = data.get("unrealized_pl")
        market_val = data.get("market_value")

        return BrokerPosition(
            symbol=data.get("symbol", ""),
            quantity=qty,
            avg_entry_price=avg_price,
            side=side,
            unrealized_pnl=float(unrealized) if unrealized is not None else None,
            market_value=float(market_val) if market_val is not None else None,
        )
