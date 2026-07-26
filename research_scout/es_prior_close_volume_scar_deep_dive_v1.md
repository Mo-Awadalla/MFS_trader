# ES Prior-Close Volume-Scar Handoff Deep Dive v1

Saved: 2026-07-26

## Verdict

The candidate contains plausible directional information, but it is not ready for live capital and is not a strong historical addition to the three-engine portfolio.

The exact prior-session volume scar outperformed three frozen anchor controls in both development and secondary holdout. Actual direction also decisively beat an equal-risk flipped placebo. Those are meaningful positives.

The limitations are equally material:

- the broader effect also appears with prior VWAP and prior terminal price, so the scar is an incremental improvement over generic prior closing value rather than a unique source of alpha;
- five-minute entry delay erased holdout expectancy;
- the median trade and median R multiple were full losses;
- five winners supplied more than the entire holdout net profit;
- portfolio overlap and correlation with the existing opening-center engine were high.

Continue unchanged prospective paper tracking only.

## Frozen candidate reconstruction

| Sample | Trades/week | P&L | Mean/trade | PF | Win rate | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Development 2021-2023 | 2.776 | $4,420.03 | $10.21 | 1.479 | 21.5% | -$1,100.09 |
| Secondary holdout 2024-2025 | 2.673 | $1,206.45 | $4.34 | 1.171 | 20.1% | -$899.26 |

Holdout expectancy declined 57.5% relative to development. Median holdout trade was -$17.79 and median R was -1.0. The typical trade therefore reaches its structural stop; profitability depends on a minority of large close-carry survivors.

## Mechanism falsification

Every control used the same opening confirmation, stop, entry, exit, and commission. Controls are diagnostics and cannot replace the frozen candidate.

| Prior-session anchor | Development P&L / PF | Holdout P&L / PF |
|---|---:|---:|
| Exact volume scar | $4,420.03 / 1.479 | $1,206.45 / 1.171 |
| Transaction VWAP | $4,025.34 / 1.427 | $882.49 / 1.125 |
| Terminal transaction price | $3,518.69 / 1.361 | $885.58 / 1.121 |
| Two-session-stale volume scar | $1,380.44 / 1.145 | $133.41 / 1.022 |

Interpretation:

1. The exact volume scar was best in both samples.
2. Recency matters: the two-session-stale scar nearly lost all expectancy.
3. The scar is not the whole mechanism. Prior VWAP and terminal price were also profitable, indicating a broader cross-day opening-acceptance effect.
4. The proper economic description is therefore: **current opening acceptance relative to fresh prior closing value, with the most-traded price providing a modestly better anchor.**

## Paired direction placebo

| Direction | Development P&L / PF | Holdout P&L / PF |
|---|---:|---:|
| Frozen direction | $4,420.03 / 1.479 | $1,206.45 / 1.171 |
| Flipped, same time and initial risk | -$1,721.76 / 0.836 | -$433.08 / 0.945 |

This supports genuine directional information rather than a generic 10:00-to-15:30 time-of-day drift.

## Execution sensitivity

### Stop implementation

Futures stops must lie on the 0.25-point tick grid. Rounding long stops down and short stops up produced:

| Sample | P&L | PF | Max DD |
|---|---:|---:|---:|
| Development | $4,224.33 | 1.448 | -$1,119.53 |
| Holdout | $1,085.28 | 1.151 | -$930.56 |

The edge survives realistic adverse stop rounding.

### Entry timing

Delayed entries were canceled whenever the frozen structural stop was touched before entry.

| Delay | Development trades/week / P&L | Holdout trades/week / P&L / PF |
|---|---:|---:|
| None | 2.776 / $4,420.03 | 2.673 / $1,206.45 / 1.171 |
| 1 minute | 2.147 / $3,819.40 | 1.990 / $627.86 / 1.088 |
| 5 minutes | 1.776 / $2,964.11 | 1.702 / $9.40 / 1.001 |
| 15 minutes | 1.340 / $3,777.29 | 1.346 / -$337.96 / 0.948 |

This is the largest practical weakness. The information must be acted on very near 10:00. A one-minute delay still made money but narrowly missed the two-trades-per-week constraint. Five minutes eliminated holdout expectancy.

The available historical test uses the one-minute bar open plus one adverse tick rather than recorded 10:00 MES quotes. That is adequate for hypothesis research but not enough to certify live execution.

### Exit timing controls

All frozen diagnostic exits remained positive in both samples:

