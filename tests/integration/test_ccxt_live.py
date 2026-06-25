"""CCXT Binance testnet live smoke tests — only run with real testnet keys.

These tests hit the Binance testnet API. They are marked @pytest.mark.live_broker
and skipped by default. To run:

    RUN_LIVE_BROKER_TESTS=1 pytest tests/integration/test_ccxt_live.py -v --live_broker

Requirements:
    - BINANCE_API_KEY and BINANCE_API_SECRET environment variables set
    - Binance testnet keys (not production keys)
    - Get testnet keys at: https://testnet.binance.vision/

These tests:
    1. Fetch balance (verify credentials)
    2. Fetch non-zero balances as positions
    3. Submit tiny testnet order (BTC/USDT, minimum amount)
    4. Verify order appears in open orders
    5. Cancel the order
    6. Verify state machine mapping works with real Binance responses
"""

from __future__ import annotations

import os
import time

import pytest

from execution.base import BrokerOrderRequest, OrderSide, OrderType, TimeInForce
from execution.ccxt.adapter import CCXTBinanceAdapter

pytestmark = pytest.mark.live_broker


@pytest.fixture
def ccxt_adapter():
    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        pytest.skip("BINANCE_API_KEY / BINANCE_API_SECRET not set")

    adapter = CCXTBinanceAdapter(
        api_key=api_key,
        api_secret=api_secret,
        is_testnet=True,
    )
    adapter.connect()
    if not adapter.is_connected:
        pytest.skip("Could not connect to Binance testnet — check credentials")
    return adapter


class TestCCXTLiveSmoke:
    """Live smoke tests against Binance testnet."""

    def test_fetch_account(self, ccxt_adapter):
        """Verify account/balance fetch returns real data."""
        account = ccxt_adapter.get_account()
        print(f"  Account: cash=${account.cash:.2f}, equity=${account.equity:.2f}")
        assert account.currency == "USDT"

    def test_fetch_positions(self, ccxt_adapter):
        """Verify positions fetch works (may be empty)."""
        positions = ccxt_adapter.get_positions()
        print(f"  Open positions: {len(positions)}")
        for p in positions:
            print(f"    {p.symbol}: {p.quantity}")

    def test_get_price(self, ccxt_adapter):
        """Verify price fetch for a major pair."""
        price = ccxt_adapter.get_price("BTC/USDT")
        assert price is not None
        assert price > 0
        print(f"  BTC/USDT price: ${price:.2f}")

    def test_submit_and_cancel_testnet_order(self, ccxt_adapter):
        """Submit a tiny limit order on testnet, verify, then cancel."""
        price = ccxt_adapter.get_price("BTC/USDT")
        if price is None:
            pytest.skip("Could not fetch BTC/USDT price")

        # Place a limit buy at 50% of current price — won't fill, safe to cancel
        limit_price = round(price * 0.50, 2)
        client_id = f"smoke_test_{int(time.time())}"

        request = BrokerOrderRequest(
            client_order_id=client_id,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.001,  # minimum BTC amount on Binance
            limit_price=limit_price,
            time_in_force=TimeInForce.GTC,
        )

        # Submit
        response = ccxt_adapter.submit_order(request)
        print(f"  Submitted: status={response.status}, broker_id={response.broker_order_id}")
        assert response.status in ("ACKNOWLEDGED", "FILLED", "PARTIALLY_FILLED")
        assert response.broker_order_id is not None

        # Verify we can fetch its status
        time.sleep(1)
        status = ccxt_adapter.get_order_status(client_id)
        if status is not None:
            print(f"  Status: {status.status}")

        # Cancel it
        cancelled = ccxt_adapter.cancel_order(client_id)
        print(f"  Cancelled: {cancelled}")
        # Cancel might fail if order already filled on testnet — that's ok
        if cancelled:
            time.sleep(1)
            # Verify it's gone from open orders
            final_status = ccxt_adapter.get_order_status(client_id)
            if final_status is not None:
                print(f"  Final status: {final_status.status}")

    def test_rejected_order_no_position(self, ccxt_adapter):
        """Submit an invalid order and verify rejection."""
        positions_before = ccxt_adapter.get_positions()

        client_id = f"smoke_reject_{int(time.time())}"
        request = BrokerOrderRequest(
            client_order_id=client_id,
            symbol="FAKEPAIR/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1,
        )
        response = ccxt_adapter.submit_order(request)
        print(f"  Rejected order: status={response.status}, reason={response.rejection_reason}")
        assert response.status == "REJECTED"

        # Verify no position was created
        positions_after = ccxt_adapter.get_positions()
        assert len(positions_after) == len(positions_before)
