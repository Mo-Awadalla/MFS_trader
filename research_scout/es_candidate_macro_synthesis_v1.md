# ES Candidate Macro Synthesis v1

Saved: 2026-07-25

## Research objective

Find intraday ES/MES rules that produce at least two trades per week, preferably near-daily activity, close every position within the cash session, use only the available Databento one-minute OHLCV bars, and survive conservative execution assumptions without parameter mining.

## What the surviving candidates actually share

The common mechanism is **accepted inventory surviving a participant handoff**.

1. **A fixed, economically meaningful anchor is established before entry.**
   - Compressed convexity uses the opening range and its midpoint.
   - Opening center migration uses the 09:30 cash open and the opening auction's volume-weighted center.
   - Midday reload uses the 09:30 cash open as the origin of morning inventory.

2. **Price must demonstrate acceptance, not merely movement.**
   - A completed five-minute close outside a compressed opening range.
   - Both the opening close and volume-weighted auction center migrating to the same side.
   - A lunch counter-move that cannot erase the morning move.

3. **The invalidation is structural.**
   The trade is wrong when price reclaims the anchor or accepted-value center. Stops are not fitted ATR multiples or optimized dollar distances.

4. **The payoff is positively skewed and comes from carrying accepted inventory toward the close.**
   The systems have low win rates and negative median trades. A minority of persistent directional sessions pays for frequent structural invalidations.

5. **The useful information is relational.**
   OHLCV indicators matter when they compare two auctions, two participant regimes, or price versus an anchor. Volume, volatility, topology, or bar shape used alone has repeatedly failed.

This is not evidence for a generic trend-following rule. It is evidence for a narrower hypothesis: when one participant group establishes value and the next group cannot reclaim the prior anchor, inventory can remain one-sided into the closing liquidity window.

## What they do not share

- No robust long-only or short-only effect.
- No stable volatility-regime filter.
- No evidence that the same shape can be copied to arbitrary 30-, 60-, or 90-minute windows.
- No reliable profit from predicting direction from volume or path shape alone.
- No comfortable execution margin: the current three-engine holdout loses money after roughly one additional tick at both entry and exit.

The clock itself is part of the mechanism. The cash open, lunch transition, and close are participant handoffs; equal-length intraday blocks are not interchangeable.

## New preregistered tests completed in this pass

### 1. Three-Auction Value Ladder

Rule: in each of three fixed 90-minute segments, follow three strictly rising or falling 30-minute volume-weighted auction centers; enter after the third auction, stop at the middle center, and exit at 15:55.

Development result: 1,206 trades, 7.731 per week, -$77.42, profit factor 0.998. It lost in 2021 and 2023; longs made $1,578.30 while shorts lost $1,655.72. Only the opening slot was profitable, primarily because of 2022.

Decision: rejected without evaluating 2024-2025.

### 2. Incomplete Counter-Auction Relay

Rule: in each of three fixed 90-minute segments, require an initial 30-minute center migration followed by a counter-migration that remains on the migrated side of the first center. Enter in the original direction, stop beyond the first center, and exit 90 minutes later.

Development result: 322 trades, 2.064 per week, -$136.10, profit factor 0.977. It lost in 2021 and 2023; longs lost $791.79 while shorts made $655.69. Again, only the opening slot was profitable, primarily because of 2022.

Decision: rejected without evaluating 2024-2025.

## Failure-derived conclusions

1. **Do not manufacture frequency by cloning a rule across clock windows.** Both new tests met the frequency requirement, but their apparent diversification was false.
2. **Accepted-value migration needs a real participant boundary.** The repeated 30-minute versions failed even when their shape matched the successful high-level story.
3. **The 2022 opening regime is a recurring false attractor.** Any new rule whose development profit is concentrated in 2022 or the opening slot fails automatically.
4. **Side filters are prohibited.** The two failed families produced opposite side asymmetries, showing how easily a post-hoc directional story could be invented.
5. **The current portfolio remains the benchmark, not a deployable discovery.** It meets the operating-frequency constraint, but its holdout edge is too cost- and tail-sensitive for live capital.

