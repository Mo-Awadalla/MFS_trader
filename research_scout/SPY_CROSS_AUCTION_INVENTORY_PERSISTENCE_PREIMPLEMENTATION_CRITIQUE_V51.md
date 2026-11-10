# SPY Cross-Auction Inventory Persistence — Preimplementation Critique v51

## Hypothesis

The prior session's 15:20 SPY Closing-auction state identifies deadline-bound market-order pressure before the close. When the next session's 09:29:50 Core Opening indicative-price displacement points in the same direction, the overnight dealer inventory transfer has not naturally netted out. Dealers and liquidity suppliers remain exposed in the same direction across two independent auction deadlines and should continue hedging briefly after the Core Open.

Frozen signal:

1. Prior session 15:20 Closing snapshot has positive `market_imbalance_qty` and side B or A.
2. Current session 09:29:50 Core Opening snapshot has positive `ref_price` and `ind_match_price`.
3. `ind_match_price - ref_price` is nonzero.
4. Prior Closing side agrees with the sign of current indicative displacement.
5. Agreement maps to long SPY for positive displacement or long SH for negative displacement.

No quantity magnitude, rolling percentile, opening gap, price bar, final opening imbalance side, or post-auction outcome is used.

## Why a desk might listen

- The mechanism observes actual exchange-published pressure at two distinct institutional liquidity deadlines.
- The previous Closing `market_imbalance_qty` is harder deadline flow than an ordinary volume proxy.
- The next Opening price displacement tests whether the direction survived overnight rather than assuming every imbalance leaves residual demand.
- SPY/SH are selected because the predicted object is underlying dealer hedge pressure, not a leveraged-wrapper lag.
- The rule is threshold-free, causal, and testable at 1/5/60-second delays.

## Relationship to prior failures

- V31 used approximate closing/opening accepted-value anchors from bars; V51 uses actual auction state.
- V34 used only the current final opening imbalance sign and bought UPRO/cash. V51 requires a prior Closing hard-market component, uses current price displacement rather than current side, trades both directions through SPY/SH, and tests cross-auction inventory persistence.
- V41/V42 used within-session growth in Closing market urgency for a pre-close trade. V51 uses the prior Closing state as an overnight inventory condition but opens no position until the next regular session.

V51 is not permission to rescue any of those rules. The exact cross-auction interaction below is frozen once.

## Strongest skeptical response

- An auction clears; the prior market imbalance does not prove dealer inventory was carried overnight.
- Closing and next-opening flow may come from unrelated allocators.
- The current indicative displacement may merely restate the overnight gap.
- Agreement may be a filtered version of failed opening continuation.
- SPY/SH may have too little payoff to survive two marketable crossings on $100.
- Previous-session pressure is a mandatory placebo in auction studies and could outperform spuriously.
- The effect may be incorporated before 09:30.

The signal must therefore be nonredundant to the opening gap, current final side, current displacement-only, and prior Closing-side-only controls. It must survive realistic execution and must beat each simpler control if P&L is ever authorized.

## Returns-blind gates

1. At least two feature signals per declared week in 2021–2023.
2. At least 100 signals in each development year and at least 20 in 2026.
3. Both SPY and SH with minority side at least 20%.
4. At least two executable 2023-overlap trades per week, both actuators, and 20% minority side.
5. Complete 1/5/60-second entry-plus-exit evidence on at least 90% of overlap signals.
6. Primary entry event-wait p95 no more than 20 seconds and every wait no more than 60 seconds.
7. Identical action including cash at least 60% using 09:29:30 and 09:29:59 current-Opening cutoffs.
8. Prior Closing side agreement at least 70% between 15:20 and 15:29:50 on primary-signal sessions.
9. Direction agreement with the opening gap and current final imbalance side each below 80%.
10. Cross-auction agreement selects between 20% and 80% of sessions with valid prior hard-market pressure and current nonzero displacement.
11. Every signal message is received before 09:30:00 and every entry observation follows it.

## Frozen execution if feasible

- Signal boundary: 09:30:00 ET.
- Entry asks after 09:30:01, 09:30:05, and 09:31:00.
- Primary entry: 09:30:05.
- Exit bid after 09:35:00.
- Fixed $100 fractional long SPY or SH.
- No margin, short sale, overlap, or overnight position.
- Maximum event wait 60 seconds; reject crossed/nonpositive quotes.

## Decision

**Pass V51 to returns-blind feasibility only.** A failure is terminal; do not switch agreement to disagreement, change Closing cutoff, change actuators, or relax controls.
