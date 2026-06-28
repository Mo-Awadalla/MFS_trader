"""Append-only event logger — the black box recorder.

Every state transition, signal, order, fill, reconciliation, and exception
flows through here. Events are NEVER updated or deleted.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger(__name__)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class EventLogger:
    """Writes append-only events to SQLite. Never mutates existing rows."""

    def __init__(self, conn: sqlite3.Connection, environment: str, run_id: str | None = None):
        self._conn = conn
        self._environment = environment
        self._run_id = run_id or f"run_{utc_now_iso()}_{uuid.uuid4().hex[:8]}"

    @property
    def run_id(self) -> str:
        return self._run_id

    def log(
        self,
        event_type: str,
        *,
        severity: str = "INFO",
        strategy: str | None = None,
        symbol: str | None = None,
        asset_class: str | None = None,
        broker: str | None = None,
        account_id: str | None = None,
        cycle_id: str | None = None,
        correlation_id: str | None = None,
        bar_timestamp: str | None = None,
        client_order_id: str | None = None,
        broker_order_id: str | None = None,
        order_state: str | None = None,
        side: str | None = None,
        order_type: str | None = None,
        time_in_force: str | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
        requested_qty: float | None = None,
        filled_qty: float | None = None,
        remaining_qty: float | None = None,
        avg_fill_price: float | None = None,
        notional: float | None = None,
        currency: str | None = None,
        reconciliation_status: str | None = None,
        message: str = "",
        details: dict[str, Any] | None = None,
        exception: str | None = None,
        latency_ms: int | None = None,
        version: str | None = None,
        source: str | None = None,
        parent_event_id: int | None = None,
        idempotency_key: str | None = None,
    ) -> int:
        """Write one event row. Returns the event id."""
        ts = utc_now_iso()
        # Only caller-supplied keys should deduplicate events. The audit log is
        # append-only, and many legitimate operational events (heartbeats,
        # reconciliation passes, bar-cycle start/complete markers) share the
        # same type and may be emitted close enough together that Windows' clock
        # resolution produces identical timestamps. A unique automatic key keeps
        # distinct rows from being suppressed; call sites that need retry
        # idempotency must pass an explicit idempotency_key.
        idem = idempotency_key or f"auto:{self._run_id}:{uuid.uuid4().hex}"

        row = {
            "timestamp": ts,
            "event_type": event_type,
            "severity": severity,
            "environment": self._environment,
            "run_id": self._run_id,
            "cycle_id": cycle_id,
            "correlation_id": correlation_id,
            "event_idempotency_key": idem,
            "strategy": strategy,
            "symbol": symbol,
            "asset_class": asset_class,
            "broker": broker,
            "account_id": account_id,
            "bar_timestamp": bar_timestamp,
            "client_order_id": client_order_id,
            "broker_order_id": broker_order_id,
            "order_state": order_state,
            "side": side,
            "order_type": order_type,
            "time_in_force": time_in_force,
            "limit_price": limit_price,
            "stop_price": stop_price,
            "requested_qty": requested_qty,
            "filled_qty": filled_qty,
            "remaining_qty": remaining_qty,
            "avg_fill_price": avg_fill_price,
            "notional": notional,
            "currency": currency,
            "reconciliation_status": reconciliation_status,
            "message": message,
            "details_json": json.dumps(details) if details else None,
            "exception": exception,
            "latency_ms": latency_ms,
            "version": version,
            "source": source,
            "parent_event_id": parent_event_id,
        }

        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        sql = f"INSERT INTO events ({cols}) VALUES ({placeholders})"

        try:
            cur = self._conn.execute(sql, tuple(row.values()))
            self._conn.commit()
            event_id = cur.lastrowid
            log.info(
                "event_logged",
                event_type=event_type,
                severity=severity,
                symbol=symbol,
                strategy=strategy,
                event_id=event_id,
            )
            return event_id  # type: ignore[return-value]
        except sqlite3.IntegrityError:
            # Duplicate idempotency key — this is the dedup mechanism working
            log.warning("event_duplicate_suppressed", event_type=event_type, idem_key=idem)
            return -1
