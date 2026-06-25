"""Alpaca adapter mocked tests — deterministic CI tests with mocked HTTP responses.

These tests prove:
  - account fetch works
  - positions normalize correctly
  - submit order maps to internal order model
  - cancel order maps correctly
  - rejects/timeouts/errors map into state machine
  - broker-specific weirdness does not leak upward

All HTTP calls are mocked via `responses` library — no real API keys needed.
"""

from __future__ import annotations

import pytest
import responses

from execution.alpaca.adapter import AlpacaAdapter
from execution.base import BrokerOrderRequest, OrderSide, OrderType, TimeInForce

PAPER_URL = "https://paper-api.alpaca.markets"
DATA_URL = "https://data.alpaca.markets"


@pytest.fixture
def adapter():
    a = AlpacaAdapter(
        api_key="test_key",
        api_secret="test_secret",
        base_url=PAPER_URL,
        data_url=DATA_URL,
    )
    return a


# Alpaca account response
ACCOUNT_RESPONSE = {
    "id": "test-account-123",
    "cash": "5000.00",
    "equity": "10000.00",
    "buying_power": "15000.00",
    "currency": "USD",
}

# Alpaca positions response
POSITIONS_RESPONSE = [
    {
        "symbol": "AAPL",
        "qty": "50",
        "avg_entry_price": "150.00",
        "side": "long",
        "unrealized_pl": "250.00",
        "market_value": "7500.00",
    },
    {
        "symbol": "MSFT",
        "qty": "-20",
        "avg_entry_price": "300.00",
        "side": "short",
        "unrealized_pl": "-100.00",
        "market_value": "-6000.00",
    },
]

# Alpaca order response (filled)
ORDER_FILLED = {
    "id": "alpaca-order-456",
    "client_order_id": "test_client_id_1",
    "status": "filled",
    "qty": "10",
    "filled_qty": "10",
    "filled_avg_price": "150.50",
    "reject_reason": None,
    "submitted_at": "2024-01-01T10:00:00Z",
}

# Alpaca order response (partial fill)
ORDER_PARTIAL = {
    "id": "alpaca-order-789",
    "client_order_id": "test_client_id_2",
    "status": "partially_filled",
    "qty": "100",
    "filled_qty": "30",
    "filled_avg_price": "151.00",
    "reject_reason": None,
    "submitted_at": "2024-01-01T10:00:00Z",
}

# Alpaca order response (rejected)
ORDER_REJECTED = {
    "id": "alpaca-order-000",
    "client_order_id": "test_client_id_3",
    "status": "rejected",
    "qty": "10",
    "filled_qty": "0",
    "filled_avg_price": None,
    "reject_reason": "insufficient buying power",
    "submitted_at": "2024-01-01T10:00:00Z",
}

# Alpaca quote response
QUOTE_RESPONSE = {
    "bid_price": "149.50",
    "ask_price": "150.50",
}


