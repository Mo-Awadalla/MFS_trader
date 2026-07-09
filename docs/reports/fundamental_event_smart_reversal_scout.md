# FundamentalEventSmartReversal-v1 Scout Results

This is survivorship-biased scout evidence, not validation or trading authorization.

Analysis: `2018-04-02 00:00:00+00:00` through `2026-07-02 00:00:00+00:00`.

## Performance

| Portfolio | Total return | CAGR | Sharpe | Sortino | Max drawdown | Final $10k |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Strategy gross/no explicit costs | -5.56% | -0.69% | -0.0084 | -0.0078 | -36.70% | $9,443.89 |
| Strategy repository-default costs | -43.47% | -6.69% | -0.5748 | -0.5519 | -50.56% | $5,652.51 |
| SPY buy-and-hold | 219.35% | 15.14% | 0.8421 | 1.0382 | -33.79% | $31,934.65 |
| 100% SPY + 20% gross strategy overlay | 202.36% | 14.38% | 0.8013 | 0.9909 | -33.79% | $30,236.31 |

## SPY and implementation diagnostics

- Beta to SPY: `0.0747`.
- Annualized alpha after default costs: `-7.5088%`.
- Correlation to SPY: `0.1280`.
- Overlay gross exposure: `20.00%`; total portfolio gross `120.00%` and net `100.00%`.
- Mean Rank IC: `0.002384` (reversal expects negative).
- Mean daily gross turnover: `0.4583x` equity.
- Mean trading cost drag: `2.3082` bps/day.
- Mean borrow drag: `0.1643` bps/day.
- SEC filing-flagged symbol-sessions: `17727`.
- Normalized SEC event rows: `20107`.
- Unique issuer filings: `19978`.
- Event-vetoed symbol-days: `83866`.
- Event-forced exits: `1479`.

## Frozen scout gates

- FAIL — `gross_total_return_positive`.
- FAIL — `gross_sharpe_positive`.
- FAIL — `mean_rank_ic_negative`.
- FAIL — `default_net_total_return_positive`.
- PASS — `mean_daily_gross_turnover_at_most_1x`.

Overall frozen scout verdict: **FAIL**.

The no-event comparator is diagnostic only and cannot replace this frozen candidate.

## Limitations

- Static current-active stock universe has survivorship bias.
- SEC filing presence is a public-information proxy, not directional fundamental sentiment.
- Shared daily backtester credits close-to-close returns after a one-bar target lag; broker next-open fills require separate reconciliation.
- Known Validation Gauntlet defects block promotion even if scout gates pass.
