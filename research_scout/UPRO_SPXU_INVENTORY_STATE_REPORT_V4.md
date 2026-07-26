# UPRO/SPXU Inventory-State Research

## New economic hurdle

A profitable strategy is no longer sufficient. The simulated $100 cash account
must also finish above a passive fractional SPY position over identical dates.

From the local Databento SPY bars:

- 2021–2023 price-only SPY: $100 to $126.66.
- 2021–2025 price-only SPY: $100 to $181.68.

These figures exclude reinvested SPY distributions, so they are easier hurdles
than true total return.

## Frozen development results

| Candidate | Trades/week | Strategy ending cash | Net P&L | PF | SPY development hurdle | Result |
|---|---:|---:|---:|---:|---:|---|
| Paired Depth Reciprocity | 4.55 | $65.40 | -$28.58 | 0.945 | $126.66 | Fail |
| Depth Migration Torque | 4.73 | $47.68 | -$60.00 | 0.891 | $126.66 | Fail |
| Quote-Size Memory | 4.73 | $107.79 | +$17.82 | 1.035 | $126.66 | Fail |
| Depth-Impedance Relief | 4.73 | $86.66 | +$0.17 fixed-notional | 1.000 | $126.66 | Fail |
| First Synchronization Pulse | 2.74 | **$131.25** | **+$32.18** | 1.087 | $126.66 | Fail robustness |
| Event-Density Acceleration | 3.32 | $92.44 | -$6.56 | 0.979 | $126.66 | Fail |
| Volume-Share Acceleration | 4.73 | $75.01 | -$15.34 | 0.971 | $126.66 | Fail |

No candidate passed every development gate, so 2024–2025 remained locked.

## First Synchronization Pulse

This was the only candidate to beat SPY during development.

The rule inspected three fixed half-hours:

1. 09:30–09:59
2. 10:00–10:29
3. 10:30–10:59

It used the first block in which both UPRO and SPXU printed an ARCA trade bar in
every minute. Inside that synchronized block it calculated each ETF's
volume-time centroid and bought the ETF whose volume mass arrived later. It
still waited until 11:01 to enter.

Results:

- 428 trades, or 2.74 per week.
- Fixed-$100 P&L: +$32.18.
- Simulated cash: $100 to $131.25.
- SPY price-only: $100 to $126.66.
- One-minute delayed entry: +$34.72.
- Five-minute delayed entry: +$39.77.
- Maximum drawdown: -$31.50.

It failed because:

- Bearish trades: -$18.94.
- One extra cent per share at both fills: -$3.37.
- Removing the five best trades: -$4.95.
- SPY outperformance was only $4.59 before dividends.

## Why 2022 matters

The strategy's annual P&L was:

- 2021: +$0.82.
- 2022: **+$29.74**.
- 2023: +$1.62.

Unlike the surrounding years, both directions worked during 2022:

| Year | Direction | Trades | P&L |
|---|---|---:|---:|
| 2021 | Bearish/SPXU | 44 | -$10.26 |
| 2021 | Bullish/UPRO | 39 | +$11.09 |
| 2022 | Bearish/SPXU | 106 | **+$11.91** |
| 2022 | Bullish/UPRO | 119 | **+$17.83** |
| 2023 | Bearish/SPXU | 53 | -$20.59 |
| 2023 | Bullish/UPRO | 67 | +$22.22 |

Thus, the 2022 gain was not only passive bullish drift. It was the sole year in
which the cross-vehicle activity clock worked symmetrically.

However, four of the five best trades occurred during 2022. Removing the five
largest winners erased the entire three-year result. This indicates sensitivity
to rare synchronization shocks rather than a stable everyday premium.

## Timing decomposition

| First complete synchronized block | Trades | P&L |
|---|---:|---:|
| 09:30–09:59 | 371 | -$0.32 |
| 10:00–10:29 | 42 | +$24.93 |
| 10:30–10:59 | 15 | +$7.57 |

Later synchronization was economically different from immediate opening
synchronization. But selecting only later blocks now would leave about 0.37
trades per week and would be a direct after-the-fact repair.

## Lessons

1. Displayed quote size by itself was not predictive. Depth reciprocity,
   migration, memory, and impedance all failed or were too weak.
2. The useful state was a change in participation synchronization, not ordinary
   price direction.
3. A bear calendar year is not sufficient evidence. A robust rule must show
   that bearish and bullish implementations both contributed during that
   regime.
4. Beating SPY requires much more than positive P&L. The five-year price-only
   hurdle is +$81.68 on $100, before dividends.
5. The next family should model the topology of activity masks—when silence
   turns into synchronized participation—without fitting a clock cutoff to the
   profitable later blocks observed here.

## Decision

First Synchronization Pulse is the best clue from this batch, but it is not a
live candidate. It barely beat the easier SPY development hurdle, failed modest
execution stress, and depended on rare 2022 winners.

