# UPRO/SPXU Expanding Analog Memory

## Why this test was different

Instead of requiring one handcrafted indicator to work unchanged across every
regime, the algorithm represented each morning with 12 joint SPY/UPRO/SPXU
features and searched only earlier sessions for similar states.

For every day:

1. Robust-standardize features using only prior-session medians and
   interquartile ranges.
2. Select ceiling(square root of prior sessions) nearest mornings.
3. Estimate the executable afternoon return of both UPRO and SPXU from those
   historical neighbors.
4. Choose the ETF with the higher positive mean only when more than half of its
   neighbors were profitable.
5. Enter at the 11:01 ask and exit at the 15:30 bid or catastrophe stop.
6. Add the current day and both potential outcomes to memory only after the
   close.

No current or future outcome entered standardization, neighbor selection, or
the decision.

## Walk-forward results

Evaluation: 2021-07-06 through 2026-07-24.

- 1,250 eligible evaluation sessions.
- 804 trades.
- 3.22 trades per week.
- Fixed-$100 P&L: +$27.60.
- Simulated cash account: $100 to $125.23.
- Price-only SPY: $100 to $170.34.
- Profit factor: 1.055.
- Maximum drawdown: -$32.10.
- Average trade: +$0.034.
- Median trade: +$0.094.

Annual P&L:

- 2021 partial: +$7.01.
- 2022: +$16.19.
- 2023: +$6.70.
- 2024: -$2.66.
- 2025: +$8.42.
- 2026 YTD: -$8.06.

Instrument-direction P&L:

- UPRO/bullish selections: +$36.54.
- SPXU/bearish selections: -$8.94.

## Robustness

- Five-minute delayed entry: +$29.57.
- Midpoint diagnostic: +$49.81.
- One extra cent per share at both fills: -$4.29.
- Two extra cents per share at both fills: -$36.17.
- Removing five best trades: -$27.95.

The algorithm was not latency-dependent. Its failure was insufficient
edge-to-cost ratio and poor stability.

## Decision

Reject unchanged.

The model found some repeatable directional information—especially in 2022—but
not enough to:

- survive modest additional execution cost;
- make bearish/SPXU selections profitable;
- remain positive in 2024 and 2026;
- avoid dependence on rare winners; or
- outperform passive SPY.

This is a weak forecasting signal rather than an investable strategy.

The feature family and algorithm were designed after broad exposure to the
historical sample, so even a passing result would still have required future
paper validation.

