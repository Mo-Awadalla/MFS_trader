"""CCXT Binance spot adapter — crypto via CCXT unified interface.

Binance-specific behavior handled here (NOT leaked upward):
  - symbol format: CCXT uses "BTC/USDT" not "BTCUSDT"
  - market buy semantics: CCXT handles quote-to-base conversion
  - precision/lot size: CCXT handles via market() metadata
  - sandbox/testnet: enabled via set_sandbox_mode(True)
  - partial fill behavior: Binance streams fills, CCXT aggregates
  - order status naming: CCXT normalizes to "open", "closed", "canceled", "expired"
  - fees: taker by default (market orders), maker for limit orders that add liquidity
  - cancel behavior: Binance supports cancel-by client_order_id

IMPORTANT: CCXT's "unified" interface hides exchange differences, but not all
of them. This adapter is specifically for Binance spot. If you want to use
a different exchange, you need a new adapter or careful testing.
"""

from __future__ import annotations

from typing import Any

import structlog

from execution.base import (
    BrokerAccount,
    BrokerAdapter,
    BrokerOrderRequest,
    BrokerOrderResponse,
    BrokerPosition,
    OrderType,
)

log = structlog.get_logger(__name__)

# CCXT unified status → our internal status
CCXT_STATUS_MAP: dict[str, str] = {
    "open": "ACKNOWLEDGED",
    "closed": "FILLED",
    "canceled": "CANCELLED",
    "cancelled": "CANCELLED",
    "expired": "EXPIRED",
    "rejected": "REJECTED",
    "pending": "ACKNOWLEDGED",
    "partial": "PARTIALLY_FILLED",
}


