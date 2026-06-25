# Handoff: mfs-trader Medium-Frequency Trading System

## State of Play

The repository now has a usable local operational path for MA/sim-broker paper-trade simulation, plus a working engine CLI, reproducible shakedown command, and operator-facing reports. The code is not yet wired for continuous Alpaca paper trading; Alpaca paper connectivity should be verified next with the live broker smoke tests using the gitignored `.env` keys.

Current branch: `main`.
Remote: `origin` → `https://github.com/Mo-Awadalla/untitled_project.git`.

## What Is Built

### Phase 1 (Data pipeline, config, storage, MA strategy, research)

- `config/`: TOML per environment (`research`, `paper`, `live`), dataclass schema, config loader, live-mode safety gate.
- `storage/`: SQLite runtime tables with WAL mode, append-only events, state repository, Parquet OHLCV IO.
- `data/`: Alpaca + CCXT downloaders, quality validation, resampling, CLI pipeline.
- `strategies/ma/signal.py`: Dual moving-average crossover signal generator; pure function, no lookahead.
- `research/runner.py` and `research/cost_model.py`: Vectorized single-asset backtest and modular trading-cost model.

### Phase 2 (Validation engine)

- Walk-forward validation.
- Block-bootstrap Monte Carlo.
- Deflated Sharpe Ratio.
- Parameter stability/plateau checks.
- `validation/gauntlet.py` orchestrates the validation gates.

### Phase 3 (Execution skeleton)

- `portfolio/sizing.py`: Portfolio sizing and target-position deltas.
- `risk/engine.py`: Portfolio risk engine, kill switch, drawdown limits, exposure limits, sector/correlation checks.
- `execution/sim_broker/`: Configurable simulated broker with fills, rejections, timeouts, partial fills, stale data, mismatches.
- `execution/order_state_machine.py`: Order lifecycle and reconciliation state mapping.
- `execution/oms.py`: Intent-before-submit, deterministic client order IDs, idempotency, reconciliation handling.
- `execution/alpaca/adapter.py`: Alpaca REST adapter for paper/live endpoints, status mapping, rate-limit retry.
- `execution/ccxt/adapter.py`: CCXT Binance spot adapter/testnet reference.
- `engine/runtime.py`: TradingEngine bar-cycle processing, risk/OMS path, startup/shutdown/reconciliation mechanics.
- `engine/replay.py`: Historical replay through the full engine and simulated broker.
- `monitoring/`: Telegram alerts, watchdog, and operational report generation.

## Key Fixes and Additions From Latest Work

1. Added missing engine CLI entry point: `engine/cli.py`.
   - `mfs-engine --help`
   - `mfs-engine --config config/paper.toml preflight`
   - `mfs-engine shakedown-ma ...`
   - `mfs-engine report ...`

2. Added reproducible MA operational shakedown: `engine/shakedown.py`.
   - Generates deterministic synthetic OHLCV bars.
   - Runs OHLCV validation.
   - Runs MA research backtest.
   - Replays bars through `TradingEngine` + `SimBroker`.
   - Exercises baseline fill path plus rejection, timeout, and partial-fill scenarios.
   - Writes Markdown and JSON reports.

3. Added operator-facing reports: `monitoring/reports.py`.
   - Summarizes events, bar-cycle completion, broker failures, risk decisions, reconciliation issues, exceptions, open orders, final positions, and promotion blockers.
   - Report CLI returns nonzero on blockers unless `--allow-blockers` is used.

4. Patched runtime cycle accounting in `engine/runtime.py`.
   - Warmup/no-signal bars now log cycle completion, so operational reports do not show false bar-cycle mismatches.
   - Risk decisions are now distinguished as:
     - `RISK_CHECK_PASSED`
     - `RISK_CHECK_REDUCED`
     - `RISK_CHECK_BLOCKED`

5. Fixed dependency declarations in `pyproject.toml`.
   - Added `scipy` and `scikit-learn` to core dependencies because existing validation/tests require them.
   - Kept `statsmodels` under the `research` extra.