class TestConnect:
    @responses.activate
    def test_connect_success(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        adapter.connect()
        assert adapter.is_connected

    @responses.activate
    def test_connect_failure_bad_credentials(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json={"error": "invalid credentials"},
            status=401,
        )
        adapter.connect()
        assert not adapter.is_connected

    def test_disconnect(self, adapter):
        adapter._connected = True
        adapter._session = type("S", (), {"close": lambda self: None})()
        adapter.disconnect()
        assert not adapter.is_connected


class TestGetAccount:
    @responses.activate
    def test_fetch_account(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        adapter.connect()
        account = adapter.get_account()
        assert account.account_id == "test-account-123"
        assert account.cash == 5000.0
        assert account.equity == 10000.0
        assert account.buying_power == 15000.0
        assert account.currency == "USD"

    @responses.activate
    def test_account_not_connected_returns_zeros(self, adapter):
        account = adapter.get_account()
        assert account.cash == 0
        assert account.equity == 0


class TestGetPositions:
    @responses.activate
    def test_fetch_positions(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/positions",
            json=POSITIONS_RESPONSE,
            status=200,
        )
        adapter.connect()
        positions = adapter.get_positions()
        assert len(positions) == 2
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 50
        assert positions[0].side == "long"
        assert positions[0].avg_entry_price == 150.0
        assert positions[0].unrealized_pnl == 250.0

    @responses.activate
    def test_short_position_normalized(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/positions",
            json=POSITIONS_RESPONSE,
            status=200,
        )
        adapter.connect()
        positions = adapter.get_positions()
        short_pos = next(p for p in positions if p.symbol == "MSFT")
        assert short_pos.quantity == -20
        assert short_pos.side == "short"

    @responses.activate
    def test_empty_positions(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/positions",
            json=[],
            status=200,
        )
        adapter.connect()
        positions = adapter.get_positions()
        assert len(positions) == 0


class TestGetOpenOrders:
    @responses.activate
    def test_fetch_open_orders(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/orders",
            json=[ORDER_PARTIAL],
            status=200,
        )
        adapter.connect()

        orders = adapter.get_open_orders()

        assert len(orders) == 1
        assert orders[0].client_order_id == "test_client_id_2"
        assert orders[0].status == "PARTIALLY_FILLED"


class TestSubmitOrder:
    @responses.activate
    def test_submit_market_buy_filled(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.POST,
            f"{PAPER_URL}/v2/orders",
            json=ORDER_FILLED,
            status=201,
        )
        adapter.connect()

        request = BrokerOrderRequest(
            client_order_id="test_client_id_1",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
            time_in_force=TimeInForce.DAY,
        )
        response = adapter.submit_order(request)
        assert response.status == "FILLED"
        assert response.filled_qty == 10
        assert response.avg_fill_price == 150.50
        assert response.broker_order_id == "alpaca-order-456"

    @responses.activate
    def test_submit_partial_fill(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.POST,
            f"{PAPER_URL}/v2/orders",
            json=ORDER_PARTIAL,
            status=201,
        )
        adapter.connect()

        request = BrokerOrderRequest(
            client_order_id="test_client_id_2",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        response = adapter.submit_order(request)
        assert response.status == "PARTIALLY_FILLED"
        assert response.filled_qty == 30
        assert response.remaining_qty == 70

    @responses.activate
    def test_submit_rejected(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.POST,
            f"{PAPER_URL}/v2/orders",
            json=ORDER_REJECTED,
            status=422,
        )
        adapter.connect()

        request = BrokerOrderRequest(
            client_order_id="test_client_id_3",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
        response = adapter.submit_order(request)
        assert response.status == "REJECTED"
        assert "insufficient" in (response.rejection_reason or "").lower() or "422" in (response.rejection_reason or "")

    @responses.activate
    def test_submit_not_connected_rejected(self, adapter):
        request = BrokerOrderRequest(
            client_order_id="test_id",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
        response = adapter.submit_order(request)
        assert response.status == "REJECTED"
        assert response.rejection_reason == "not_connected"

    @responses.activate
    def test_submit_limit_order(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        limit_order_resp = {
            "id": "alpaca-limit-1",
            "client_order_id": "limit_1",
            "status": "new",
            "qty": "10",
            "filled_qty": "0",
            "filled_avg_price": None,
            "reject_reason": None,
            "submitted_at": "2024-01-01T10:00:00Z",
        }
        responses.add(
            responses.POST,
            f"{PAPER_URL}/v2/orders",
            json=limit_order_resp,
            status=201,
        )
        adapter.connect()

        request = BrokerOrderRequest(
            client_order_id="limit_1",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            limit_price=145.00,
            time_in_force=TimeInForce.GTC,
        )
        response = adapter.submit_order(request)
        assert response.status == "ACKNOWLEDGED"
        assert response.broker_order_id == "alpaca-limit-1"


class TestCancelOrder:
    @responses.activate
    def test_cancel_success(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        # Status lookup returns the order
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/orders:by_client_order_id",
            json={**ORDER_FILLED, "status": "new", "filled_qty": "0", "filled_avg_price": None},
            status=200,
            match=[responses.matchers.query_string_matcher("client_order_id=test_client_id_1")],
        )
        # Cancel by broker order ID
        responses.add(
            responses.DELETE,
            f"{PAPER_URL}/v2/orders/alpaca-order-456",
            status=204,
        )
        adapter.connect()
        result = adapter.cancel_order("test_client_id_1")
        assert result is True

    @responses.activate
    def test_cancel_not_found(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        # Status lookup returns 404 — order not found
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/orders:by_client_order_id",
            status=404,
        )
        adapter.connect()
        result = adapter.cancel_order("nonexistent")
        assert result is False

    def test_cancel_not_connected(self, adapter):
        assert not adapter.cancel_order("test")


class TestGetOrderStatus:
    @responses.activate
    def test_get_status_filled(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/orders:by_client_order_id",
            json=ORDER_FILLED,
            status=200,
        )
        adapter.connect()
        response = adapter.get_order_status("test_client_id_1")
        assert response is not None
        assert response.status == "FILLED"
        assert response.filled_qty == 10

    @responses.activate
    def test_get_status_not_found(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/orders:by_client_order_id",
            status=404,
        )
        adapter.connect()
        response = adapter.get_order_status("nonexistent")
        assert response is None


class TestGetPrice:
    @responses.activate
    def test_get_price_midpoint(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{DATA_URL}/v2/stocks/AAPL/quotes/latest",
            json=QUOTE_RESPONSE,
            status=200,
        )
        adapter.connect()
        price = adapter.get_price("AAPL")
        assert price == 150.0  # midpoint of 149.50 and 150.50

    @responses.activate
    def test_get_price_falls_back_to_latest_trade_for_one_sided_quote(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.GET,
            f"{DATA_URL}/v2/stocks/AAPL/quotes/latest",
            json={"quote": {"bp": 0, "ap": 0.01}},
            status=200,
        )
        responses.add(
            responses.GET,
            f"{DATA_URL}/v2/stocks/AAPL/trades/latest",
            json={"trade": {"p": 201.25}},
            status=200,
        )
        adapter.connect()
        price = adapter.get_price("AAPL")
        assert price == 201.25

    @responses.activate
    def test_get_price_not_connected(self, adapter):
        price = adapter.get_price("AAPL")
        assert price is None


class TestStatusMapping:
    """Verify all Alpaca status values map correctly to our state machine."""

    @pytest.mark.parametrize(
        "alpaca_status,expected",
        [
            ("new", "ACKNOWLEDGED"),
            ("accepted", "ACKNOWLEDGED"),
            ("pending_new", "ACKNOWLEDGED"),
            ("partially_filled", "PARTIALLY_FILLED"),
            ("filled", "FILLED"),
            ("canceled", "CANCELLED"),
            ("cancelled", "CANCELLED"),
            ("pending_cancel", "CANCEL_REQUESTED"),
            ("rejected", "REJECTED"),
            ("expired", "EXPIRED"),
            ("stopped", "FILLED"),
        ],
    )
    def test_status_mapping(self, alpaca_status, expected):
        from execution.alpaca.adapter import ALPACA_STATUS_MAP

        assert ALPACA_STATUS_MAP.get(alpaca_status) == expected


class TestIdempotencyClientOrderId:
    """Verify client_order_id is passed through to Alpaca for idempotency."""

    @responses.activate
    def test_client_order_id_in_request_body(self, adapter):
        responses.add(
            responses.GET,
            f"{PAPER_URL}/v2/account",
            json=ACCOUNT_RESPONSE,
            status=200,
        )
        responses.add(
            responses.POST,
            f"{PAPER_URL}/v2/orders",
            json=ORDER_FILLED,
            status=201,
        )
        adapter.connect()

        request = BrokerOrderRequest(
            client_order_id="deterministic_id_abc123",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
        adapter.submit_order(request)

        # Verify the request body contained our client_order_id
        call_body = responses.calls[-1].request.body
        if isinstance(call_body, bytes):
            call_body = call_body.decode()
        assert "deterministic_id_abc123" in call_body
