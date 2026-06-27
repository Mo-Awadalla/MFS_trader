# mfs-trader

Medium-frequency trading system where tradable hypotheses are frozen as Experiments and filtered through a promotion pipeline before paper or live deployment.

## Language

**Strategy**:
A reusable signal definition and its parameter schema (e.g. dual MA crossover, Bollinger Bands). Not promoted; only a factory for Experiments.
_Avoid_: Alpha, hypothesis (when you mean the frozen bundle), system

**Experiment**:
A frozen tradable hypothesis identified by an immutable UUID (primary key), a canonical experiment hash (fingerprint of the frozen snapshot), and a human-readable label. Includes strategy identity, parameters, universe, data version, cost/slippage model, risk/sizing config, and decision-path code commit.
_Avoid_: Strategy (when you mean a specific qualified instance), run, backtest

**Artifact Manager**:
The file-system authority for Experiment evidence. It owns canonical artifact paths, directory creation, low-level reads/writes, and overwrite policy; it does not own Experiment identity or lifecycle semantics.
_Avoid_: Experiment registry, run folder, artifact store

**Experiment Evidence**:
Files that document what happened to an Experiment or Run, including metadata, validation reports, verdicts, replay attribution, diagnostics, logs, paper sessions, and live sessions. Evidence is grouped under the Experiment UUID that it belongs to.
_Avoid_: Runtime state, promotion status, strategy config

**Immutable Artifact**:
Experiment Evidence that is written once and then preserved for audit. Validation reports, verdicts, replay attribution, diagnostics, session files, and run logs are immutable artifacts.
_Avoid_: Mutable report, latest file, scratch output

**Run Log Artifact**:
The completed runtime log copied into an Experiment's artifact directory after execution. It is final evidence, not a streaming log sink or appendable runtime file.
_Avoid_: Logger, log handler, live log stream

**Artifact Kind**:
The canonical category of an Experiment artifact, such as validation report JSON, replay attribution JSON, or run log. A kind determines the artifact's canonical path, format, and mutability policy.
_Avoid_: Filename string, report type, output name

**Legacy Artifact Location**:
A historical artifact path from before canonical Experiment artifact layout existed, such as a path under `runs/`. It is optional provenance only, never a second supported storage backend.
_Avoid_: Artifact root, managed artifact path, fallback store

**Experiment Hash**:
SHA-256 of the canonical frozen snapshot (strategy, strategy template version, params, universe, data, cost/slippage, portfolio, risk, execution assumptions, paper thresholds, git commit, config version, random seed). Proves exactly what was tested.
_Avoid_: UUID (when you mean identity), config file path

**Strategy Template Version**:
Immutable signal-engine revision for a Strategy (e.g. `bollinger_bands:v2`, `dual_ma_crossover:v2`). Same hypothesis can span template versions; Experiments record which engine produced them.
_Avoid_: Strategy version (when you mean code commit), Experiment UUID

**Superseded**:
Terminal status for an Experiment invalidated by a newer Experiment (e.g. decision-path bugfix). Kept for audit history; not failed, not retired, must never resume.
_Avoid_: Suspended, retired

**Run**:
One execution of an Experiment that produces evidence (backtest, WFA fold set, MC batch, engine replay, paper session, live dry-run).
_Avoid_: Experiment, trial

**Promotion Candidate**:
An Experiment currently moving through the gauntlet.
_Avoid_: Strategy, run

**Gauntlet**:
The full Experiment promotion lifecycle. An Experiment moves through: research → validation → paper ops → live dry-run → live candidate → live → suspended/retired (with scale/de-scale while live).
_Avoid_: Validation (when you mean the whole pipeline), shakedown

**Validation Gauntlet**:
The statistical validation stage within the Gauntlet: WFA, Monte Carlo, DSR, and parameter stability.
_Avoid_: Gauntlet (when you mean only this stage), backtest

**Shakedown**:
An operational plumbing test for Strategy templates and engine infrastructure (data path, engine, OMS, sim broker, event logging, reports, replay determinism, failure-mode handling). May produce evidence but does not promote an Experiment and does not authorize paper or live deployment.
_Avoid_: Gauntlet, validation, paper ops