## Brand-new hypothesis queue

These concepts were ranked sequentially to limit multiple testing. Priority 1 has now been tested exactly once; the others remain sealed.

### Priority 1: Overnight-to-Cash Anchor Relay

Economic claim: Globex participants establish an overnight accepted-value center. If the first 30 cash-session minutes move both their volume-weighted center and final close to the same side of the overnight center, the cash participant group has repriced inventory rather than merely opened away from it.

Frozen mechanism for the next test:

- Overnight auction: 18:00 ET on the prior trading evening through 09:29 ET.
- Overnight anchor: volume-weighted mean of one-minute typical price.
- Opening auction: 09:30-09:59 ET.
- Long: opening auction center and 09:59 close are both above the overnight anchor.
- Short: both are below the overnight anchor.
- Entry: 10:00 open plus one adverse tick.
- Stop trigger: opening auction center; stop fill one adverse tick beyond it.
- Exit: 15:30 open plus one adverse tick.
- One MES maximum, one trade per day, no overnight position.
- No distance, volatility, day-of-week, side, or regime filter.

Why it was different: it tested an actual participant handoff unavailable to the two failed equal-clock families.

Result:

- Development 2021-2023: 486 trades, 3.115 per week, +$3,891.63, profit factor 1.366. Every development year and both directions were positive.
- Secondary holdout 2024-2025: 302 trades, 2.904 per week, -$383.97, profit factor 0.952. The long side made $136.48 while the short side lost $520.45.

Decision: rejected. Do not install a long-only filter. The failure suggests that the Globex center is not a stable anchor once the cash participant group forms its own local auction.

### Priority 2: Morning-to-Lunch Anchor Transfer

Economic claim: a closing-session edge may exist when lunch accepts a new value center relative to the entire morning auction, not when a small counter-shape happens inside an arbitrary block.

Sealed concept:

- Morning auction: 09:30-11:29; lunch auction: 11:30-13:29.
- Compute a volume-weighted center for each.
- Long if the lunch center and 13:29 close are both above the morning center; short if both are below.
- Enter 13:30, stop beyond the lunch center, exit 15:55.
- Symmetric rules, one MES, no magnitude thresholds.

This should be tested only if Priority 1 fails its development gates.

### Priority 3: Opening Acceptance With Closing-Participation Confirmation

Economic claim: early acceptance is more credible when volume participation migrates with price rather than when price alone escapes. This is not a raw volume-direction rule; it asks whether the higher-volume half of the opening auction is also the later, directionally accepted half.

Sealed concept:

- Split 09:30-09:59 into two fixed 15-minute auctions.
- Require the second center and 09:59 close to be on the same side of the first center.
- Require second-half volume to exceed first-half volume.
- Enter 10:00 in the migration direction, stop beyond the first-half center, exit 15:30.
- No volume ratio or distance threshold beyond the natural greater-than comparison.

This remains third priority because the added volume condition increases researcher degrees of freedom and may reduce frequency below the required floor.

## Anti-overfitting protocol

1. Test one queued family at a time on 2021-2023 only.
2. Require at least two aggregate trades per week, positive P&L in every development year, positive P&L on both sides, and no single clock component contributing more than total profit while others lose.
3. Freeze exact rules before every first run.
4. Do not rescue failures with side, year, day-of-week, volatility, or clock filters.
5. Evaluate 2024-2025 only after every development gate passes, and label it secondary because those years have already informed the broader research program.
6. Demand profitability after an additional $1.25 per trade, a positive result after removing the five best trades, and a five-day block-bootstrap probability of loss below 20% before considering anything beyond paper trading.
7. The cleanest next evidence remains untouched 2026-forward MES executable quotes and fills.

## Current decision

No new candidate from this pass is accepted. Continue paper tracking of the unchanged three-engine benchmark. The Overnight-to-Cash Anchor Relay is rejected after its secondary holdout. Do not rescue it with a side filter, and do not immediately test the two remaining sealed ideas in the same research pass.
