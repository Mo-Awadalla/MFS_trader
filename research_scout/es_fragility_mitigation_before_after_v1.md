# ES Fragility Mitigation: Before vs After v1

Saved: 2026-07-25

## Status

The unchanged three-engine portfolio is the benchmark. The one-position first-signal rule is a prospective paper challenger created after 2024-2025 had already informed the research program. Its historical comparison is diagnostic, not a new validation result.

## Mitigation rule

- Keep all three component signals, stops, and exits unchanged.
- Take at most one trade per RTH session.
- Take the earliest valid signal.
- If signals share the same entry minute, select the smaller frozen initial structural risk.
- Break an exact risk tie alphabetically by engine name.
- Ignore every later signal that day, even if the selected trade stops.

The rule does not use historical engine P&L, direction, volatility, agreement, or future signals.

## Secondary holdout comparison: 2024-2025

| Metric | Three-engine benchmark | One-position challenger | Change |
|---|---:|---:|---:|
| Trades | 724 | 444 | -280 |
| Trades per week | 6.962 | 4.269 | -2.693 |
| Net P&L | $1,605.49 | $1,023.94 | -$581.55 |
| Mean trade | $2.218 | $2.306 | +$0.088 |
| Profit factor | 1.077 | 1.083 | +0.006 |
| Maximum daily drawdown | -$1,384.58 | -$1,296.30 | +$88.28 |
| Median initial risk per active day | $61.26 | $31.98 | -47.8% |
| 95th-percentile initial risk | $191.34 | $98.79 | -48.4% |
| Maximum initial risk | $509.23 | $263.74 | -48.2% |

The challenger retains more than four trades per week and reduces initial exposure almost exactly by half. Nominal expectancy and profit factor do not materially change.

## Execution reserve

| Extra reserve per trade | Benchmark holdout | Challenger holdout |
|---|---:|---:|
| $0.00 | $1,605.49 | $1,023.94 |
| $1.25 | $700.49 | $468.94 |
| $2.50 | -$204.51 | -$86.06 |

The challenger loses less under the strict reserve because it takes fewer trades, but both systems fail the required $2.50-per-trade buffer.

## Tail and concentration

| Metric | Benchmark | Challenger |
|---|---:|---:|
| Net without five largest winners | -$578.31 | -$1,011.11 |
| Positive-week fraction | 43.8% | 42.9% |
| Best month share of total profit | 50.8% | 57.3% |
| Net after removing each year's best month | $37.64 | -$47.83 |
| 12-month rolling minimum | $46.39 | -$386.79 |
| 12-month rolling fraction positive | 100.0% | 85.7% |

The one-position rule makes profit concentration worse. It removes many ordinary trades but still depends on a few large winners.

## Five-day block bootstrap

| Metric | Benchmark | Challenger |
|---|---:|---:|
| Probability total P&L is nonpositive | 27.1% | 30.3% |
| Median simulated max drawdown | -$2,147.05 | -$1,629.72 |
| Bad 5% max drawdown | -$4,199.38 | -$3,217.72 |

The challenger improves the simulated drawdown distribution by roughly 24%, but the probability that total P&L is nonpositive becomes slightly worse.

## Calendar comparison

Both systems remain positive in all five historical years. The challenger changes the year distribution materially:

| Year | Benchmark | Challenger |
|---|---:|---:|
| 2021 | $1,312.64 | $550.81 |
| 2022 | $3,904.86 | $1,552.79 |
| 2023 | $1,155.45 | $311.92 |
| 2024 | $144.49 | $845.63 |
| 2025 | $1,461.00 | $178.31 |

This apparent redistribution was observed after holdout and must not be interpreted as regime robustness.

## Verdict

The mitigation succeeds at **exposure control**:

- no concurrent positions;
- one trade per day;
- approximately 50% lower active-day structural risk;
- lower bootstrap drawdown tails;
- frequency remains above four trades per week.

It fails at **edge robustness**:

- negative under the $2.50-per-trade reserve;
- negative without the five largest winners;
- greater best-month concentration;
- higher bootstrap probability of a nonpositive total;
- weaker rolling 12-month behavior.

Keep the unchanged portfolio as the immutable paper benchmark. Track the challenger prospectively as a risk-reduction alternative, but do not treat it as an improved strategy.

## Forward approval protocol

The challenger may be considered further only after:

1. At least 100 untouched trades and approximately 12 calendar months.
2. Actual MES bid/ask fills recorded for every entry, stop, and exit.
3. Both six-month halves positive after actual costs.
4. Positive total after an additional $2.50-per-trade reserve.
5. Positive total after removing the five largest winners.
6. No single month contributing more than total net profit.
7. Drawdown inside a dollar limit chosen before paper trading.

No rule changes are allowed during that collection period.
