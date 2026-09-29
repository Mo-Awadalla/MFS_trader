"""Durable, session-scoped observations; never operator-supplied activity totals."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from engine.paper_calendar import resolve_calendar

if TYPE_CHECKING:
    from engine.paper_guard import PaperRunnerOwnership

IDENTITY_KEYS = (
    "experiment_uuid", "experiment_hash", "session_id", "session_kind", "config_hash",
    "code_version", "broker_environment", "calendar_id", "calendar_version",
    "bar_frequency", "data_grace_seconds", "expected_slippage_bps",
)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def execution_version() -> str:
    """Hash executable source, including uncommitted code, without invoking git."""
    root = Path(__file__).resolve().parents[1]
    result = hashlib.sha256()
    for package in ("engine", "execution", "portfolio", "risk", "storage", "strategies", "config"):
        for path in sorted((root / package).rglob("*.py")):
            result.update(str(path.relative_to(root)).encode())
            result.update(path.read_bytes())
    return result.hexdigest()


def instant(value: Any) -> datetime:
    ts = pd.Timestamp(value)
    if pd.isna(ts) or ts.tzinfo is None:
        raise ValueError("paper evidence timestamps require a timezone")
    return ts.tz_convert("UTC").to_pydatetime()


def finite(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a paper evidence number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite paper evidence number")
    return result


class PaperLedger:
    def __init__(self, conn: sqlite3.Connection, identity: dict[str, Any], now: datetime):
        self.conn = conn
        self.session_id = identity["session_id"]
        self.attempt_id: str | None = None
        self.identity = identity
        self._ownership: PaperRunnerOwnership | None = None
        self._ownership_token: str | None = None
        conn.execute("PRAGMA synchronous=FULL")
        old = conn.execute("SELECT * FROM paper_sessions WHERE session_id=?", (self.session_id,)).fetchone()
        if old is not None:
            if any(old[key] != identity[key] for key in IDENTITY_KEYS):
                raise ValueError("paper session Experiment/configuration/execution identity mismatch")
            self.identity = dict(old)
        else:
            self.identity = {
                **identity, "account_fingerprint": "unverified", "window_started_at": now.isoformat(),
                "binding_digest": digest(identity), "created_at": now.isoformat(),
            }
            keys = list(self.identity)
            conn.execute(
                f"INSERT INTO paper_sessions ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                tuple(self.identity[k] for k in keys),
            )
            conn.commit()

    def start_attempt(self, now: datetime, ownership: PaperRunnerOwnership) -> None:
        """Commit before broker effects, recovering only after exclusive takeover."""
        ownership.assert_owned()
        database = self.conn.execute("PRAGMA database_list").fetchone()["file"]
        if Path(database).resolve() != ownership.db_path:
            raise ValueError("paper ownership does not cover this database")
        self._ownership = ownership
        self._ownership_token = ownership.claim_attempt()
        with self.conn:
            for row in self.rows("paper_attempts"):
                if row["ended_at"] is None:
                    downtime = max(0.0, (now - instant(row["last_heartbeat_at"])).total_seconds())
                    self.conn.execute(
                        "UPDATE paper_attempts SET ended_at=?, outcome='interrupted', reason=?, downtime_seconds=? WHERE attempt_id=? AND ended_at IS NULL",
                        (now.isoformat(), "unclosed attempt detected on restart", downtime, row["attempt_id"]),
                    )
                    self.event("ATTEMPT_INTERRUPTED", now, {"downtime_seconds": downtime}, row["attempt_id"])
                    self.conn.execute(
                        "UPDATE paper_cycles SET result='blocked',reason='interrupted during execution' WHERE session_id=? AND attempt_id=? AND result='started'",
                        (self.session_id, row["attempt_id"]),
                    )
                elif row["outcome"] == "stopped" and row["downtime_seconds"] is None:
                    downtime = max(0.0, (now - instant(row["ended_at"])).total_seconds())
                    self.conn.execute("UPDATE paper_attempts SET downtime_seconds=? WHERE attempt_id=?",
                                      (downtime, row["attempt_id"]))
                    self.event("RESUME_DOWNTIME", now, {"downtime_seconds": downtime}, row["attempt_id"])
            self.attempt_id = uuid.uuid4().hex
            self.conn.execute(
                "INSERT INTO paper_attempts (attempt_id,session_id,experiment_uuid,started_at,last_heartbeat_at) VALUES (?,?,?,?,?)",
                (self.attempt_id, self.session_id, self.identity["experiment_uuid"], now.isoformat(), now.isoformat()),
            )
            self.event("ATTEMPT_STARTED", now, {})

    def assert_active_attempt(self) -> None:
        if self._ownership is None:
            raise ValueError("paper attempt has no exclusive owner")
        self._ownership.assert_owned()
        if self._ownership.token != self._ownership_token:
            raise ValueError("paper attempt ownership has expired")
        row = self.conn.execute(
            "SELECT 1 FROM paper_attempts WHERE attempt_id=? AND session_id=? AND ended_at IS NULL",
            (self.attempt_id, self.session_id),
        ).fetchone()
        if row is None:
            raise ValueError("paper attempt is no longer active")

    def event(self, kind: str, now: datetime, details: dict, attempt_id: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO paper_attempt_events (session_id,attempt_id,event_type,occurred_at,details_json) VALUES (?,?,?,?,?)",
            (self.session_id, attempt_id or self.attempt_id, kind, now.isoformat(), json.dumps(details, allow_nan=False)),
        )

    def bind_account(self, account_id: str) -> None:
        if not account_id or account_id == "unknown":
            raise ValueError("paper account identity unavailable")
        fingerprint = digest([self.identity["experiment_uuid"], self.identity["broker_environment"], account_id])
        old = self.identity["account_fingerprint"]
        if old not in {"unverified", fingerprint}:
            raise ValueError("paper account identity mismatch on restart")
        self.identity["account_fingerprint"] = fingerprint
        self.identity["binding_digest"] = digest({k: self.identity[k] for k in (*IDENTITY_KEYS, "account_fingerprint")})
        with self.conn:
            self.conn.execute("UPDATE paper_sessions SET account_fingerprint=?,binding_digest=? WHERE session_id=?",
                              (fingerprint, self.identity["binding_digest"], self.session_id))

    def close_attempt(self, now: datetime, outcome: str, reason: str | None) -> None:
        if self.attempt_id is None:
            return
        self.assert_active_attempt()
        with self.conn:
            changed = self.conn.execute(
                "UPDATE paper_attempts SET ended_at=?,outcome=?,reason=? "
                "WHERE attempt_id=? AND session_id=? AND ended_at IS NULL",
                (now.isoformat(), outcome, reason, self.attempt_id, self.session_id),
            )
            if changed.rowcount != 1:
                raise ValueError("paper terminal attempt write lost ownership")
            self.conn.execute(
                "UPDATE paper_cycles SET result='blocked',reason=? "
                "WHERE session_id=? AND attempt_id=? AND result='started'",
                (reason or "attempt ended before cycle completion", self.session_id, self.attempt_id),
            )
            self.event("ATTEMPT_CLOSED", now, {"outcome": outcome, "reason": reason})

    def rows(self, table: str) -> list[dict[str, Any]]:
        allowed = {"paper_attempts", "paper_attempt_events", "paper_cycles", "paper_session_orders",
                   "paper_fills", "paper_reference_prices", "paper_drill_events", "paper_order_reservations"}
        if table not in allowed:
            raise ValueError("unsupported paper evidence table")
        return [dict(row) for row in self.conn.execute(f"SELECT * FROM {table} WHERE session_id=? ORDER BY rowid", (self.session_id,))]

    def record_cycle(self, cycle: dict[str, Any], now: datetime) -> None:
        self.assert_active_attempt()
        row = {**cycle, "session_id": self.session_id, "attempt_id": self.attempt_id}
        keys = list(row)
        with self.conn:
            changed = self.conn.execute(
                f"INSERT INTO paper_cycles ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)}) "
                f"ON CONFLICT(session_id,cycle_key) DO UPDATE SET {','.join(k+'=excluded.'+k for k in keys if k not in {'session_id', 'cycle_key', 'attempt_id'})} "
                "WHERE paper_cycles.attempt_id=excluded.attempt_id AND paper_cycles.result='started'",
                tuple(row[k] for k in keys),
            )
            if changed.rowcount != 1:
                raise ValueError("paper cycle is terminal or owned by another attempt")
            self.conn.execute(
                "UPDATE paper_attempts SET last_heartbeat_at=? WHERE attempt_id=? AND ended_at IS NULL",
                (now.isoformat(), self.attempt_id),
            )

    def record_reference_prices(self, cycle_key: str, prices: dict[str, float], now: datetime) -> None:
        with self.conn:
            self.event("REFERENCE_PRICES", now, {"cycle_key": cycle_key, "prices": prices, "source": "broker.get_price"})

    def capture_orders(self, now: datetime) -> None:
        """Recover attribution even if the process died between submission and capture."""
        references = {}
        for event in self.rows("paper_attempt_events"):
            if event["event_type"] == "REFERENCE_PRICES":
                details = json.loads(event["details_json"])
                references.setdefault(details["cycle_key"], (details, event["occurred_at"]))
        env = self.identity["broker_environment"]
        broker = "sim_broker" if env == "sim_broker" else "alpaca"
        with self.conn:
            for cycle in self.rows("paper_cycles"):
                if not cycle["decision_record_id"]:
                    continue
                orders = self.conn.execute(
                    "SELECT * FROM orders_live WHERE correlation_id=? AND broker=? AND environment='paper'",
                    (cycle["decision_record_id"], broker),
                ).fetchall()
                for order in orders:
                    oid = order["client_order_id"]
                    self.conn.execute("INSERT OR IGNORE INTO paper_session_orders VALUES (?,?,?,?,?,?,?)",
                                      (self.session_id, oid, self.identity["experiment_uuid"], env, cycle["cycle_key"], cycle["attempt_id"], now.isoformat()))
                    if cycle["cycle_key"] in references:
                        reference, observed_at = references[cycle["cycle_key"]]
                        price = reference["prices"].get(order["symbol"])
                        if price is not None and finite(price) > 0:
                            self.conn.execute("INSERT OR IGNORE INTO paper_reference_prices VALUES (?,?,?,?,?,?,?,?)",
                                              (digest([self.session_id, oid, "reference"]), self.session_id, self.identity["experiment_uuid"], oid,
                                               order["symbol"], price, reference["source"], observed_at))
                    qty = finite(order["filled_qty"])
                    previous = self.conn.execute("SELECT COALESCE(SUM(fill_qty),0),COALESCE(SUM(fill_qty*fill_price),0) FROM paper_fills WHERE session_id=? AND client_order_id=?", (self.session_id, oid)).fetchone()
                    delta = qty - previous[0]
                    if delta > 1e-9 and order["avg_fill_price"] is not None:
                        price = (qty * finite(order["avg_fill_price"]) - previous[1]) / delta
                        if price <= 0:
                            raise ValueError("inconsistent cumulative fill price")
                        self.conn.execute("INSERT OR IGNORE INTO paper_fills VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                          (digest([oid, qty]), self.session_id, self.identity["experiment_uuid"], env, oid, order["broker_order_id"],
                                           order["symbol"], order["side"], delta, qty, price, now.isoformat(), "orders_live.broker_status"))

    def reconcile_orders(self, broker: Any, now: datetime) -> None:
        """Record an exact broker match without changing any OMS lifecycle state."""
        for link in self.rows("paper_session_orders"):
            row = self.conn.execute("SELECT * FROM orders_live WHERE client_order_id=?", (link["client_order_id"],)).fetchone()
            status = broker.get_order_status(link["client_order_id"])
            if row is None or status is None:
                raise ValueError("broker order reconciliation unavailable")
            if row["reconciliation_status"] in {"MISMATCHED", "UNRESOLVED"}:
                raise ValueError("persisted unresolved order requires manual repair")
            if (status.status != row["order_state"] or status.broker_order_id != row["broker_order_id"]
                    or not math.isclose(finite(status.filled_qty), finite(row["filled_qty"]), abs_tol=1e-9)
                    or not math.isclose(finite(status.remaining_qty), finite(row["remaining_qty"]), abs_tol=1e-9)
                    or status.avg_fill_price != row["avg_fill_price"]):
                raise ValueError("broker order reconciliation mismatch")
            with self.conn:
                self.conn.execute("UPDATE orders_live SET reconciliation_status='MATCHED' WHERE client_order_id=?",
                                  (link["client_order_id"],))
                self.event("ORDER_RECONCILED", now, {"client_order_id": link["client_order_id"], "status": "MATCHED"})

    def record_kill_switch_block(self, reason: str, now: datetime) -> None:
        """Called only by the active kill-switch execution guard, never from notes."""
        details = json.dumps({"binding_digest": self.identity["binding_digest"],
                              "reason": reason, "submitted": False, "source": "paper_run.kill_switch_guard"})
        drill_id = f"kill-switch-{self.attempt_id}"
        with self.conn:
            for kind in ("KILL_SWITCH_ACTIVATED", "NEW_ORDER_BLOCKED"):
                self.conn.execute(
                    "INSERT INTO paper_drill_events (session_id,experiment_uuid,drill_id,event_type,occurred_at,details_json) VALUES (?,?,?,?,?,?)",
                    (self.session_id, self.identity["experiment_uuid"], drill_id, kind, now.isoformat(), details),
                )

    def snapshot(self, now: datetime) -> dict[str, Any]:
        orders = [dict(row) for row in self.conn.execute(
            "SELECT o.* FROM orders_live o JOIN paper_session_orders p ON p.client_order_id=o.client_order_id WHERE p.session_id=? AND p.experiment_uuid=? AND p.broker_environment=?",
            (self.session_id, self.identity["experiment_uuid"], self.identity["broker_environment"]),
        )]
        # Never copy raw account identifiers into an artifact.
        for order in orders:
            order.pop("account_id", None)
        return {"identity": dict(self.identity), "observed_until": now.isoformat(), "orders": orders,
                "attempts": self.rows("paper_attempts"), "cycles": self.rows("paper_cycles"),
                "order_links": self.rows("paper_session_orders"), "fills": self.rows("paper_fills"),
                "order_reservations": self.rows("paper_order_reservations"),
                "reference_prices": self.rows("paper_reference_prices"), "drill_events": self.rows("paper_drill_events")}


def derive_observations(evidence: dict[str, Any], expected_slippage_bps: float) -> dict[str, Any]:
    """Recompute all activity metrics from attributable records, rejecting ambiguity."""
    identity = evidence["identity"]
    sid, exp, env = (identity[k] for k in ("session_id", "experiment_uuid", "broker_environment"))
    if env not in {"sim_broker", "alpaca_paper"}:
        raise ValueError("wrong broker environment")
    for key in ("experiment_hash", "config_hash", "code_version", "account_fingerprint"):
        value = identity.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError(f"incomplete paper identity: {key}")
    if identity["binding_digest"] != digest({k: identity[k] for k in (*IDENTITY_KEYS, "account_fingerprint")}):
        raise ValueError("paper identity digest mismatch")
    # JSON itself permits NaN/Infinity; evidence does not, including unused fields.
    json.dumps(evidence, allow_nan=False)
    start, end = instant(identity["window_started_at"]), instant(evidence["observed_until"])
    if end < start:
        raise ValueError("paper window ends before it starts")
    calendar = resolve_calendar(identity["calendar_id"], identity["calendar_version"])
    expected = {c.cycle_key: c for c in calendar.expected_cycles(identity["bar_frequency"], start, end)}
    grace = finite(identity["data_grace_seconds"])
    if grace < 0:
        raise ValueError("negative data grace")
    completed, observed, watermarks, sessions = 0, set(), set(), set()
    for row in evidence["cycles"]:
        key = row["cycle_key"]
        if row["session_id"] != sid or key in observed or key not in expected:
            raise ValueError("duplicate, out-of-window or unrelated cycle")
        observed.add(key)
        cycle = expected[key]
        if row["market_session"] != cycle.market_session or instant(row["expected_at"]) != cycle.expected_at:
            raise ValueError("cycle calendar mismatch")
        if row["result"] in {"completed", "late_completed"}:
            watermark = row["input_data_watermark"]
            mapped = calendar.cycle_for_bar(identity["bar_frequency"], pd.Timestamp(watermark))
            begun, done = instant(row["started_at"]), instant(row["completed_at"])
            if (mapped is None or mapped.cycle_key != key or watermark in watermarks
                    or not cycle.expected_at <= begun <= done <= end
                    or (done - cycle.expected_at).total_seconds() > grace):
                raise ValueError("stale, repeated or inconsistent cycle completion")
            completed += 1
            sessions.add(cycle.market_session)
            watermarks.add(watermark)
    links = {}
    for row in evidence["order_links"]:
        if row["session_id"] != sid or row["experiment_uuid"] != exp or row["broker_environment"] != env:
            raise ValueError("unrelated order link")
        if row["cycle_key"] not in observed or row["client_order_id"] in links:
            raise ValueError("unattributable or duplicate order link")
        links[row["client_order_id"]] = row
    orders = {}
    broker = "sim_broker" if env == "sim_broker" else "alpaca"
    for row in evidence["orders"]:
        oid = row["client_order_id"]
        if oid not in links or oid in orders or row["broker"] != broker or row["environment"] != "paper":
            raise ValueError("unrelated or duplicate order")
        orders[oid] = row
        linked_cycle = next(c for c in evidence["cycles"] if c["cycle_key"] == links[oid]["cycle_key"])
        if row["correlation_id"] != linked_cycle["decision_record_id"]:
            raise ValueError("order decision attribution mismatch")
    references = {}
    for row in evidence["reference_prices"]:
        if row["session_id"] != sid or row["experiment_uuid"] != exp or row["client_order_id"] not in orders:
            raise ValueError("unrelated reference price")
        if row["source"] != "broker.get_price" or finite(row["price"]) <= 0 or row["client_order_id"] in references:
            raise ValueError("invalid reference price")
        references[row["client_order_id"]] = row
    fills, quantities, notionals, samples = set(), {}, {}, []
    expected_bps = finite(expected_slippage_bps)
    if expected_bps <= 0 or expected_bps != finite(identity["expected_slippage_bps"]):
        raise ValueError("expected slippage must match the positive configured value")
    for row in evidence["fills"]:
        oid = row["client_order_id"]
        if row["session_id"] != sid or row["experiment_uuid"] != exp or row["broker_environment"] != env or oid not in orders:
            raise ValueError("unrelated fill")
        if row["fill_id"] in fills:
            raise ValueError("duplicate fill evidence")
        fills.add(row["fill_id"])
        qty, price = finite(row["fill_qty"]), finite(row["fill_price"])
        if qty <= 0 or price <= 0 or oid not in references:
            raise ValueError("unattributable fill/reference price")
        if (row["source"] != "orders_live.broker_status" or row["broker_order_id"] != orders[oid]["broker_order_id"]
                or row["fill_id"] != digest([oid, finite(row["cumulative_filled_qty"])])):
            raise ValueError("fill provenance mismatch")
        quantities[oid] = quantities.get(oid, 0.0) + qty
        notionals[oid] = finite(notionals.get(oid, 0.0) + qty * price)
        if not math.isclose(quantities[oid], finite(row["cumulative_filled_qty"]), rel_tol=1e-9):
            raise ValueError("inconsistent cumulative fill quantity")
        reference = references[oid]
        if row["symbol"] != orders[oid]["symbol"] or row["side"] != orders[oid]["side"] or reference["symbol"] != row["symbol"]:
            raise ValueError("fill/reference order identity mismatch")
        if not start <= instant(reference["observed_at"]) <= instant(row["observed_at"]) <= end:
            raise ValueError("reference/fill observation time is inconsistent")
        actual = finite((price / finite(reference["price"]) - 1) * 10000 * (1 if row["side"] == "buy" else -1))
        samples.append({"fill_id": row["fill_id"], "client_order_id": oid,
                        "reference_id": reference["reference_id"], "reference_price_source": reference["source"],
                        "expected_slippage_source": "effective_config.cost_model.slippage_fixed_pct",
                        "actual_slippage_bps": actual, "expected_slippage_bps": expected_bps})
    trades = 0
    for oid, row in orders.items():
        qty = finite(row["filled_qty"])
        if not math.isclose(qty, quantities.get(oid, 0), abs_tol=1e-9):
            raise ValueError("order fill total is not backed by fill records")
        if qty > 0 and not math.isclose(notionals[oid] / qty, finite(row["avg_fill_price"]), rel_tol=1e-9):
            raise ValueError("order average price differs from fill records")
        if (row["order_state"] == "FILLED" and row["reconciliation_status"] in {"MATCHED", "REPAIRED"}
                and qty > 0 and math.isclose(qty, finite(row["requested_qty"]), rel_tol=1e-9)
                and finite(row["remaining_qty"]) == 0):
            trades += 1
    attempts = evidence["attempts"]
    if not attempts:
        raise ValueError("missing durable attempts")
    interruptions = 0
    for row in attempts:
        if row["session_id"] != sid or row["experiment_uuid"] != exp:
            raise ValueError("unrelated attempt")
        if row["ended_at"] is None or not start <= instant(row["started_at"]) <= instant(row["last_heartbeat_at"]) <= instant(row["ended_at"]) <= end:
            raise ValueError("unclosed or inconsistent attempt times")
        if row["downtime_seconds"] is not None and finite(row["downtime_seconds"]) < 0:
            raise ValueError("negative restart downtime")
        interruptions += row["outcome"] not in {"completed"}
    attempt_ids = {a["attempt_id"] for a in attempts}
    if len(attempt_ids) != len(attempts):
        raise ValueError("duplicate attempt evidence")
    if any(c["attempt_id"] not in attempt_ids for c in evidence["cycles"]):
        raise ValueError("cycle has no attributable attempt")
    if any(link["attempt_id"] not in attempt_ids for link in links.values()):
        raise ValueError("order has no attributable attempt")
    drill_groups: dict[str, list[dict]] = {}
    for row in evidence["drill_events"]:
        if row["session_id"] != sid or row["experiment_uuid"] != exp:
            raise ValueError("unrelated drill event")
        details = json.loads(row["details_json"])
        if (details.get("binding_digest") != identity["binding_digest"]
                or details.get("source") != "paper_run.kill_switch_guard"
                or not start <= instant(row["occurred_at"]) <= end):
            raise ValueError("drill identity mismatch")
        drill_groups.setdefault(row["drill_id"], []).append(row)
    drill_proved = False
    for rows in drill_groups.values():
        activated = next((r for r in rows if r["event_type"] == "KILL_SWITCH_ACTIVATED"), None)
        blocked = next((r for r in rows if r["event_type"] == "NEW_ORDER_BLOCKED" and json.loads(r["details_json"]).get("submitted") is False), None)
        if activated and blocked and instant(activated["occurred_at"]) <= instant(blocked["occurred_at"]):
            drill_proved = True
    count = len(expected)
    return {"window": {"calendar_days": (end-start).total_seconds()/86400,
                       "market_sessions": len(sessions), "trades": trades, "unplanned_interruptions": interruptions,
                       "insufficient_activity_override_approved": False},
            "bar_cycle_report": {"expected_bar_cycles": count, "completed_bar_cycles": completed,
                                 "bar_cycle_completion": completed/count if count else 0.0,
                                 "unexplained_missed_cycles": count-completed},
            "slippage_samples": samples, "drill_proved": drill_proved}
