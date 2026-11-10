# Treasury Dealer Dollar-Years Overhang Critique v66

## Frozen hypothesis

For every official Treasury auction:

1. Calculate dealer takedown share as
   `primary_dealer_accepted / comp_accepted`.
2. Form a like-for-like bucket from security type, reported security term,
   floating-rate flag, and inflation-index flag.
3. Subtract the dealer share at the immediately preceding auction in the same
   bucket.
4. Calculate rate-exposure years from issue date to maturity date. For
   floating-rate securities use 0.25 years, reflecting quarterly reset rather
   than legal maturity.
5. Define unexpected dealer dollar-years as:

   `(dealer_share - prior_like_for_like_dealer_share)
    × comp_accepted × rate_exposure_years`

6. Sum the value across all auctions on the official auction date.
7. Map it to the first SPY session strictly after the auction date. If more
   than one auction date maps to that session, sum again.
8. Positive overhang selects SPXU; negative overhang selects UPRO; exact zero
   is cash.
9. Prospectively buy the selected ETF at the exact 09:33 ask and sell at the
   exact 15:30 bid, using fixed $100 notional and fractional shares.

There is no magnitude threshold, price confirmation, volatility filter,
weekday rule, security-type deletion, stop, or fitted coefficient.

## Why a serious desk could investigate it

Treasury auctions are scheduled primary-market inventory transfers. A rise in
Primary Dealer awards relative to the previous comparable auction means dealer
balance sheets absorbed more supply than end-investors did. Weighting that
surprise by accepted face amount and years of rate exposure translates many
security types into a single transparent inventory-pressure unit.

If dealers distribute or hedge unexpected duration after the auction, rates
can remain under pressure into the next cash session. Through the discount-rate
channel, positive dealer overhang maps to equity weakness; unusually low dealer
absorption maps to equity strength.

Unlike prior generic bond/equity return rules, this feature starts with a
specific primary-market allocation event and a known inventory holder.

## Internal attack

### 1. Dealer awards need not remain dealer risk

Dealers can pre-hedge, lay off inventory rapidly, or hold awards for clients.
The award share is not a position ledger.

Required falsification: an extra-session-lag control and security-weighting
controls must be weaker than the actual next-session state.

### 2. Equity/rate sign changes across macro regimes

Higher yields can accompany stronger growth and rising equities; lower yields
can accompany recession fear. A fixed rate-to-equity sign is therefore
vulnerable in exactly the 2021–2023 regime transition.

Required falsification: every year and both UPRO/SPXU sleeves must be positive.
No inflation-regime or year filter may be added.

### 3. Dollar-years is not DV01

Legal maturity overstates the interest-rate sensitivity of long coupons and
does not incorporate yield, coupon, convexity, or inflation breakevens. It is
chosen because it is auditable and parameter-free, not because it is exact.

Required falsification: action must be reasonably stable to an
accepted-notional-only diagnostic and a fixed-rate-coupon-only diagnostic.
Those diagnostics cannot replace the frozen construction.

### 4. “Previous comparable auction” can still mix regimes

Auction sizes, reopenings, SOMA treatment, and demand composition change. Exact
reported term and security flags reduce but do not eliminate this problem.

Required falsification: coverage must be broad in all three years, direction
must be balanced, and no single term bucket may dominate the absolute feature.

### 5. Bills may manufacture cadence

Frequent bills have very short rate exposure. They could create many tiny
signals without economically meaningful duration.

Required falsification: the audit must report bill and coupon contribution
shares and action agreement with coupon-only construction. No post-outcome bill
deletion is permitted.

### 6. The next-day clock may be too slow

Immediate auction information is rapidly incorporated. Waiting until the next
session improves causal certainty but may leave no edge.

This is a genuine mechanism risk, not something to optimize away. Failure
prohibits moving entry to the auction release window.

## Returns-blind construction gates

- Official snapshot hash recorded and all required numeric fields valid on at
  least 95% of 2021–2023 rows.
- At least 90% of distinct development auction dates with valid source rows
  map to a nonzero next-session dealer-overhang state.
- At least 2.0 signals per week and at least 90 signals per year.
- Minority actuator share at least 35%.
- At least 20 direction switches per year.
- No single like-for-like bucket contributes more than 50% of total absolute
  auction shock.
- Dollar-years action agreement at least 70% with accepted-notional-only on
  all shared event sessions and with fixed-rate-coupon-only conditional on
  sessions where the coupon diagnostic is nonzero.
- Exact 09:33 primary-feed quote coverage at least 90%.
- Independent 2023 feed action agreement is exact because the feature is
  source-only; independent quote coverage is reported separately.
- Action agreement below 80% with prior-day SPY direction and the rejected
  Treasury-maturity impulse v58.

Any construction miss rejects v66 before post-09:33 prices or P&L are read.

## Frozen development gates if construction passes

- More than 2.0 executed trades per declared week.
- Profit factor greater than 1.10.
- Positive fixed-notional P&L in 2021, 2022, and 2023.
- Positive UPRO and SPXU P&L separately.
- Compounded $100 ending cash above adjusted SPY.
- Positive after one extra cent adverse at entry and exit.
- Positive with a five-minute entry delay.
- Positive after deleting the five best auction-date clusters.
- Auction-date moving-block-bootstrap 2.5th percentile above zero.
- One-sided auction-day sign-permutation p-value below 0.05.
- Positive independent-feed overlap with PF above one and both sleeves.
- Actual mean trade P&L above accepted-notional-only, coupon-only, and
  extra-session-lag controls.

Recent years remain locked after any miss. No security-type, year, side, term,
clock, weighting, threshold, or sign repair is allowed.