**Promotion Status**:
The Experiment's current lifecycle stage within the Gauntlet. Allowed values: `research`, `validation_running`, `validation_failed`, `validation_passed`, `paper_ops`, `live_dry_run`, `live_candidate`, `live`, `suspended`, `retired`, `superseded`.
_Avoid_: Blocker (when you mean why advancement is blocked), pass/fail (as a status)

**Promotion Blocker**:
Experiment-scoped veto on advancing to the next lifecycle stage. Does not by itself halt trading.
_Avoid_: Kill switch, suspended, failure (as a status)

**Kill Switch**:
Experiment-scoped control on trading activity. Soft kill blocks new orders; hard or catastrophic kill suspends the Experiment.
_Avoid_: Promotion blocker, strategy halt (when you mean one Experiment)

**Suspended**:
An Experiment lifecycle status meaning trading and promotion are halted until an explicit manual resume or postmortem workflow completes.
_Avoid_: Blocked, halted (as a generic term)

**Operational Report Blocker**:
Evidence computed from a Run's event log (e.g. reconciliation mismatches, broker timeouts). May create an Experiment-level promotion blocker but is not the canonical blocker store.
_Avoid_: Promotion blocker (when you mean the canonical Experiment record)

**Strategy-Template Halt**:
Reserved for code or template defects affecting all Experiments using a Strategy. Not used because one Experiment failed.
_Avoid_: Kill switch (when you mean one Experiment)

**Pair Candidate**:
An ordered pair of two eligible symbols being tested for a statistical arbitrage relationship during formation. It is research input, not an active trade and not an Experiment by itself.
_Avoid_: Position, Experiment, spread trade

**Pair Relationship**:
A fitted relationship between two symbols, including cointegration result, hedge ratio, intercept, spread definition, and diagnostics from the formation window. It may be selected for trading by an Experiment.
_Avoid_: Pair candidate, active pair, portfolio position

**Active Pair**:
A Pair Relationship currently carrying an open long/short spread position inside an Experiment. Active pairs obey max active pair, one-symbol-at-a-time, stop, exit, and max holding constraints.
_Avoid_: Pair candidate, cointegrated pair

**Spread**:
For Pairs v1, the residual series `log_price_y - beta * log_price_x - intercept` from OLS on log prices. The spread is normalized to a rolling z-score for entry, exit, and stop decisions.
_Avoid_: Price difference, ratio, residual (when you mean the traded spread)

**Paper Ops**:
Operational testing stage where an Experiment trades against a broker (paper) to prove implementation behavior. Not alpha validation.
_Avoid_: Paper trading (when you mean alpha test), validation

**Paper Broker Session**:
One bounded broker-authority run for an Experiment in Paper Ops. A paper broker session records lifecycle gate outcomes, caps, broker actions, reconciliation, drills, and final pass/block status as immutable Experiment Evidence.
_Avoid_: Paper run (when you mean the evidence-bearing broker session), live dry-run

**Simulated Paper Drill**:
A controlled `sim_broker` paper broker session that forces reject, timeout, and reconciliation failure modes before any real paper broker authority is allowed.
_Avoid_: Backtest, Alpaca smoke test

**Alpaca Paper Smoke**:
A one-shot paper broker session against Alpaca paper that may submit at most one tiny far-limit DAY order, immediately cancel it, and reconcile broker state.
_Avoid_: Continuous paper trading, live dry-run, market order test

**Paper Capital Cap**:
The explicit paper broker session limits on per-order notional, session notional, and open paper exposure. Missing or excessive caps block broker authority before order submission.
_Avoid_: Risk limit, portfolio allocation

**Paper Operator Report**:
Experiment-level paper readiness evidence aggregating paper broker sessions, operational reports, lifecycle gates, caps, drills, and blockers. It supports but does not replace manual operator confirmation.
_Avoid_: Operational report (when you mean one engine DB summary), automatic promotion

**Live Dry-Run**:
A distinct promotion stage using live broker credentials and live account/market reads, with order submission disabled at the lifecycle level regardless of config.
_Avoid_: Paper ops, live candidate

**Live Candidate**:
Passed live dry-run; awaiting final deployment approval. Live credentials, orders still disabled. The "loaded gun, safety on" state.
_Avoid_: Live (when deployment is not yet approved)

