# SH/SPXU Inverse-Leverage Liquidity Curvature — Preimplementation Critique v33

## Frozen hypothesis

SH and SPXU are same-issuer ETFs expressing the same S&P 500 downside factor at
−1× and −3× daily leverage. Their proportional-spread ratio is the market's
secondary-market surcharge for moving from ordinary inverse exposure to
leveraged inverse exposure.

For SH and SPXU separately:

1. calculate each minute's proportional BBO spread,
   `(ask - bid) / ((ask + bid) / 2)`;
2. take its median from 09:45–09:59 ET;
3. take its median again from 10:00–10:14 ET.

For each block define:

`inverse leverage surcharge = median SPXU spread / median SH spread`.

The signal is the change in this surcharge:

- if the surcharge contracts, buy UPRO;
- if the surcharge expands, buy SPXU;
- exact equality, missing windows, or invalid quotes mean cash.

Contraction means the incremental price of warehousing convex downside has
fallen relative to ordinary inverse exposure: dealer risk capacity is
improving, so positive equity carry is the proposed beneficiary. Expansion
means convex downside immediacy is becoming relatively expensive: the
proposed state is deteriorating risk capacity and SPXU exposure.

Entry is the observed 10:16 ask and exit is the observed 15:30 bid. Deploy at
most $100 in one long fractional position. No futures, margin, short sale,
passive-fill assumption, or overnight holding is used.

No absolute spread cutoff, ratio threshold, magnitude rank, price filter,
weekday, volatility state, direction deletion, or clock search is permitted.

## Why an elite ETF desk might listen

The construction is an internal leverage curve rather than a directional price
indicator. Comparing two same-issuer inverse funds controls for the underlying
factor and much of the product plumbing, while the ratio removes their
permanent spread-level difference. The time change asks whether the market is
repricing the *incremental* cost of leveraged downside risk.

This is distinct from:

- v17, which measured the common spread mode of opposite UPRO/SPXU wrappers;
- v28, which measured event latency from SH to SPXU;
- v14, which used price-return residuals across leverage levels.

An ETF desk could plausibly monitor this curve as an execution/risk-capacity
state even if it ultimately contains no directional alpha.

## Hard internal critique

1. **The sign is not guaranteed.** A tighter SPXU spread can reflect greater
   bearish demand and competition among liquidity providers, not benign dealer
   capacity. The frozen sign cannot be inverted after outcomes.
2. **Minimum-tick geometry can dominate.** SH and SPXU trade at different
   prices; proportional spreads reduce but do not eliminate tick discreteness.
3. **Displayed spread is not inventory.** Dealer identities, hedge books, and
   risk limits are unobserved.
4. **One-minute BBO is sampled, not time-weighted.** A median of terminal minute
   quotes may be venue-state noise.
5. **The instruments have different clienteles and AUM.** Ratio changes can
   reflect product-specific orders unrelated to the equity market.
6. **The proposed effect may be contemporaneous only.** Any true risk-capacity
   repricing could already be absorbed by 10:16.
7. **Cross-feed invariance is binding.** A leverage curve that changes sign
   across ARCX.PILLAR and EQUS.MINI is not a market state.
8. **SPXU's execution hurdle remains severe.** Both sleeves, all development
   years, cost stress, and winner deletion must pass.
9. **Similarity to earlier liquidity work is a real concern.** The idea
   advances only because the cross-sectional object—same-side leverage
   curvature—is new. No repair or combination with v17/v28 is allowed.

## Returns-blind admission gates

Before reading any post-10:16 price:

- valid measurements on at least 95% of eligible development sessions;
- at least 12 valid minute spreads per instrument in each 15-minute block;
- at least 2.0 executable signals per calendar week;
- at least 100 executable entries in each development year;
- at least 20% of entries in the minority direction;
- at least 75% same direction when both ARCA and EQUS.MINI signal;
- at least 65% identical action, including joint no-trades, across overlap
  sessions;
- at least 95% selected-ETF entry-quote availability.

Failure stops the candidate without P&L.

## Frozen return gates if admitted

- fixed-$100 P&L positive and profit factor above one;
- positive 2021, 2022, and 2023;
- positive UPRO and SPXU sleeves;
- compounded cash above price-only SPY;
- positive after one extra cent per share at entry and exit;
- positive after a five-minute delayed entry;
- positive after removing the ten best trades;
- outperform the exact sign-flipped rule;
- outperform a same-clock raw SH spread-change control;
- outperform a same-clock raw SPXU spread-change control;
- independently rebuilt EQUS overlap execution positive.

Only a complete development pass unlocks 2024–2025.

## Preimplementation decision

**Advance to a returns-blind audit.** The same-side leverage surcharge is a
coherent ETF-desk object and materially different from prior spread modes, but
tick geometry and venue dependence are serious enough that cross-feed
measurement gates come before any return.
