# UPRO/SPXU Signed Inventory-Flux Persistence — Preimplementation Critique v25

## Scope

This hypothesis uses no futures data, futures signal, futures stop, margin, or
short sale. The sensor and actuator are the long-only UPRO/SPXU pair. SPY is
used only as the passive performance hurdle.

## Hypothesis stated before outcome inspection

A sale of UPRO and a purchase of SPXU both express bearish S&P demand. Invert
the SPXU aggressor sign so last-sale events from both wrappers occupy one common
underlying coordinate.

For each wrapper and each of two non-overlapping event windows—09:30–09:59 and
10:00–10:29 ET:

1. retain only BBO rows whose last-sale exchange timestamp proves the trade
   occurred in that row's one-minute interval;
2. map `B` to +1 and `A` to -1;
3. multiply by last-trade size;
4. divide signed size by total sampled size within that wrapper;
5. invert SPXU and equally average the two wrapper imbalances.

At least five fresh events must exist in every wrapper/block cell. Buy UPRO only
when both block scores are positive; buy SPXU only when both are negative.
Disagreement or an exact zero means cash. The 10:30 interval is completed,
10:30–10:31 is a causal dead minute, entry is the observed 10:31 ask, and exit
is the observed 15:30 bid. Deploy $100, hold one long fractional position, and
make at most one trade per day.

## Would a high-end ETF desk listen?

**Yes, as a sampled metaorder-persistence measurement with an inverse-wrapper
replication channel.**

Raw UPRO activity is ambiguous because sells and buys have opposite inventory
meaning. Raw comparison with SPXU is also invalid because the products have
different prices and activity. V25 first signs the observed trade, projects
both wrappers into the same underlying direction, normalizes each by its own
sampled activity, and then equal-weights the wrappers. Requiring the resulting
flux sign to persist in two disjoint blocks asks whether directional inventory
is being worked through time rather than appearing in one isolated print.

This is not V16's cross-wrapper relay count: temporal adjacency is irrelevant
here and trade size matters. It is not V18's signed-impact asymmetry: no
post-trade quote response enters the signal. The state variable is persistent
signed inventory flux itself.

## Strongest argument that it should work

Institutional orders are commonly sliced. If projected aggressor imbalance has
the same sign in both inverse wrappers and survives a block boundary, the state
has two forms of replication: across products and across time. Equal wrapper
weighting prevents UPRO's activity level from overwhelming SPXU. Continued
execution or dealer hedging can carry the common direction into the afternoon.

## Strongest arguments that it should not work

1. **BBO-1m is a lossy event sampler.** It reports the last sale in each
   interval, not complete signed volume. Multiplying by size does not recover
   omitted trades.
2. **Aggressor side is not investor intent.** A buy-initiated ETF trade may be a
   hedge, arbitrage leg, or liquidity event rather than a directional view.
3. **The two wrappers are not independent.** Shared market makers can create
   apparent replication through the same arbitrage process.
4. **Persistence may mean exhaustion.** Two blocks of one-sided flow can imply
   that the price response is already complete. The continuation sign is frozen
   from the metaorder premise and may not be reversed after results.
5. **Size normalization discards dollars.** It deliberately measures direction
   rather than capital, but a few small prints and a few large prints can still
   dominate sampled imbalance.
6. **Five events is only a measurement floor.** It is not enough for a stable
   structural order-flow estimate; higher cutoffs may not be searched.
7. **Venue composition can flip the state.** ARCA and EQUS.MINI must agree
   before P&L is allowed.
8. **SPXU spread drag and positive equity carry remain severe.** Both sleeves,
   all years, costs, delay, concentration, and SPY outperformance are binding.

## Returns-blind admission gates

- valid four-cell measurement on at least 90% of eligible ARCA sessions;
- at least two nonzero executable signals per calendar week;
- neither direction below 20%;
- at least 100 executable signals in each development year;
- median fresh-event count at least ten in every wrapper/block cell;
- at least 65% same-direction agreement when both feeds signal;
- at least 55% identical action across all common overlap dates, including
  mutual no-trades;
- at least 95% entry-quote availability.

Failure ends the candidate without reading post-entry prices.

## Frozen return gates

Development must have PF above one; positive 2021, 2022, and 2023; positive
UPRO and SPXU sleeves; ending cash above passive SPY; positive P&L after one
extra cent on entry and exit; positive P&L after five extra entry minutes;
positive P&L after deleting the ten best trades; and higher P&L than both the
sign-flipped rule and a single-block-only contrast.

Only a complete development survivor may open 2024–2025. Holdout must pass the
analogous year, sleeve, SPY, cost, concentration, and consolidated-feed gates.
The unchanged rule is then reported separately on available 2026 data.

## Preimplementation decision

**Advance to a returns-blind audit.** The inverse sign map, within-wrapper
normalization, equal wrapper weighting, and cross-block persistence form a
specific measurable object. The last-sale sampling limitation is serious
enough that event coverage and feed invariance decide admission.
