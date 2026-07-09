# Cross-Asset Carry + Trend Public-Data Scout v1

**Verdict: PASS**

This is a frozen falsification scout using curated public pysystemtrade data. It is not validation or trading approval.

## Inputs

- Source commit: `883c8681cf880d83acad5c39b842403a8eac5676`
- Analysis: 2010-01-04 through 2024-03-28
- Universe: 15 predeclared futures markets across six asset classes
- Primary signal: equal-weight carry sign plus 12-month trend sign
- Target volatility: 10.0%
- Default one-way cost: 2.0 bps
- Execution lag: 2 common sessions

## Component attribution

| Path | Total return | Ann. arithmetic | CAGR | Sharpe | Sortino | Ann. vol | Max drawdown | Final equity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| carry gross | 104.61% | 5.42% | 5.01% | 0.5230 | 0.7440 | 10.37% | -24.80% | 20461.3097 |
| carry net (2.0 bps) | 83.06% | 4.67% | 4.21% | 0.4495 | 0.6390 | 10.38% | -27.51% | 18305.9633 |
| trend gross | 145.56% | 6.77% | 6.32% | 0.5977 | 0.7885 | 11.33% | -25.23% | 24556.1645 |
| trend net (2.0 bps) | 125.69% | 6.20% | 5.71% | 0.5468 | 0.7217 | 11.33% | -25.41% | 22568.7688 |
| combined gross | 168.26% | 7.36% | 6.97% | 0.6566 | 0.8892 | 11.22% | -27.40% | 26826.3385 |
| combined net (2.0 bps) | 147.72% | 6.82% | 6.39% | 0.6080 | 0.8231 | 11.22% | -29.18% | 24772.3844 |

## Frozen subperiods

| Path | Total return | Ann. arithmetic | CAGR | Sharpe | Sortino | Ann. vol | Max drawdown | Final equity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2010_2016 | 48.70% | 5.97% | 5.65% | 0.6104 | 0.8071 | 9.78% | -16.58% | 14869.5404 |
| 2017_2024 | 66.60% | 7.64% | 7.11% | 0.6137 | 0.8578 | 12.46% | -24.17% | 16659.8184 |

## Cost sensitivity

| Path | Total return | Ann. arithmetic | CAGR | Sharpe | Sortino | Ann. vol | Max drawdown | Final equity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| combined 0.0 bps | 168.26% | 7.36% | 6.97% | 0.6566 | 0.8892 | 11.22% | -27.40% | 26826.3385 |
| combined 1.0 bps | 157.79% | 7.09% | 6.68% | 0.6323 | 0.8562 | 11.22% | -28.29% | 25779.1272 |
| combined 2.0 bps | 147.72% | 6.82% | 6.39% | 0.6080 | 0.8231 | 11.22% | -29.18% | 24772.3844 |
| combined 5.0 bps | 119.80% | 6.01% | 5.52% | 0.5350 | 0.7244 | 11.22% | -31.76% | 21979.7722 |

## Asset-class contributions

| Asset class | Gross P&L | Default-net P&L | Gross return contribution | Net return contribution |
| --- | ---: | ---: | ---: | ---: |
| equity_index | 50.78% | 47.77% | 43.89% | 42.40% |
| rates | 36.61% | 30.76% | 27.20% | 23.65% |
| fx | 41.67% | 36.19% | 23.66% | 21.22% |
| energy | 16.85% | 14.90% | 9.22% | 8.45% |
| metals | -8.99% | -9.86% | -4.78% | -5.66% |
| agriculture | 31.34% | 27.95% | 14.81% | 14.27% |

## Leave-one-asset-class-out

| Path | Total return | Ann. arithmetic | CAGR | Sharpe | Sortino | Ann. vol | Max drawdown | Final equity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| without equity_index | 74.87% | 4.41% | 3.89% | 0.4048 | 0.5535 | 10.88% | -35.97% | 17486.5174 |
| without rates | 106.41% | 5.63% | 5.07% | 0.4805 | 0.6466 | 11.72% | -25.58% | 20640.6718 |
| without fx | 109.19% | 5.59% | 5.17% | 0.5332 | 0.7426 | 10.47% | -35.10% | 20918.8523 |
| without energy | 136.10% | 6.46% | 6.04% | 0.5934 | 0.7877 | 10.88% | -23.29% | 23610.0049 |
| without metals | 176.03% | 7.49% | 7.17% | 0.7052 | 0.9354 | 10.63% | -23.04% | 27602.5535 |
| without agriculture | 125.28% | 6.10% | 5.70% | 0.5778 | 0.7617 | 10.56% | -24.88% | 22528.4786 |

## SPY utility

| Path | Total return | Ann. arithmetic | CAGR | Sharpe | Sortino | Ann. vol | Max drawdown | Final equity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SPY | 502.20% | 13.70% | 13.03% | 0.8069 | 0.9732 | 16.98% | -33.72% | 60219.8329 |
| spy plus 20pct | 629.57% | 15.07% | 14.52% | 0.8711 | 1.0631 | 17.30% | -32.58% | 72957.4635 |
| spy plus 50pct primary | 859.49% | 17.11% | 16.68% | 0.9360 | 1.1630 | 18.28% | -30.89% | 95949.3449 |

## Portfolio diagnostics

- mean_daily_turnover: `0.108186`
- median_daily_turnover: `0.000000`
- max_daily_turnover: `3.137575`
- mean_daily_cost_bps: `0.216372`
- total_cost_arithmetic_return: `0.079906`
- mean_active_markets: `8.364744`
- min_active_markets_when_invested: `3.000000`
- mean_gross_notional: `2.066214`
- max_gross_notional: `3.414016`
- roll_count: `471.000000`
- rebalance_count: `161.000000`
- spy_daily_correlation: `0.076104`
- largest_absolute_gross_asset_class_pnl_share: `27.27%`
- best_12_positive_month_pnl_share: `37.17%`

## Frozen hard gates

- [x] combined_gross_total_return_positive
- [x] combined_gross_sharpe_at_least_0_40
- [x] combined_net_total_return_positive
- [x] combined_net_sharpe_at_least_0_35
- [x] carry_and_trend_gross_total_returns_positive
- [x] both_subperiods_net_profitable_with_positive_sharpe
- [x] all_leave_one_asset_class_out_net_sharpes_positive
- [x] largest_asset_class_absolute_gross_pnl_share_at_most_60pct
- [x] best_12_months_positive_pnl_share_at_most_50pct
- [x] combined_profitable_at_5bps
- [x] primary_overlay_sharpe_not_below_spy
- [x] primary_overlay_drawdown_within_1pct_of_spy
- [x] primary_overlay_cagr_within_1pct_of_spy

## Limitations

- Public source multiple-price data are curated and stale after 2024-03-28.
- The panel lacks complete individual-contract chains, volume, open interest, and exact notice dates.
- Source roll calendars may contain maintainer judgment or manual edits.
- Back-adjusted point changes and supplied contract mappings are suitable only for falsification research.
- A passing scout requires independent raw-contract replication before validation or trading.

## Decision rule

A FAIL rejects this exact construction without parameter rescue. A PASS only permits a five-market raw-contract replication; it does not permit paper or live trading.