class CCXTBinanceAdapter(BrokerAdapter):
    """Binance spot adapter via CCXT.

    Args:
        api_key: Binance API key (from env var).
        api_secret: Binance API secret (from env var).
        is_testnet: If True, use Binance testnet (sandbox mode).
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        is_testnet: bool = True,
    ):
        try:
            import ccxt
        except ImportError as e:
            raise ImportError(
                "ccxt is required for crypto trading. Install: pip install ccxt"
            ) from e

        self._ccxt = ccxt
        self._exchange = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                    "adjustForTimeDifference": True,
                },
            }
        )
        if is_testnet:
            self._exchange.set_sandbox_mode(True)

        self._is_testnet = is_testnet
        self._connected = False

    @property
    def name(self) -> str:
        return "ccxt_binance"

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        """Verify connection by fetching balance."""
        try:
            # Fetch balance to verify credentials
            self._exchange.fetch_balance()
            self._connected = True
            log.info("ccxt_binance_connected", testnet=self._is_testnet)
        except Exception as e:
            log.error("ccxt_binance_connect_failed", error=str(e))
            self._connected = False

    def disconnect(self) -> None:
        self._connected = False

    def submit_order(self, request: BrokerOrderRequest) -> BrokerOrderResponse:
        """Submit an order to Binance via CCXT."""
        if not self.is_connected:
            return BrokerOrderResponse(
                client_order_id=request.client_order_id,
                broker_order_id=None,
                status="REJECTED",
                rejection_reason="not_connected",
            )

        # Map order type to CCXT
        ccxt_type = "market" if request.order_type == OrderType.MARKET else "limit"

        try:
            ccxt_order = self._exchange.create_order(
                symbol=request.symbol,
                type=ccxt_type,
                side=request.side.value,
                amount=request.quantity,
                price=request.limit_price,
                params={
                    "clientOrderId": request.client_order_id,
                    "timeInForce": "GTC" if ccxt_type == "limit" else None,
                },
            )
            return self._parse_ccxt_order(ccxt_order, request.client_order_id)
        except Exception as e:
            error_str = str(e)
            log.warning(
                "ccxt_order_failed",
                symbol=request.symbol,
                error=error_str,
            )
            # Classify error
            if "insufficient" in error_str.lower() or "balance" in error_str.lower():
                return BrokerOrderResponse(
                    client_order_id=request.client_order_id,
                    broker_order_id=None,
                    status="REJECTED",
                    rejection_reason=f"insufficient_balance: {error_str}",
                )
            elif "timeout" in error_str.lower() or "timed out" in error_str.lower():
                return BrokerOrderResponse(
                    client_order_id=request.client_order_id,
                    broker_order_id=None,
                    status="TIMEOUT",
                    rejection_reason=error_str,
                )
            else:
                return BrokerOrderResponse(
                    client_order_id=request.client_order_id,
                    broker_order_id=None,
                    status="REJECTED",
                    rejection_reason=error_str,
                )

    def cancel_order(self, client_order_id: str) -> bool:
        """Cancel an order by client_order_id.

        Binance supports cancel-by-clientOrderId, but CCXT requires the symbol.
        We search open orders to find the symbol.
        """
        if not self.is_connected:
            return False

        try:
            # Find the order to get its symbol
            order = self.get_order_status(client_order_id)
            if order is None:
                return False

            # We need the symbol to cancel in CCXT
            # Fetch open orders to find the symbol
            open_orders = self._exchange.fetch_open_orders()
            target = next(
                (o for o in open_orders if o.get("clientOrderId") == client_order_id),
                None,
            )
            if target is None:
                return False  # order not open or not found

            symbol = target["symbol"]
            self._exchange.cancel_order(target["id"], symbol)
            log.info("ccxt_cancel_ok", client_order_id=client_order_id)
            return True
        except Exception as e:
            log.error("ccxt_cancel_error", error=str(e), client_order_id=client_order_id)
            return False

    def get_order_status(self, client_order_id: str) -> BrokerOrderResponse | None:
        """Get order status by client_order_id.

        CCXT doesn't have a direct "get by client_order_id" method for all exchanges.
        For Binance, we fetch the order by clientOrderId via the API.
        """
        if not self.is_connected:
            return None

        try:
            # Binance supports fetching by clientOrderId
            orders = self._exchange.fetch_open_orders()
            for o in orders:
                if o.get("clientOrderId") == client_order_id:
                    return self._parse_ccxt_order(o, client_order_id)

            # Check closed orders
            # CCXT's fetch_orders needs a symbol, so we search recent orders
            # This is a limitation — for a production system we'd cache the symbol
            # from the original submit. For now, return None if not in open orders.
            return None
        except Exception as e:
            log.error("ccxt_status_error", error=str(e), client_order_id=client_order_id)
            return None

    def get_positions(self) -> list[BrokerPosition]:
        """Fetch all non-zero balances from Binance.

        In spot trading, "positions" are just non-zero balances.
        """
        if not self.is_connected:
            return []

        try:
            balance = self._exchange.fetch_balance()
            positions: list[BrokerPosition] = []

            for currency, amount in balance.get("total", {}).items():
                if amount and float(amount) > 1e-8:
                    # Get current price in USDT
                    symbol = f"{currency}/USDT"
                    try:
                        ticker = self._exchange.fetch_ticker(symbol)
                        price = ticker.get("last", 0)
                    except Exception:
                        price = 0

                    positions.append(
                        BrokerPosition(
                            symbol=currency,
                            quantity=float(amount),
                            avg_entry_price=float(balance.get("info", {}).get(currency, {}).get("avgEntryPrice", 0)),
                            side="long",  # spot balances are always long
                            market_value=float(amount) * price if price else None,
                        )
                    )

            return positions
        except Exception as e:
            log.error("ccxt_positions_error", error=str(e))
            return []

    def get_account(self) -> BrokerAccount:
        """Fetch account balance from Binance."""
        if not self.is_connected:
            return BrokerAccount(account_id="unknown", cash=0, equity=0, currency="USDT")

        try:
            balance = self._exchange.fetch_balance()
            usdt_free = float(balance.get("USDT", {}).get("free", 0))
            usdt_total = float(balance.get("USDT", {}).get("total", 0))

            # Calculate total equity (all currencies converted to USDT)
            total_equity = usdt_total
            for currency, amount in balance.get("total", {}).items():
                if currency == "USDT" or not amount or float(amount) <= 0:
                    continue
                symbol = f"{currency}/USDT"
                try:
                    ticker = self._exchange.fetch_ticker(symbol)
                    price = ticker.get("last", 0)
                    total_equity += float(amount) * price
                except Exception:
                    pass

            return BrokerAccount(
                account_id="binance_account",
                cash=usdt_free,
                equity=total_equity,
                currency="USDT",
            )
        except Exception as e:
            log.error("ccxt_account_error", error=str(e))
            return BrokerAccount(account_id="unknown", cash=0, equity=0, currency="USDT")

    def get_price(self, symbol: str) -> float | None:
        """Get latest price for a trading pair (e.g. BTC/USDT)."""
        if not self.is_connected:
            return None

        try:
            ticker = self._exchange.fetch_ticker(symbol)
            return float(ticker.get("last", 0)) or None
        except Exception as e:
            log.error("ccxt_price_error", symbol=symbol, error=str(e))
            return None

    def _parse_ccxt_order(self, order: dict[str, Any], client_order_id: str) -> BrokerOrderResponse:
        """Parse CCXT order dict into BrokerOrderResponse."""
        ccxt_status = order.get("status", "open")
        internal_status = CCXT_STATUS_MAP.get(ccxt_status, "UNKNOWN")

        filled = float(order.get("filled", 0))
        remaining = float(order.get("remaining", 0))
        avg_price = order.get("average")
        if avg_price is not None:
            avg_price = float(avg_price)

        # CCXT may report cost (filled * avg_price) — not currently used but available
        # cost = order.get("cost")

        return BrokerOrderResponse(
            client_order_id=client_order_id,
            broker_order_id=str(order.get("id", "")) or None,
            status=internal_status,
            filled_qty=filled,
            avg_fill_price=avg_price,
            remaining_qty=remaining,
            rejection_reason=order.get("reject_reason"),
            timestamp=order.get("timestamp"),
        )
