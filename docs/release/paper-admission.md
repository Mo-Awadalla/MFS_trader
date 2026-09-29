# Paper admission boundaries

This release is an experimental research/validation workbench with simulated execution. Offline engineering checks do not establish broker-paper qualification or authorize real broker activity.

## Retired unqualified routes

`paper-trade-ma`, `paper-dry-run-ma`, and `paper-run --alpaca-paper-smoke` are no longer CLI commands/options. The standalone `run_alpaca_paper_smoke` API and its broker-submit implementation have been removed. It had no durable pre-effect session reservation and could submit again when a session ID was reused with a different symbol. Retirement removes that authority; it is **not** a repaired or qualified broker smoke implementation.

The old `run_ma_paper_trade_once` and `run_ma_paper_dry_run` diagnostic functions accept simulation brokers only. They cannot be used for authenticated broker reads or submissions. Existing historical smoke artifacts remain readable and are not rewritten; a legacy smoke flag or simulated drill does not establish current broker-paper qualification.

## Guarded continuous boundary

The retained `paper-run` continuous orchestration checks the requested Experiment and current numerical qualification. Both credential-bearing origins must match the Alpaca HTTPS paper trading origin and Alpaca market-data origin. A live trading origin, arbitrary data origin, disabled submission, dry-run mode, missing startup reconciliation, nonpersistent kill state, or nonfinite/out-of-bounds paper cap blocks admission.

Before credentials, prepared MA and ETF strategies must match the frozen strategy name/version, complete parameters, exact universe, frequency, data adjustment/source, execution timing, cost/slippage assumptions, risk profile, and portfolio settings. MA executes the complete frozen parameters rather than silently replacing non-CLI parameters with defaults. A qualified Bollinger Bands snapshot cannot authorize MA. A Yahoo-data snapshot cannot silently become an Alpaca hypothesis.

CLI construction passes a deferred broker factory to `PaperRunLoop`; it neither obtains credentials nor connects first. The loop owns exclusive local runner admission, durable attempts, finalized-session rejection, ledger/checkpoint identity, persisted halt and unresolved-order checks before invoking that factory. The actual adapter is checked against the admitted origins before connection. A checksummed checkpoint belonging to another session is still rejected before credentials. Credential/connect failures after admission have durable attempt outcomes. ETF refresh is deferred until the admitted running loop; initial preparation requires local cached bars.

Paper caps remain additional authority bounds, not changes to strategy sizing or risk-limit semantics. Current numerical qualification, observed paper operational evidence, and publication approval remain separate decisions. No real Experiment was qualified or promoted by these changes.

## Offline regression targets

The coordinator runs validation after integration; no mid-flight validation is implied here:

- `tests/unit/test_cli_smoke.py`: retired routes, repeated retired smoke session with different symbols, invalid data origins, mismatched checkpoint before credentials, durable attempt before credential lookup.
- `tests/unit/test_paper_strategy.py`: synthetic frozen ETF/MA preparation, full MA parameters, strategy/universe/parameter/cost/risk/portfolio/frequency/source substitution rejection before data access.
- `tests/unit/test_paper_session.py`: simulation-only diagnostic boundary, adapter/config origin agreement, finite caps, simulated evidence remains unqualified.
- `tests/integration/test_ma_paper_trade.py` and `tests/integration/test_ma_paper_dry_run.py`: retained diagnostics use synthetic simulation brokers and real temporary SQLite.
- `tests/unit/test_paper_run.py` and `tests/unit/test_paper_evidence.py`: loop/ledger admission, recovery and bounded submission (owned by runtime integration).

All test invocations must set `RUN_LIVE_BROKER_TESTS=0 MFS_TEST_LOAD_DOTENV=0`. No real `.env`, credentials, broker endpoint, or Experiment evidence is needed.
