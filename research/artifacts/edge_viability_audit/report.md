# Edge Viability Audit — ETF TSMOM family

Data: 2021-06-30 → 2026-06-26 (1253 daily bars, 261 weeks). Universe: SPY, QQQ, IWM, IEF, GLD, DBC, EFA, EEM, VNQ, TLT (+SHY cash).

## VERDICT: **NON_TRADEABLE_KILL_OR_PIVOT** (5/8 kill criteria tripped)

| Kill criterion | Tripped |
|---|---|
| signal_predictive_power_weak | YES |
| top_minus_bottom_spread_not_persistent | no |
| edge_dies_under_modest_costs_le_5x | no |
| fails_to_beat_random_selection_p95 | YES |
| fails_to_beat_shuffled_signals_p95 | YES |
| fails_to_beat_passive_benchmarks | YES |
| gains_concentrated_single_year_gt_70pct | no |
| wfa_mc_dsr_gauntlet_fails | YES |

### Interpretation

- Pooled positive-momentum forward returns are positive, but the (+mom) vs (-mom) difference is
  statistically indistinguishable (diff p 0.47–0.94). The positive means are market beta, not signal.
- Cross-sectional 63d momentum rank **anti-predicts**: top-3 minus bottom-3 spread is negative at every
  horizon (~ -4% to -6% annualized, t = -2.4 at 8w), with the same sign in train and test. On this
  universe/period, ranking by 63d momentum selects the wrong assets persistently.
- The strategy sits at the 17th percentile of random 3-of-10 selection and the 2nd percentile of its own
  shuffled-signal null: the signal ordering actively destroys value versus chance.
- Costs are not the problem (breakeven ~19.5 bp/side vs 1 bp assumed). The edge is absent, not eroded.
- Regime table shows returns concentrate in low-dispersion / low-correlation / no-drawdown regimes —
  consistent with the C12 v3 gate direction — but gating cannot rescue a selection rule that is
  anti-predictive at the ranking level.

## 1. Signal predictive power (pooled across ETFs)

| Horizon | n(+mom) | hit rate | mean fwd | median | t | p | boot 95% CI | diff(+/-) t | diff p |
|---|---|---|---|---|---|---|---|---|---|
| 1w | 1386 | 53.75% | 0.13% | 0.21% | 2.028 | 0.043 | [-0.00%, 0.26%] | 0.073 | 0.942 |
| 2w | 1380 | 53.33% | 0.24% | 0.26% | 2.706 | 0.007 | [0.01%, 0.48%] | -0.222 | 0.824 |
| 4w | 1367 | 56.77% | 0.54% | 0.68% | 4.372 | 0.000 | [0.12%, 0.97%] | 0.425 | 0.671 |
| 8w | 1343 | 56.59% | 1.05% | 0.92% | 5.989 | 0.000 | [0.31%, 1.84%] | 0.722 | 0.470 |

Caveat: overlapping multi-week horizons inflate naive t-stats; trust bootstrap CIs.

Train/test (positive-momentum diff vs negative):

| Horizon | train diff-p | test diff-p |
|---|---|---|
| 1w | 0.434 | 0.803 |
| 2w | 0.193 | 0.387 |
| 4w | 0.247 | 0.357 |
| 8w | 0.235 | 0.025 |

## 2. Cross-sectional selection (top-3 vs bottom-3 by 63d momentum)

Weekly top-3 one-way turnover: 36.91%

| Horizon | spread mean | spread t | ann. spread | train mean | test mean | rank-IC | IC t | net 1x | net 2x | net 5x |
|---|---|---|---|---|---|---|---|---|---|---|
| 1w | -0.07% | -0.569 | -3.87% | -0.20% | 0.06% | 0.005 | 0.186 | -0.09% | -0.10% | -0.15% |
| 2w | -0.20% | -1.174 | -5.31% | -0.38% | -0.01% | -0.007 | -0.263 | -0.23% | -0.26% | -0.35% |
| 4w | -0.36% | -1.361 | -4.72% | -0.55% | -0.16% | 0.007 | 0.236 | -0.42% | -0.48% | -0.66% |
| 8w | -0.86% | -2.355 | -5.57% | -0.92% | -0.80% | -0.048 | -1.839 | -0.97% | -1.09% | -1.45% |

## 3. Regime dependency (pooled +momentum 4w forward returns)

| Regime | Bucket | weeks | mean fwd 4w | hit | diff(+/-) p |
|---|---|---|---|---|---|
| volatility | high | 126 | 0.32% | 55.96% | 0.974 |
| volatility | low | 127 | 0.70% | 57.36% | 0.992 |
| dispersion | high | 128 | 0.14% | 51.74% | 0.053 |
| dispersion | low | 129 | 0.80% | 60.10% | 0.001 |
| correlation | high | 124 | 0.16% | 53.26% | 0.005 |
| correlation | low | 125 | 0.85% | 59.63% | 0.000 |
| spy_drawdown | in_drawdown_gt_10pct | 69 | -0.56% | 47.01% | 0.000 |
| spy_drawdown | normal | 192 | 0.79% | 58.96% | 0.002 |
| rates_proxy_tlt_12w | rising_rates_tlt_down | 166 | 0.56% | 55.76% | 0.321 |
| rates_proxy_tlt_12w | falling_rates_tlt_up | 83 | 0.52% | 57.97% | 0.103 |

## 4. Capacity and cost

- Turnover/year: 18.871 | trades: 1525 | base cost: 1 bp/side
- Breakeven cost multiplier (Sharpe → 0): 19.500x = 19.500 bp/side

| Cost | Sharpe | CAGR | MaxDD |
|---|---|---|---|
| 1x | 0.330 | 3.45% | -33.24% |
| 2x | 0.312 | 3.21% | -33.57% |
| 5x | 0.259 | 2.51% | -34.56% |

## 5. Null models (weekly-grid, like-for-like rule and costs)

- Strategy weekly Sharpe: 0.166
- Random 3-of-10 (500 sims): mean 0.400, p95 0.774, strategy percentile 16.80%
- Shuffled signals (500 sims): mean 0.579, p95 0.894, strategy percentile 2.00%
- Rebalance anchors: W-MON 0.177, W-TUE 0.268, W-WED 0.248, W-THU 0.369
- Benchmarks: equal_weight_10etf 0.536, spy_buy_hold 0.720, sixty_forty 0.283, shy -0.493

## 6. Robustness

- Rolling 26w Sharpe: min -3.665, median 0.685, negative fraction 27.57%
- WFA: mean fold Sharpe 0.994, positive folds 83.33%, strict pass: no
- MC: 5th pct Sharpe -0.391, strict pass: no
- DSR: p = 0.231, strict pass: no
- Full-sample net Sharpe 0.330, CAGR 3.45%, MaxDD -33.24%

## Notes and limitations

- History limited to 2021-06-30 onward (data access constraint): ~5 years, one full hiking cycle. All regime
  splits use full-sample medians (descriptive, not tradable rules).
- Null models use a weekly-grid equal-weight approximation of the base rule so strategy and nulls face
  identical costs; daily-backtest metrics (section 4/6) use the exact base implementation.
- Audit only: no parameters tuned, no variants added, no candidate promoted.
