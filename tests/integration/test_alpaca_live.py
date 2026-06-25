"""Alpaca live smoke tests — only run with real paper account keys.

These tests hit the real Alpaca paper API. They are marked @pytest.mark.live_broker
and skipped by default. To run:

    RUN_LIVE_BROKER_TESTS=1 pytest tests/integration/test_alpaca_live.py -v --live_broker

Requirements:
    - ALPACA_API_KEY and ALPACA_API_SECRET environment variables set
    - Paper account (not live) — the tests use paper-api.alpaca.markets

These tests:
    1. Fetch account (verify credentials)
    2. Fetch positions (expect empty on clean paper account)
    3. Submit tiny paper order (1 share AAPL market buy)
    4. Verify order appears in broker history
    5. Cancel/verify the order or resulting position
    6. Verify state machine mapping works with real broker responses
"""

from __future__ import annotations

import os
import time

import pytest

from execution.alpaca.adapter import AlpacaAdapter
from execution.base import BrokerOrderRequest, OrderSide, OrderType, TimeInForce

pytestmark = pytest.mark.live_broker


@pytest.fixture
def alpaca_adapter():
    api_key = os.environ.get("ALPACA_API_KEY")
    api_secret = os.environ.get("ALPACA_API_SECRET")
    if not api_key or not api_secret:
        pytest.skip("ALPACA_API_KEY / ALPACA_API_SECRET not set")

    adapter = AlpacaAdapter(
        api_key=api_key,
        api_secret=api_secret,
        base_url="https://paper-api.alpaca.markets",
        data_url="https://data.alpaca.markets",
    )
    adapter.connect()
    if not adapter.is_connected:
        pytest.skip("Could not connect to Alpaca paper API — check credentials")
    return adapter


class TestAlpacaLiveSmoke:
    """Live smoke tests against Alpaca paper account."""

    def test_fetch_account(self, alpaca_adapter):
        """Verify account fetch returns real data."""
        account = alpaca_adapter.get_account()
        assert account.account_id != "unknown"
        assert account.equity > 0
        print(f"  Account: {account.account_id}, equity: ${account.equity:.2f}")

    def test_fetch_positions(self, alpaca_adapter):
        """Verify positions fetch works (may be empty)."""
        positions = alpaca_adapter.get_positions()
        print(f"  Open positions: {len(positions)}")
        for p in positions:
            print(f"    {p.symbol}: {p.quantity} @ {p.avg_entry_price}")

    def test_get_price(self, alpaca_adapter):
        """Verify price fetch for a liquid symbol."""
        price = alpaca_adapter.get_price("AAPL")
        assert price is not None
        assert price > 0
        print(f"  AAPL price: ${price:.2f}")

    def test_submit_and_cancel_paper_order(self, alpaca_adapter):
        """Submit a tiny paper order, verify it, then cancel it.

        Uses a limit order far from market price so it stays open and
        can be cancelled without filling.
        """
        price = alpaca_adapter.get_price("AAPL")
        if price is None:
            pytest.skip("Could not fetch AAPL price")

        # Place a limit buy at 50% of current price — won't fill, safe to cancel
        limit_price = round(price * 0.50, 2)
        client_id = f"smoke_test_{int(time.time())}"

        request = BrokerOrderRequest(
            client_order_id=client_id,
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1,
            limit_price=limit_price,
            time_in_force=TimeInForce.DAY,
        )

        # Submit
        response = alpaca_adapter.submit_order(request)
        print(f"  Submitted: status={response.status}, broker_id={response.broker_order_id}")
        assert response.status in ("ACKNOWLEDGED", "FILLED", "PARTIALLY_FILLED")
        assert response.broker_order_id is not None

        # Verify we can fetch its status
        status = alpaca_adapter.get_order_status(client_id)
        assert status is not None
        print(f"  Status: {status.status}")

        # Cancel it
        if status.status not in ("FILLED", "CANCELLED", "REJECTED", "EXPIRED"):
            cancelled = alpaca_adapter.cancel_order(client_id)
            print(f"  Cancelled: {cancelled}")
            assert cancelled

            # Verify final status
            time.sleep(1)
            final_status = alpaca_adapter.get_order_status(client_id)
            assert final_status is not None
            assert final_status.status in ("CANCELLED", "FILLED")  # race possible
            print(f"  Final status: {final_status.status}")

    def test_rejected_order_no_position(self, alpaca_adapter):
        """Submit an invalid order and verify it's rejected without position change."""
        positions_before = alpaca_adapter.get_positions()

        # Submit order for a nonexistent symbol
        client_id = f"smoke_reject_{int(time.time())}"
        request = BrokerOrderRequest(
            client_order_id=client_id,
            symbol="FAKESYMBOL123",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1,
        )
        response = alpaca_adapter.submit_order(request)
        print(f"  Rejected order: status={response.status}, reason={response.rejection_reason}")
        assert response.status == "REJECTED"

        # Verify no position was created
        positions_after = alpaca_adapter.get_positions()
        assert len(positions_after) == len(positions_before)
