# SPY Official Macro-Release Delayed Discovery — Preimplementation Critique v45

## Frozen hypothesis

On pre-announced U.S. Census economic-release and regular FOMC policy-statement episodes, a direction established during the first ten minutes of observable SPY price discovery persists through the remainder of that release-specific information block.

This is an event-conditioned continuation hypothesis, not an unconditional opening-range breakout or generic same-clock effect.

## Why the mechanism could exist

### 1. Heterogeneous interpretation

Macro releases contain several components, revisions, and interactions with prior expectations. Participants do not necessarily agree immediately on the implications for growth, inflation, rates, and equity risk premia. Fast repricing can establish direction while slower mandates continue reallocating.

### 2. Cash-market participation constraints

An 08:30 release occurs before the equity cash open. Futures and premarket instruments react immediately, but many cash-only portfolios, mutual funds, and benchmark-aware desks express changes after 09:30. The first ten cash minutes may therefore reveal the direction of delayed cash-market absorption.

### 3. Institutional execution horizons

At 10:00 and 14:00, an initial price jump can be followed by staged execution rather than instantaneous completion. Large orders may be split to control impact, creating continuation over tens of minutes or hours.

### 4. Exogenous timing

The event calendar is published independently of SPY returns. Conditioning on official releases gives a stronger causal anchor than selecting ordinary clock windows because they happened to backtest well.

## Exact non-overlapping episodes

Multiple reports sharing the same date and clock form one information episode. Different release clocks on the same date remain separate trades.

| Official release clock | SPY signal window | Entry | Exit | Rationale |
|---|---|---|---|---|
| 08:30 ET | 09:31 to 09:40 | 09:41 | 09:55 | cash-opening interpretation, closed before 10:00 slot |
| 10:00 ET | 10:01 to 10:10 | 10:11 | 13:55 | post-release interpretation, closed before FOMC slot |
| 14:00 ET | 14:01 to 14:10 | 14:11 | 15:30 | policy-statement interpretation into late session |

Signal is the sign of the SPY one-minute close-to-close change across each signal window. Bars use bar-open timestamps: 09:30 to 09:39 for the 08:30 episode, 10:00 to 10:09 for the 10:00 episode, and 14:00 to 14:09 for the FOMC episode. The final close is known at least one minute before entry. Positive selects UPRO; negative selects SPXU; exact zero skips. Entry pays the selected instrument's observed ask and exit receives its observed bid. No magnitude threshold is permitted.

### Pre-return technical correction

The first feasibility implementation established that the ARCA and EQUS leveraged-ETF BBO files contain only UPRO and SPXU, not SPY. It therefore produced zero complete signals without reading any post-entry return. Before target returns were inspected, the signal source was corrected to the locally available ARCX.PILLAR SPY OHLCV-1m bars, with EQUS.MINI SPY OHLCV-1m bars as the independent signal feed. This changes data representation from midpoint to one-minute close but does not alter the mechanism, event dates, direction rule, clocks, entries, exits, or return gates.

## Strongest reasons it may fail

### 1. The information may already be incorporated

For 08:30 releases, futures have one hour to reprice before the cash open. The opening auction and first ten minutes may finish—not begin—the cash adjustment. Continuation after 09:41 may therefore be absent or reverse.

### 2. Ten minutes is late for 10:00 and FOMC releases

The informational edge is likely most valuable in seconds, where this non-HFT design deliberately cannot compete. A ten-minute wait may retain only generic price momentum or adverse selection.

### 3. The 08:30 sleeve has a very short holding period

A 09:41 ask-to-09:55 bid trade has little time to overcome two leveraged-ETF spreads. This sleeve can invalidate the whole mechanism even if longer sleeves look positive.

### 4. Event families are economically heterogeneous

Retail sales, housing, trade, inventories, and FOMC decisions affect equities through different channels. Pooling them may average away real effects. However deleting losing families after seeing results would be prohibited side deletion.

### 5. Direction may depend on surprise, not observed price sign

The rule does not possess point-in-time consensus forecasts or first-release values. Price confirmation is used as a sufficient statistic, but it could select exhaustion rather than persistent information.

### 6. Leveraged inverse ETF drag remains material

SPXU's structural and intraday behavior can impair bearish trades. Both directions must be profitable; a long-only rescue is prohibited.

### 7. Calendar density is only moderately above the cadence floor

Development has 2.476 scheduled episodes/week. Degraded dates, missing quotes, zero signals, or unavailable executions can push actual cadence below two.

### 8. Ex-post archive risk

Historical archive pages report realized release dates, including rescheduling. They are acceptable for identifying when a release actually happened, but this test does not prove that every date was available unchanged far in advance. A passing result would require a live forward calendar process before deployment.

## Why this is not a disguised consumed family

- It is not an unconditional ORB: ordinary non-event dates do not trade.
- It is not same-clock seasonality: the calendar is exogenous and event clocks vary.
- It does not use order-flow imbalance, ES scars, ETF cross-flow, BTC flow, or auction imbalance.
- It does not optimize a return threshold or choose a clock from observed P&L.
- Its principal falsification control is the same clock shifted to the next eligible non-event session.

## Returns-blind falsification requirements

Before target returns may be inspected:

1. at least 95% of scheduled development episodes must have complete ARCX.PILLAR SPY signal bars and complete UPRO/SPXU entry and exit BBOs;
2. executable cadence must remain at least two episodes per calendar week;
3. every development year must retain at least 100 executable episodes;
4. all three release clocks must remain represented;
5. ARCA and EQUS must agree on signal direction at least 75% where both are available;
6. neither direction may represent less than 20% of nonzero signals;
7. every signal endpoint must precede entry, and each exit must precede the next canonical release slot.

## Frozen return controls

If feasibility passes, development must compare the actual event rule with:

- next-session shifted event clocks using the same signal and execution logic;
- direction-flipped trades on the actual calendar;
- unconditional SPY total return over the same development span.

The actual rule must also survive:

- one additional cent at both entry and exit;
- a five-minute entry delay with unchanged exit;
- removal of the ten most profitable trades;
- independent-feed execution during the ARCA/EQUS overlap;
- annual, direction, and release-clock decompositions.

## Prior probability

Moderate-low. Exogenous event timing and institutional execution provide a coherent mechanism, and cadence is sufficient before execution filtering. The strongest threat is that the ten-minute confirmation window captures the end of repricing while spread costs dominate the remaining horizon. The strategy deserves one frozen falsification attempt, not iterative clock or family mining.