6. Updated README quickstart.
   - Added venv setup.
   - Added local smoke checks.
   - Corrected `mfs-data` global `--config` ordering.
   - Clarified live mode is gated.

7. Added test coverage for the new path.
   - `tests/unit/test_cli_smoke.py`
   - `tests/unit/test_operational_report.py`
   - `tests/integration/test_ma_shakedown.py`

8. Created local `.env` with temporary Alpaca paper keys.
   - `.env` is gitignored and must never be committed.
   - `ALPACA_BASE_URL` is intentionally `https://paper-api.alpaca.markets` without `/v2`; the adapter appends `/v2/...` internally.

## Verification Results

Latest full local verification after the code changes:

```text
ruff check .
All checks passed!

pytest -q
316 passed, 10 skipped
```

Skipped tests are live broker tests gated behind `RUN_LIVE_BROKER_TESTS=1`.

Manual smoke checks run successfully:

```bash
mfs-engine --config config/paper.toml preflight
mfs-data --config config/research.toml status
mfs-engine shakedown-ma --out-dir runs/ma_shakedown_verify --bars 140 --fast-window 5 --slow-window 20 --no-trend-filter
mfs-engine report --db runs/ma_shakedown_verify/baseline.sqlite
```

Observed shakedown/report result:

```text
MA shakedown status: PASS
Operational Report: PASS
Bars started/completed: 140/140
Broker timeouts: 0
Broker rejections: 0
Risk blocks: 0
Risk reductions: 121
Reconciliation mismatches: 0
Exceptions: 0
```

Local generated artifacts live under `runs/ma_shakedown_verify/`; `runs/` is gitignored.

## Current Readiness

Ready:

- Local sim-broker paper-trade simulations.
- Deterministic MA operational shakedown.
- Operator report generation from runtime SQLite DBs.
- Config preflight.
- Data status CLI.
- Alpaca paper credentials are present locally in `.env` and ignored by git.

Not ready yet:

- Continuous Alpaca paper trading loop.
- Real Alpaca paper order flow has not been verified in this latest environment after adding `.env`.
- No `mfs-engine paper-run` / `paper-dry-run` command exists yet.
- No recent real Alpaca market data has been downloaded for replay in this clone.
- MA remains a plumbing/ops validator, not a validated alpha strategy.

## Recommended Next Steps

1. Recreate/install the local venv if needed:

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -e ".[dev,alpaca,crypto,research,monitoring,alerts]"
```

2. Verify Alpaca paper connectivity:

```bash
RUN_LIVE_BROKER_TESTS=1 .venv/Scripts/python -m pytest tests/integration/test_alpaca_live.py -v --live_broker
```

This should verify account fetch, positions, price fetch, safe far-limit submit/cancel, and invalid-symbol rejection.

3. Download/check real Alpaca data:

```bash
.venv/Scripts/mfs-data --config config/research.toml download --symbol AAPL
.venv/Scripts/mfs-data --config config/research.toml status
```

4. Add a real-data replay CLI before live paper orders.
   Suggested command shape:

```bash
mfs-engine replay-data --config config/paper.toml --symbol AAPL --broker sim
```

5. Add a read-only paper dry run before order placement.
   Suggested command shape:

```bash
mfs-engine paper-dry-run --config config/paper.toml --symbol AAPL
```

6. Only after the above passes, add explicit opt-in paper order placement.
   Suggested command shape:

```bash
mfs-engine paper-run --config config/paper.toml --symbol AAPL --confirm-paper-orders
```

## Important Constraints

- `.env` files are gitignored and must never be committed.
- Use Alpaca paper keys for paper tests; do not use live keys.
- Paper/live should share engine logic; mode should come from config and explicit safety gates.
- Live mode remains intentionally gated by `config/live.toml` and `live_deployment.authorized = false`.
- Binance is not viable for NY live crypto use; keep it as mock/testnet reference unless a Coinbase/Gemini/Kraken adapter is added.
- Single-strategy first-live rule: only one strategy should touch live trading until months of clean paper/live operation.
