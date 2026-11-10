# SPY Auction Reserve-Liquidity Wedge — Preimplementation Critique v53

## Hypothesis

NYSE Arca's `auct_interest_clr_price` reflects eligible auction-only interest. `ind_match_price` maximizes matched shares subject to collars and includes reserve quantity. Their price difference therefore measures how the broader eligible/hidden liquidity set changes the projected clearing price.

Define at each snapshot:

`wedge = ind_match_price - auct_interest_clr_price`

V53 compares 09:29:00 with 09:29:50:

- both wedges must be nonzero and have the same sign;
- the absolute wedge must be strictly larger at 09:29:50;
- positive widening maps to long UPRO;
- negative widening maps to long SPXU.

The rule contains no magnitude threshold, imbalance sign, quantity, opening gap, reference-price return, or post-auction outcome.

## Institutional mechanism

A widening same-sign wedge means reserve and broader price-setting liquidity are increasingly pulling the projected auction price away from the auction-interest-only clearing level as the uncross approaches. That liquidity is more likely to remain relevant in continuous trading than a one-off auction-only order. The prediction is brief continuation in the wedge direction after the open.

The liquidity providers are reserve/continuous-book participants and auction market makers. The effect should disappear when the wedge contracts, flips, or is fully incorporated before the first delayed order.

## Why this is causally new

- V35's proposed continuous-versus-auction clearing-price test was rejected because `cont_book_clr_price` was sparsely populated. V53 uses two fields populated on virtually every Core Opening.
- V36 used imbalance side versus indicative displacement.
- V37 used reference-price versus indicative-price returns.
- V53 isolates the incremental price contribution of the broader/reserve liquidity set relative to auction-only interest.

## Strongest skeptical response

- Field semantics may not identify beneficial-owner reserve flow or AP activity.
- The wedge may be a deterministic calculation artifact rather than latent demand.
- Widening can be caused by one tick and lose to spread.
- The direction may duplicate the final indication, imbalance side, or opening gap.
- Public participants see the same auction state and may incorporate it before 09:30.
- The 09:29:00 start and 09:29:50 endpoint may be unstable.
- Leveraged wrappers may add tracking noise without adding alpha.

These objections are tested returns-blind and through mandatory controls if P&L is authorized.

## Frozen stability checks

- Early-start variant: 09:28:00 to 09:29:50.
- Late-end variant: 09:29:00 to 09:29:59.

Each must produce at least 60% identical action including cash relative to the primary rule. Neither may replace it.

## Returns-blind gates

1. At least two development signals per week.
2. At least 100 signals per development year and 20 in 2026.
3. Both directions with minority at least 20%.
4. At least two executable development-overlap trades per week, both actuators, and 20% minority.
5. At least 90% complete 1/5/60-second entry-plus-exit evidence.
6. Primary entry wait p95 no more than 30 seconds and every wait no more than 60.
7. Both stability variants at least 60% identical action including cash.
8. Direction agreement below 80% with opening-gap sign, final imbalance side, final indicative/reference displacement, and recent indicative-price movement.
9. Widening selects between 20% and 80% of sessions with valid two-snapshot wedge data.
10. Every signal message arrives before 09:30 and every entry follows it.

## Frozen execution if feasible

- Signal boundary: 09:30:00.
- Entry asks after 09:30:01, 09:30:05, and 09:31:00.
- Primary entry: 09:30:05.
- Exit bid after 09:35:00.
- Fixed $100 fractional long UPRO or SPXU; no margin, shorting, overlap, or overnight.

## Decision

**Pass V53 to returns-blind feasibility only.** Failure locks the wedge definition, clocks, direction, actuators, and gates.
