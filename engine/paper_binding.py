"""Immutable paper-session admission to one durable local SQLite ledger."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path

from engine.paper_guard import PaperRunnerOwnership
from experiments.artifacts import ArtifactManager
from storage.schema import init_db

_LEDGER_ID_KEY = "paper_ledger_instance_id"


def _ledger_id(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM engine_state WHERE key=?", (_LEDGER_ID_KEY,)).fetchone()
    if row is None:
        return None
    value = row[0]
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("paper ledger instance identity is invalid")
    return value


def open_bound_paper_db(
    db_path: str | Path,
    artifacts: ArtifactManager,
    *,
    experiment_uuid: str,
    experiment_hash: str,
    session_id: str,
    ownership: PaperRunnerOwnership,
) -> sqlite3.Connection:
    """Claim before effects, or reopen only the original ledger without creating it.

    The caller holds both database and artifact-session OS locks throughout this
    call and execution. A crash between claim publication and token commit leaves
    a refused, immutable claim, never permission to initialize fresh authority.
    Existing unclaimed paper evidence requires explicit migration outside this API.
    """
    ownership.assert_owned()
    path = Path(db_path).resolve()
    if path != ownership.db_path:
        raise ValueError("paper ledger ownership does not cover this database")
    claim_path = artifacts.paper_ledger_claim_path(experiment_uuid, session_id)
    binding = {
        "schema_version": 1,
        "experiment_uuid": experiment_uuid,
        "experiment_hash": experiment_hash,
        "session_id": session_id,
        "database_path": str(path),
    }
    conn = None
    try:
        if claim_path.exists():
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
            if not isinstance(claim, dict) or any(claim.get(k) != v for k, v in binding.items()):
                raise ValueError("paper ledger claim identity mismatch")
            # mode=rw refuses a missing database; never run init_db on resume.
            conn = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)
            conn.row_factory = sqlite3.Row
            token = _ledger_id(conn)
            if token is None or token != claim.get("ledger_instance_id"):
                raise ValueError("paper ledger instance identity mismatch")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA foreign_keys=ON")
            return conn

        session_path = artifacts.paper_session_path(experiment_uuid, session_id)
        if session_path.exists() or (claim_path.parent.exists() and any(claim_path.parent.iterdir())):
            raise ValueError("paper ledger claim missing for existing session evidence")
        token = None
        if path.exists():
            conn = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)
            token = _ledger_id(conn)
            prior = conn.execute(
                "SELECT 1 FROM paper_sessions WHERE session_id=? LIMIT 1", (session_id,),
            ).fetchone()
            if prior is not None:
                raise ValueError("paper ledger claim missing for existing session")
            if token is None and conn.execute("SELECT 1 FROM paper_sessions LIMIT 1").fetchone():
                raise ValueError("paper ledger instance identity missing for existing paper evidence")
            conn.close()
            conn = None
        token = token or str(uuid.uuid4())
        artifacts.claim_paper_ledger(
            experiment_uuid, session_id, {**binding, "ledger_instance_id": token},
        )
        conn = init_db(path)
        conn.execute("PRAGMA synchronous=FULL")
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO engine_state (key,value,updated_at) VALUES (?,?,datetime('now'))",
                (_LEDGER_ID_KEY, token),
            )
        if _ledger_id(conn) != token:
            raise ValueError("paper ledger instance identity collision")
        # SQLite FULL commits protect the token; sync the newly created DB name.
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return conn
    except BaseException as exc:
        if conn is not None:
            conn.close()
        if isinstance(exc, (sqlite3.Error, OSError, json.JSONDecodeError)):
            raise ValueError("paper ledger binding unavailable or corrupt") from exc
        raise
