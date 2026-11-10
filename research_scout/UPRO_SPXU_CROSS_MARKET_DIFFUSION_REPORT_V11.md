# UPRO/SPXU Cross-Market Diffusion v11

## Verdict

**No cross-market candidate passed both development and holdout. None is approved for paper or live trading.**

Signals use the completed 09:30 and 10:00 QQQ/IWM/SPY 30-minute bars, wait through 10:30, enter UPRO or SPXU at the observed 10:31 ask, and exit at the observed 15:55 bid.

## Development: 2021–2023

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Breadth Consensus | 3.21 | $197.00 | $81.16 | 1.217 | $126.66 |
| Sequential Breadth Relay | 0.94 | $154.51 | $47.14 | 1.464 | $126.66 |
| Synthetic-Index Catch-up | 4.73 | $164.47 | $68.43 | 1.123 | $126.66 |

## Secondary holdout: 2024–2025

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Breadth Consensus | 2.89 | $116.28 | $22.94 | 1.117 | $144.41 |
| Sequential Breadth Relay | 1.00 | $75.94 | $-26.10 | 0.657 | $144.41 |
| Synthetic-Index Catch-up | 4.76 | $98.61 | $10.36 | 1.032 | $144.41 |

## 2026 diagnostic extension through June 29

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Breadth Consensus | 3.30 | $94.99 | $-3.73 | 0.937 | $108.05 |
| Sequential Breadth Relay | 1.13 | $98.01 | $-1.89 | 0.832 | $108.05 |
| Synthetic-Index Catch-up | 4.76 | $93.39 | $-5.08 | 0.934 | $108.05 |

## Full retrospective span

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash |
|---|---:|---:|---:|---:|---:|
| Breadth Consensus | 3.09 | $217.60 | $100.37 | 1.160 | $197.41 |
| Sequential Breadth Relay | 0.97 | $115.00 | $19.14 | 1.101 | $197.41 |
| Synthetic-Index Catch-up | 4.73 | $151.46 | $73.70 | 1.077 | $197.41 |

## Consolidated execution audit: 2023-03-28 through 2025-12-31

| Candidate | ARCA BBO P&L | Consolidated BBO P&L |
|---|---:|---:|
| Breadth Consensus | $61.10 | $56.60 |
| Sequential Breadth Relay | $-7.94 | $-11.53 |
| Synthetic-Index Catch-up | $36.16 | $34.83 |

## Robustness

- **Breadth Consensus:** development +1-cent stress $38.90; five-minute delay $80.60; full result without ten best sessions $7.74. Failed development gates: each development year positive.
- **Sequential Breadth Relay:** development +1-cent stress $35.19; five-minute delay $48.97; full result without ten best sessions $-26.53. Failed development gates: minimum two trades per week.
- **Synthetic-Index Catch-up:** development +1-cent stress $2.98; five-minute delay $57.64; full result without ten best sessions $-34.66. Failed development gates: each development year positive, positive after removing ten best sessions.

This pass changed the information source instead of repairing the failed SPY/leveraged-pair rules. The tests use cross-market breadth, sequential information diffusion, and a synthetic-index residual.

Machine-readable results: `research_scout/upro_spxu_cross_market_diffusion_results_v11.json`.
