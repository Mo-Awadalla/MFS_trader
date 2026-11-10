# BTC Spot Asia–Europe Flow Baton to UPRO/SPXU — Preimplementation Critique v26

## Scope

The signal uses Binance **spot** BTCUSDT klines only. No crypto futures,
perpetuals, funding, margin, or derivatives enter the rule. The position is a
$100 long fractional holding of UPRO or SPXU, with no short sale and no
overnight ETF exposure. SPY supplies only the passive hurdle.

## Hypothesis stated before outcome inspection

BTC spot is a continuously traded risk-transfer venue while U.S. equities are
closed. Split each equity overnight into two disjoint participant cohorts in
America/New_York time:

- **Asia baton:** prior trading day 16:00 through current day 00:59;
- **Europe baton:** current day 01:00 through 08:59.

For every 30-minute BTC spot bar, signed taker quote flow is:

`2 * taker_buy_quote_volume - total_quote_volume`.

Within each cohort, divide summed signed flow by summed quote volume. This
produces a scale-free taker imbalance in [-1, +1].

- If both cohort imbalances are positive, buy $100 fractional UPRO at the
  observed 09:31 ask.
- If both are negative, buy $100 fractional SPXU.
- If signs disagree or either is exactly zero, hold cash.

Exit at the observed 15:30 bid. There is one position and at most one trade per
equity session.

## Would a high-end systematic or ETF desk listen?

**Yes, as a cross-time-zone information-handoff experiment.**

The novel object is not BTC return. It is whether aggressive spot capital keeps
the same direction as control passes between two non-overlapping overnight
participant cohorts. A persistent sign is consistent with a global risk
allocation being worked through a market that never closed. U.S. equities then
provide a separate venue in which delayed risk transfer may continue.

Using normalized taker quote flow matters. It observes aggressor direction and
dollar activity directly, unlike unsigned ETF volume. Dividing by each
cohort's own total activity prevents the more active time zone or BTC's changing
price level from mechanically dominating.

## Strongest argument that it should work

Material macro information released outside U.S. hours must first trade
somewhere. BTC spot is open, liquid, and sensitive to global dollar liquidity
and risk appetite. Same-signed aggressive flow in successive geographic clocks
is harder to attribute to one local burst. If the state represents a persistent
global allocation rather than a crypto-only event, U.S. equity inventory can
adjust after its cash open in the same direction.

## Strongest arguments that it should not work

1. **BTC is not an S&P future.** Crypto-specific liquidations, regulation,
   exchange news, and token flows can be orthogonal or opposite to equities.
2. **The relationship is regime-dependent.** BTC's equity beta changed
   materially between 2021, the 2022 deleveraging, and later institutional
   adoption.
3. **One venue is not the world.** Binance spot taker flow can reflect
   venue-specific stablecoin and regional activity.
4. **The signal may be stale by 09:31.** U.S. premarket trading can absorb the
   information before the cash open.
5. **Taker flow can be absorption, not continuation.** Aggressive buying that
   fails to move BTC may predict reversal. The continuation sign is frozen and
   cannot be inverted after outcomes.
6. **Time-zone labels are approximate.** Fixed New York windows straddle
   daylight-saving changes and do not identify trader geography.
7. **Cross-asset effect size may be smaller than wrapper spreads.** Correct
   direction alone is insufficient for UPRO/SPXU execution.
8. **No independent BTC feed exists locally.** Internal flow/price coherence is
   a measurement check, not a substitute for venue replication.
9. **The historical equity sample is heavily researched.** A survivor remains
   a paper candidate requiring genuinely new forward validation.

## Returns-blind admission gates

Before reading any post-09:31 ETF price:

- complete 30-minute BTC coverage on at least 98% of eligible equity sessions;
- at least two nonzero executable signals per calendar week;
- neither UPRO nor SPXU below 20% of signals;
- at least 100 executable signals in each development year;
- within each cohort, the BTC return sign must agree with that cohort's taker
  imbalance sign on at least 52% of measured sessions;
- at least 95% ARCA entry-quote availability;
- at least 95% EQUS entry-quote availability on its overlap.

The 52% requirement is deliberately modest: it only asks whether the signed
flow measure has the expected contemporaneous orientation in its own market.
Failure ends the candidate without ETF P&L.

## Frozen return gates

Development must have PF above one; positive 2021, 2022, and 2023; positive
UPRO and SPXU sleeves; ending cash above passive SPY; positive fixed-$100 P&L
after one extra cent on both fills and after five extra entry minutes; positive
P&L after deleting the ten best trades; and higher P&L than:

1. the exact sign-flipped rule;
2. a BTC price-only persistence contrast using the same two windows; and
3. a single-Europe-block taker-flow contrast.

Only a complete development survivor may open 2024–2025. Holdout must pass the
analogous year, sleeve, SPY, cost, delay, remove-best-five, and consolidated
execution gates. The unchanged rule is not extended past 2025 because the local
spot sensor ends on 2025-12-31.

## Preimplementation decision

**Advance to a returns-blind feasibility audit.** A 24/7 signed spot-flow baton
is independently observed, economically interpretable, and unrelated to the
exhausted intraday ETF geometry families. Its lack of a second BTC venue and
potential crypto-specificity make the own-market coherence and cross-year
gates essential.