**Live**:
Final deployment approval given: `authorized=true`, `dry_run_mode=false`, capital caps valid, orders enabled and capped.
_Avoid_: Live candidate, paper ops

**Retired**:
Terminal operator-confirmed status. The Experiment is removed from active promotion and trading. Re-evaluation requires a new Experiment.
_Avoid_: Suspended, superseded

**Order State**:
The lifecycle of a single order from intent through terminal outcome (e.g. INTENDED, SUBMITTING, FILLED, TIMEOUT, UNKNOWN). Separate from reconciliation.
_Avoid_: Reconciliation status, portfolio state

**Reconciliation Status**:
Whether a specific order's broker record matches internal records (NOT_CHECKED, MATCHED, MISMATCHED, REPAIRED, UNRESOLVED). Not an order lifecycle state.
_Avoid_: Order state, portfolio state

**Portfolio State**:
The authoritative derived state for rollback and flatten decisions: KNOWN, PARTIAL, or UNKNOWN. The decision engine uses only this field.
_Avoid_: Order state, promotion status, exposure confidence (as a stored field)

**Exposure Confidence**:
Dashboard telemetry derived from `portfolio_state` at read time — never stored independently. HIGH = KNOWN, MEDIUM = PARTIAL, LOW = UNKNOWN.
_Avoid_: Risk score, promotion status, portfolio state (as a separate authority)

## Rules

Promotion applies to Experiments, not Strategy templates or individual Runs.

Experiment identity: immutable UUID (primary key), canonical experiment hash (fingerprint), human-readable label (for operators). The UUID is identity; the hash proves what was tested; the label is for humans.

Registry owns identity. Artifact Manager owns evidence. Engine DB owns runtime state.

`metadata.json` is physically managed by Artifact Manager but semantically owned by the Experiment Registry/Store. Registry/Store decides metadata content, lifecycle validity, and promotion status; Artifact Manager decides the canonical path and enforces low-level write/read and overwrite rules.

Artifact immutability is policy by kind. `metadata_json` is mutable only through Registry/Store for lifecycle metadata updates; all other evidence artifacts are write-once and Artifact Manager must reject overwrites even if a caller asks for overwrite.

Runtime logging remains owned by the runtime/logger. Artifact Manager archives the completed `logs/run.log` once after execution; it does not manage open log handles, streaming appends, flush behavior, or crash recovery.

Artifact Manager is identity-blind. It may validate storage concerns such as UUID syntax and path traversal safety, but it must not query the Experiment Registry to prove that an Experiment exists.

Artifact kinds are canonical domain categories, not arbitrary strings. Public APIs may accept exact string values for convenience, but Artifact Manager must normalize them to `ArtifactKind` and reject unknown kinds immediately.

An Artifact Kind defines the artifact contract: canonical path, serialization format, and mutability policy. Artifact Manager enforces JSON-vs-text behavior by kind; callers do not choose arbitrary serialization for a kind.

Artifact Manager is forward-looking only. It only knows the canonical `experiments/<uuid>/` layout; legacy paths may remain in metadata as optional historical provenance, but new code must never write new Experiment evidence to legacy locations.

Readers must never observe a partially written artifact, and immutable artifacts must never be silently replaced. Immutable evidence is created exactly once; mutable metadata updates must appear atomically to readers.

Looking up an artifact path must not mutate the filesystem. Writing an artifact creates the required parent directories implicitly so callers never manage Experiment artifact directories as a separate lifecycle step.

Material changes create a new Experiment (no inherited promotion): strategy logic or parameters; **strategy template version**; universe definition; data version, date range, or content; cost/slippage model; execution assumptions; portfolio sizing; risk limits; decision-path code changes (strategy, portfolio, risk, execution, OMS, validation, replay, data processing); paper thresholds after Experiment creation; broker change when execution assumptions materially change (fills, fees, routing).

A strategy template version bump (e.g. `bollinger_bands:v1` → `v2`) is material when signal-engine behavior changes, even if the hypothesis and parameters are unchanged. The archived Experiment stands; new template versions require new Experiments.

Immaterial changes remain the same Experiment (audit event still required): monitoring, logging, reporting, dashboard, artifact paths, documentation, CLI UX, Telegram chat ID, cooldowns.

