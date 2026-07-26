# UPRO/SPXU $100 Intraday Hypothesis Test — Version 1

## Decision

None of the six new hypotheses is ready to trade.

One new candidate, **Second-Auction Ownership Lease**, was profitable in the
2021–2023 development sample and met the required frequency, but it failed two
frozen robustness gates:

- 2021 was negative.
- One additional cent per share of adverse execution at both entry and exit
  changed its result from +$24.16 to -$6.82.

The older **Opening-Center Migration** benchmark passed every development gate,
then lost money in both 2024 and 2025. It therefore also fails as a deployable
system.

These are research results, not evidence that live trading will be profitable.

## Account and execution model

- Starting cash: $100.
- Instruments: buy fractional UPRO for bullish exposure or fractional SPXU for
  bearish exposure.
- Cash-only: no borrowing, short sales, futures margin, or account-level
  leverage.
- Maximum gross position: the lesser of current cash and $100.
- Planned loss cap: position size is also limited to $10 divided by three times
  the SPY signal-to-stop percentage.
- One position and at most one trade per hypothesis per day.
- Entry: observed ETF ask.
- Exit: observed ETF bid.
- No overnight positions.
- Missing or invalid entry quotes cancel the trade; prices are never
  forward-filled.

This is intentionally conservative for a small account. It does not include
broker commissions, payment-for-order-flow effects, fractional-order price
improvement, taxes, or live-order rejection.

## Why this is not a latency strategy

The system never reacts to an individual quote or trade:

- A rule using the completed 09:59 SPY bar enters at 10:01.
- A rule using the completed 10:14 SPY bar enters at 10:16.
- A rule using the completed 14:29 SPY bar enters at 14:31.
- Stops are detected from completed SPY one-minute bars and executed at the
  following minute's ETF bid.
- Extra one-minute and five-minute entry delays were tested.

A proposed fast UPRO/SPXU tracking-error convergence trade was rejected before
testing because one-minute BBO snapshots cannot model the queue, fill
probability, or latency needed to compete with near-zero-latency firms.

## Frozen hypotheses

### 1. Daily Reset Recoil

Hypothesis: the prior SPY close is the anchor around which leveraged exposure
was last reset. If SPY gaps away from that anchor, recoils during the first
half-hour, but cannot cross the prior close, inherited positioning may reassert.

Mechanism:

1. Measure the gap from the prior 15:59 close to the 09:30 open.
2. Require the 09:30–09:59 move to oppose the gap.
3. Require the 09:59 close to remain on the gap side of the prior close.
4. Enter in the gap direction at 10:01.
5. Stop at the prior close; otherwise exit at 15:30.

### 2. Second-Auction Ownership Lease

Hypothesis: opening direction becomes durable only if a distinct second
participant window accepts value beyond the opening auction's center.

Mechanism:

1. Calculate the volume-weighted SPY typical-price center over 09:30–09:59.
2. Require that center and the 09:59 close to be on the same side of the 09:30
   open.
3. Calculate a second center over 10:00–10:14.
4. Require both the second center and the 10:14 close to remain beyond the
   opening center in the original direction.
5. Enter at 10:16.
6. Stop at the opening center; otherwise exit at 15:30.

### 3. Opening Liquidity Seesaw

Hypothesis: directional acceptance is more credible when liquidity improves
relatively in the ETF that must be bought and deteriorates in the opposite ETF.

Mechanism:

1. Require opening-center migration.
2. For UPRO and SPXU separately, divide the 10:00 proportional spread by that
   instrument's median spread over 09:31–10:00.
3. Trade only if the selected directional ETF has the lower relative spread.
4. Enter at 10:01, stop at the opening center, and exit at 15:30.

### 4. Dual-ETF Path Hysteresis

Hypothesis: the sum of UPRO's and SPXU's opening midpoint returns measures
whether the leveraged pair retained value jointly instead of paying a churn
tax. Positive retention might separate clean migration from oscillation.

Mechanism:

1. Require opening-center migration.
2. Add the 09:30–10:00 midpoint return of UPRO to the corresponding SPXU return.
3. Require the sum to be positive.
4. Enter at 10:01, stop at the opening center, and exit at 15:30.

### 5. Reset-Corridor Escape

Hypothesis: the prior close and current opening center are competing definitions
of value. A first-hour traversal of both followed by escape beyond the corridor
may reveal which participant group has control.

Mechanism:

1. Form the interval between the prior SPY close and the opening center.
2. Require the opening range to touch both boundaries.
3. Require the 09:59 close to finish outside the corridor.
4. Trade the escape direction at 10:01.
5. Stop at the opposite corridor boundary; otherwise exit at 15:30.

### 6. Closing Rebalance Torque

Hypothesis: when the full-day and late-afternoon SPY moves agree, leveraged-fund
derivative rebalancing may reinforce the move into the close.

Mechanism:

1. At 14:30, require the prior-close-to-14:29 and
   13:30-open-to-14:29-close moves to be nonzero and have the same sign.
