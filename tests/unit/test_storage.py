"""Tests for the storage layer — SQLite schema, events, orders, positions."""

from __future__ import annotations

import sqlite3

import pytest

from storage.event_logger import EventLogger, utc_now_iso
from storage.repository import (
    get_engine_state,
    get_open_orders,
    get_order,
    get_positions,
    is_strategy_halted,
    set_engine_state,
    set_strategy_kill_switch,
    update_order_state,
    upsert_order,
    upsert_position,
)
from storage.schema import init_db


@pytest.fixture
def db(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "test.sqlite"
    conn = init_db(db_path)
    yield conn
    conn.close()


class TestSchema:
    def test_init_creates_tables(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t[0] for t in tables]
        assert "events" in names
        assert "orders_live" in names
        assert "positions_live" in names
        assert "engine_state" in names
        assert "data_quality" in names
        assert "runs" in names
        assert "strategy_kill_switches" in names

    def test_wal_mode(self, db):
        mode = db.execute("PRAGMA journal_mode").fetchone()
        assert mode[0] == "wal"


class TestEventLogger:
    def test_log_event(self, db):
        logger = EventLogger(db, environment="research", run_id="test_run_1")
        event_id = logger.log(
            "SIGNAL_GENERATED",
            strategy="ma",
            symbol="AAPL",
            message="MA crossover signal",
        )
        assert event_id > 0

        cur = db.execute("SELECT event_type, strategy, symbol FROM events WHERE id = ?", (event_id,))
        row = cur.fetchone()
        assert row[0] == "SIGNAL_GENERATED"
        assert row[1] == "ma"
        assert row[2] == "AAPL"

    def test_event_append_only(self, db):
        """Events table should never support UPDATE — but SQLite doesn't enforce this.
        We verify the count only grows."""
        logger = EventLogger(db, environment="research")
        logger.log("ENGINE_STARTUP")
        logger.log("SIGNAL_GENERATED", symbol="AAPL")
        count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count == 2
        logger.log("ENGINE_HEARTBEAT")
        count = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert count == 3

    def test_idempotency_dedup(self, db):
        """Same idempotency key should not produce duplicate events."""
        logger = EventLogger(db, environment="research")
        logger.log("ORDER_INTENT", client_order_id="ma_AAPL_2024-01-01_hash", idempotency_key="key1")
        logger.log("ORDER_INTENT", client_order_id="ma_AAPL_2024-01-01_hash", idempotency_key="key1")
        count = db.execute(
            "SELECT COUNT(*) FROM events WHERE event_type = 'ORDER_INTENT'"
        ).fetchone()[0]
        assert count == 1  # duplicate suppressed

    def test_run_id_consistent(self, db):
        logger = EventLogger(db, environment="paper", run_id="run_abc")
        logger.log("ENGINE_STARTUP")
        cur = db.execute("SELECT run_id FROM events WHERE event_type = 'ENGINE_STARTUP'")
        assert cur.fetchone()[0] == "run_abc"


class TestOrdersLive:
    def test_upsert_and_get_order(self, db):
        order = {
            "client_order_id": "ma_AAPL_2024-01-01_hash",
            "broker_order_id": None,
            "broker": "alpaca",
            "account_id": "acct1",
            "environment": "paper",
            "strategy": "ma",
            "symbol": "AAPL",
            "asset_class": "equity",
            "side": "buy",
            "order_type": "market",
            "time_in_force": "day",
            "limit_price": None,
            "stop_price": None,
            "requested_qty": 10.0,
            "filled_qty": 0.0,
            "remaining_qty": 10.0,
            "avg_fill_price": None,
            "notional": 1900.0,
            "currency": "USD",
            "order_state": "SUBMITTING",
            "reconciliation_status": "NOT_CHECKED",
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "bar_timestamp": "2024-01-01T16:00:00Z",
            "correlation_id": "corr1",
            "version": "0.1.0",
        }
        upsert_order(db, order)
        retrieved = get_order(db, "ma_AAPL_2024-01-01_hash")
        assert retrieved is not None
        assert retrieved["order_state"] == "SUBMITTING"

    def test_update_order_state(self, db):
        order = {
            "client_order_id": "test_order_1",
            "broker": "alpaca",
            "environment": "paper",
            "strategy": "ma",
            "symbol": "AAPL",
            "asset_class": "equity",
            "side": "buy",
            "order_type": "market",
            "requested_qty": 10.0,
            "filled_qty": 0.0,
            "remaining_qty": 10.0,
            "order_state": "SUBMITTING",
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        upsert_order(db, order)
        update_order_state(
            db,
            "test_order_1",
            "FILLED",
            filled_qty=10.0,
            remaining_qty=0.0,
            avg_fill_price=190.0,
            broker_order_id="broker_123",
        )
        updated = get_order(db, "test_order_1")
        assert updated["order_state"] == "FILLED"
        assert updated["filled_qty"] == 10.0
        assert updated["broker_order_id"] == "broker_123"

    def test_get_open_orders(self, db):
        for i, state in enumerate(["ACKNOWLEDGED", "FILLED", "CANCELLED"]):
            upsert_order(
                db,
                {
                    "client_order_id": f"order_{i}",
                    "broker": "alpaca",
                    "environment": "paper",
                    "strategy": "ma",
                    "symbol": "AAPL",
                    "asset_class": "equity",
                    "side": "buy",
                    "order_type": "market",
                    "requested_qty": 10.0,
                    "filled_qty": 0.0,
                    "remaining_qty": 10.0,
                    "order_state": state,
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                },
            )
        open_orders = get_open_orders(db, strategy="ma")
        assert len(open_orders) == 1  # only ACKNOWLEDGED


class TestPositionsLive:
    def test_upsert_position(self, db):
        pos = {
            "environment": "paper",
            "strategy": "ma",
            "symbol": "AAPL",
            "asset_class": "equity",
            "broker": "alpaca",
            "account_id": "acct1",
            "side": "long",
            "quantity": 10.0,
            "avg_entry_price": 190.0,
            "notional": 1900.0,
            "unrealized_pnl": 50.0,
            "realized_pnl": 0.0,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        }
        upsert_position(db, pos)
        positions = get_positions(db, strategy="ma")
        assert len(positions) == 1
        assert positions[0]["symbol"] == "AAPL"

    def test_upsert_position_updates_existing(self, db):
        for qty in [10.0, 20.0]:
            upsert_position(
                db,
                {
                    "environment": "paper",
                    "strategy": "ma",
                    "symbol": "AAPL",
                    "asset_class": "equity",
                    "broker": "alpaca",
                    "side": "long",
                    "quantity": qty,
                    "realized_pnl": 0.0,
                    "created_at": utc_now_iso(),
                    "updated_at": utc_now_iso(),
                },
            )
        positions = get_positions(db, strategy="ma")
        assert len(positions) == 1
        assert positions[0]["quantity"] == 20.0


class TestEngineState:
    def test_set_and_get_engine_state(self, db):
        set_engine_state(db, "halted", "true")
        assert get_engine_state(db, "halted") == "true"
        set_engine_state(db, "halted", "false")
        assert get_engine_state(db, "halted") == "false"

    def test_strategy_kill_switch(self, db):
        assert not is_strategy_halted(db, "ma")
        set_strategy_kill_switch(db, "ma", halted=True, reason="max_daily_loss")
        assert is_strategy_halted(db, "ma")
        set_strategy_kill_switch(db, "ma", halted=False)
        assert not is_strategy_halted(db, "ma")


class TestParquetIO:
    def test_write_and_read_bars(self, tmp_path):
        import pandas as pd

        from storage.parquet_io import read_bars, write_bars

        idx = pd.date_range("2024-01-01", periods=10, freq="1min", tz="UTC")
        df = pd.DataFrame(
            {
                "open": [100.0] * 10,
                "high": [101.0] * 10,
                "low": [99.0] * 10,
                "close": [100.5] * 10,
                "volume": [1000.0] * 10,
            },
            index=idx,
        )
        path = tmp_path / "test.parquet"
        write_bars(df, path)
        result = read_bars(path)
        assert len(result) == 10
        assert "close" in result.columns

    def test_append_bars_dedup(self, tmp_path):
        import pandas as pd

        from storage.parquet_io import append_bars, read_bars

        idx1 = pd.date_range("2024-01-01", periods=5, freq="1min", tz="UTC")
        df1 = pd.DataFrame(
            {"open": [100.0] * 5, "high": [101.0] * 5, "low": [99.0] * 5, "close": [100.5] * 5, "volume": [1000.0] * 5},
            index=idx1,
        )
        idx2 = pd.date_range("2024-01-01 00:03:00", periods=5, freq="1min", tz="UTC")
        df2 = pd.DataFrame(
            {"open": [200.0] * 5, "high": [201.0] * 5, "low": [199.0] * 5, "close": [200.5] * 5, "volume": [2000.0] * 5},
            index=idx2,
        )
        path = tmp_path / "test.parquet"
        append_bars(df1, path)
        new_count = append_bars(df2, path)
        result = read_bars(path)
        # 5 + 5 - 2 overlap (00:03, 00:04) = 8
        assert len(result) == 8
        assert new_count == 3  # 5 new - 2 duplicates
        # Overlapping bars should have updated values
        assert result.loc[idx2[0], "close"] == 200.5
