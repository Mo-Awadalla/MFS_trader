# UPRO/SPXU Cross-Inverse Aggressor Relay — Preimplementation Critique v16

## Hypothesis stated before outcome inspection

UPRO and SPXU are two wrappers around opposite daily S&P 500 exposure. Map the
last trade in UPRO to its observed aggressor sign and invert the sign of the last
trade in SPXU. After this projection, a buy-initiated UPRO trade and a
sell-initiated SPXU trade both express bullish underlying demand.

During 09:45–10:14 ET, retain only last trades whose exchange timestamp proves
that they occurred in the corresponding one-minute BBO interval. Order these
fresh events by exchange time. A **relay** occurs when adjacent events:

1. come from different wrappers;
2. are no more than two minutes apart; and
3. have the same projected underlying sign.

The session score is the sum of the projected signs of all relays. A positive
score forecasts persistent bullish inventory transfer; a negative score
forecasts persistent bearish inventory transfer. A zero score produces no
trade. The intended implementation enters UPRO or SPXU after the signal window
and exits intraday.

This is not ordinary one-instrument order-flow imbalance. The claimed
information is the *transmission of an aggressor sign across inverse wrappers*.
The second ETF acts as a control channel that must independently express the
same underlying direction.

## Would a high-end ETF desk listen?

**Yes, as a research hypothesis—not as a production recommendation.**

The potentially interesting element is the natural sign inversion. ETF-specific
retail activity, displayed-depth noise, and quote-management noise need not
propagate into the inverse wrapper with the same projected underlying sign.
Underlying metaorders or shared dealer hedging pressure can. This creates an
identified cross-instrument confirmation object using fields that exist in the
current data.

It is also distinct from the failed Paired Depth Reciprocity strategy:

- that strategy used displayed bid and ask sizes;
- this strategy ignores displayed depth;
- it uses timestamp-verified aggressor-side events;
- it requires temporal transmission across wrappers rather than simultaneous
  book states.

## Strongest argument that it should work

Institutional orders commonly execute as sequences rather than isolated prints.
Demand arriving through one leveraged wrapper can be hedged or expressed in the
other wrapper by market makers and arbitrageurs. If the next fresh aggressor
event in the inverse wrapper has the same projected S&P sign, wrapper-specific
noise has acquired cross-product confirmation. A signed excess of these relays
may identify the direction in which inventories are still being transferred.

The signal aggregates thirty minutes and targets a multi-hour hold. It therefore
does not claim that a one-minute sampled trade beats a colocated arbitrageur.

## Strongest arguments that it should not work

1. **The BBO record is a lossy sampler.** It contains the last sale in each
   interval, not every trade. A relay count is a sampled-event statistic, not
   complete signed volume.
2. **Last-sale fields can be forward-filled.** A record is invalid as a trade
   event unless `ts_event` lies inside its own one-minute interval. Failing this
   check would repeatedly count an old trade.
3. **The economic response may already be complete.** Cross-wrapper arbitrage
   and hedging are fast. A confirmed relay could mark completed price discovery,
   not persistent inventory.
4. **Venue composition can manufacture the result.** ARCA and EQUS.MINI observe
   different event sets. If the sign changes across feeds, the proposed latent
   state is not measured robustly.
5. **The side field is easy to misread.** Databento defines `B` as a
   buy-initiated last trade and `A` as a sell-initiated last trade. SPXU must be
   inverted exactly once.
6. **Adjacent-event pairing is not causal proof.** Two trades within two minutes
   can share a market cause without one causing the other. “Relay” is shorthand
   for temporal confirmation, not a structural causal estimate.
7. **SPXU costs are asymmetric.** Even a valid bearish forecast can fail as a
   $100 fractional-share implementation because SPXU's spread is materially
   wider.
8. **Bull-market drift can create apparent success.** Both projected directions,
   every development year, and an untouched holdout must contribute. Beating
   fixed-notional P&L is insufficient; the compounded account must beat passive
   SPY over the same span.

## Returns-blind admission gates

Before any post-entry price or P&L is read:

- at least 95% of eligible sessions must have valid paired quote coverage;
- nonzero signals must occur at least twice per calendar week;
- neither direction may be less than 20% of nonzero signals;
- the median session must contain at least ten relays;
- on the 2023-03-28–2025-12-31 feed overlap, at least 60% of dates on which both
  feeds signal must have the same direction;
- at least 50% of all overlap dates must produce the same action, including
  mutual no-trades.

These are measurement gates, not alpha gates. Failure means no return backtest.
Passing means only that the quantity is measurable often enough to justify a
frozen development test.

## Preimplementation decision

**Advance only to the returns-blind feasibility audit.** The mechanism is
specific, uses an untested field, has a direction fixed by construction, and is
not a relabeled failed strategy. It is not yet admitted to a P&L backtest.

