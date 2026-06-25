"""SQLite schema for the MFS trading system.

Three layers:
  events         = append-only audit log (immutable truth)
  orders_live    = current/latest order view (updatable cockpit instrument)
  positions_live = current/latest position view (updatable)
  engine_state   = current kill-switch / runtime state
  data_quality   = data validation results
  runs           = experiment tracking index

All timestamps are ISO 8601 UTC. SQLite runs in WAL mode.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
-- ============================================================================
-- events: append-only audit log. NEVER UPDATE OR DELETE.
-- ============================================================================
CREATE TABLE IF NOT EXISTS events (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp             TEXT NOT NULL,           -- ISO 8601 UTC
    event_type            TEXT NOT NULL,
    severity              TEXT NOT NULL DEFAULT 'INFO',  -- INFO|WARN|ERROR|CRITICAL
    environment           TEXT NOT NULL,           -- research|paper|live

    -- Identifiers
    run_id                TEXT,                    -- engine process lifetime
    cycle_id              TEXT,                    -- one bar-cycle execution
    correlation_id        TEXT,                    -- signal→target→risk→order→fill group
    event_idempotency_key TEXT UNIQUE,             -- dedup duplicate event writes

    -- Context
    strategy              TEXT,
    symbol                TEXT,
    asset_class           TEXT,                    -- equity|crypto
    broker                TEXT,
    account_id            TEXT,
    bar_timestamp         TEXT,

    -- Order fields (nullable)
    client_order_id       TEXT,
    broker_order_id       TEXT,
    order_state           TEXT,
    side                  TEXT,                    -- buy|sell
    order_type            TEXT,                    -- market|limit|stop
    time_in_force         TEXT,                    -- day|gtc|ioc|fok
    limit_price           REAL,
    stop_price            REAL,
    requested_qty         REAL,
    filled_qty            REAL,
    remaining_qty         REAL,
    avg_fill_price        REAL,
    notional              REAL,
    currency              TEXT,

    -- Reconciliation metadata (separate from order lifecycle state)
    reconciliation_status TEXT,                    -- NOT_CHECKED|MATCHED|MISMATCHED|REPAIRED|UNRESOLVED

    -- Body
    message               TEXT,
    details_json          TEXT,
    exception             TEXT,
    latency_ms            INTEGER,
    version               TEXT,                    -- strategy version / git commit
    source                TEXT,                    -- which module emitted this
    parent_event_id       INTEGER REFERENCES events(id),

    FOREIGN KEY (parent_event_id) REFERENCES events(id)
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_client_order_id ON events(client_order_id);
CREATE INDEX IF NOT EXISTS idx_events_broker_order_id ON events(broker_order_id);
CREATE INDEX IF NOT EXISTS idx_events_correlation_id ON events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_cycle_id ON events(cycle_id);
CREATE INDEX IF NOT EXISTS idx_events_strategy ON events(strategy, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_symbol ON events(symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity, timestamp);

-- ============================================================================
-- orders_live: current/latest order state. Updatable cockpit instrument.
-- Reconstructed from events if needed.
-- ============================================================================
CREATE TABLE IF NOT EXISTS orders_live (
    client_order_id       TEXT PRIMARY KEY,
    broker_order_id       TEXT,
    broker                TEXT NOT NULL,
    account_id            TEXT,
    environment           TEXT NOT NULL,
    strategy              TEXT NOT NULL,
    symbol                TEXT NOT NULL,
    asset_class           TEXT NOT NULL,
    side                  TEXT NOT NULL,
    order_type            TEXT NOT NULL,
    time_in_force         TEXT,
    limit_price           REAL,
    stop_price            REAL,
    requested_qty         REAL NOT NULL,
    filled_qty            REAL NOT NULL DEFAULT 0,
    remaining_qty         REAL NOT NULL,
    avg_fill_price        REAL,
    notional              REAL,
    currency              TEXT,
    order_state           TEXT NOT NULL,           -- 12-state machine
    reconciliation_status TEXT NOT NULL DEFAULT 'NOT_CHECKED',
    created_at            TEXT NOT NULL,           -- ISO 8601 UTC
    updated_at            TEXT NOT NULL,
    bar_timestamp         TEXT,
    correlation_id        TEXT,
    version               TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_broker_order_id ON orders_live(broker_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders_live(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_strategy ON orders_live(strategy);
CREATE INDEX IF NOT EXISTS idx_orders_state ON orders_live(order_state);

-- ============================================================================
-- positions_live: current/latest position state. Updatable.
-- ============================================================================
CREATE TABLE IF NOT EXISTS positions_live (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    environment           TEXT NOT NULL,
    strategy              TEXT NOT NULL,
    symbol                TEXT NOT NULL,
    asset_class           TEXT NOT NULL,
    broker                TEXT NOT NULL,
    account_id            TEXT,
    side                  TEXT NOT NULL,           -- long|short|flat
    quantity              REAL NOT NULL DEFAULT 0,
    avg_entry_price       REAL,
    notional              REAL,
    unrealized_pnl        REAL,
    realized_pnl          REAL NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    UNIQUE(environment, strategy, symbol, broker)
);

CREATE INDEX IF NOT EXISTS idx_positions_strategy ON positions_live(strategy);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions_live(symbol);

-- ============================================================================
-- engine_state: kill-switch and runtime state. Survives restart.
-- ============================================================================
CREATE TABLE IF NOT EXISTS engine_state (
    key                   TEXT PRIMARY KEY,
    value                 TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

-- ============================================================================
-- data_quality: results of data validation checks.
-- ============================================================================
CREATE TABLE IF NOT EXISTS data_quality (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp             TEXT NOT NULL,
    symbol                TEXT NOT NULL,
    asset_class           TEXT NOT NULL,
    source                TEXT NOT NULL,           -- alpaca|ccxt_binance
    exchange              TEXT,
    result                TEXT NOT NULL,           -- PASS|WARN|FAIL
    bar_frequency         TEXT NOT NULL,
    checks_run            TEXT NOT NULL,           -- JSON list of check names
    issues_json           TEXT,                    -- JSON list of issues
    bars_checked          INTEGER,
    bars_failed           INTEGER,
    latest_bar_timestamp  TEXT,
    environment           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dq_symbol ON data_quality(symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_dq_result ON data_quality(result);

-- ============================================================================
-- runs: experiment tracking index. Full artifacts live in external store.
-- ============================================================================
CREATE TABLE IF NOT EXISTS runs (
    run_id                TEXT PRIMARY KEY,        -- date_strategy_version_hash_counter
    timestamp             TEXT NOT NULL,
    environment           TEXT NOT NULL,
    strategy              TEXT NOT NULL,
    strategy_version      TEXT NOT NULL,
    git_commit            TEXT,
    random_seed           INTEGER,
    python_version        TEXT,
    dependency_snapshot   TEXT,                    -- path to requirements lock
    machine_id            TEXT,
    timezone              TEXT,

    -- Data
    symbols_json          TEXT,                    -- JSON list
    universe_definition   TEXT,
    selection_rule        TEXT,
    bar_frequency         TEXT,
    data_source           TEXT,
    data_version          TEXT,
    adjustment            TEXT,
    in_sample_period      TEXT,
    out_of_sample_period  TEXT,
    point_in_time_universe INTEGER,                -- 0 or 1

    -- Parameters
    parameters_json       TEXT,
    cost_model_json       TEXT,
    fees_version          TEXT,
    slippage_version      TEXT,

    -- Validation results
    oos_sharpe            REAL,
    oos_sortino           REAL,
    oos_cagr              REAL,
    oos_max_dd            REAL,
    mc_prob_positive_sharpe REAL,
    mc_prob_ruin          REAL,
    mc_5pct_cagr          REAL,
    mc_95pct_max_dd       REAL,
    dsr_pvalue            REAL,
    dsr_method            TEXT,
    m_raw                 INTEGER,
    m_eff_corr            REAL,
    parameter_stability   TEXT,                    -- pass|fail
    benchmark             TEXT,

    -- Lifecycle
    promotion_status      TEXT NOT NULL DEFAULT 'research',  -- research|research_passed|paper|live_candidate|live|suspended|retired
    rejection_reason      TEXT,

    -- Artifacts
    artifacts_dir         TEXT,                    -- path to external run artifacts
    config_snapshot_path  TEXT,
    report_path           TEXT,

    notes                 TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_strategy ON runs(strategy, timestamp);
CREATE INDEX IF NOT EXISTS idx_runs_promotion ON runs(promotion_status);

-- ============================================================================
-- strategy_kill_switches: per-strategy kill state (survives restart).
-- ============================================================================
CREATE TABLE IF NOT EXISTS strategy_kill_switches (
    strategy              TEXT PRIMARY KEY,
    halted                INTEGER NOT NULL DEFAULT 0,  -- 0|1
    reason                TEXT,
    halted_at             TEXT,
    resumed_at            TEXT,
    consecutive_losses    INTEGER NOT NULL DEFAULT 0,
    updated_at            TEXT NOT NULL
);
"""


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Initialize the SQLite database with WAL mode and full schema."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # WAL mode for concurrent read (dashboard) + write (engine)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")  # safe with WAL
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA timezone='UTC'")

    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def get_read_only_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open a read-only connection for dashboard/monitoring — cannot lock the writer."""
    db_path = Path(db_path)
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