| Exit | Development P&L / PF | Holdout P&L / PF |
|---|---:|---:|
| 14:30 | $3,136.82 / 1.344 | $1,585.58 / 1.232 |
| 15:00 | $3,731.61 / 1.405 | $1,730.70 / 1.247 |
| Frozen 15:30 | $4,420.03 / 1.479 | $1,206.45 / 1.171 |
| 15:55 | $4,495.03 / 1.485 | $1,342.09 / 1.189 |

The persistence effect is not unique to the exact 15:30 exit. None of the alternative exits may replace the frozen rule because they were evaluated after the candidate was known.

### Cost budget

The frozen holdout result after extra cost per trade:

| Additional cost | Holdout P&L |
|---:|---:|
| $0.00 | $1,206.45 |
| $1.25 | $858.95 |
| $2.50 | $511.45 |
| $5.00 | -$183.55 |

Historical break-even additional friction was approximately $4.34 per trade beyond the already modeled adverse entry tick, adverse exit tick, and $1.24 commission. Tick-grid stop rounding reduces that reserve further.

## Tail and calendar concentration

### Development

- Net after removing best trade: $3,843.77.
- Net after removing five best: $2,154.98.
- Net after removing ten best: $678.68.
- Positive weeks: 45.5%.
- Positive months: 66.7%.
- Positive quarters: 75.0%.
- Longest losing-trade streak: 17.

### Secondary holdout

- Net after removing best trade: $795.19.
- Net after removing five best: -$662.35.
- Net after removing ten best: -$2,041.15.
- Positive weeks: 37.1%.
- Positive months: 58.3%.
- Positive quarters: 50.0%.
- Longest losing-trade streak: 14.

Only four of eight holdout quarters were profitable. The five best holdout trades totaled $1,868.80, or 155% of net holdout profit.

### Moving-block bootstrap

| Holdout bootstrap | Probability total P&L ≤ 0 |
|---|---:|
| Five-session blocks, baseline cost | 21.3% |
| Twenty-session blocks, baseline cost | 18.7% |
| Five-session blocks, another $2.50/trade | 38.6% |
| Twenty-session blocks, another $2.50/trade | 42.1% |

Longer blocks modestly support the baseline edge but show that cost-stressed profitability is highly uncertain.

## Relationship with the three-engine benchmark

| Holdout diagnostic | Result |
|---|---:|
| Candidate active days | 278 |
| Candidate days overlapping benchmark | 257 |
| Overlap fraction | 92.4% |
| Daily correlation, all days | 0.586 |
| Daily correlation on overlapping days | 0.801 |
| Correlation with opening-center engine | 0.691 |
| Correlation with compressed convexity | 0.252 |
| Correlation with midday reload | 0.107 |

The candidate is mostly another expression of the opening-center family, not an independent fourth engine.

The descriptive unweighted combination produced $2,811.94 in holdout with PF 1.101, but:

- combined drawdown increased to -$2,267.30;
- another $2.50 per trade reduced combined profit to $306.94;
- selection occurred after both holdouts were observed.

The historical combination must not be promoted or assigned optimized weights.

## Final classification

### Evidence supporting the candidate

- Positive in all five calendar years and both directions.
- Exact scar beat all frozen anchor controls in both samples.
- Fresh scar decisively beat the stale scar.
- Actual direction beat the equal-risk flipped placebo.
- Adverse tick-grid stops remained profitable.
- Several exit clocks remained profitable.

### Evidence against deployment

- No pristine holdout remains.
- Holdout expectancy decayed by more than half.
- Five-minute entry delay erased the edge.
- No recorded 10:00 MES quotes are available in the present dataset.
- Median trade is a full structural loss.
- Five winners exceed total holdout profit.
- Cost-stressed bootstrap failure probability is roughly 39%-42%.
- It strongly overlaps the opening-center engine.

## Decision and forward test

Preserve the exact candidate for forward paper tracking, with adverse tick-grid stop rounding recorded as a conservative implementation diagnostic. Do not change its anchor, direction, 10:00 entry, 15:30 exit, side eligibility, or risk logic.

Before live consideration, require genuinely new data with:

1. recorded executable MES bid/ask quotes around 10:00 and every stop event;
2. at least 100 forward trades;
3. positive net P&L after an additional $2.50 per trade;
4. both long and short forward P&L positive;
5. no five trades contributing more than total net profit;
6. block-bootstrap probability of loss below 20%;
7. evaluation as a standalone rule before any portfolio combination.

At the historical rate, 100 trades requires roughly 37 weeks. Until then, this remains an interesting but fragile paper hypothesis.
