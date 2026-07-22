# Bitcoin Crowded-Long Unwind — Binance Perpetual v1 Results

Status: **DEVELOPMENT SCOUT FAILED — STOPPED**

Specification: `research_scout/bitcoin_crowded_long_unwind_binance_v1.json`

Specification SHA-256: `42b399210c699e914cda970a79ada2f64eacd4cf4762440a5e00e854f212316b`

An asynchronously returned pre-result design review required explicit information-availability semantics. The authoritative rerun uses a five-minute publication lag, a 00:10 decision, and excludes any position crossing an actual funding event. This conservative correction did not change any selected day or performance number; no later partition was opened.

Machine evidence:

- `data/parquet/bitcoin_crowded_long_unwind_binance_v1/development/report.json`
- `data/parquet/bitcoin_crowded_long_unwind_binance_v1/development/report.md`
- `data/parquet/bitcoin_crowded_long_unwind_binance_v1/development/panel.parquet`

## Verdict

The frozen crowded-long short produced a positive average in development, but only 15 trades, no trades in 2022, and a bootstrap interval spanning materially negative outcomes. It failed two terminal gates and therefore does not progress.

This is **interesting descriptive evidence, not a validated edge**. Internal validation and final holdout remain locked.

## Frozen rule

At 00:10 UTC once per day:

- require the already-settled funding rate to be positive and above the 90th percentile of the prior 270 settlements;
- require BTC-denominated open interest to have increased over the prior eight hours;
- short the Binance BTCUSDT USDⓈ-M perpetual at the 00:30 kline open;
- exit at the 07:30 kline open;
- otherwise remain flat.

The trade ends before the 08:00 funding settlement, so no funding cash flow is assumed.

## Development result

Period: 2020-09-01 through 2022-12-31.

| Metric | Result |
|---|---:|
| Complete point-in-time days | 849 |
| Triggered trades | **15** |
| Exposure fraction | 1.77% |
| Mean gross short return | +58.8171 bps |
| Mean after 10 bps fee-only cost | +48.8171 bps |
| Mean after 20 bps conservative cost | +38.8171 bps |
| Directional accuracy | 53.33% |
| Bootstrap 95% gross interval | **[-55.81, +176.65] bps** |
| First chronological half | +103.17 bps |
| Second chronological half | +20.01 bps |
| Mean after largest 5% absolute outcomes removed | +20.91 bps |
| Top 5% profit contribution | 34.01% |
| Gross zero-cash total return | +8.77% |
| Conservative zero-cash total return | +5.57% |
| Conservative zero-cash Sharpe | 0.423 |

The zero-cash annualized metrics include hundreds of flat days and should not be interpreted as evidence of scalable performance. The trade count and uncertainty are decisive.

## Frozen gates

Passed:

- positive gross mean;
- directional accuracy above 50%;
- positive mean in both chronological halves;
- positive after conservative costs;
- positive after removing the largest 5% of absolute outcomes;
- acceptable profit concentration;
- complete timestamp alignment;
- combined trigger mean above funding-only mean.

Failed:

1. **Minimum 40 selected days:** only 15.
2. **Bootstrap lower bound above zero:** lower bound was -55.81 bps.

All gates were conjunctive. The scout failed.

## Controls

| Control | Days | Mean short gross | Accuracy |
|---|---:|---:|---:|
| Extreme funding only | 49 | +8.00 bps | 40.82% |
| Rising OI only | 190 | +2.75 bps | 48.42% |
| Extreme premium only | 12 | **-31.84 bps** | 33.33% |
| Combined funding + rising OI | 15 | +58.82 bps | 53.33% |

The combined condition was stronger than either component, but this comparison was based on very few events. Funding-only and OI-only were not independently tradeable after the conservative 20 bps cost. The basis-only control had the wrong sign.

## Time instability

| Year | Trades | Gross mean | Conservative mean |
|---|---:|---:|---:|
| 2020 partial | 5 | +151.21 bps | +131.21 bps |
| 2021 | 10 | +12.62 bps | **-7.38 bps** |
| 2022 | 0 | n/a | n/a |

The apparent aggregate profit was concentrated in five late-2020 events. The ten 2021 events did not survive conservative costs on average, and the rule generated no 2022 events.

This is a severe regime-coverage problem even though the chronological-half gate happened to pass. The rule cannot be called stable when one complete calendar year contains no opportunities.

## Outcome distribution

Selected short-return quantiles:

- Minimum: -418.63 bps
- 5th percentile: -302.41 bps
- 25th percentile: -36.15 bps
- Median: +90.91 bps
- 75th percentile: +130.02 bps
- 95th percentile: +446.19 bps
- Maximum: +589.50 bps

Fifteen observations are inadequate to estimate this tail reliably. The wide bootstrap interval reflects that uncertainty.

## Accounting audit

An independent recomputation from `panel.parquet` confirmed:

- short return exactly equals `1 - exit_open / entry_open`;
- gross mean exactly equals 58.817126892655246 bps;
- fee-only mean exactly equals 48.81712689265524 bps;
- conservative mean exactly equals 38.817126892655224 bps;
- funding and OI timestamps plus the frozen five-minute publication lag are at or before the 00:10 cutoff;
- entry is after the cutoff;
- exit is after entry and before the next funding settlement;
- all 849 session dates are unique.

No later-partition returns were evaluated. The runner independently returned:

`BLOCKED: internal_validation locked: development did not pass`

## Interpretation

The conjunction may identify rare stressed episodes, but development cannot distinguish a repeatable mechanism from a small number of crisis observations. The evidence does not support trading it, training ML on it, or using it as a risk model.

The following are prohibited rescues on this consumed sample:

- lower the 90th-percentile threshold;
- shorten the 270-settlement history;
- remove the rising-OI requirement;
- change from BTC OI to USD OI;
- change the 8-hour OI lag;
- move entry or exit;
- invert to continuation;
- add premium, volume, volatility, top-trader ratios, stops, or leverage;
- fit an ML classifier to the 15 events;
- inspect 2023–2025 for this specification.

## Final assessment

**Reject `Bitcoin-Crowded-Long-Unwind-BinancePerp-v1` as a trading strategy.**

Retain only the limited research lesson: in 2020–2021, a small subset of extreme positive-funding events with rising OI preceded some large seven-hour declines, but the sample was too sparse and unstable to establish an after-cost edge.
