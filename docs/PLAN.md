# Plan: Medium-Frequency Trading System

## Strategy Sourcing Philosophy

Strategies are hypotheses, not assets. All strategies come from public testable sources — academic papers, factor libraries, quant platforms. They are rebuilt cleanly, punished with costs and validation, and most die. **The gauntlet is the strategy.**

## Build Order (4 Phases)

### Phase 1 — Minimal End-to-End Skeleton
1. `config/` — TOML per environment (research/paper/live), secrets in env vars
2. `storage/` — SQLite (WAL, append-first, UTC) for events/orders/positions; Parquet for bars
3. `data/` — Alpaca (equities) + CCXT Coinbase (crypto), 1-min raw → resample up. Quality gate: PASS/WARN/FAIL. Stricter for live
4. `strategies/MA` — baseline pipeline validator, not an edge candidate. SMA/EMA crossover, trend filter, long-only. Its job is testing data/reports/gauntlet/paper plumbing, not making money
5. `research/` — vectorbt runner, single-asset report

### Phase 2 — Validation Engine
6. `validation/WFA` — primary: 18m train / 6m test / 3m step; robustness: 12m/3m/1m; expanding window for finalized params
7. `validation/MC` — block-bootstrap (20-day blocks) + parameter perturbation, 10k paths. Metrics: terminal wealth, Sharpe/Sortino distribution, max DD, P(loss), P(ruin)
8. `validation/DSR` — M_eff via correlation/eigenvalue; M_raw as conservative bound; interpretability via parameter-region clustering
9. `validation/parameter stability` — plateau detection, top region within 20-30% of selected, no isolated peaks

### Phase 3 — Execution Skeleton
10. `portfolio/` — sizing, target positions, allocation rules. Tested independently with dummy targets before any strategy touches it
11. `risk/` — per-position (0.5-1%), daily (3%/block at 2%), weekly (6%), monthly (15%/hard halt/manual review), sector (35% gross/10% net), correlation cluster (25-35% gross), max 10-15 positions early / 30 later. Three exception severities: soft (strategy-disable), hard (halt), catastrophic (freeze/manual). No blind flattening
12. `execution/` — broker adapters (Alpaca + CCXT), order model, fill model, position tracking. Deterministic client_order_id. Order state machine: 12 states + separate reconciliation_status field
13. `engine/` — single runtime, mode=research|paper|live. Startup reconciliation, SIGTERM graceful shutdown, crash recovery via broker reconciliation. Engine replay mode: same pipeline but historical bars + simulated broker
14. `monitoring/` — Streamlit read-only dashboard, Telegram alerts with throttling, external watchdog process, daily reconciliation reports

### Phase 4 — Real Strategy Expansion
15. `strategies/BB` — window 10-50 step 5, std_mult 1.5-3.0 step 0.25, BB width percentile filter (25/75 default), 3 modes (none/normal/contracting)
16. `strategies/pairs` — intra-sector equities + crypto spot pairs. Engle-Granger, 12m rolling, log-prices, z-score entry ≥2.0 / exit ≤0.5. Add: hedge-ratio stability, half-life filter, pair retirement on decay
17. `strategies/CSMR` — short-term reversal, top/bottom quartile, equal-weight dollar-neutral, rebalance weekly. Add: shortability check, borrow availability, liquidity filters, price floor

## Key Design Decisions

