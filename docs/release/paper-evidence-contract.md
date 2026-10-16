# Paper evidence and recovery contract

This release is an offline research/simulation workbench. Simulation is not broker-paper qualification. Nothing in this contract authorizes a live session or changes an Experiment lifecycle automatically. The existing `confirm-paper-ops-pass` command remains an explicit manual confirmation; a report alone cannot promote an Experiment.

## Observation identity

A continuous paper session has a durable SQLite identity: Experiment UUID and full hash, session id/kind, effective configuration hash, execution-source hash, broker environment, hashed account fingerprint, calendar declaration, cadence, grace interval and configured fixed expected-slippage basis. Account fingerprints include the Experiment and environment; raw account IDs and credentials are not copied into paper artifacts. A restart with another configuration, execution source, account or session fails closed.

The execution hash covers Python source in engine, execution, portfolio, risk, storage, strategies and config. It is a source-content identity (including local edits), not a claim that a published release or a corrected research evaluation passed. Corrected numerical-validation eligibility is a separate admission requirement owned by release integration.

`sim_broker` and `alpaca_paper` are distinct environments. Continuous Alpaca paper admission requires paper mode, the exact paper trading and market-data origins, adapter/configuration agreement, enabled submission, current numerical qualification and manual CLI broker confirmation. Every non-simulated loop binds the strategy name/version, full parameters, universe, cadence, costs, risk/portfolio assumptions and data declaration to the qualified frozen Experiment. It then uses the repository's canonical strategy callable, not an arbitrary caller-injected callback. Simulation retains injectable diagnostics but cannot satisfy broker-paper qualification.

The continuous broker route accepts only an explicitly frozen
`broker_market_after_completed_bar_observed_fill` execution mode with completed-bar
execution enabled. Research `next_bar_open` and ETF first-executable-price assumptions
are not relabeled as equivalent. Existing qualified research artifacts with those
assumptions require a separate justified evaluation; this offline change neither
rewrites them nor authorizes a broker campaign.

Use the shared CLI configuration position: `mfs-engine --config CONFIG paper-run ...`.
The subcommand does not define a second configuration option. CLI adapter construction
and credential lookup are deferred into the loop, after exclusive local ownership,
identity/finalization checks, a committed attempt, kill-switch/lifecycle/qualification
checks and bound checkpoint/persisted-state admission. A SOFT or HARD kill switch
leaves a durable halted attempt with its original reason and no broker activity.

## Calendar and cycles

The declaration `XNYS-mfs / 2026.1` covers 2024-01-01 through 2026-12-31. It excludes weekends and the NYSE full-day holidays, including the 2025-01-09 mourning closure, and specifies 13:00 New York early closes. All exchange instants use `America/New_York`, including DST changes. Queries outside coverage fail closed; extending coverage requires a reviewed calendar declaration and regressions, not an implicit extrapolation.

Expected cycles come from calendar sessions and the configured cadence, never loop iterations. Daily labels use the UTC session date; intraday labels use the interval start. The final interval on an early close is shortened to the actual close. Expected time, actual start, actual completion and the input-data watermark are separate fields. A daily bar becomes eligible at the exchange close, and only cycles whose expected time is in the actual observation window count. Old historical bars do not become current paper sessions.

One eligible cycle can complete only once. Repeated, stale, premature, holiday and weekend labels cannot create completions. Unique observed exchange sessions are counted separately from cycle count. Missing calendar-derived cycles remain in the denominator even when no row or no new data arrives. An overdue cycle is durably recorded and halts the loop rather than leaving a perfect ratio while waiting forever. The default grace is one intraday cadence, or 18 hours after the daily close to accommodate the existing next-date daily-data availability convention. Tests inject the clock and sleeper.

## Orders, fills and slippage

The runtime uses an identity-scoped deterministic order namespace and decision correlation ID. The started cycle and broker reference prices are committed before processing the decision. This permits attribution of an order even if termination occurs immediately after submission and before the next capture.

Only unique orders with lifecycle `FILLED`, positive fully filled quantity, zero remaining quantity and reconciliation `MATCHED` or `REPAIRED` count as trades. Partial fills and multiple fill observations are not extra trades. The paper observer can record an exact broker-status match in existing reconciliation metadata; it does not transition an OMS order state or repair a mismatch. A missing broker status, inconsistent cumulative fill, unresolved reconciliation or account switch halts execution.

Fill increments have deterministic IDs based on order ID and cumulative quantity. Duplicate polls collapse. Each slippage sample is computed from an attributable fill and the pre-decision broker reference-price record, with order ID, fill ID, reference ID and reference source retained. Actual adverse slippage is signed by order side. Expected slippage is explicitly the effective configuration's fixed slippage component; it is not a claim of full variable-impact financial parity. Samples without an attributable reference price are rejected.

Broker-paper submissions additionally pass a paper-only guard immediately before the OMS. It uses the actual risk-adjusted order quantity and a fresh broker quote, then commits a session/attempt-scoped reservation before any broker effect. Per-order, cumulative-session and projected gross-open-exposure caps retain their existing values and admission semantics; the guard refuses a violating intent rather than resizing it or changing strategy/risk rules. Exposure uses fresh prices for every observed position and the proposed signed quantity, so reducing an existing position is not double-counted. Unavailable positions/prices, non-finite values and outstanding orders fail closed.