A decision-path bugfix always creates a new Experiment and requires full re-qualification. The old Experiment becomes `superseded`, not `suspended`.

Paper-to-live progression is a lifecycle transition on the same Experiment, not a new Experiment.

Identical data re-downloaded with unchanged content (hash/manifest match) is not a material change.

"Passed the gauntlet" may only be said about a frozen Experiment after it has completed the required lifecycle gates for its current promotion target.

"Passed validation" means the Experiment passed WFA, MC, DSR, and stability only.

"Passed shakedown" means the plumbing worked. It is not alpha evidence.

Shakedown proves the machine can run. Validation proves the hypothesis deserves paper. Paper proves the implementation behaves against a broker. Do not mix these or promotion language becomes fiction.

`promotion_status` tracks where the Experiment currently sits in the promotion lifecycle, not every pass/fail detail:

- `research` — exists but has not started or completed statistical validation
- `validation_running` — Validation Gauntlet in progress
- `validation_failed` — failed WFA, MC, DSR, or stability; terminal for this Experiment unless superseded by a new one
- `validation_passed` — passed WFA, MC, DSR, and stability; eligible for paper ops, not live
- `paper_ops` — in paper operational testing; not paper-approved, under evaluation
- `live_dry_run` — live credentials; live account, position, order, quote, and reconciliation reads; order submission disabled even if config is wrong
- `live_candidate` — passed live dry-run; deployment checklist ready; awaiting final human approval; orders still disabled
- `live` — `authorized=true`, `dry_run_mode=false`, capital caps valid, deployment checklist passed, orders enabled and capped
- `suspended` — halted due to kill switch, catastrophic failure, manual intervention, unresolved broker state, or serious operational breach
- `retired` — operator-confirmed terminal removal; re-evaluation requires a new Experiment
- `superseded` — invalidated by a newer Experiment; audit history only; must never resume

Failures inside a stage are represented as blockers, events, reports, or kill-switch state. They do not automatically change `promotion_status` unless the Experiment is explicitly halted, suspended, or retired.

Scaling is metadata on live Experiments (`capital_tier`, `capital_status`), not a `promotion_status`.

Status says where the Experiment is. Blockers say why it cannot advance. Events say what happened. Do not mix them.

Blockers stop promotion. Kill switches stop trading. Suspended freezes the Experiment.

Kill switches are Experiment-scoped, not Strategy-scoped. Two Experiments sharing the same Strategy template are controlled independently.

Promotion blockers block advancement only. Kill switches control trading: soft kill blocks new orders (status unchanged, usually also sets a blocker); hard or catastrophic kill sets `promotion_status` to `suspended`. Use `suspended` for hard kill, catastrophic unknown state, manual suspension, serious operational breach, or unresolved broker state — not for routine in-stage failures like elevated reconciliation rates.

Operational report blockers are evidence from a Run. They may create Experiment-level promotion blockers but are not the canonical blocker store.

Paper ops passed means an Experiment completed its configured paper trading window and satisfied operational criteria. It does not mean the strategy produced alpha.

Paper ops thresholds are Experiment-scoped config values frozen in the Experiment snapshot before paper starts (defaults: 30 calendar days, 100 minimum trades, 200 target trades). Changing them creates a new Experiment or requires explicit operator override.

Paper Sharpe is recorded but is not a paper ops pass/fail metric unless losses trigger a defined retirement or kill-switch rule.

The system may automatically evaluate paper ops readiness, but advancement from `paper_ops` to `live_dry_run` requires explicit operator confirmation (`confirm-paper-ops-pass`). No automatic promotion.

Slippage uses two thresholds: warning at 1.5× modeled, blocker at 2.0× over the paper window. Warnings require operator acknowledgment before advancement.

Bar-cycle completion must be ≥99.5% over the paper window, with zero unexplained missed cycles.

Paper ops proves the machine behaves. It does not re-litigate alpha. The system can recommend graduation; only the operator promotes.

`live_dry_run` proves the live environment can be observed safely. `live_candidate` means ready but not armed. `live` means armed, capped, and explicitly approved.

Advancement to live stages is hybrid: system evaluates readiness, operator explicitly confirms each promotion. No automatic promotion into live.

