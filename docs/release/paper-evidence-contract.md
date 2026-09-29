# Paper evidence and recovery contract

This release is an offline research/simulation workbench. Simulation is not broker-paper qualification. Nothing in this contract authorizes a live session or changes an Experiment lifecycle automatically. The existing `confirm-paper-ops-pass` command remains an explicit manual confirmation; a report alone cannot promote an Experiment.

## Observation identity

A continuous paper session has a durable SQLite identity: Experiment UUID and full hash, session id/kind, effective configuration hash, execution-source hash, broker environment, hashed account fingerprint, calendar declaration, cadence, grace interval and configured fixed expected-slippage basis. Account fingerprints include the Experiment and environment; raw account IDs and credentials are not copied into paper artifacts. A restart with another configuration, execution source, account or session fails closed.

The execution hash covers Python source in engine, execution, portfolio, risk, storage, strategies and config. It is a source-content identity (including local edits), not a claim that a published release or a corrected research evaluation passed. Corrected numerical-validation eligibility is a separate admission requirement owned by release integration.

`sim_broker` and `alpaca_paper` are distinct environments. Continuous Alpaca paper admission requires paper mode, paper configuration, the exact paper trading endpoint and manual CLI broker confirmation. A simulated campaign cannot satisfy the broker-paper confirmation gate, even with sufficient simulated activity.

## Calendar and cycles

The declaration `XNYS-mfs / 2026.1` covers 2024-01-01 through 2026-12-31. It excludes weekends and the NYSE full-day holidays, including the 2025-01-09 mourning closure, and specifies 13:00 New York early closes. All exchange instants use `America/New_York`, including DST changes. Queries outside coverage fail closed; extending coverage requires a reviewed calendar declaration and regressions, not an implicit extrapolation.

Expected cycles come from calendar sessions and the configured cadence, never loop iterations. Daily labels use the UTC session date; intraday labels use the interval start. The final interval on an early close is shortened to the actual close. Expected time, actual start, actual completion and the input-data watermark are separate fields. A daily bar becomes eligible at the exchange close, and only cycles whose expected time is in the actual observation window count. Old historical bars do not become current paper sessions.

One eligible cycle can complete only once. Repeated, stale, premature, holiday and weekend labels cannot create completions. Unique observed exchange sessions are counted separately from cycle count. Missing calendar-derived cycles remain in the denominator even when no row or no new data arrives. An overdue cycle is durably recorded and halts the loop rather than leaving a perfect ratio while waiting forever. The default grace is one intraday cadence, or 18 hours after the daily close to accommodate the existing next-date daily-data availability convention. Tests inject the clock and sleeper.

## Orders, fills and slippage

The runtime uses an identity-scoped deterministic order namespace and decision correlation ID. The started cycle and broker reference prices are committed before processing the decision. This permits attribution of an order even if termination occurs immediately after submission and before the next capture.

Only unique orders with lifecycle `FILLED`, positive fully filled quantity, zero remaining quantity and reconciliation `MATCHED` or `REPAIRED` count as trades. Partial fills and multiple fill observations are not extra trades. The paper observer can record an exact broker-status match in existing reconciliation metadata; it does not transition an OMS order state or repair a mismatch. A missing broker status, inconsistent cumulative fill, unresolved reconciliation or account switch halts execution.

Fill increments have deterministic IDs based on order ID and cumulative quantity. Duplicate polls collapse. Each slippage sample is computed from an attributable fill and the pre-decision broker reference-price record, with order ID, fill ID, reference ID and reference source retained. Actual adverse slippage is signed by order side. Expected slippage is explicitly the effective configuration's fixed slippage component; it is not a claim of full variable-impact financial parity. Samples without an attributable reference price are rejected.

Supplied totals, samples, drill booleans and insufficient-activity claims remain operator notes. They never replace observed trades, sessions, interruptions or fill-derived samples. Affirmative drill evidence requires identity-bound activation and observed new-order-blocked events, not absent or truthy flags. The kill-switch guard records these outcomes when it actually refuses execution. Such an operational halt is retained; drill proof does not erase interruption history or authorize automatic resume.

## Durability and recovery

`paper_sessions`, `paper_attempts`, `paper_attempt_events`, `paper_cycles`, `paper_session_orders`, `paper_fills`, `paper_reference_prices` and `paper_drill_events` form the scoped ledger. SQLite uses FULL synchronous commits. An attempt-start row is committed before broker connection/reconciliation/execution. A process kill therefore leaves an unclosed attempt even if no `finally` executes.

On restart, unclosed attempts become interrupted with downtime measured since their last durable heartbeat. In-flight cycles become blocked rather than fabricated completions. Graceful incomplete attempts and their resume downtime remain in the ledger too. Halt reasons and unresolved state are not cleared by a restart, even when a checkpoint is missing. Startup reconciliation is mandatory for the paper loop regardless of the general engine configuration flag, and unknown/partial portfolio authority blocks execution.

Checkpoints are atomically replaced after file fsync and contain an identity binding plus a SHA-256 integrity checksum. They are not the activity source of truth: the durable ledger is. Corrupt/mismatched checkpoints halt before broker activity. A checksum detects accidental corruption, not malicious modification by a user who can rewrite both the database and artifacts.

Incomplete windows receive immutable per-attempt reports, and their rows remain available on resume. A finalized session artifact is immutable and refuses another run before broker connection. Restart deduplication relies on the existing persisted OMS deterministic-client-ID check; this work does not change its state machine, reconciliation state machine, strategy rules or risk limits.

## Qualification and operational limits

The runbook thresholds are unchanged: 30 calendar days, 20 market sessions, 100 observed trades, at least 99.5% cycle completion, slippage warning at 1.5x and blocking at 2.0x. Existing zero-unexplained-missed-cycle/unresolved-reconciliation checks remain fail closed. Incomplete/interrupted attempts block a passing window; resuming does not conceal downtime.

Report construction checks the immutable observation snapshot against the named session's SQLite ledger. Confirmation re-derives metrics and reports from the immutable observation records, verifies all identities and rejects incomplete, mismatched, non-finite or internally inconsistent evidence. Legacy totals-only reports require a new observation-backed campaign; they are not grandfathered into qualification.

The trust boundary remains the local operator's artifact/database storage. Evidence is attributable and internally checked, not cryptographically attested by the broker. Broker credentials, production connectivity, live campaigns and promotion of real Experiments are outside this offline reconciliation work.
