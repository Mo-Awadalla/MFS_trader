"""Tests for the simulated broker — the malicious fake broker."""

from __future__ import annotations

from execution.base import BrokerOrderRequest, OrderSide, OrderType, TimeInForce
from execution.sim_broker.broker import SimBroker, SimBrokerConfig


def _make_request(client_order_id="test_1", symbol="AAPL", qty=10, side=OrderSide.BUY):
    return BrokerOrderRequest(
        client_order_id=client_order_id,
        symbol=symbol,
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        time_in_force=TimeInForce.DAY,
    )


class TestSimBrokerBasic:
    def test_connect_and_submit(self):
        broker = SimBroker()
        broker.connect()
        assert broker.is_connected

        response = broker.submit_order(_make_request())
        assert response.status == "FILLED"
        assert response.filled_qty == 10
        assert response.avg_fill_price > 0

    def test_not_connected_rejects(self):
        broker = SimBroker()
        # Don't connect
        response = broker.submit_order(_make_request())
        assert response.status == "REJECTED"
        assert "not_connected" in response.rejection_reason

    def test_get_positions_after_fill(self):
        broker = SimBroker()
        broker.connect()
        broker.submit_order(_make_request(qty=10))
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 10

    def test_sell_reduces_position(self):
        broker = SimBroker()
        broker.connect()
        broker.submit_order(_make_request(qty=10, side=OrderSide.BUY))
        broker.submit_order(
            _make_request(client_order_id="test_2", qty=5, side=OrderSide.SELL)
        )
        positions = broker.get_positions()
        assert positions[0].quantity == 5

    def test_get_account(self):
        broker = SimBroker()
        broker.connect()
        account = broker.get_account()
        assert account.cash > 0
        assert account.equity > 0


class TestIdempotency:
    def test_same_client_order_id_no_duplicate(self):
        """Same target twice → no duplicate orders (idempotency)."""
        broker = SimBroker()
        broker.connect()
        req = _make_request(client_order_id="idempotent_1", qty=10)

        # Submit once
        resp1 = broker.submit_order(req)
        assert resp1.status == "FILLED"

        # Submit again with same client_order_id
        resp2 = broker.submit_order(req)
        assert resp2.status == "FILLED"
        assert resp2.filled_qty == 10  # same, not doubled

        # Position should only reflect ONE fill
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 10  # not 20

    def test_different_client_order_ids_both_fill(self):
        broker = SimBroker()
        broker.connect()
        broker.submit_order(_make_request(client_order_id="order_1", qty=10))
        broker.submit_order(_make_request(client_order_id="order_2", qty=5))
        positions = broker.get_positions()
        assert positions[0].quantity == 15


class TestRejections:
    def test_always_reject(self):
        config = SimBrokerConfig(reject_probability=1.0, seed=42)
        broker = SimBroker(config)
        broker.connect()
        response = broker.submit_order(_make_request())
        assert response.status == "REJECTED"
        assert response.rejection_reason is not None

    def test_rejected_order_no_position_change(self):
        """Rejected order → no position change."""
        config = SimBrokerConfig(reject_probability=1.0, seed=42)
        broker = SimBroker(config)
        broker.connect()
        broker.submit_order(_make_request())
        positions = broker.get_positions()
        assert len(positions) == 0  # no position created


class TestTimeouts:
    def test_always_timeout(self):
        config = SimBrokerConfig(timeout_probability=1.0, seed=42)
        broker = SimBroker(config)
        broker.connect()
        response = broker.submit_order(_make_request())
        assert response.status == "TIMEOUT"
        assert response.broker_order_id is None

    def test_timeout_no_position_change(self):
        config = SimBrokerConfig(timeout_probability=1.0, seed=42)
        broker = SimBroker(config)
        broker.connect()
        broker.submit_order(_make_request())
        positions = broker.get_positions()
        assert len(positions) == 0


