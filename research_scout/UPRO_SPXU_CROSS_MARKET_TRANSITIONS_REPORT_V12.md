# UPRO/SPXU Cross-Market Transitions v12

## Verdict

**No transition candidate passed both development and holdout. None is approved for paper or live trading.**

The three hypotheses were frozen before calculation and carry forward only the cross-market diffusion mechanism—not the prior Breadth Consensus rule or its favorable cases.

## Development: 2021-2023

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Synchronized Breadth Acceleration | 3.12 | $73.64 | $-16.90 | 0.960 | $126.66 |
| Consensus Formation Event | 1.16 | $101.71 | $5.80 | 1.043 | $126.66 |
| Leadership Curvature | 4.74 | $68.87 | $-18.55 | 0.969 | $126.66 |

## Secondary holdout: 2024-2025

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Synchronized Breadth Acceleration | 3.04 | $55.99 | $-47.59 | 0.806 | $144.41 |
| Consensus Formation Event | 1.41 | $84.69 | $-13.48 | 0.861 | $144.41 |
| Leadership Curvature | 4.77 | $48.14 | $-59.80 | 0.832 | $144.41 |

## 2026 diagnostic extension through June 29

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Synchronized Breadth Acceleration | 3.54 | $96.12 | $-2.46 | 0.960 | $108.05 |
| Consensus Formation Event | 1.16 | $88.91 | $-11.51 | 0.367 | $108.05 |
| Leadership Curvature | 4.76 | $112.38 | $13.48 | 1.198 | $108.05 |

## Full retrospective span

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Synchronized Breadth Acceleration | 3.12 | $39.63 | $-66.95 | 0.908 | $197.41 |
| Consensus Formation Event | 1.25 | $76.58 | $-19.19 | 0.923 | $197.41 |
| Leadership Curvature | 4.74 | $37.26 | $-64.87 | 0.937 | $197.41 |

## Consolidated execution audit: 2023-03-28 through 2025-12-31

| Candidate | ARCA BBO P&L | Consolidated BBO P&L |
|---|---:|---:|
| Synchronized Breadth Acceleration | $-39.04 | $-39.46 |
| Consensus Formation Event | $-10.81 | $-13.75 |
| Leadership Curvature | $-66.41 | $-70.63 |

## Frozen-gate audit

- **Synchronized Breadth Acceleration:** development +1-cent stress $-61.59; five-minute delay $-1.40; failed development gates: profit factor at least one, each development year positive, bullish and bearish positive, ending cash above spy, positive after one extra cent each fill, positive after five minute entry delay, positive after removing ten best sessions.
- **Consensus Formation Event:** development +1-cent stress $-10.85; five-minute delay $6.51; failed development gates: minimum two trades per week, each development year positive, bullish and bearish positive, ending cash above spy, positive after one extra cent each fill, positive after removing ten best sessions.
- **Leadership Curvature:** development +1-cent stress $-82.50; five-minute delay $-15.91; failed development gates: profit factor at least one, each development year positive, bullish and bearish positive, ending cash above spy, positive after one extra cent each fill, positive after five minute entry delay, positive after removing ten best sessions.

Machine-readable results: `research_scout/upro_spxu_cross_market_transitions_results_v12.json`.
