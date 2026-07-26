# ES Unconventional Hypothesis Pass v1

Saved: 2026-07-25

## Objective

Test mechanisms that do not reduce to standard momentum, mean reversion, breakout, VWAP attraction, or conventional order-book imbalance while preserving:

- at least two trades per week;
- intraday-only positions;
- one MES per engine;
- conservative simulated fills or recorded executable MES quotes;
- positive 2021, 2022, and 2023 development P&L;
- positive long and short development P&L;
- no post-hoc inverse, side, clock, magnitude, or regime filters.

## 1. Auction Hysteresis Escape

Idea: cumulative value is auction memory rather than a magnet. When price crosses the cash open while the dynamic value center remains stranded on the opposite side, trade away from stale value.

Result:

- 490 trades; 3.141 per week.
- -$1,686.35; profit factor 0.689.
- 2021: -$799.74.
- 2022: -$867.02.
- 2023: -$19.59.
- Long: -$668.89; short: -$1,017.46.
- 94.9% stopped at the cash-open invalidation.

Decision: rejected without holdout access. The obvious fade is a result-derived inverse and is prohibited.

## 2. Auction Arrow of Time

Idea: distinguish information-bearing volume that arrives before directional displacement from reactive volume that arrives after displacement using a time-antisymmetric opening-auction statistic.

Result:

- 749 trades; 4.801 per week.
- -$1,986.26; profit factor 0.907.
- 2021: -$1,721.24.
- 2022: -$308.75.
- 2023: +$43.73.
- Long: -$1,039.59; short: -$946.67.

Decision: rejected without holdout access. Negating or thresholding the arrow score is prohibited.

## 3. Displayed Liquidity Shadow

Idea: visible liquidity is a target rather than support. At 15:30:05, trade toward the larger displayed MES top-of-book queue and cross the recorded spread at entry and 15:59:45 exit.

Result:

- 738 trades; 4.731 per week.
- -$596.37; profit factor 0.961.
- 2021: -$937.53.
- 2022: +$967.45.
- 2023: -$626.29.
- Long: -$1,357.52; short: +$761.15.
- Median recorded MES entry and exit spread: one tick.

Decision: rejected without holdout access. Short-only selection or queue-direction reversal is prohibited.

## What this pass teaches

1. A novel representation is not automatically novel information.
2. One-minute volume sequencing did not persist into the later cash session.
3. A single displayed queue snapshot is too transient to provide symmetric direction.
4. The recurring 2022-only success pattern remains an effective false-discovery alarm.
5. Frequency was easy to obtain; stable expectancy was not.

## Next untouched direction

The next family should use a **counterfactual auction**, not a forecast from the observed path alone:

- construct the auction center produced by actual volume placement;
- construct a paired center using the same prices but a deliberately neutral volume assignment;
- trade only the sign of the displacement between observed and counterfactual clearing states;
- use no fitted threshold and preserve a single symmetric rule.

No exact counterfactual or direction is specified here. It must be chosen and preregistered before any calculation so the failed Arrow-of-Time result cannot determine the transformation.
