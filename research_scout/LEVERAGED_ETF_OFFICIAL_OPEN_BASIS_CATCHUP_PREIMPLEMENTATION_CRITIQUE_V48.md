# Leveraged-ETF Official-Open Basis Catch-Up — Preimplementation Critique v48

## Chronology and novelty

V48 is the first new cash-only cycle after the accepted V1–V47 audit history. It does not use futures, options, borrowed instruments, or a repaired rule from an earlier candidate.

Two alternatives were rejected before measurement:

- A late SPY imbalance-side-flip rule was too close to V36's price/quantity disagreement and would invite another cutoff search.
- "Successful absorption with sticky indicative price" was the logical complement of sparse V35 and would be a condition inversion after seeing V35 feasibility.

V48 instead uses official ARCX Core Opening prices for the complete 1×/2×/3× long and inverse ETF ladder. V40 used official opening **quantities** and relative long-versus-inverse participation. V48 uses cross-leverage **prices** and a trailing self-normalized tracking basis. Earlier minute-BBO leverage geometry did not observe synchronized official auction outcomes.

## Economic hypothesis

The 3× ETFs are thinner and more inventory-sensitive than SPY and the 1×/2× products. At the opening uncross, a 3× ETF can print behind the leverage-scaled price discovery already expressed by its lower-leverage ladder. Once continuous quoting begins, authorized participants and market makers can hedge the 3× wrapper against the more liquid lower-leverage products, causing the lagging 3× price to catch up.

For each session, use the previous eligible ARCX official close and current ARCX official Core Opening price.

Long ladder:

`positive_basis = median(SPY overnight return, SSO overnight return / 2) - UPRO overnight return / 3`

Inverse ladder:

`negative_basis = median(-SPY overnight return, SH overnight return, SDS overnight return / 2) - SPXU overnight return / 3`

Each basis is compared with its own trailing 20-eligible-session median, using prior sessions only.

- Buy UPRO when SPY, SSO, and UPRO all opened higher and the positive basis is strictly above its trailing median.
- Buy SPXU when SPY opened lower, SH/SDS/SPXU all opened higher, and the negative basis is strictly above its trailing median.
- Otherwise remain in cash.

The direction is necessarily aligned with the overnight move, but the defining selection variable is not the gap: it is an unusually lagging 3× official auction price relative to a lower-leverage consensus and its own recent basis.

## Why an institutional ETF desk might listen

1. The rule measures a concrete wrapper-arbitrage state at an official auction.
2. Lower-leverage products are more liquid price-discovery instruments and form a causal hedge consensus.
3. Trailing basis centering absorbs persistent financing, tracking, and product-specific differences without fitting a return threshold.
4. The predicted liquidity takers are post-open arbitrageurs buying the lagging 3× wrapper while hedging in SPY or lower-leverage ETFs; the simulated account takes only the permitted long cash-ETF leg.
5. The effect should disappear when opening auction liquidity is sufficient, when the 3× price is not behind its own recent basis, or when convergence is already complete before realistic latency.
6. Exact 1-, 5-, and 60-second delays can falsify whether this is merely simultaneous repricing.

## Strongest skeptical desk response

- This may be opening-gap continuation with extra arithmetic.
- Official ARCX opening prices are venue outcomes, not NAV or a consolidated fair value.
- Leveraged ETF overnight returns contain financing, distributions, and path-independent tracking differences that a short rolling median may not remove.
- A positive residual may be below one tick or spread and therefore economically meaningless.
- Market makers may eliminate any genuine basis discrepancy before a non-colocated order can arrive.
- The trade-event-conditioned EQUS.MINI feed may miss the standing quote needed to distinguish a stale quote from a missing event.
- Comparing two leverage ladders after many historical wrapper studies carries severe familywise contamination.

These objections are binding tests. V48 must beat a matched opening-gap-only control, trading SPY itself, a one-session-shifted basis, a randomized session match, and lower-leverage alternatives. It must survive observed asks/bids, one cent per share adverse execution, and 1/5/60-second delays. If the gap-only control explains the result, the institutional story fails.

## Frozen data and integrity rules

1. Use only ARCX `OPENING_PRICE` and `CLOSE_PRICE` statistics for SPY, SSO, UPRO, SH, SDS, and SPXU.
2. Require exactly one positive opening and closing statistic per symbol/session.
3. Previous close means the immediately preceding complete eligible session for that symbol.
4. Exclude the union of ARCX and EQUS degraded dates from primary results.
5. Exclude a session from signal construction and rolling history if any absolute raw close-to-open return exceeds 25%; this fixed integrity cap is for splits/corporate actions, not alpha selection.
6. Use the trailing 20 eligible basis observations; current-session values never enter their own baseline.
7. Ten- and 40-session baselines are adjacent stability diagnostics, not selectable alternatives.
8. The signal becomes observable at 09:30:01 ET only if all six opening statistics were received before that boundary.

## Returns-blind gates before P&L

1. At least 2.0 feature signals per declared week in 2021–2023.
2. At least 100 feature signals in each complete development year after warm-up.
3. Minority actuator at least 20% and both UPRO/SPXU represented.
4. At least 20 signals in the 2026 temporal extension.
5. Signal selection between 20% and 80% of otherwise eligible warm sessions.
6. Identical action including cash at least 70% under both 10- and 40-session baselines.
7. Absolute correlation between SPY gap magnitude and basis excess below 0.80.
8. Every selected opening statistic unique, positive, and received before 09:30:01.
9. Exact entry/exit evidence coverage at least 90% after extracting first valid TBBO asks/bids at signal time plus 1, 5, and 60 seconds and the fixed exit.
10. At least two executable development trades per week, both actuators, and 20% minority side.
11. Relevant-side 1×/2×/3× quote evidence on at least 80% of executable sessions.
12. No causal timestamp violation and maximum event wait of 60 seconds.

## Frozen execution if every gate passes

- Signal availability boundary: 09:30:01 ET.
- Entry delays: first valid trade-event pre-trade ask after 09:30:02, 09:30:06, and 09:31:01.
- Primary delay: 5 seconds (09:30:06).
- Exit: first valid trade-event pre-trade bid after 09:35:00.
- Maximum event wait: 60 seconds.
- Fixed $100 fractional long UPRO or SPXU; no overlap, margin, shorting, or overnight holding.
- Reject nonpositive or crossed quotes.
- No stop; same-day maximum holding time is under five minutes.

## Decision

**Pass exactly one V48 specification to returns-blind feasibility.** No return, exit bid, or P&L is authorized until every gate above passes and a preregistration JSON is frozen.