- `paper_ops` → `live_dry_run`: operator confirms paper ops passed
- `live_dry_run` → `live_candidate`: dry-run checklist passes + operator confirms
- `live_candidate` → `live`: deployment checklist passes + operator confirms + `authorized=true`

While `single_strategy_first_live=true`, if any Experiment is `live`, no other Experiment may enter `live` or `live_dry_run`.

Experiments are never automatically retired. The system may recommend retirement; only the operator confirms via `confirm-retire`. Re-evaluation after retirement creates a new Experiment.

Threshold breaches produce blockers, de-scaling, kill switches, suspension, or retirement recommendations — never silent retirement.

| Signal | Typical response |
|--------|------------------|
| Minor operational breach | Promotion blocker or soft kill |
| Serious operational breach | Soft/hard kill; unknown broker state → `suspended` |
| Alpha decay (warning) | `capital_status=reduced` + blocker; operator review |
| Alpha decay (serious) | `suspended` + retirement recommendation |
| Risk event (soft) | Soft kill + blocker + postmortem required |
| Risk event (hard) | `suspended` |

`capital_status=reduced` means the Experiment remains `live` at smaller capital. `suspended` means trading halted and postmortem required. `retired` is terminal and operator-confirmed only.

Alpha decay on a live Experiment defaults to `suspended` + retirement recommendation unless deterioration is within expected Monte Carlo/live distribution and drawdown is tolerable — then `capital_status=reduced` + blocker + operator review.

Operational breaches suspend only when state is unsafe, unknown, or severe. Minor breaches create blockers or soft kills.

The system may recommend death. Only the operator signs the death certificate.

Treat an Experiment like a scientific specimen in formaldehyde. Once created, you do not fix it — you create a new specimen and preserve the old one for audit.

Flatten decisions are made from reconciled broker positions, not historical order states. Orders are evidence; positions are reality.

`order_state`, `reconciliation_status`, and `portfolio_state` remain separate. The decision engine relies on `portfolio_state` only. `exposure_confidence` is derived telemetry for dashboards at read time — never stored as an independent field.

`portfolio_state` definitions:

- **KNOWN** — current broker positions and pending exposure are fully reconciled; safe to flatten and cancel safe orders
- **PARTIAL** — broker-reported net positions are fully known, but one or more non-terminal orders are still reconciling and their final execution cannot increase net exposure beyond configured limits; flatten confirmed positions only after canceling or confirming outstanding orders; block new orders; suspend Experiment; continue reconciliation
- **UNKNOWN** — broker truth cannot be established; future net exposure is ambiguous; freeze; no flatten; no new orders; manual intervention required

A historically known fill does not authorize liquidation if pending orders could still change net exposure. Flatten only when the current reconciled broker position is confirmed with no ambiguous future exposure.

Resume from `suspended` never auto-restores trading authority. Operator must explicitly `confirm-resume`. Store `suspended_from_status` at suspension time.

| Suspension cause | Resume target | Requirements |
|------------------|---------------|--------------|
| Operational / UNKNOWN portfolio | Same stage (`suspended_from_status`) | `portfolio_state=KNOWN`, postmortem, kill switch cleared, no active blockers |
| Risk soft-kill escalation | Same stage | Postmortem, blocker cleared |
| Alpha decay | Operator choice | `live` (reduced), `live_candidate`, or `confirm-retire` |
| Manual suspension | Same stage | Operator checklist |

After any live suspension, default to `capital_status=reduced` on resume unless operator explicitly restores full tier.

## Phase 4 — Strategy Expansion

Order: BB → CSMR → Momentum → pairs. Each strategy implements `StrategyTemplate` (`strategies/contract.py`). BB (`bollinger_bands:v2`) is the reference implementation.

### Strategy Contract (`strategies/contract.py`)

Every strategy template must implement a single plug-in surface — no per-strategy API drift:

| Method | Purpose |
|--------|---------|
| `generate_signals(df, params)` | OHLCV → signal frame (`position`, `signal`, raw cross columns) |
| `default_params()` | Frozen default hypothesis parameters |
| `sweep_grid()` | Full research sweep grid |
| `compact_sweep_grid()` | Small grid for tests and smoke sweeps |
| `diagnose_signals(df, params)` | Returns `StrategyDiagnostics` |
| `validate_inputs(df)` | Raises on missing columns or bad index |
| `required_columns()` | Tuple of required OHLCV column names |
| `warmup_bars(params)` | Bars before first valid signal |
| `metadata()` | Strategy identity dict (includes `strategy_template_version`) |
| `supports_long()` / `supports_short()` | Capability flags |