| Area | Decision |
|---|---|
| Data storage | 1-min raw Parquet source of truth, resample helper. External artifact store at `~/trading_artifacts/runs/`. Repo has `runs_manifest.jsonl` / `experiment_index.sqlite` with pointers |
| Backtest engine | vectorbt for research prototyping. Engine replay mode for deployment-qualifying backtests |
| Transaction costs | Modular: commissions + SEC Section 31 + FINRA TAF + exchange fees + hybrid slippage. Calibration loop updates from observed fills |
| Paper trading | Ops test, not alpha test. 30 days AND 100-200 trades. Pass/fail = operational criteria |
| Paper/live architecture | Same engine, different config mode. Live dry-run mode: real data, read-only broker |
| Order state machine | 12 states (INTENDED, BLOCKED_BY_RISK, SUBMITTING, ACKNOWLEDGED, PARTIALLY_FILLED, FILLED, CANCEL_REQUESTED, CANCELLED, REJECTED, EXPIRED, TIMEOUT, UNKNOWN) + separate reconciliation_status |
| Kill switches | Three severity classes. Flatten only if state KNOWN. Unknown state → freeze/alert/manual |
| Universe rules | Equities: explicit definition, liquidity/price thresholds, survivorship bias documented, PIT timing. Coinbase spot USD: BTC/USD, ETH/USD, SOL/USD, and LTC/USD; stablecoin exclusion and min volume. Shelved: Binance USDⓈ-M perps (BTCUSDT, ETHUSDT, SOLUSDT), funding-aware strategies only, 1× leverage, reduce-only exits |
| Data quality | Three outcomes (PASS/WARN/FAIL). Live: latest bar missing/stale → block signal. No forward-fill |
| Experiment tracking | External artifact store. Metadata: git commit, random_seed, data version, M_raw, M_eff_corr, universe definition, promotion_status |
| Testing | pytest + property-based + state machine + idempotency + reconciliation matrix + lookahead-bias + mock broker + golden + data-leakage + config safety + DB durability |
| Live deployment gate | gauntlet → paper ops → live dry-run → manual approval → 10-25% capital → scale on conditions → retire on underperformance |
| Capital scaling | Initial 10-25%. Scale only after sufficient trades + days + clean reconciliation + within-model slippage. De-scale on drawdown. Retire on underperformance |
| Rollback | Halt → cancel safe orders → reconcile → flatten only if state KNOWN → suspended → postmortem → manual restart |
| Single-strategy first-live | Only one strategy live at a time until 3+ months clean operation |

## Strategy Retirement Thresholds

- Sharpe < 0.5 over 3-month rolling window
- Max drawdown exceeds MC 95th percentile
- 20 consecutive losing trades
- Slippage > 2x modeled assumption for 30 consecutive trades
- Reconciliation failure rate > 5% over 7 days
- Cointegration p-value > 0.05 for 2 consecutive retests (pairs only)

Retired strategies can be re-evaluated after 3 months with fresh data.

## Directory Structure

```
project/
├── config/              # TOML: research, paper, live
├── data/                # download, validate, resample, parquet
├── strategies/          # ma/, bb/, pairs/, csmr/ — pure signal functions
├── research/            # vectorbt runner, sweep helpers
├── research_scout/      # public-source hypothesis tracking
├── validation/          # wfa/, mc/, dsr/, stability/
├── portfolio/           # sizing, allocation
├── risk/                # circuit breakers, exposure, correlation
├── execution/           # broker adapters (alpaca, ccxt, sim_broker), order model, fills
├── engine/              # runtime loop, replay mode, startup/shutdown, reconcile
├── monitoring/          # streamlit, telegram, heartbeat, watchdog, reports
├── storage/             # sqlite schema, parquet io
├── tests/               # unit, integration, mock, replay, golden, property
├── scripts/             # one-off tasks
├── notebooks/           # analysis only
└── runs_manifest.jsonl  # pointers to external artifact store
```

## Gauntlet Summary

```
Any strategy → research (vectorbt)
             → WFA (3-tier: primary/robustness/expanding)
             → MC (block bootstrap + parameter perturbation)
             → DSR (M_eff_corr + M_raw bound)
             → Stability (plateau, not peak)
             → Paper ops (30d + 100-200 trades, operational pass)
             → Live dry-run (real data, read-only broker)
             → Manual approval + capital cap (10-25%)
             → Scale (clean conditions)
             → Retire (live underperformance / decay)
```

Most strategies die. That is the point.
