# SPY Sequential Auction Barycenter Lease — Preimplementation Critique v24

## Lineage

“Delayed Ownership Lease” was recorded as an untouched next hypothesis in the
SPY/SH v1 report before this test. V24 freezes that idea exactly and changes
only the actuator from unlevered SPY/SH trade bars to observed UPRO/SPXU BBO.
No historical return from this rule has been inspected.

## Hypothesis stated before outcome inspection

Treat 09:30–09:59 and 10:00–10:29 as two disjoint participant cohorts. For each
block, compute the volume-weighted mean of one-minute typical price
`(high + low + close) / 3`.

- Bullish: the first center is above the 09:30 cash open, the second center is
  above the first, and the 10:29 close is above the second center.
- Bearish: reverse every inequality.
- Otherwise: cash.

The second cohort is said to “lease” ownership from the opening cohort only
while price remains beyond the first center. Observe the complete 10:30 dead
minute; cancel if it touches the first center. At 10:31 buy $100 of fractional
UPRO for bullish or SPXU for bearish exposure at the observed ask. Exit at the
observed bid one minute after a completed SPY bar touches the first center, or
at 15:30 if no invalidation occurs. One position and at most one trade per day.

## Would a high-end ETF desk listen?

**Yes, because the state is a transfer between independently formed volume
barycenters, and it has a direct falsification test.**

A price return can be produced by a thin endpoint. A volume center requires
traded activity to migrate. Requiring a second, non-overlapping center to move
farther and its terminal print to remain beyond that center asks whether
accepted value is being handed from the opening auction to the next participant
cohort. The first center is not an arbitrary stop: returning through it means
the second cohort no longer controls value.

UPRO/SPXU is an economically motivated actuator. The earlier unlevered
opening-center translation had a small gross effect that could not pay
ordinary SPY/SH friction. A three-times wrapper can amplify the same underlying
move, but only observed ask-to-bid execution is credited.

## Strongest argument that it should work

Successive centers use disjoint volume, so the second migration cannot be
caused by the same opening prints. The terminal-close condition prevents a
large early print from moving the second center while price has already
rejected it. Persistent accepted-value migration is consistent with a
metaorder or dealer hedge being transferred across cohorts and continuing into
the afternoon.

## Strongest arguments that it should not work

1. **It may be smoothed momentum.** Volume weighting and cohort language do not
   prove information beyond the 10:29 price return.
2. **ARCA volume may not represent market-wide accepted value.** A serious
   result requires high signal agreement when rebuilt from EQUS.MINI bars.
3. **The 30-minute partition is conventional.** It is inherited from the
   previously documented hypothesis, not estimated, but other partitions could
   behave differently and may not be searched.
4. **The first center can be a wide stop.** Full-$100 exposure has no fixed
   dollar loss cap beyond the structural invalidation.
5. **Leveraged wrappers add tracking and spread drag.** SPXU in particular may
   destroy an otherwise symmetric signal.
6. **The dead minute may remove precisely the fastest reversals.** That is
   intentional causal discipline, but it can lower frequency.
7. **Close-carry can be tail-dependent.** Winner deletion is mandatory because
   the known scar and three-engine futures families depended on rare trends.
8. **The broader sample is heavily researched.** A historical survivor is a
   paper candidate, not proof of a live edge.

## Returns-blind admission gates

Before any post-entry ETF price is read:

- at least two executable development entries per calendar week;
- at least 95% valid ARCA entry-quote availability;
- neither direction below 20%;
- at least 100 executable entries in each development year;
- at least 85% same-direction agreement when both ARCA and EQUS.MINI signal;
- at least 75% identical action across all common eligible overlap dates,
  counting mutual no-trades.

Failure ends the candidate without P&L.

## Frozen return gates

Development must have PF above one; positive 2021, 2022, and 2023; positive
UPRO and SPXU sleeves; ending cash above passive SPY; positive P&L after one
extra cent on both fills; positive P&L with five extra entry minutes and
stale-state cancellation; positive P&L after deleting the ten best trades; and
higher mean P&L than both an exact sign-flipped placebo and a price-only
two-block momentum contrast using the identical clocks.

Only a complete development survivor may open 2024–2025. Holdout must pass the
analogous year, side, SPY, cost, delay, remove-best-five, consolidated execution,
and mechanism-contrast gates. The unchanged rule is then reported separately
on 2026 YTD if matching signal and execution data exist.

## Preimplementation decision

**Advance to a returns-blind audit.** The state is independently measurable on
two feeds, its direction and stop follow from the ownership-transfer premise,
and it was documented before implementation. It remains vulnerable to being
ordinary momentum in disguise; the price-only contrast is binding.
