"""Experiment-scoped kill switches.

Per CONTEXT.md: kill switches are *Experiment-scoped*, not Strategy-scoped. Two
Experiments sharing the same Strategy template are controlled independently.

Severity semantics:

- ``SOFT``         — blocks new orders; promotion_status unchanged (usually
                     paired with a promotion blocker). Resume keeps the
                     Experiment in its current lifecycle stage.
- ``HARD``         — hard kill: sets promotion_status to ``SUSPENDED`` and
                     records ``suspended_from_status``. Resume requires explicit
                     operator confirmation (``confirm-resume``).
- ``CATASTROPHIC`` — unknown broker state / serious operational breach;
                     same lifecycle effect as HARD but flagged so the
                     postmortem workflow knows the bar was unclean.

A kill switch record is **mutable runtime state**, not part of the frozen
Experiment snapshot. It lives in the registry's index SQLite so it survives
restarts and is queryable from the operator CLI.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from experiments.storage import utc_now_iso


class KillSwitchSeverity(StrEnum):
    """Canonical kill switch severities."""

    SOFT = "soft"
    HARD = "hard"
    CATASTROPHIC = "catastrophic"


class KillSwitchError(Exception):
    """Raised on kill switch misuse (e.g. clearing a non-existent switch)."""


@dataclass(frozen=True)
class KillSwitchState:
    """Current kill switch state for one Experiment."""

    experiment_uuid: str
    severity: KillSwitchSeverity
    reason: str
    set_at: str
    set_by: str | None
    cleared_at: str | None = None
    cleared_by: str | None = None

    @property
    def is_active(self) -> bool:
        return self.cleared_at is None

    @property
    def is_soft(self) -> bool:
        return self.severity == KillSwitchSeverity.SOFT

    @property
    def is_hard(self) -> bool:
        return self.severity in {KillSwitchSeverity.HARD, KillSwitchSeverity.CATASTROPHIC}

    @property
    def is_catastrophic(self) -> bool:
        return self.severity == KillSwitchSeverity.CATASTROPHIC

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_uuid": self.experiment_uuid,
            "severity": self.severity.value,
            "reason": self.reason,
            "set_at": self.set_at,
            "set_by": self.set_by,
            "cleared_at": self.cleared_at,
            "cleared_by": self.cleared_by,
            "is_active": self.is_active,
        }


KILL_SWITCH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_kill_switches (
    experiment_uuid    TEXT PRIMARY KEY,
    severity           TEXT NOT NULL,
    reason             TEXT NOT NULL,
    set_at             TEXT NOT NULL,
    set_by             TEXT,
    cleared_at         TEXT,
    cleared_by         TEXT,
    updated_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kill_switch_active
    ON experiment_kill_switches(cleared_at) WHERE cleared_at IS NULL;
"""


def _row_to_state(row: sqlite3.Row) -> KillSwitchState | None:
    if row is None:
        return None
    return KillSwitchState(
        experiment_uuid=str(row["experiment_uuid"]),
        severity=KillSwitchSeverity(str(row["severity"])),
        reason=str(row["reason"]),
        set_at=str(row["set_at"]),
        set_by=str(row["set_by"]) if row["set_by"] is not None else None,
        cleared_at=str(row["cleared_at"]) if row["cleared_at"] is not None else None,
        cleared_by=str(row["cleared_by"]) if row["cleared_by"] is not None else None,
    )


class ExperimentKillSwitchStore:
    """SQLite-backed kill switch store, attached to the registry index.

    The store keeps one row per experiment_uuid, reflecting the current state
    (active if ``cleared_at`` is NULL). A new activate replaces the prior
    active state (escalation path) so the most-recent severity wins.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.executescript(KILL_SWITCH_SCHEMA_SQL)
        self._conn.commit()

    def set(
        self,
        experiment_uuid: str,
        severity: KillSwitchSeverity,
        reason: str,
        *,
        set_by: str | None = None,
    ) -> KillSwitchState:
        now = utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO experiment_kill_switches (
                experiment_uuid, severity, reason, set_at, set_by,
                cleared_at, cleared_by, updated_at
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?)
            ON CONFLICT(experiment_uuid) DO UPDATE SET
                severity=excluded.severity,
                reason=excluded.reason,
                set_at=excluded.set_at,
                set_by=excluded.set_by,
                cleared_at=NULL,
                cleared_by=NULL,
                updated_at=excluded.updated_at
            """,
            (experiment_uuid, severity.value, reason, now, set_by, now),
        )
        self._conn.commit()
        return self.get(experiment_uuid)  # type: ignore[return-value]

    def get(self, experiment_uuid: str) -> KillSwitchState | None:
        row = self._conn.execute(
            """
            SELECT experiment_uuid, severity, reason, set_at, set_by,
                   cleared_at, cleared_by
            FROM experiment_kill_switches
            WHERE experiment_uuid = ?
            """,
            (experiment_uuid,),
        ).fetchone()
        return _row_to_state(row)

    def get_active(self, experiment_uuid: str) -> KillSwitchState | None:
        state = self.get(experiment_uuid)
        return state if state is not None and state.is_active else None

    def clear(
        self,
        experiment_uuid: str,
        *,
        cleared_by: str | None = None,
    ) -> KillSwitchState:
        existing = self.get(experiment_uuid)
        if existing is None:
            raise KillSwitchError(
                f"Cannot clear kill switch for {experiment_uuid}: not set"
            )
        if not existing.is_active:
            raise KillSwitchError(
                f"Kill switch for {experiment_uuid} already cleared at "
                f"{existing.cleared_at}"
            )
        now = utc_now_iso()
        self._conn.execute(
            """
            UPDATE experiment_kill_switches
            SET cleared_at = ?, cleared_by = ?, updated_at = ?
            WHERE experiment_uuid = ?
            """,
            (now, cleared_by, now, experiment_uuid),
        )
        self._conn.commit()
        return self.get(experiment_uuid)  # type: ignore[return-value]

    def list_active(self) -> list[KillSwitchState]:
        rows = self._conn.execute(
            """
            SELECT experiment_uuid, severity, reason, set_at, set_by,
                   cleared_at, cleared_by
            FROM experiment_kill_switches
            WHERE cleared_at IS NULL
            ORDER BY set_at
            """
        ).fetchall()
        return [state for state in (_row_to_state(r) for r in rows) if state is not None]