`strategy_template_version` is `{name}:{template_version}` (e.g. `bollinger_bands:v2`). It distinguishes same hypothesis vs different implementation without renaming the strategy. Included in experiment fingerprints and validation reports; archived experiments are never rewritten when the template bumps.

Registry: `strategies/registry.py` — `get_strategy(name)`, `registered_strategies()`, `strategy_template_version(name)`.

### Strategy diagnostics

`StrategyDiagnostics` (`strategies/contract.py`) is the shared diagnostics dataclass. Built via `diagnose_from_signal_frame()` from any signal DataFrame:

- Raw vs filtered entry/exit event counts
- Entry/exit signal counts (position diffs)
- Average holding period, turnover, percent time invested
- `rejected_by_reason` (e.g. width filter rejections for BB)
- Warmup bars, NaN position bars, execution mode (`next_bar_open`)
- Optional entry/exit signal timestamps

Each strategy's `diagnose_signals()` delegates to the shared builder with strategy-specific raw cross column names.

### Contract tests (`tests/contracts/`)

Reusable helpers in `tests/contracts/helpers.py` — `run_contract_suite(strategy)` asserts:

- Required surface present and metadata complete
- `validate_inputs` enforces columns
- Deterministic output, no lookahead, signal = position diff
- Warmup handling, exit contract (flatten on raw exit while long)
- Diagnostics internally consistent
- BB parameter roundtrip (strategy-specific hook)

`tests/contracts/test_strategy_contract.py` parametrizes over `registered_strategies()` so new strategies inherit the suite automatically. Replay golden determinism remains in `tests/replay/`.

### Strategy template lifecycle

1. **Implement** — subclass `StrategyTemplate`, register in `strategies/registry.py`, bump `template_version` on material signal-logic changes.
2. **Validate** — contract suite + unit tests + replay golden (if deployment path exists).
3. **Experiment** — freeze UUID + hash + label; record `strategy_template_version` in experiment metadata.
4. **Bugfix** — bump `template_version`, mark prior experiment `superseded`, create new experiment; never mutate archived artifacts.
5. **Promote** — Validation Gauntlet on frozen experiment only.

Historical note: exit-state bug in BB/MA long-only paths fixed in `v2` (NaN-hold pattern replaces `replace(0, NA).ffill()` that swallowed exits).

## Experiment Registry (`experiments/`)

Single source of truth for frozen Experiments — separate from engine runtime SQLite.

| Store | Role |
|-------|------|
| `experiments/index.sqlite` | Query index (strategy, template version, promotion_status, data_source) |
| `experiments/<uuid>/metadata.json` | Audit artifact / source of truth for frozen snapshot |
| Engine `*.sqlite` | Runtime only (orders, events, kill switches) |

Package layout: `models.py`, `hashing.py`, `storage.py`, `registry.py`, `backfill.py`.

**Identity:** immutable UUID (primary key), canonical `experiment_hash` (SHA-256 of decision-path snapshot), human `label`.

**Hash includes:** strategy, `strategy_template_version`, parameters, universe, data version, date range, execution mode, cost model, slippage model, risk profile, portfolio config, paper thresholds, git commit, config version, random seed.

**Hash excludes:** uuid, label, `experiment_hash`, `promotion_status`, `created_at`, `superseded_by`, legacy artifact pointers, reports, logs.

**Registry API:** `create(draft)`, `import_existing(experiment)` (backfill), `get(uuid)`, `get_by_hash`, `list_experiments(...)`, `transition_promotion_status`, `mark_superseded`.

**BB pipeline:** `run_bb_validation_gauntlet(..., registry=, experiment_label=)` registers experiment and records validation outcome. Archived `BB-AAPL-1D-Default` backfilled via `experiments.backfill.backfill_bb_aapl_1d_default()` without mutating `runs/bb_aapl_validation_alpaca/`.

**Artifact Manager:** implemented. Canonical evidence writes go through `experiments/<uuid>/` using `ArtifactManager`; non-metadata evidence is write-once.

