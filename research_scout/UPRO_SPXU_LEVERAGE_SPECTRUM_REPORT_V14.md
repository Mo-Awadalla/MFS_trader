# UPRO/SPXU Persistent Leverage-Spectrum Odd Mode v14

## Verdict

**The persistent odd-mode hypothesis is rejected unchanged.**

The signal requires the +/-3 versus +/-1 odd residual to retain the same sign in both completed morning half-hours.

Implementation audit: the first run accidentally required every one-minute trade bar inside each block and was superseded. The saved result uses the frozen exact boundary-return definition. No formula, clock, sign, or gate changed.

## Development: 2021-2023

| Rule | Trades/week | Ending cash | Fixed-$100 P&L | Mean/trade | PF |
|---|---:|---:|---:|---:|---:|
| Persistent odd mode | 0.91 | $96.15 | $1.34 | $0.01 | 1.010 |
| Low-leverage direction | 0.91 | $124.88 | $27.31 | $0.20 | 1.218 |
| Sign-flipped residual | 0.92 | $76.99 | $-20.75 | $-0.15 | 0.866 |

Price-only SPY ending cash: $126.66.

## Secondary holdout: 2024-2025

| Rule | Trades/week | Ending cash | Fixed-$100 P&L | Mean/trade | PF |
|---|---:|---:|---:|---:|---:|
| Persistent odd mode | 0.98 | $80.66 | $-14.48 | $-0.16 | 0.848 |
| Low-leverage direction | 0.98 | $116.39 | $20.40 | $0.22 | 1.267 |
| Sign-flipped residual | 0.98 | $101.26 | $6.57 | $0.07 | 1.078 |

Price-only SPY ending cash: $144.41.

## Full retrospective span

| Rule | Trades/week | Ending cash | Fixed-$100 P&L | Mean/trade | PF |
|---|---:|---:|---:|---:|---:|
| Persistent odd mode | 0.88 | $77.55 | $-13.15 | $-0.06 | 0.944 |
| Low-leverage direction | 0.88 | $145.35 | $47.71 | $0.21 | 1.236 |
| Sign-flipped residual | 0.88 | $77.96 | $-14.17 | $-0.06 | 0.941 |

Price-only SPY ending cash: $181.68.

## Robustness and identification

- Development with one extra cent at each fill: $-10.84.
- Development with five-minute entry delay: $5.32.
- Development after removing ten best sessions: $-47.35.
- Consolidated rebuilt 2024-2025 P&L: $-20.93.
- ARCA/consolidated identical-action rate: 38.5% over 65 common sessions.

## Gate failures

- Development Gate: minimum two trades per week, each development year positive, bullish and bearish positive, ending cash above spy, positive after one extra cent each fill, positive after removing ten best sessions, mean trade pnl above low leverage market direction placebo.
- Holdout Gate: development gate passed, each holdout year positive, bullish and bearish positive, ending cash above spy, positive after one extra cent each fill, positive after removing five best sessions, mean trade pnl above low leverage market direction placebo, fixed notional pnl above sign flipped placebo, consolidated rebuilt signal and execution positive, arca consolidated signal agreement at least 90 percent.

Preimplementation critique: `research_scout/UPRO_SPXU_LEVERAGE_SPECTRUM_PREIMPLEMENTATION_CRITIQUE_V14.md`.

Machine-readable results: `research_scout/upro_spxu_leverage_spectrum_results_v14.json`.