2. Enter at 14:31 in that direction.
3. Stop at the 13:30 SPY open; otherwise exit at 15:55.

## Development results: 2021–2023

All dollars below use fixed $100 notional per trade. “Midpoint” is a
non-executable diagnostic; “BBO” buys at the observed ask and sells at the
observed bid.

| Candidate | Trades/week | BBO P&L | Midpoint P&L | Quoted-spread drag | Profit factor | Gate |
|---|---:|---:|---:|---:|---:|---|
| Daily Reset Recoil | 1.45 | -$7.25 | +$3.62 | $10.87 | 0.950 | Fail |
| Second-Auction Ownership Lease | 2.55 | +$24.16 | +$42.16 | $18.00 | 1.124 | Fail |
| Opening Liquidity Seesaw | 1.94 | -$0.33 | +$14.33 | $14.66 | 0.998 | Fail |
| Dual-ETF Path Hysteresis | 1.34 | -$1.74 | +$7.66 | $9.40 | 0.983 | Fail |
| Reset-Corridor Escape | 1.14 | -$16.16 | -$8.10 | $8.06 | 0.842 | Fail |
| Closing Rebalance Torque | 2.83 | -$7.47 | +$12.77 | $20.24 | 0.950 | Fail |
| Opening-Center Migration benchmark | 2.79 | +$35.22 | +$55.16 | $19.94 | 1.185 | Pass development |

The gate required at least two trades per week, positive observed-BBO P&L,
profit factor above one, positive P&L in every development year and in both
directions, and positive P&L after one extra cent per share of adverse execution
at entry and exit.

## The most interesting new candidate

Second-Auction Ownership Lease produced:

- 398 trades, or 2.55 per week.
- +$24.16 fixed-notional P&L at observed BBO.
- A simulated cash path from $100 to $122.23.
- +$14.75 on bearish signals and +$9.41 on bullish signals.
- +$28.93 with one extra minute of delay.
- +$31.49 with five extra minutes of delay.

But the failure is material:

- 2021: -$5.82.
- 2022: +$28.33.
- 2023: +$1.65.
- One extra cent per share at each fill: -$6.82.
- Removing the five best trades: -$13.78.

This looks like a real but cost-thin 2022 episode, not a stable edge. Under the
frozen protocol it was not allowed to see the 2024–2025 holdout.

## Benchmark holdout: 2024–2025

The older opening-center benchmark passed development, so it was unlocked:

| Execution/stress | Trades/week | P&L | Profit factor |
|---|---:|---:|---:|
| ARCA observed BBO | 2.69 | -$7.17 | 0.933 |
| Midpoint diagnostic | 2.69 | +$4.56 | 1.046 |
| One extra cent per share at each fill | 2.69 | -$26.17 | 0.786 |
| One additional minute delay | 2.53 | -$10.85 | 0.900 |
| Five additional minutes delay | 2.24 | -$8.65 | 0.913 |
| Consolidated observed BBO | 2.65 | -$11.42 | 0.894 |

Observed-BBO P&L was negative in both 2024 (-$5.64) and 2025 (-$1.53). The
simulated $100 cash path ended at $91.64 on ARCA quotes and $87.86 on
consolidated quotes.

The five-session block bootstrap estimated a 67.5% probability that total
holdout P&L was nonpositive, with a 95% interval from -$40.39 to +$25.69. This
does not establish an edge.

## What the failures teach us

1. **The system does not need faster reactions.** Delaying entries by one or
   five minutes did not repair holdout performance. The sought effect must
   persist for hours, not milliseconds.
2. **Gross directional drift is too small.** The benchmark retained only $4.56
   of midpoint P&L over 280 holdout trades. Crossing the quoted spread cost
   approximately $11.74 and changed the sign.
3. **More filters are not automatically better.** Four creative qualifiers
   reduced frequency below the two-trades-per-week constraint without creating
   robust observed-BBO profitability.
4. **The payoff is dependent on rare trend days.** The development benchmark
   changed from +$35.22 to -$4.04 after removing its five best trades.
5. **UPRO/SPXU asymmetry matters.** SPXU is usually the more expensive ETF to
   cross, so a symmetric SPY signal does not create symmetric executable
   economics.
6. **Limit-order assumptions would manufacture an answer.** One-minute BBO data
   cannot establish queue position or whether a resting fractional order would
   fill. Any future test should continue to use marketable fills unless
   higher-resolution trade-and-quote data supports a defensible fill model.

## Research conclusion

The data is sufficient to test non-latency intraday hypotheses and to reject
these versions. It is not evidence that intraday trading is impossible.

The next hypothesis family should demand a much larger expected move per trade,
retain at least two weekly opportunities, and use a predeclared execution-cost
margin rather than merely requiring slightly positive historical P&L. A sensible
minimum standard is that the rule remains profitable after observed BBO costs,
one additional cent per share at both fills, multi-minute delays, removal of its
largest winners, and untouched later-year validation.

