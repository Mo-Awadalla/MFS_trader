"""Operational reporting for engine/replay SQLite databases.

These reports are operator-facing summaries, not research performance reports.
They answer: did the engine run, did orders reconcile, did risk block anything,
and are there conditions that should stop paper/live promotion?
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from storage.schema import get_read_only_connection

SEVERITY_ORDER = ("INFO", "WARN", "ERROR", "CRITICAL")
OPEN_ORDER_STATES = {"ACKNOWLEDGED", "PARTIALLY_FILLED", "SUBMITTING", "CANCEL_REQUESTED"}


@dataclass(frozen=True)
class OperationalReport:
    """Operator-facing summary of one engine/replay database."""

    database: str
    first_event_at: str | None
    last_event_at: str | None
    events_total: int
    bars_started: int
    bars_completed: int
    severity_counts: dict[str, int] = field(default_factory=dict)
    event_counts: dict[str, int] = field(default_factory=dict)
    order_state_counts: dict[str, int] = field(default_factory=dict)
    open_orders: list[dict[str, Any]] = field(default_factory=list)
    final_positions: list[dict[str, Any]] = field(default_factory=list)
    risk_blocks: int = 0
    risk_reductions: int = 0
    reconciliation_mismatches: int = 0
    broker_timeouts: int = 0
    broker_rejections: int = 0
    exceptions: int = 0
    data_quality_counts: dict[str, int] = field(default_factory=dict)
    passed: bool = False
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "database": self.database,
            "first_event_at": self.first_event_at,
            "last_event_at": self.last_event_at,
            "events_total": self.events_total,
            "bars_started": self.bars_started,
            "bars_completed": self.bars_completed,
            "severity_counts": self.severity_counts,
            "event_counts": self.event_counts,
            "order_state_counts": self.order_state_counts,
            "open_orders": self.open_orders,
            "final_positions": self.final_positions,
            "risk_blocks": self.risk_blocks,
            "risk_reductions": self.risk_reductions,
            "reconciliation_mismatches": self.reconciliation_mismatches,
            "broker_timeouts": self.broker_timeouts,
            "broker_rejections": self.broker_rejections,
            "exceptions": self.exceptions,
            "data_quality_counts": self.data_quality_counts,
            "passed": self.passed,
            "blockers": self.blockers,
        }


def build_operational_report(db: str | Path | sqlite3.Connection) -> OperationalReport:
    """Build an operational report from an engine SQLite DB or connection."""

    owns_conn = not isinstance(db, sqlite3.Connection)
    if owns_conn:
        db_path = Path(db)  # type: ignore[arg-type]
        conn = get_read_only_connection(db_path)
        database = str(db_path)
    else:
        conn = db
        database = ":connection:"

    try:
        events_total = _scalar(conn, "SELECT COUNT(*) FROM events")
        first_event_at = _scalar(conn, "SELECT MIN(timestamp) FROM events")
        last_event_at = _scalar(conn, "SELECT MAX(timestamp) FROM events")
        severity_counts = _count_by(conn, "events", "severity")
        event_counts = _count_by(conn, "events", "event_type")
        order_state_counts = _count_by(conn, "orders_live", "order_state")
        data_quality_counts = _count_by(conn, "data_quality", "result")

        bars_started = _scalar(
            conn,
            """
            SELECT COUNT(DISTINCT cycle_id)
            FROM events
            WHERE event_type = 'ENGINE_HEARTBEAT'
              AND message LIKE 'Processing bar%'
            """,
        )
        bars_completed = _scalar(
            conn,
            """
            SELECT COUNT(DISTINCT cycle_id)
            FROM events
            WHERE event_type = 'ENGINE_HEARTBEAT'
              AND message LIKE 'Bar % complete%'
            """,
        )

        open_orders = _rows(
            conn,
            """
            SELECT client_order_id, symbol, side, requested_qty, filled_qty,
                   remaining_qty, order_state, reconciliation_status, updated_at
            FROM orders_live
            WHERE order_state IN ('ACKNOWLEDGED','PARTIALLY_FILLED','SUBMITTING','CANCEL_REQUESTED')
            ORDER BY updated_at DESC
            """,
        )
        final_positions = _rows(
            conn,
            """
            SELECT strategy, symbol, side, quantity, avg_entry_price, notional, updated_at
            FROM positions_live
            WHERE quantity != 0
            ORDER BY strategy, symbol
            """,
        )

        risk_blocks = event_counts.get("RISK_CHECK_BLOCKED", 0)
        risk_reductions = event_counts.get("RISK_CHECK_REDUCED", 0)
        reconciliation_mismatches = event_counts.get("RECONCILIATION_MISMATCH", 0)
        broker_timeouts = event_counts.get("BROKER_TIMEOUT", 0)
        broker_rejections = event_counts.get("BROKER_REJECT", 0)
        exceptions = sum(count for name, count in event_counts.items() if name.startswith("EXCEPTION"))

        blockers = _build_blockers(
            events_total=events_total,
            bars_started=bars_started,
            bars_completed=bars_completed,
            severity_counts=severity_counts,
            open_orders=open_orders,
            data_quality_counts=data_quality_counts,
            risk_blocks=risk_blocks,
            risk_reductions=risk_reductions,
            reconciliation_mismatches=reconciliation_mismatches,
            broker_timeouts=broker_timeouts,
            exceptions=exceptions,
        )

        return OperationalReport(
            database=database,
            first_event_at=first_event_at,
            last_event_at=last_event_at,
            events_total=events_total,
            bars_started=bars_started,
            bars_completed=bars_completed,
            severity_counts=severity_counts,
            event_counts=event_counts,
            order_state_counts=order_state_counts,
            open_orders=open_orders,
            final_positions=final_positions,
            risk_blocks=risk_blocks,
            risk_reductions=risk_reductions,
            reconciliation_mismatches=reconciliation_mismatches,
            broker_timeouts=broker_timeouts,
            broker_rejections=broker_rejections,
            exceptions=exceptions,
            data_quality_counts=data_quality_counts,
            passed=not blockers,
            blockers=blockers,
        )
    finally:
        if owns_conn:
            conn.close()


def format_operational_report(report: OperationalReport) -> str:
    """Render a report as Markdown."""

    status = "PASS" if report.passed else "BLOCKED"
    lines = [
        "# Operational Report",
        "",
        f"Status: {status}",
        f"Database: `{report.database}`",
        f"Window: {report.first_event_at or 'n/a'} → {report.last_event_at or 'n/a'}",
        "",
        "## Run Summary",
        "",
        f"- Events: {report.events_total}",
        f"- Bars started/completed: {report.bars_started}/{report.bars_completed}",
        f"- Broker timeouts: {report.broker_timeouts}",
        f"- Broker rejections: {report.broker_rejections}",
        f"- Risk blocks: {report.risk_blocks}",
        f"- Risk reductions: {report.risk_reductions}",
        f"- Reconciliation mismatches: {report.reconciliation_mismatches}",
        f"- Exceptions: {report.exceptions}",
        "",
        "## Promotion Blockers",
        "",
    ]
    if report.blockers:
        lines.extend(f"- {blocker}" for blocker in report.blockers)
    else:
        lines.append("- None detected by this report.")

    lines.extend([
        "",
        "## Severity Counts",
        "",
        *_format_counts(report.severity_counts, preferred=SEVERITY_ORDER),
        "",
        "## Order States",
        "",
        *_format_counts(report.order_state_counts),
        "",
        "## Data Quality",
        "",
        *_format_counts(report.data_quality_counts),
        "",
        "## Final Positions",
        "",
    ])
    lines.extend(_format_rows(report.final_positions, ["strategy", "symbol", "side", "quantity", "avg_entry_price"]))

    lines.extend(["", "## Open Orders", ""])
    lines.extend(_format_rows(report.open_orders, ["client_order_id", "symbol", "side", "remaining_qty", "order_state"]))
    lines.append("")
    return "\n".join(lines)


def write_operational_report(
    report: OperationalReport,
    output_path: str | Path,
    *,
    fmt: str = "markdown",
) -> Path:
    """Write an operational report to disk."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        output.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
    elif fmt == "markdown":
        output.write_text(format_operational_report(report), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported report format: {fmt}")
    return output


def _build_blockers(
    *,
    events_total: int,
    bars_started: int,
    bars_completed: int,
    severity_counts: dict[str, int],
    open_orders: list[dict[str, Any]],
    data_quality_counts: dict[str, int],
    risk_blocks: int,
    risk_reductions: int,
    reconciliation_mismatches: int,
    broker_timeouts: int,
    exceptions: int,
) -> list[str]:
    blockers: list[str] = []
    if events_total == 0:
        blockers.append("No engine events were recorded.")
    if bars_started != bars_completed:
        blockers.append(f"Bar cycle mismatch: started={bars_started}, completed={bars_completed}.")
    if severity_counts.get("CRITICAL", 0) > 0:
        blockers.append(f"Critical events recorded: {severity_counts['CRITICAL']}.")
    if severity_counts.get("ERROR", 0) > 0:
        blockers.append(f"Error events recorded: {severity_counts['ERROR']}.")
    if open_orders:
        blockers.append(f"Open/unresolved orders remain: {len(open_orders)}.")
    if data_quality_counts.get("FAIL", 0) > 0:
        blockers.append(f"Data quality failures recorded: {data_quality_counts['FAIL']}.")
    if risk_blocks > 0:
        blockers.append(f"Risk blocked {risk_blocks} bar cycle(s).")
    if reconciliation_mismatches > 0:
        blockers.append(f"Reconciliation mismatches recorded: {reconciliation_mismatches}.")
    if broker_timeouts > 0:
        blockers.append(f"Broker timeouts recorded: {broker_timeouts}.")
    if exceptions > 0:
        blockers.append(f"Exception events recorded: {exceptions}.")
    return blockers


def _scalar(conn: sqlite3.Connection, sql: str) -> Any:
    row = conn.execute(sql).fetchone()
    value = row[0] if row else 0
    return 0 if value is None else value


def _count_by(conn: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    rows = conn.execute(
        f"SELECT {column}, COUNT(*) FROM {table} GROUP BY {column} ORDER BY {column}"
    ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows if row[0] is not None}


def _rows(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql).fetchall()]


def _format_counts(counts: dict[str, int], preferred: tuple[str, ...] = ()) -> list[str]:
    if not counts:
        return ["- None"]
    ordered = Counter(counts)
    keys = [key for key in preferred if key in ordered]
    keys.extend(sorted(key for key in ordered if key not in keys))
    return [f"- {key}: {ordered[key]}" for key in keys]


def _format_rows(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    if not rows:
        return ["- None"]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return lines
