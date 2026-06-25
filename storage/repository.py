"""State repository — updatable cockpit instruments (orders_live, positions_live).

These are derived from the append-only events log but kept as fast-queryable
current-state tables. They CAN be updated (unlike events).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from storage.event_logger import utc_now_iso


def upsert_order(conn: sqlite3.Connection, order: dict[str, Any]) -> None:
    """Insert or update an order in orders_live."""
    now = utc_now_iso()
    order["updated_at"] = now
    if "created_at" not in order or order["created_at"] is None:
        order["created_at"] = now

    cols = list(order.keys())
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "client_order_id")
    sql = (
        f"INSERT INTO orders_live ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT(client_order_id) DO UPDATE SET {updates}"
    )
    conn.execute(sql, tuple(order.values()))
    conn.commit()


def update_order_state(
    conn: sqlite3.Connection,
    client_order_id: str,
    order_state: str,
    *,
    filled_qty: float | None = None,
    remaining_qty: float | None = None,
    avg_fill_price: float | None = None,
    broker_order_id: str | None = None,
    reconciliation_status: str | None = None,
) -> None:
    """Patch specific fields on an existing order."""
    sets = ["order_state = ?", "updated_at = ?"]
    vals: list[Any] = [order_state, utc_now_iso()]
    if filled_qty is not None:
        sets.append("filled_qty = ?")
        vals.append(filled_qty)
    if remaining_qty is not None:
        sets.append("remaining_qty = ?")
        vals.append(remaining_qty)
    if avg_fill_price is not None:
        sets.append("avg_fill_price = ?")
        vals.append(avg_fill_price)
    if broker_order_id is not None:
        sets.append("broker_order_id = ?")
        vals.append(broker_order_id)
    if reconciliation_status is not None:
        sets.append("reconciliation_status = ?")
        vals.append(reconciliation_status)
    vals.append(client_order_id)
    sql = f"UPDATE orders_live SET {', '.join(sets)} WHERE client_order_id = ?"
    conn.execute(sql, vals)
    conn.commit()


def get_order(conn: sqlite3.Connection, client_order_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM orders_live WHERE client_order_id = ?", (client_order_id,)
    )
    row = cur.fetchone()
    return dict(row) if row else None


def get_open_orders(conn: sqlite3.Connection, strategy: str | None = None) -> list[dict[str, Any]]:
    if strategy:
        cur = conn.execute(
            "SELECT * FROM orders_live WHERE strategy = ? AND order_state IN "
            "('ACKNOWLEDGED','PARTIALLY_FILLED','SUBMITTING','CANCEL_REQUESTED') "
            "ORDER BY updated_at DESC",
            (strategy,),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM orders_live WHERE order_state IN "
            "('ACKNOWLEDGED','PARTIALLY_FILLED','SUBMITTING','CANCEL_REQUESTED') "
            "ORDER BY updated_at DESC"
        )
    return [dict(r) for r in cur.fetchall()]


def upsert_position(conn: sqlite3.Connection, pos: dict[str, Any]) -> None:
    now = utc_now_iso()
    pos["updated_at"] = now
    if "created_at" not in pos or pos["created_at"] is None:
        pos["created_at"] = now

    cols = list(pos.keys())
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    conflict_cols = "environment, strategy, symbol, broker"
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in ("environment", "strategy", "symbol", "broker"))
    sql = (
        f"INSERT INTO positions_live ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT({conflict_cols}) DO UPDATE SET {updates}"
    )
    conn.execute(sql, tuple(pos.values()))
    conn.commit()


def get_positions(conn: sqlite3.Connection, strategy: str | None = None) -> list[dict[str, Any]]:
    if strategy:
        cur = conn.execute(
            "SELECT * FROM positions_live WHERE strategy = ? AND quantity != 0 ORDER BY symbol",
            (strategy,),
        )
    else:
        cur = conn.execute(
            "SELECT * FROM positions_live WHERE quantity != 0 ORDER BY symbol"
        )
    return [dict(r) for r in cur.fetchall()]


def set_engine_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO engine_state(key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, utc_now_iso()),
    )
    conn.commit()


def get_engine_state(conn: sqlite3.Connection, key: str) -> str | None:
    cur = conn.execute("SELECT value FROM engine_state WHERE key = ?", (key,))
    row = cur.fetchone()
    return row[0] if row else None


def set_strategy_kill_switch(
    conn: sqlite3.Connection, strategy: str, halted: bool, reason: str | None = None
) -> None:
    now = utc_now_iso()
    conn.execute(
        "INSERT INTO strategy_kill_switches(strategy, halted, reason, halted_at, resumed_at, "
        "consecutive_losses, updated_at) "
        "VALUES (?, ?, ?, ?, NULL, 0, ?) "
        "ON CONFLICT(strategy) DO UPDATE SET halted=excluded.halted, reason=excluded.reason, "
        "halted_at=excluded.halted_at, resumed_at=excluded.resumed_at, updated_at=excluded.updated_at",
        (strategy, int(halted), reason, now if halted else None, now),
    )
    conn.commit()


def is_strategy_halted(conn: sqlite3.Connection, strategy: str) -> bool:
    cur = conn.execute(
        "SELECT halted FROM strategy_kill_switches WHERE strategy = ?", (strategy,)
    )
    row = cur.fetchone()
    return bool(row[0]) if row else False
