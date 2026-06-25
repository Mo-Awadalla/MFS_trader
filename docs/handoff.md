# Handoff: mfs-trader Medium-Frequency Trading System

## State of Play

All four phases scoped (`docs/PLAN.md`) with Phases 1-3 fully built. Uncommitted working tree on `main` (no commits yet — bare repo). All source code lives under the workspace root.

## Conversation Summary

### Phase 1 (Data pipeline, config, storage, MA strategy, research) — Built

- `config/`: TOML per environment (research, paper, live), `schema.py` with all dataclasses, `loader.py` with live-mode safety gate (rejects paper keys, missing capital, unauthorized).
- `storage/`: 7 SQLite tables (WAL mode, append-only events), state repository (upsert), Parquet IO.
- `data/`: Alpaca + CCXT downloaders, quality validator (`PASS`/`WARN`/`FAIL`), resample helper (1-min → any frequency), CLI pipeline.
- `strategies/ma/signal.py`: Dual MA crossover signal generator (SMA/EMA, trend filter, long-only/short, sweep grid). Pure function — no state, no lookahead.
- `research/runner.py`, `research/cost_model.py`: Vectorized backtest runner with modular cost model (SEC/FINRA/TAF/crypto fees + hybrid slippage), performance metrics.

### Phase 2 (Validation engine) — Built

- `validation/wfa/`: 3-tier (18m/6m/3m primary, 12m/3m/1m robustness, expanding).
- `validation/mc/`: Block-bootstrap (20-day blocks), 10k paths, parameter perturbation.
- `validation/dsr/`: Deflated Sharpe Ratio (M_eff via eigenvalue participation ratio, M_raw conservative bound, M_cluster).
- `validation/stability/`: Plateau detection, isolated peak check.
- `validation/gauntlet.py`: Orchestrator — all four checks, unified pass/fail.

### Phase 3 (Execution skeleton) — Built

- `portfolio/sizing.py`: Fixed fraction, vol target, dollar-neutral, position delta.
- `risk/engine.py`: 10 checks (kill switch, per-position, daily/weekly/monthly, sector, correlation). 3 exception severity classes (SOFT/HARD/CATASTROPHIC). No blind flattening.
- `execution/sim_broker/`: Malicious fake broker — configurable rejections, timeouts, partial fills, stale data, mismatches, unreachable.
- `execution/order_state_machine.py`: 12 states + separate `reconciliation_status`. All allowed/forbidden transitions documented. Timeout → reconcile (not retry).
- `execution/oms.py`: Deterministic `client_order_id`, DB intent write before broker submit, freeze on DB failure, idempotency, timeout reconciliation.
- `execution/alpaca/adapter.py`: Alpaca REST API v2 — Basic Auth, all statuses mapped to state machine, rate limit retry.
- `execution/ccxt/adapter.py`: CCXT Binance spot adapter — error classification, `clientOrderId` passthrough, testnet support.
- `engine/runtime.py`: Startup reconciliation, kill-switch persistence across restart, SIGTERM graceful shutdown, deterministic bar cycle, NaN exposure filtering.
- `engine/replay.py`: Historical bars through full pipeline with `sim_broker`, deterministic.
- `monitoring/`: Telegram alerts (throttling/dedup/cooldown/escalation/recovery) + external heartbeat watchdog.

### Key Fixes Made This Session

1. **NaN exposure bug** (`engine/runtime.py:251`): MA strategy returns `float(np.nan)` before MA windows warm up (~100 bars). Engine now filters NaN exposures before passing to OMS. Also defensive NaN guard in `execution/oms.py:216` — converts NaN quantity to 0.0 for INTENT logging.

2. **Cancel order** (`execution/alpaca/adapter.py`): Alpaca `DELETE /v2/orders:by_client_order_id?client_order_id={id}` returns 404. Adapter does GET status lookup first to retrieve `broker_order_id`, then DELETE by `broker_order_id`.

3. **Price fetch** (`execution/alpaca/adapter.py`): Alpaca quotes use `bp`/`ap` field names (not `bid_price`/`ask_price`). Adapter handles both.

4. **Golden file path** (`tests/replay/test_ma_replay_vs_vectorbt.py`): `GOLDEN_DIR` was double-nested (`tests/tests/replay/golden`). Fixed from `parents[1] / "tests" / "replay" / "golden"` to `parents[1] / "replay" / "golden"`.