**CSMR v1:** implemented and validated as canonical long/short cross-sectional mean reversion. Corrected terminal experiment `6ed472a7-a361-46b2-bdb9-2a196c459cca` failed the Validation Gauntlet on the Alpaca SIP current-active liquid panel (`data_source=alpaca_sip_current_active_common_shortable_liquidity_scouted_2026-06-26`). Evidence lives at `experiments/6ed472a7-a361-46b2-bdb9-2a196c459cca/`; verdict is `FAIL`. Do not tune CSMR v1. Any CSMR variant is a new Experiment.

**Momentum v1:** implemented and validated as canonical cross-sectional 12-1 momentum. Corrected terminal experiment `fcd91de3-6d84-4458-918f-693640c2eb52` failed the Validation Gauntlet on the Alpaca SIP current-active liquid panel (`data_source=alpaca_sip_current_active_common_shortable_liquidity_scouted_2026-06-26`). Evidence lives at `experiments/fcd91de3-6d84-4458-918f-693640c2eb52/`; verdict is `FAIL`. Do not tune Momentum v1. Any Momentum variant such as 6-1, long-only, sector-neutral, beta-neutral, volatility-weighted, different buckets, or different rebalance frequency is a new Experiment.

**Pairs v1:** frozen as a US-equities-only statistical arbitrage subsystem. It inherits CSMR/Momentum tradability filters, excludes crypto, uses the top 150 symbols by 20-day median dollar volume, and tests all-vs-all candidate pairs unless sector data already exists, in which case same-sector filtering may be used. Pair selection uses Engle-Granger cointegration with `p <= 0.05` over a 252-trading-day formation window. Hedge ratio is OLS on log prices with intercept. Spread is `log_price_y - beta * log_price_x - intercept`, normalized by rolling z-score. Entry is `|z| >= 2.0`; exit is `|z| <= 0.5`; stop is `|z| >= 4.0` or 60 trading days max holding. Refit occurs on the first trading session of each month. Max active pairs is 20, with one active position per symbol. Capital uses equal gross budget per pair. No optimization or tuning.

**Pairs v1 discipline:** if Pairs v1 fails, archive it. Do not tune thresholds, add crypto, add sector filtering retroactively, change lookback, or change z-score thresholds. Any variant is a new Experiment.

**Pairs v1 negative-control gate:** Pairs v1 must fail early and cleanly before signal generation when the feasible universe cannot support the declared matching requirements. The canonical failure is `UNIVERSE_COVERAGE_FAILURE` at Layer 2A, recorded as immutable feasibility evidence on the Experiment, with no validation report written because the Validation Gauntlet never ran.

**Paper-run safety spine:** `paper-run` is lifecycle-gated and defaults to sim/stub execution. It must refuse wrong `promotion_status`, experiment hash mismatch, any active Experiment kill switch, and any `portfolio_state` other than `KNOWN`; Alpaca paper is only reachable through the explicit one-shot Paper Broker Session gate.

**Alpaca paper boundary:** Alpaca paper is broker authority, so it is allowed only as a one-shot Paper Broker Session with explicit operator confirmation, tiny caps, prior passing Simulated Paper Drill evidence, and immediate cancel/reconcile. It is not a continuous loop and not a live dry-run.

## Implementation backlog (domain ahead of code)

- ~~Experiment registry (UUID, hash, label)~~ ✓
- ~~Artifact Manager (`validation/`, `replay/`, `paper/` under `experiments/<uuid>/`)~~ ✓
- ~~Momentum canonical v1 hypothesis~~ ✓
- ~~Pairs v1 negative-control feasibility gate~~ ✓
- ~~`promotion_status` vocabulary migration (`validation_passed`, `paper_ops`, `superseded`, etc.)~~ ✓
- ~~Experiment-scoped kill switches~~ ✓
- ~~`portfolio_state` derivation in runtime~~ ✓
- ~~Operator confirm commands (`confirm-paper-ops-pass`, `confirm-resume`, `confirm-retire`)~~ ✓
- ~~Sim/stub-only `paper-run` CLI safety gate~~ ✓
- Pairs vX pair-discovery subsystem (research-only first; create Experiment/evidence if it enters validation)
