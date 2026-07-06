# ETF TSM Engine Replay

Status: PASS
Symbols: `SPY, QQQ, IWM, IEF, GLD, SHY, DBC`
Bars: 5405 (2005-01-03 14:30:00+00:00 to 2026-06-29 13:30:00+00:00)
Replay DB: `docs\reports\etf_tsm_engine_replay\etf_tsm_engine_replay.sqlite`
Operational report: `docs\reports\etf_tsm_engine_replay\etf_tsm_engine_replay_operational.md`

## What this proves

This replay feeds the validation-passed ETF TSM target weights through the runtime engine, portfolio sizing, risk engine, OMS, SQLite state, and simulated broker fills. It is operational evidence, not a new validation pass and not live-trading approval.

## Research vs Runtime

- Research final equity: 50944.366641
- Research Sharpe: 0.795371
- Research max drawdown: -0.173009
- Research rebalances/trade rows: 258/776
- Replay bars/cycles: 5405/5405
- Replay orders submitted/filled/rejected/timed out: 1072/1072/0/0
- Replay mark-to-market equity: 27759.417250
- Replay final positions: {'DBC': 94.34438287240306, 'IWM': 10.39065989800991, 'QQQ': 4.788720978370359}

## Final target vs replay weights

| Symbol | Target weight | Replay weight |
| --- | ---: | ---: |
| SPY | 0.000000 | 0.000000 |
| QQQ | 0.338333 | 0.346742 |
| IWM | 0.302335 | 0.310650 |
| IEF | 0.000000 | 0.000000 |
| GLD | 0.000000 | 0.000000 |
| SHY | 0.000000 | 0.000000 |
| DBC | 0.255862 | 0.250579 |

## Runtime config overrides

- portfolio.execution_mode: continuous_rebalance
- portfolio.per_position_risk_pct: 0.05
- risk_limits.per_position_pct: 0.05
- risk_limits.max_gross_exposure_pct: 1.0
- risk_limits.max_net_exposure_pct: 1.0
- engine.startup_reconciliation_required: False
- portfolio.min_notional_delta: 25.0
- portfolio.min_pct_position_delta: 0.05
- target_weight_timing: weights shifted one bar to match vectorized research execution

## Differences / blockers

- None on structural runtime replay checks.

## Assumption gaps

- Replay uses a simulated broker, not Alpaca paper/live broker authority.
- ETF target weights are precomputed from the frozen signal function and replayed through runtime as a target-weight adapter.
- Runtime sizing is configured so fixed-fraction sizing maps target weights to notional exposure; this proves operational plumbing, not new alpha.
- Portfolio equity is held constant for target sizing during replay; mark-to-market equity is computed from filled orders at the end.
