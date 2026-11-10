# UPRO/SPXU Index-Simplex Coherence v13

## Verdict

**The frozen rule failed. It must not be repaired on these data.**

QQQ and IWM must agree in first-hour direction, while SPY must lie inside their return interval. Entry is the 10:31 ask and exit is the 15:55 bid.

## Development: 2021-2023

| Group | Trades/week | Ending cash | Fixed-$100 P&L | Mean/trade | PF |
|---|---:|---:|---:|---:|---:|
| Coherent simplex | 1.20 | $136.90 | $35.82 | $0.19 | 1.286 |
| Unfiltered breadth | 3.21 | $197.00 | $81.16 | $0.16 | 1.217 |
| Outside simplex | 2.01 | $143.90 | $45.35 | $0.15 | 1.183 |

Price-only SPY ending cash: $126.66.

## Secondary holdout: 2024-2025

| Group | Trades/week | Ending cash | Fixed-$100 P&L | Mean/trade | PF |
|---|---:|---:|---:|---:|---:|
| Coherent simplex | 1.18 | $100.16 | $5.25 | $0.04 | 1.057 |
| Unfiltered breadth | 2.89 | $116.28 | $22.94 | $0.08 | 1.117 |
| Outside simplex | 1.73 | $116.10 | $17.69 | $0.10 | 1.170 |

Price-only SPY ending cash: $144.41.

## 2026 diagnostic through June 29

| Group | Trades/week | Ending cash | Fixed-$100 P&L | Mean/trade | PF |
|---|---:|---:|---:|---:|---:|
| Coherent simplex | 1.24 | $91.84 | $-7.93 | $-0.27 | 0.697 |
| Unfiltered breadth | 3.30 | $94.99 | $-3.73 | $-0.04 | 0.937 |
| Outside simplex | 2.16 | $103.43 | $4.20 | $0.08 | 1.126 |

Price-only SPY ending cash: $108.05.

## Full retrospective span

| Group | Trades/week | Ending cash | Fixed-$100 P&L | Mean/trade | PF |
|---|---:|---:|---:|---:|---:|
| Coherent simplex | 1.18 | $125.93 | $33.14 | $0.10 | 1.137 |
| Unfiltered breadth | 3.09 | $217.60 | $100.37 | $0.11 | 1.160 |
| Outside simplex | 1.91 | $172.79 | $67.23 | $0.12 | 1.174 |

Price-only SPY ending cash: $197.41.

## Robustness

- Development with one extra cent at each fill: $20.80.
- Development with five-minute entry delay: $42.23.
- Development after removing ten best sessions: $-16.02.

## Gate failures

- Development Gate: minimum two trades per week, positive after removing ten best sessions.
- Holdout Gate: development gate passed, each holdout year positive, bullish and bearish positive, ending cash above spy, positive after one extra cent each fill, positive after removing five best sessions, mean trade pnl above unfiltered breadth consensus, mean trade pnl above incoherent same sign sessions.

## Consolidated execution audit

- ARCA fixed-$100 P&L: $16.28.
- Consolidated fixed-$100 P&L: $13.22.

Preimplementation critique: `research_scout/UPRO_SPXU_INDEX_SIMPLEX_PREIMPLEMENTATION_CRITIQUE_V13.md`.

Machine-readable results: `research_scout/upro_spxu_index_simplex_results_v13.json`.