class TestPartialFills:
    def test_partial_fill_updates_position(self):
        """Partial fill → position = filled qty, remaining tracked."""
        config = SimBrokerConfig(partial_fill_probability=1.0, seed=42)
        broker = SimBroker(config)
        broker.connect()
        response = broker.submit_order(_make_request(qty=100))
        assert response.status == "PARTIALLY_FILLED"
        assert response.filled_qty < 100
        assert response.filled_qty > 0
        assert response.remaining_qty == 100 - response.filled_qty

        # Position should reflect partial fill
        positions = broker.get_positions()
        assert positions[0].quantity == response.filled_qty

    def test_cancel_partial_preserves_filled(self):
        """Cancelled partial fill → filled qty preserved."""
        config = SimBrokerConfig(partial_fill_probability=1.0, seed=42)
        broker = SimBroker(config)
        broker.connect()
        response = broker.submit_order(_make_request(qty=100))
        filled = response.filled_qty

        # Cancel the order
        cancelled = broker.cancel_order("test_1")
        assert cancelled

        # Check status
        status = broker.get_order_status("test_1")
        assert status.status == "CANCELLED"
        assert status.filled_qty == filled  # filled qty preserved

        # Position still has the partial fill
        positions = broker.get_positions()
        assert positions[0].quantity == filled


class TestStaleData:
    def test_stale_data_returns_no_positions(self):
        config = SimBrokerConfig(stale_data=True)
        broker = SimBroker(config)
        broker.connect()
        broker.submit_order(_make_request(qty=10))
        positions = broker.get_positions()
        assert len(positions) == 0  # stale = no data

    def test_stale_data_returns_no_price(self):
        config = SimBrokerConfig(stale_data=True)
        broker = SimBroker(config)
        broker.connect()
        price = broker.get_price("AAPL")
        assert price is None


class TestPositionMismatch:
    def test_mismatch_reports_doubled_positions(self):
        config = SimBrokerConfig(position_mismatch=True)
        broker = SimBroker(config)
        broker.connect()
        broker.submit_order(_make_request(qty=10))
        positions = broker.get_positions()
        # Mismatch: reports 2x the actual quantity
        assert positions[0].quantity == 20


class TestUnreachable:
    def test_unreachable_disconnected(self):
        config = SimBrokerConfig(unreachable=True)
        broker = SimBroker(config)
        broker.connect()
        assert not broker.is_connected

    def test_unreachable_rejects_orders(self):
        config = SimBrokerConfig(unreachable=True)
        broker = SimBroker(config)
        broker.connect()
        response = broker.submit_order(_make_request())
        assert response.status == "REJECTED"


class TestCancelOrder:
    def test_cancel_acknowledged_order(self):
        broker = SimBroker()
        broker.connect()
        # We can't easily test cancel on an ack'd-but-not-filled order
        # because sim_broker fills immediately. But we can test cancel
        # on a partial fill.
        config = SimBrokerConfig(partial_fill_probability=1.0, seed=42)
        broker = SimBroker(config)
        broker.connect()
        broker.submit_order(_make_request(qty=100))
        assert broker.cancel_order("test_1")

    def test_cancel_nonexistent_returns_false(self):
        broker = SimBroker()
        broker.connect()
        assert not broker.cancel_order("nonexistent")

    def test_cancel_filled_returns_false(self):
        broker = SimBroker()
        broker.connect()
        broker.submit_order(_make_request(qty=10))
        # Order is already FILLED — can't cancel
        assert not broker.cancel_order("test_1")


class TestInjectPosition:
    def test_inject_position_for_reconciliation(self):
        broker = SimBroker()
        broker.connect()
        broker.inject_position("AAPL", 50, 150.0)
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 50

    def test_inject_zero_clears(self):
        broker = SimBroker()
        broker.connect()
        broker.inject_position("AAPL", 50, 150.0)
        broker.inject_position("AAPL", 0, 150.0)
        positions = broker.get_positions()
        assert len(positions) == 0
