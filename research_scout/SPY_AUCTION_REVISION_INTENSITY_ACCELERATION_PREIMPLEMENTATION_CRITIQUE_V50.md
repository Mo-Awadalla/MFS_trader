# SPY Auction Revision-Intensity Acceleration — Preimplementation Critique v50

## Hypothesis

V50 measures the event-time intensity of official SPY Core Opening indicative-price revisions, not the final imbalance sign or the size of a price move.

Primary windows:

- early: 09:28:00 inclusive to 09:29:00 exclusive;
- late: 09:29:00 inclusive to 09:29:50 exclusive.

Count actual changes in `ind_match_price` within each window. A signal exists when the late revision rate is strictly greater than the early revision rate and the late net indicative-price move is nonzero. Trade the direction of the late move: positive to UPRO, negative to SPXU.

No imbalance quantity, final side, magnitude threshold, rolling percentile, opening gap, bar return, or post-auction outcome enters the rule.

## Institutional mechanism

A burst of late indicative-price revisions means price-setting auction interest is arriving faster as the uncross approaches. When that burst has a net direction, auction liquidity suppliers have less time to reprice or source offsetting interest. The predicted effect is a short continuation of the late price-discovery shock into continuous ETF quoting.

The economic actors are deadline-bound auction participants demanding liquidity and market makers/APs supplying it. The effect should disappear when late revisions are balanced, when revision intensity is not accelerating, or when continuous-market prices incorporate the shock before realistic latency.

## Why this is different

- V34 used a final imbalance sign.
- V35 used paired/unpaired absorption between two snapshots.
- V36 used final price-versus-quantity disagreement.
- V37 compared indicative and reference returns between two snapshots.
- V50 uses the full event path's revision-arrival rate and tests whether intensity acceleration adds information beyond the same late net move.

It is also not a conventional opening-momentum rule: the signal can be absent despite a large net move if revisions are not accelerating.

## Strongest skeptical response

- Message intensity may reflect deterministic exchange publication behavior rather than order arrival.
- Counting price changes can be sensitive to window boundaries and repeated prices.
- The late net move may already be fully incorporated in SPY before 09:30.
- Direction may collapse to the opening gap, early auction momentum, or final imbalance sign.
- A one-minute continuation is slow relative to institutional reaction.
- UPRO/SPXU spread costs may dominate a genuine but tiny SPY effect.
- The historical family is contaminated and any window search would be fatal.

Therefore the windows, strict inequalities, direction map, and gates below are frozen before scanning the message path.

## Returns-blind gates

1. At least two feature signals per declared week in 2021–2023.
2. At least 100 signals in each full development year.
3. At least 20 signals in 2026.
4. Both directions, with minority side at least 20%.
5. Identical action including cash at least 60% for both fixed adjacent window shifts:
   - left: 09:27:50–09:28:50 versus 09:28:50–09:29:40;
   - right: 09:28:10–09:29:10 versus 09:29:10–09:29:59.
6. Primary entry/exit evidence coverage at least 90% over the TBBO overlap.
7. At least two executable development-overlap trades per week, both actuators, and 20% minority side.
8. Entry event-wait p95 no more than 30 seconds and every wait no more than 60 seconds.
9. Direction agreement below 80% with each simpler control: opening-gap sign, early-window net-move sign, and final imbalance side.
10. Acceleration selects between 20% and 80% of sessions with a nonzero late net move.
11. Every defining message is received before the fixed 09:30:00 signal boundary and every simulated order is later.

Failure locks the clocks and conditions without P&L.

## Frozen execution if feasible

- Signal boundary: 09:30:00.
- Entry asks after 09:30:01, 09:30:05, and 09:31:00 (1/5/60 seconds).
- Primary entry: 09:30:05.
- Exit bid after 09:35:00.
- Maximum event wait: 60 seconds.
- Fixed $100 fractional long UPRO or SPXU, one position, no margin, shorting, or overnight holding.

## Alpha requirements if authorized

Preregister first, then report executable ask-to-bid results, spread drag, one-cent stress, fixed-dollar and compounded outcomes, each year/direction, SPY benchmark, best-trade deletion, 1/5/60-second delays, degraded-date sensitivity, and mandatory controls including net-move-only, final-snapshot, shifted session, previous session, reversed sign, intraday permutation, gap-only, momentum-only, randomized actuator-session matching, and trading SPY itself.

## Decision

**Pass V50 to one returns-blind scan.** The mechanism is worth hearing only if intensity acceleration is frequent, stable, nonredundant, and observable before executable orders.
