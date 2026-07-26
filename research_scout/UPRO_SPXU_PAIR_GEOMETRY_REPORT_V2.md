# UPRO/SPXU Pair-Geometry Research

## Purpose

This batch deliberately abandoned gap continuation, moving averages, opening
breakouts, RSI-style conditions, and closing-rebalance stories. Signals were
derived from the internal geometry of the leveraged/inverse ETF pair:

- volume treated as a clock;
- quoted spread treated as frictional work;
- same-direction movement of inverse ETFs treated as a mirror failure;
- price-path straightness treated as inventory-transfer efficiency;
- unmatched new highs and lows treated as path topology;
- tracking error treated as creation/redemption pressure; and
- volume-weighted price treated as gravitational displacement.

Every rule compressed 90 morning minutes into one decision, waited until 11:01,
and exited by 15:30. There was no sub-minute reaction or assumed passive fill.

## Frozen development results

Period: 2021–2023. P&L uses $100 per trade, buying at the observed ask and
selling at the observed bid.

| Hypothesis | Trades/week | BBO P&L | Midpoint P&L | PF | Result |
|---|---:|---:|---:|---:|---|
| Late Volume Clock | 1.20 | +$43.70 | +$52.47 | 1.251 | Failed frequency only |
| Friction-Work Acceleration | 1.20 | -$42.28 | -$32.02 | 0.805 | Failed |
| Same-Sign Anomaly Ledger | 1.30 | -$31.09 | -$19.91 | 0.762 | Failed |
| Oriented Path Tortuosity | 4.72 | -$41.37 | -$5.68 | 0.923 | Failed |
| Unmatched Record Topology | 4.02 | +$20.29 | +$49.92 | 1.050 | Failed robustness |
| Creation/Redemption Residual | 4.73 | -$59.38 | -$20.75 | 0.893 | Failed |
| Volume-Price Gravity Tilt | 1.20 | -$64.25 | -$55.24 | 0.722 | Failed |

No rule passed all preregistered development gates, so none was allowed to
access 2024–2025.

## Interesting failure 1: Late Volume Clock

For each ETF, the rule calculated:

`sum(minutes since 09:30 × volume) / sum(volume)`

It bought the ETF whose volume center of mass occurred later.

On 187 sessions with uninterrupted 90-minute ARCA trade bars:

- 1.20 trades per week;
- +$43.70 observed-BBO P&L;
- +$28.72 after one extra cent per share at both fills;
- +$55.50 with five additional minutes of entry delay;
- +$13.40 after removing the five best trades;
- positive in 2021, 2022, and 2023;
- positive in both directions.

It failed only the required two-trades-per-week frequency gate.

## Preregistered sparse-event continuation

A follow-up was frozen before calculation. Missing ARCA trade bars were treated
as zero-volume minutes rather than fabricated prices. This retained the same
score and sign while allowing ordinary sparse-trading mornings.

Results:

- 738 trades, or 4.73 per week;
- -$21.07 observed-BBO P&L;
- +$13.35 midpoint diagnostic;
- -$81.32 after one extra cent per share at both fills;
- -$5.00 with a five-minute delay;
- -$55.52 after removing the five best trades;
- simulated cash path from $100 to $72.97.

Year P&L was -$22.29 in 2021, +$5.26 in 2022, and -$4.03 in 2023. Bullish
signals made +$37.19, while bearish signals lost -$58.25. Selecting only bullish
signals now would be an explicitly prohibited after-the-fact repair.

The complete-window result therefore appears to identify a rare high-activity
market state. It cannot simply be generalized to normal days.

## Interesting failure 2: Unmatched Record Topology

This rule counted cases in which UPRO made a new morning high without SPXU
simultaneously making its theoretically matching low, and vice versa.

It met the frequency constraint and made +$20.29 at observed quotes, but:

- midpoint P&L was +$49.92, showing large spread drag;
- one extra cent per share at both fills changed P&L to -$31.24;
- removing the five best trades changed P&L to -$14.32;
- 2021 was -$11.03;
- bearish signals were -$17.64.

This is a geometric clue, not an executable edge.

## What this changes

The useful distinction is no longer “momentum versus mean reversion.” The data
suggests three different clocks:

1. **Clock time:** the ordinary 09:30–16:00 session.
2. **Event time:** when each ETF's actual traded-volume mass arrives.
3. **Liquidity time:** whether the quoted spread can absorb the expected move.

The rare complete-volume-clock state aligned all three and looked promising.
Extending the signal to ordinary event-sparse days destroyed the result.

That does not justify fitting a minimum-volume, centroid-distance, direction, or
spread threshold. Doing so after seeing these outcomes would overfit precisely
the state we discovered.

## Decision

No strategy from this batch should be traded. The batch did, however, produce a
new research object: **cross-vehicle clock synchronization**. A legitimate next
test would require a newly frozen definition using a different sample or fresh
future data. The current history should not be mined for the cutoff that turns
the rare complete-clock subset into a two-trades-per-week rule.

## User-requested 2024–2025 curiosity check

After Late Volume Clock failed the frozen development frequency gate, the user
explicitly requested that its locked years be opened for curiosity. This is an
exploratory result, not clean validation.

Using the exact unchanged rule:

- 115 trades, or 1.11 per week;
- +$11.83 fixed-$100 observed-BBO P&L;
- simulated cash account from $100 to $107.51;
- 2024: -$6.11;
- 2025: +$17.94;
- consolidated-BBO P&L: +$11.60;
- one extra cent per share at both fills: +$5.09;
- two extra cents per share at both fills: -$1.65;
- five-minute delayed entry: +$8.93;
- maximum fixed-notional drawdown: -$28.33;
- P&L after removing the five best trades: -$48.22.

The five-session block bootstrap assigned a 41.9% probability to nonpositive
total P&L and produced a very wide 95% interval of -$57.03 to +$103.26.

The positive total is interesting because it survived feed and latency checks,
but it was concentrated in 2025, bullish trades, and a handful of winners. It
does not repair the frequency failure or establish a stable live edge.
