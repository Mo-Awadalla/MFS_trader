# UPRO/SPXU Temporal Flow Geometry v10

## Verdict

**No flow-geometry candidate passed both development and holdout. None is approved for paper or live trading.**

Rules were frozen before outcome calculation. Each score uses the completed 09:30–10:29 window, waits through 10:30, buys fractional UPRO or SPXU at the observed 10:31 ask, and sells at the observed 15:55 bid.

## Development: 2021–2023

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Relative Dollar-Flow Surprise | 4.73 | $15.45 | $-168.20 | 0.747 | $126.66 |
| Price–Volume Phase Compass | 4.74 | $146.95 | $56.65 | 1.103 | $126.66 |
| Lagged Flow–Price Transfer | 4.74 | $157.88 | $64.02 | 1.117 | $126.66 |

## Secondary holdout: 2024–2025

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Relative Dollar-Flow Surprise | 4.77 | $50.24 | $-55.28 | 0.844 | $144.41 |
| Price–Volume Phase Compass | 4.77 | $38.56 | $-82.09 | 0.775 | $144.41 |
| Lagged Flow–Price Transfer | 4.77 | $61.67 | $-35.00 | 0.898 | $144.41 |

## 2026 diagnostic extension

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Relative Dollar-Flow Surprise | 4.76 | $82.61 | $-17.21 | 0.811 | $107.76 |
| Price–Volume Phase Compass | 4.76 | $85.36 | $-13.96 | 0.843 | $107.76 |
| Lagged Flow–Price Transfer | 4.76 | $127.15 | $25.88 | 1.374 | $107.76 |

## Full retrospective span: 2021–2026 YTD

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Relative Dollar-Flow Surprise | 4.74 | $6.41 | $-240.69 | 0.783 | $196.88 |
| Price–Volume Phase Compass | 4.74 | $48.37 | $-39.39 | 0.961 | $196.88 |
| Lagged Flow–Price Transfer | 4.74 | $123.79 | $54.90 | 1.057 | $196.88 |

## Consolidated execution audit: 2023-03-28 through 2025-12-31

| Candidate | ARCA BBO P&L | Consolidated BBO P&L |
|---|---:|---:|
| Relative Dollar-Flow Surprise | $-74.40 | $-78.33 |
| Price–Volume Phase Compass | $-74.79 | $-78.73 |
| Lagged Flow–Price Transfer | $-12.71 | $-16.30 |

## Robustness

- **Relative Dollar-Flow Surprise:** development +1-cent stress $-228.00; five-minute delay $-163.24; full-period result without ten best sessions $-317.42. Failed development gates: profit factor at least one, each development year positive, bullish and bearish positive, ending cash above spy, positive after one extra cent each fill, positive after five minute entry delay, positive after removing ten best sessions.
- **Price–Volume Phase Compass:** development +1-cent stress $-5.06; five-minute delay $66.29; full-period result without ten best sessions $-117.16. Failed development gates: each development year positive, bullish and bearish positive, positive after one extra cent each fill, positive after removing ten best sessions.
- **Lagged Flow–Price Transfer:** development +1-cent stress $5.13; five-minute delay $71.61; full-period result without ten best sessions $-26.41. Failed development gates: positive after removing ten best sessions.

## Interpretation

These were deliberately unusual hypotheses: cross-session normalized capital flow, signed price–volume path area, and lagged flow-to-price transfer. They were not optimized, sign-flipped, thresholded, or combined after results.

A historical pass would still not prove the outcome was not luck. A survivor would require forward paper validation because the broader research program has already inspected every historical year.

Machine-readable results: `research_scout/upro_spxu_flow_geometry_results_v10.json`.
