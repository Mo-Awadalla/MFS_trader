# SPY Closing-Liquidity Memory Reset — Preimplementation Critique v31

## Frozen hypothesis

Two accepted-value anchors coexist during the cash session:

- the prior session's 15:00–15:29 SPY volume-weighted typical-price center;
- the current session's 09:30–09:59 SPY volume-weighted typical-price center.

The first is inherited closing inventory and the second is the new opening
auction's inventory. Merely being above or below either anchor is ordinary
price direction. The proposed information is the **ordered traversal** between
them.

From 10:00 through 13:29 ET, compress consecutive touches of the same anchor
into one visit. Reject a session if a one-minute bar contains both anchors,
because their within-bar order is unknowable. The session signals only when:

1. both anchors have been visited in a definite order;
2. after the second distinct visit, price never revisits the first anchor
   through 13:29;
3. the 13:29 close is on the second anchor's side of the midpoint between the
   anchors; and
4. the completed 13:30 bar does not revisit the first anchor.

The side is the direction from the first visited anchor to the second:

- upward traversal buys UPRO;
- downward traversal buys SPXU.

Entry is the observed 13:31 ask and the time exit is the observed 15:55 bid.
The first-anchor revisit is also the structural invalidation after entry,
executed at the next observed ETF bid. A session can create at most one trade.
The account starts with and deploys at most $100, using fractional shares and no
futures, margin, short sale, or overnight position.

No distance threshold, volatility filter, weekday, magnitude rank, clock
search, side deletion, or parameter fit is allowed.

## Why a high-end ETF desk might listen

An ETF or index desk manages inventory against more than one definition of
fair value. Yesterday's closing transfer and today's opening transfer can leave
different participant groups anchored at different prices. A completed visit
to both anchors followed by failure to return to the first is a causal
ownership claim: the market inspected both inventories, then stopped paying
rent to the first one.

This is not a generic breakout, VWAP attraction rule, or moving-average
signal. The same terminal price can produce opposite actions depending on the
order in which the two independently formed auction centers were visited.
The idea was also recorded before this implementation in
`spy_sh_fractional_hypotheses_results_v1.md` as an untouched successor named
"Closing Liquidity Memory Reset."

## Hard internal critique

1. **It may just relabel momentum.** Ending near the second visited anchor can
   correlate strongly with the preceding price move. If admitted to P&L, the
   frozen rule must beat a same-frequency plain 10:00-to-13:29 direction
   control.
2. **Bar-range touches are coarse.** A minute high/low proves that an anchor
   traded inside the bar, not the exact transaction path. Same-bar dual
   touches are therefore excluded rather than ordered artificially.
3. **Typical-price volume centers are approximations.** One-minute OHLCV does
   not contain the price-level volume distribution. Cross-feed action
   agreement is binding.
4. **The first visit may occur before 10:00.** The state machine deliberately
   begins only after the opening anchor is fully known; it does not infer an
   unobservable earlier sequence.
5. **Absence of a return is censored by the clock.** The 13:29 cutoff is a
   participant handoff, not an optimized duration, but a later revisit could
   still occur.
6. **SPXU has a structurally higher hurdle.** The observed 2021–2025 diagnostic
   found about 6.61 bps of mean SPXU round-trip spread drag versus 2.58 bps for
   UPRO, before inverse-fund decay. Both sleeves must remain positive; no
   bullish-only repair is permitted.
7. **Winner concentration is likely.** A few large trend afternoons can
   dominate a seemingly sound traversal rule. Removing the ten best
   development trades is binding.
8. **A clean story is not alpha.** If frequency, feed invariance, or any
   development gate fails, the rule is rejected unchanged and no inverse,
   midpoint, distance, side, or timing repair is attempted.

## Returns-blind admission gates

Before any post-entry price or P&L is read:

- at least 2.0 executable entries per calendar week in 2021–2023;
- at least 100 executable entries in each development year;
- at least 20% of entries in the minority direction;
- at least 95% 13:31 entry-quote availability;
- at least 85% same direction when both ARCA and EQUS.MINI signal;
- at least 75% identical action, including joint no-trades, across feed-overlap
  dates.

Failure stops the experiment before outcome inspection.

## Frozen development gates if admitted

- positive fixed-$100 P&L and profit factor above one;
- positive P&L in 2021, 2022, and 2023;
- positive UPRO and SPXU sleeves;
- compounded ending cash above price-only SPY;
- positive after one extra cent per share at both fills;
- positive with a five-minute delayed entry;
- positive after removing the ten best trades;
- better mean trade than the same-frequency plain price-direction control;
- independently rebuilt EQUS.MINI signal and execution remain positive.

Only a complete development pass may unlock 2024–2025.

## Preimplementation decision

**Advance to a returns-blind measurement audit.** The state variable is
pre-recorded, causal, parameter-light, and materially distinct from the failed
single-anchor retest and sequential-center migration rules. Its principal risks
are low cadence, bar-level touch ambiguity, and disguised momentum; the frozen
gates directly test those objections.