Session usage is the sum of each durable reservation's larger reserved or observed filled notional. Cancellation/rejection never refunds authority; restart never resets this sum. Missing/uncertain reservation outcomes block further submissions until reconciled outside the loop. Actual cumulative fill quantities and average prices are durably observed and checked after OMS execution and on recovery. Existing market-order semantics are unchanged: an adverse fill can exceed its pre-submit quote; that observed breach halts subsequent activity rather than claiming an impossible guaranteed market execution price. No compensating order or state-machine transition is introduced. Ordinary research/replay does not install this guard. Simulated paper diagnostics may opt into it by configuring caps, without acquiring broker qualification.

After each guarded submission, fill capture and reconciliation run inside the
guard's observation step, before a second order in the same cycle can use session
authority. A fill without the affirmative, fully reconciled terminal observation
cannot leave later submissions relying only on its lower reserved quote.

Supplied totals, samples, drill booleans and insufficient-activity claims remain operator notes. They never replace observed trades, sessions, interruptions or fill-derived samples. Affirmative drill evidence requires identity-bound activation and observed new-order-blocked events, not absent or truthy flags. The kill-switch guard records these outcomes when it actually refuses execution. Such an operational halt is retained; drill proof does not erase interruption history or authorize automatic resume.

## Durability and recovery

`paper_sessions`, `paper_attempts`, `paper_attempt_events`, `paper_cycles`, `paper_session_orders`, `paper_order_reservations`, `paper_fills`, `paper_reference_prices` and `paper_drill_events` form the scoped ledger. SQLite uses FULL synchronous commits. An attempt-start row is committed before broker construction/connection/reconciliation/execution. A process kill therefore leaves an unclosed attempt even if no `finally` executes.

Nonblocking OS ownership is held from local preflight through attempt finalization, checkpoint publication, immutable reports and cleanup. Locks cover both the database (including different sessions sharing engine state) and the Experiment/session artifact path (including different databases claiming one session). Lock files are never unlinked or replaced, and process death releases ownership without stale-PID or heartbeat heuristics. Another runner cannot infer a still-owned attempt is dead, create a competing attempt or touch its checkpoint/report. Attempt ownership is generation-fenced; terminal outcomes cannot be rewritten, and cycle writes cannot replace terminal or other-attempt records. Continuous paper execution currently requires POSIX local-file locking; unsupported platforms refuse this surface explicitly without breaking research/CLI imports.

The artifact-session lock also protects a durable create-if-absent
`paper/sessions/<session-id>/ledger-claim.json`. Before attempt creation or any
credential/broker access, this claim binds the Experiment UUID/full hash and
session to the canonical database path and a unique initialized
`engine_state.paper_ledger_instance_id` token. File and directory fsync protect
claim publication; SQLite FULL commits protect the token. The claim is never
removed on failure, interruption or process death. Resume opens an existing
database without creation and requires both identities to match: selecting another
database, deleting/recreating an empty database at the same path, or changing its
token cannot reset attempts, halts, downtime or cumulative reservation authority.
Identity does not depend on device/inode numbers. A database-path migration is
explicitly outside this admission API and fails closed.

A crash after claim publication but before database/token initialization leaves
an immutable failed-closed reservation, not permission to create replacement
authority. Existing session reports or ledger sessions without a claim are not
silently migrated or rewritten in place; an explicit evidence-preserving recovery
decision is required outside this release's runner.

On restart, unclosed attempts become interrupted with downtime measured since their last durable heartbeat. In-flight cycles become blocked rather than fabricated completions. Graceful incomplete attempts and their resume downtime remain in the ledger too. Halt reasons and unresolved state are not cleared by a restart, even when a checkpoint is missing. Startup reconciliation is mandatory for the paper loop regardless of the general engine configuration flag, and unknown/partial portfolio authority blocks execution.

A terminal OMS state alone is not affirmative reconciliation. Except for orders
blocked locally by risk before broker submission, persisted orders require
`MATCHED`; missing, `NOT_CHECKED`, `REPAIRED` or other status refuses restart before
credentials or broker connection. An abrupt death after a fill but before
reconciliation therefore preserves the original order/status, records interruption
and a halted attempt, and does not resubmit. Manual reconciliation/repair is
required before future execution; the runner neither invents `MATCHED` nor clears
halt authority automatically. Fully matched same-ledger resumes still perform
mandatory startup broker reconciliation.

Checkpoints use unique temporary files, file and directory fsync, and atomic replacement; they contain an identity binding plus a SHA-256 integrity checksum. They are not the activity source of truth: the durable ledger is. Corrupt/mismatched checkpoints halt before credentials or broker activity and are not overwritten by the refused run. A checksum detects accidental corruption, not malicious modification by a user who can rewrite both the database and artifacts.

Incomplete windows receive immutable per-attempt reports, and their rows remain available on resume. A finalized session artifact is immutable and refuses another run before broker connection. Restart deduplication relies on the existing persisted OMS deterministic-client-ID check; this work does not change its state machine, reconciliation state machine, strategy rules or risk limits.

## Qualification and operational limits

The runbook thresholds are unchanged: 30 calendar days, 20 market sessions, 100 observed trades, at least 99.5% cycle completion, slippage warning at 1.5x and blocking at 2.0x. Existing zero-unexplained-missed-cycle/unresolved-reconciliation checks remain fail closed. Incomplete/interrupted attempts block a passing window; resuming does not conceal downtime.

Report construction checks the immutable observation snapshot against the named session's SQLite ledger. Confirmation re-derives metrics and reports from the immutable observation records, verifies all identities and rejects incomplete, mismatched, non-finite or internally inconsistent evidence. Legacy totals-only reports require a new observation-backed campaign; they are not grandfathered into qualification.

The trust boundary remains the local operator's artifact/database storage. Evidence is attributable and internally checked, not cryptographically attested by the broker. Broker credentials, production connectivity, live campaigns and promotion of real Experiments are outside this offline reconciliation work.
