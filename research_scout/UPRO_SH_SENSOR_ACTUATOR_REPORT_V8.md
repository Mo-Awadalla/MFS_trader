# UPRO/SH Sensor–Actuator Separation v8

## Verdict

**REJECT.** This is the untouched result of the frozen substitution test. SH
was used only as the bearish execution instrument; all 12 state features still
came from SPY, UPRO, and SPXU.

## Before and after

| Metric | UPRO/SPXU v7 | UPRO/SH v8 | SPY price-only |
|---|---:|---:|---:|
| Ending $100 cash | $125.2279 | $137.3266 | $170.3359 |
| Fixed-$100 P&L | $27.6008 | $38.2689 | — |
| Profit factor | 1.0548 | 1.0872 | — |
| Trades/week | 3.216 | 3.033 | — |
| Worst trade | $-9.6510 | $-9.6510 | — |
| P&L without best five | $-27.9539 | $-16.0322 | — |

## Actuator attribution

- UPRO bullish P&L: $41.0398
- SH bearish P&L: $-2.7709

## Calendar-year P&L

- 2021: $9.8547
- 2022: $19.4770
- 2023: $6.0729
- 2024: $-3.7691
- 2025: $13.2396
- 2026: $-6.6063

## Consolidated-feed audit

The complete UPRO/SH consolidated overlap supports a separate expanding-memory
run from 2023-09-29 to
2025-12-31. It produced
353 trades, $-2.3526 fixed-notional P&L, a
0.9868 profit factor, and
$96.2500 ending cash. This is reported
as an execution-feed audit, not substituted for the full-period primary result.

## Frozen acceptance gates

- PASS — minimum two trades per week
- FAIL — profit factor at least 1 15
- FAIL — each 2022 through 2026 ytd positive
- FAIL — both instruments positive
- PASS — positive after one extra cent each fill
- PASS — positive after five minute delay
- FAIL — positive after removing five best
- FAIL — beats same period spy price only
- PASS — improves v7 ending cash and profit factor

## Interpretation

The correct comparison is not whether SH looks better in isolation. It is
whether replacing only the bearish actuator repairs the recurring SPXU drag
while preserving frequency, robustness, and the passive-SPY hurdle. No
thresholds or features were repaired after observing SH outcomes.
