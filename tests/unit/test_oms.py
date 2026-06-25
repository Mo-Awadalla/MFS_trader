"""Tests for the OMS — order management system with sim_broker."""

from __future__ import annotations

import sqlite3

import pytest

from execution.base import OrderSide, OrderType
from execution.oms import OMS, OrderIntent
from execution.sim_broker.broker import SimBroker, SimBrokerConfig
from storage.event_logger import EventLogger
from storage.repository import get_order, get_positions
from storage.schema import init_db


@pytest.fixture
def db(tmp_path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "test.sqlite")
    yield conn
    conn.close()


@pytest.fixture
def broker() -> SimBroker:
    b = SimBroker(SimBrokerConfig(seed=42))
    b.connect()
    return b


@pytest.fixture
def oms(db, broker) -> OMS:
    logger = EventLogger(db, environment="paper", run_id="test_run")
    return OMS(broker, db, logger, environment="paper")


def _make_intent(client_order_id=None, strategy="ma", symbol="AAPL", qty=10):
    return OrderIntent(
        strategy=strategy,
        symbol=symbol,
        asset_class="equity",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=qty,
        bar_timestamp="2024-01-01T16:00:00Z",
    )


class TestCreateAndSubmit:
    def test_successful_order(self, oms, db):
        intent = _make_intent()
        client_id = oms.create_and_submit(intent)
        assert client_id is not None

        order = get_order(db, client_id)
        assert order is not None
        assert order["order_state"] == "FILLED"
        assert order["filled_qty"] == 10

    def test_position_updated_after_fill(self, oms, db):
        intent = _make_intent(qty=10)
        oms.create_and_submit(intent)
        positions = get_positions(db, strategy="ma")
        assert len(positions) == 1
        assert positions[0]["quantity"] == 10

    def test_rejected_order_no_position(self, oms, db):
        # Use a broker that always rejects
        reject_broker = SimBroker(SimBrokerConfig(reject_probability=1.0, seed=42))
        reject_broker.connect()
        logger = EventLogger(db, environment="paper")
        reject_oms = OMS(reject_broker, db, logger, environment="paper")

        intent = _make_intent()
        client_id = reject_oms.create_and_submit(intent)
        order = get_order(db, client_id)
        assert order["order_state"] == "REJECTED"

        # No position should exist
        positions = get_positions(db, strategy="ma")
        assert len(positions) == 0


class TestIdempotency:
    def test_same_intent_no_duplicate(self, oms, db):
        """Same target twice → no duplicate orders."""
        intent = _make_intent()
        client_id_1 = oms.create_and_submit(intent)
        client_id_2 = oms.create_and_submit(intent)

        assert client_id_1 == client_id_2  # deterministic ID

        # Only one order in DB
        order = get_order(db, client_id_1)
        assert order is not None
        assert order["filled_qty"] == 10  # not 20

        # Only one position
        positions = get_positions(db, strategy="ma")
        assert len(positions) == 1
        assert positions[0]["quantity"] == 10  # not 20


class TestTimeout:
    def test_timeout_sets_timeout_state(self, oms, db):
        timeout_broker = SimBroker(SimBrokerConfig(timeout_probability=1.0, seed=42))
        timeout_broker.connect()
        logger = EventLogger(db, environment="paper")
        timeout_oms = OMS(timeout_broker, db, logger, environment="paper")

        intent = _make_intent()
        client_id = timeout_oms.create_and_submit(intent)
        order = get_order(db, client_id)
        assert order["order_state"] == "TIMEOUT"

    def test_timeout_no_position_change(self, oms, db):
        timeout_broker = SimBroker(SimBrokerConfig(timeout_probability=1.0, seed=42))
        timeout_broker.connect()
        logger = EventLogger(db, environment="paper")
        timeout_oms = OMS(timeout_broker, db, logger, environment="paper")

        intent = _make_intent()
        timeout_oms.create_and_submit(intent)
        positions = get_positions(db, strategy="ma")
        assert len(positions) == 0

    def test_reconcile_timeout_finds_order(self, db):
        """Timeout → reconcile by client_order_id → find order was filled."""
        # First: normal broker that fills
        broker = SimBroker(SimBrokerConfig(seed=42))
        broker.connect()
        logger = EventLogger(db, environment="paper")
        oms = OMS(broker, db, logger, environment="paper")

        # Submit and get filled
        intent = _make_intent()
        client_id = oms.create_and_submit(intent)
        order = get_order(db, client_id)
        assert order["order_state"] == "FILLED"

        # Now reconcile (simulating a timeout that was actually filled)
        new_state = oms.reconcile_timeout(client_id, intent)
        assert new_state.value == "FILLED"


class TestPartialFills:
    def test_partial_fill_updates_position(self, oms, db):
        partial_broker = SimBroker(SimBrokerConfig(partial_fill_probability=1.0, seed=42))
        partial_broker.connect()
        logger = EventLogger(db, environment="paper")
        partial_oms = OMS(partial_broker, db, logger, environment="paper")

        intent = _make_intent(qty=100)
        client_id = partial_oms.create_and_submit(intent)
        order = get_order(db, client_id)
        assert order["order_state"] == "PARTIALLY_FILLED"
        assert order["filled_qty"] < 100
        assert order["filled_qty"] > 0

        # Position = partial fill amount
        positions = get_positions(db, strategy="ma")
        assert positions[0]["quantity"] == order["filled_qty"]


class TestFreeze:
    def test_frozen_oms_blocks_new_orders(self, oms, db):
        oms.freeze("test_freeze")
        intent = _make_intent()
        client_id = oms.create_and_submit(intent)
        assert client_id is None

        # No order should be in DB
        from storage.repository import get_open_orders

        orders = get_open_orders(db, strategy="ma")
        assert len(orders) == 0

    def test_unfreeze_allows_orders(self, oms, db):
        oms.freeze("test")
        oms.unfreeze()
        intent = _make_intent()
        client_id = oms.create_and_submit(intent)
        assert client_id is not None


class TestDeterministicClientId:
    def test_same_inputs_same_id(self, oms):
        id1 = oms.generate_client_order_id("ma", "AAPL", "2024-01-01T16:00:00Z", "abc12345")
        id2 = oms.generate_client_order_id("ma", "AAPL", "2024-01-01T16:00:00Z", "abc12345")
        assert id1 == id2

    def test_different_bar_different_id(self, oms):
        id1 = oms.generate_client_order_id("ma", "AAPL", "2024-01-01T16:00:00Z", "abc12345")
        id2 = oms.generate_client_order_id("ma", "AAPL", "2024-01-02T16:00:00Z", "abc12345")
        assert id1 != id2

    def test_different_target_different_id(self, oms):
        id1 = oms.generate_client_order_id("ma", "AAPL", "2024-01-01T16:00:00Z", "abc12345")
        id2 = oms.generate_client_order_id("ma", "AAPL", "2024-01-01T16:00:00Z", "def67890")
        assert id1 != id2
