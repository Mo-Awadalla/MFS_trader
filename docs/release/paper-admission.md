# Paper admission boundaries

This release is an experimental research/validation workbench with simulated execution. Offline engineering checks do not establish broker-paper qualification or authorize real broker activity.

## Retired unqualified routes

`paper-trade-ma`, `paper-dry-run-ma`, and `paper-run --alpaca-paper-smoke` are no longer CLI commands/options. The standalone `run_alpaca_paper_smoke` API and its broker-submit implementation have been removed. It had no durable pre-effect session reservation and could submit again when a session ID was reused with a different symbol. Retirement removes that authority; it is **not** a repaired or qualified broker smoke implementation.

The old `run_ma_paper_trade_once` and `run_ma_paper_dry_run` diagnostic functions accept simulation brokers only. They cannot be used for authenticated broker reads or submissions. Existing historical smoke artifacts remain readable and are not rewritten; a legacy smoke flag or simulated drill does not establish current broker-paper qualification.

## Retained qualification prerequisites

Both `simulated_drills` and `alpaca_paper_smoke` remain mandatory prerequisites in
the common `evaluate_paper_ops_pass_session` evaluator used by operator reporting
and manual confirmation. An otherwise complete 30-day pass session cannot
qualify without either prerequisite. Numerical qualification and explicit manual
confirmation remain separate, unchanged gates.

The simulated prerequisite must identify the current Experiment UUID/hash and
provide affirmative lifecycle checks and consistent reject, timeout, and
reconciliation drill outcomes in the existing session format. Simulation proves
only that prerequisite; it never substitutes for broker smoke.

Broker smoke requires a distinct `paper_ops_smoke` session of type
`alpaca_paper_smoke`, attributable Alpaca-paper observations, and its immutable
`paper_ops_smoke_report.json`. The report must match recomputation from those
observations, including the existing five-market-session/seven-day window,
cycle/interruption checks and observed kill-switch drill. Its execution,
configuration, calendar and account identity must match the candidate pass
session. Missing, truthy-only, nonfinite, inconsistent, wrong-Experiment or
wrong-environment evidence cannot satisfy either prerequisite. Unbound legacy
PASS reports remain readable historical material, not current qualification.
Confirmation records hashes of the accepted prerequisite artifacts alongside
the full pass-session evidence.

The retired one-shot smoke producer remains removed. This validator adds no
broker access or replacement producer. In the absence of qualifying retained
broker-smoke evidence, qualification remains blocked; no requirement is relaxed
to work around that absence. Regression fixtures use explicitly synthetic
temporary events and real temporary SQLite only, never real broker qualification
or changes to real Experiment metadata.

## Guarded continuous boundary

The retained `paper-run` continuous orchestration checks the requested Experiment and current numerical qualification. Both credential-bearing origins must match the Alpaca HTTPS paper trading origin and Alpaca market-data origin. A live trading origin, arbitrary data origin, disabled submission, dry-run mode, missing startup reconciliation, nonpersistent kill state, or nonfinite/out-of-bounds paper cap blocks admission.

Before credentials, prepared MA and ETF strategies must match the frozen strategy name/version, complete parameters, exact universe, frequency, data adjustment/source, execution timing, cost/slippage assumptions, risk profile, and portfolio settings. MA executes the complete frozen parameters rather than silently replacing non-CLI parameters with defaults. A qualified Bollinger Bands snapshot cannot authorize MA. A Yahoo-data snapshot cannot silently become an Alpaca hypothesis.

`bind_paper_strategy_callable` resolves the canonical MA/ETF implementation from those verified full parameters and symbols. Broker-paper orchestration must use this callable, not trust a caller-supplied function merely because its declared name matches. Simulation retains injectable callbacks for failure testing. Prepared closures capture independent frozen parameter values and reject subsequent runtime parameter substitution.

CLI construction passes a deferred broker factory to `PaperRunLoop`; it neither obtains credentials nor connects first. The loop owns exclusive local runner admission, durable attempts, finalized-session rejection, ledger/checkpoint identity, persisted halt and unresolved-order checks before invoking that factory. The actual adapter is checked against the admitted origins before connection. A checksummed checkpoint belonging to another session is still rejected before credentials. Credential/connect failures after admission have durable attempt outcomes. ETF refresh is deferred until the admitted running loop; initial preparation requires local cached bars.

Paper caps remain additional authority bounds, not changes to strategy sizing or risk-limit semantics. Current numerical qualification, observed paper operational evidence, and publication approval remain separate decisions. No real Experiment was qualified or promoted by these changes.

## Execution timing is a separate broker admission gate

`verify_broker_paper_execution_mode(config, experiment)` accepts only the explicit frozen mode `broker_market_after_completed_bar_observed_fill`, with completed-bar processing enabled. This names the retained continuous implementation: the exchange-calendar loop admits a completed, timely bar; the canonical strategy computes its targets; sizing uses the observed broker quote; the engine submits a market order when processing that cycle; subsequent broker-reported fills are observed evidence. Submission can be later than the bar boundary. The reference quote is not a guaranteed fill price, and execution/fill time is not promised to coincide with the next session open or any bar close.

`bar_close_execution = true` is not evidence of next-open scheduling. Neither a one-bar target shift nor a strategy's theoretical signal convention implements a guaranteed next-open fill. Consequently `next_bar_open`, `next_bar_close`, and `signals_after_t_minus_1_close_first_executable_price` are unsupported frozen assumptions for broker-paper admission and are rejected before credentials by the CLI and non-simulation loop. No equivalence with the retained ETF hypothesis or research/replay fill models is claimed.

Only temporary synthetic test snapshots declare the observed-fill mode in this change. Existing real snapshots and evidence remain byte-for-byte untouched; no lifecycle or financial-parity authority follows from naming this mode. Simulation preparation can still inspect hypotheses with other frozen timing conventions, but it does not run the broker timing gate or establish qualified execution. There is no authorization override for unsupported broker timing.

## Offline regression targets

The coordinator runs validation after integration; no mid-flight validation is implied here:

- `tests/unit/test_cli_smoke.py`: retired routes, repeated retired smoke session with different symbols, invalid data origins, mismatched checkpoint before credentials, durable attempt before credential lookup, unsupported frozen timing refusal with metadata preservation.
- `tests/unit/test_paper_strategy.py`: synthetic frozen ETF/MA preparation, full MA parameters, strategy/universe/parameter/cost/risk/portfolio/frequency/source substitution rejection before data access; research-timing preparation remains simulation-only and fails explicit broker admission.
- `tests/unit/test_paper_session.py`: simulation-only diagnostic boundary, adapter/config origin agreement, finite caps, simulated evidence remains unqualified.
- `tests/integration/test_ma_paper_trade.py` and `tests/integration/test_ma_paper_dry_run.py`: retained diagnostics use synthetic simulation brokers and real temporary SQLite.
- `tests/unit/test_paper_run.py` and `tests/unit/test_paper_evidence.py`: loop/ledger admission, recovery and bounded submission (owned by runtime integration).

All test invocations must set `RUN_LIVE_BROKER_TESTS=0 MFS_TEST_LOAD_DOTENV=0`. No real `.env`, credentials, broker endpoint, or Experiment evidence is needed.