5. **Golden params** (`tests/replay/test_ma_replay_vs_vectorbt.py`): Golden file stored only 2 params; match test read those but lost `trend_filter_active`/`long_only`. Fixed by storing all 4 params in the golden file.

### Test Results

```
310 passed, 10 skipped (live_broker), lint clean
```

- `tests/unit/test_alpaca_adapter.py`: 32 mocked (responses library)
- `tests/unit/test_ccxt_adapter.py`: 27 mocked (monkeypatch)
- `tests/integration/test_alpaca_live.py`: 5 live smoke tests — all passing (account fetch, positions, price, submit+cancel, rejected order → no position)
- `tests/integration/test_ccxt_live.py`: 5 CCXT testnet smoke tests — skipped by default
- `tests/integration/test_pre_paper_gauntlet.py`: 11 integration tests — all passing (idempotency, determinism, timeout, partial fill, kill-switch persistence, reconciliation)
- `tests/replay/test_ma_replay_vs_vectorbt.py`: 5 golden replay tests — all passing (vectorbt comparison, determinism, flat strategy, golden create + match)

### Live Broker Credentials (REDACTED)

Alpaca paper API keys are in `.env` (gitignored). They are temporary and will be rotated. Live broker tests require `RUN_LIVE_BROKER_TESTS=1` env var. CCXT Binance testnet keys are also in `.env`.

### Graphification Output

The project was graphed with `/graphify`:
- **1307 nodes, 3458 edges, 81 communities**
- Output: `graphify-out/graph.html`, `graphify-out/GRAPH_REPORT.md`, `graphify-out/graph.json`
- God nodes: `SimBroker` (84 edges), `EventLogger` (82), `DrawdownState` (78), `PortfolioState` (77)
- Top communities: Data Download & Pipeline, Event Logging & Error Handling, Telegram Alert Manager, MA Strategy Signals & Tests, Walk-Forward Analysis & Tests, Cost Model & Backtest Config, Risk Engine & Kill Switch

## Immediate Next Steps

1. **MA operational shakedown** — run MA through full pipeline: replay golden comparison (done) → Alpaca paper dry-run (live data, read-only) → Alpaca paper trading (2 weeks, 20-30 trades minimum, operational pass criteria).

2. **Phase 4 strategies** (in order):
   - **BB** (Bollinger Bands with volatility filter) — window 10-50 step 5, std_mult 1.5-3.0 step 0.25, BB width percentile filter, 3 modes (none/normal/contracting)
   - **CSMR** (cross-sectional mean reversion) — short-term reversal, top/bottom quartile, equal-weight dollar-neutral, rebalance weekly
   - **Pairs** (intra-sector equities + crypto spot) — Engle-Granger, 12m rolling, log-prices, z-score entry ≥2.0 / exit ≤0.5

3. **Crypto venue** — Binance unavailable in NY (kept as mock/testnet reference). Need Coinbase, Gemini, or Kraken adapter before crypto live trading. Deferred.

## Suggested Skills

| Skill | When to Use |
|---|---|
| `tdd` | Building Phase 4 strategies (BB, CSMR, pairs) — red-green-refactor loop for strategy signal generators |
| `grill-with-docs` | Stress-testing BB/CSMR/pairs design against existing domain model in PLAN.md and code |
| `improve-codebase-architecture` | After Phase 4, finding refactoring opportunities, consolidating tightly-coupled modules |
| `ubiquitous-language` | Establishing consistent domain terminology across strategy docs, config, and code |
| `to-issues` | Breaking Phase 4 into independently-grabbable issues on the issue tracker |
| `diagnose` | Hard bugs or performance regressions (NaN exposure was discovered this way) |
| `customize-opencode` | Changing opencode config (`.opencode/`, `opencode.jsonc`, new skills/agents) |
| `review` | Reviewing changes since a fixed point before committing or merging |
| `handoff` | Writing a handoff doc for another agent session |

## Important Constraints

- Single-strategy first-live rule: only one strategy goes live until 3+ months clean operation.
- Binance is out for NY. Crypto live trading deferred until Coinbase/Gemini/Kraken adapter.
- Paper/live share the same engine — mode is set by config, not code path.
- All `.env` files gitignored — never commit keys.
- Live broker tests need `RUN_LIVE_BROKER_TESTS=1` env var.
- Pre-paper operations gauntlet (11 tests) must pass before any strategy touches paper.
