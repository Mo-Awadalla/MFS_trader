# IBBIntradayAfternoonRecovery-v1 Results

Generated: 2026-06-29T21:02:33-04:00

## Data source

- Instrument: `IBB`.
- Benchmark/context: `SPY`.
- Source: Yahoo Chart API `range=730d&interval=60m&includePrePost=false`.
- Data window: 2023-08-01 09:30:00-04:00 to 2026-06-29 15:30:00-04:00.
- Valid IBB sessions evaluated: 721.
- Largest-biotech-ETF note: Nasdaq ETF summary check showed IBB market cap around $8.92B during the run, larger than XBI/FBT/BBH in the quick comparison.

## Frozen rule recap

If IBB return from first regular-session open to the close of the 11:30 ET hourly bar is <= -0.750%, buy the next available 12:30 ET hourly bar open and exit at the final same-day regular-session close. Long-only, flat by close. Net return subtracts 0.100% round-trip cost.

## Verdict

SCOUT FAIL

- PASS: `at_least_40_trades`
- FAIL: `net_average_positive`
- FAIL: `net_median_positive`
- FAIL: `net_win_rate_above_52pct`
- FAIL: `both_halves_positive`
- FAIL: `top5_under_50pct_total_net_profit`


Half-sample net average: first half -0.209%, second half -0.174%.

Top 5 net-profit contribution: n/a.

## Summary metrics

| Series | N | Mean | Median | Win rate | Worst | Best |
|---|---:|---:|---:|---:|---:|---:|
| Signal trades, gross 12:30-to-close | 124 | -0.092% | -0.094% | 43.548% | -3.154% | 2.735% |
| Signal trades, net after 10 bps | 124 | -0.192% | -0.194% | 36.290% | -3.254% | 2.635% |
| Signal-day IBB open-to-close | 124 | -1.358% | -1.354% | 3.226% | -5.409% | 0.773% |
| Signal-day SPY same window | 124 | -0.053% | 0.014% | 52.419% | -3.382% | 2.519% |
| All sessions same-window net | 721 | -0.094% | -0.091% | 43.551% | -3.712% | 8.122% |


## By calendar year, signal trades net after cost

| Year | Trades | Mean | Median | Win rate |
|---|---:|---:|---:|---:|
| 2023 | 16 | -0.132% | -0.127% | 43.750% |
| 2024 | 34 | -0.248% | -0.264% | 38.235% |
| 2025 | 45 | -0.292% | -0.294% | 33.333% |
| 2026 | 29 | -0.002% | -0.082% | 34.483% |


## Worst signal days after cost

| Date | Morning return | Net 12:30-to-close return |
|---|---:|---:|
| 2025-04-08 | -2.338% | -3.254% |
| 2025-05-06 | -1.920% | -2.552% |
| 2025-04-01 | -0.857% | -1.877% |
| 2024-11-14 | -0.934% | -1.466% |
| 2024-08-07 | -1.385% | -1.452% |


## Best signal days after cost

| Date | Morning return | Net 12:30-to-close return |
|---|---:|---:|
| 2025-04-10 | -5.348% | 2.635% |
| 2026-02-26 | -1.998% | 1.519% |
| 2026-06-09 | -0.803% | 1.514% |
| 2025-11-07 | -1.263% | 1.185% |
| 2026-01-12 | -1.597% | 1.099% |


## Interpretation guardrail

This is a scout result, not a trading authorization. If this failed, do not rescue it by changing the threshold or timing window inside this hypothesis. If it passed, it would still need a new frozen Experiment with cleaner data, more robust intraday validation, explicit event/news filters, and paper/sim execution checks.
