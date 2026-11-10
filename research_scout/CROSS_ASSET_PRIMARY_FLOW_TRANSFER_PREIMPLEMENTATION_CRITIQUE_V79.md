# Cross-Asset Primary-Flow Transfer: Preimplementation Critique v79

## Frozen hypothesis

Daily changes in ETF shares outstanding are completed primary-market
creations or redemptions, not merely secondary-market price changes.  A
relative increase in HYG shares versus IEF shares is consistent with capital
being allocated toward credit risk rather than intermediate Treasury
duration; the opposite relative change is consistent with defensive
allocation.

For each official iShares as-of date:

1. compute HYG's fractional shares-outstanding change from its immediately
   preceding official observation;
2. compute IEF's fractional shares-outstanding change the same way;
3. define relative primary flow as `HYG fractional change - IEF fractional
   change`;
4. delay the state to the next U.S. cash session because an as-of date is not a
   proven pre-close publication timestamp;
5. buy UPRO at the observed 09:31 ask when relative flow is positive, or SPXU
   when it is negative; and
6. sell at the observed 15:30 bid and remain flat overnight.

A zero difference, missing observation, nonpositive NAV/shares value, or
nonconsecutive source observation produces cash.  There is no magnitude,
percentile, volatility, price, weekday, or calendar filter.

## Why an ETF desk could take the research question seriously

The signal begins with actual changes in fund units.  It therefore measures a
primary-market event rather than inferring allocation from price correlation.
HYG and IEF are economically distinct, highly liquid risk and defensive
wrappers from the same issuer, which reduces issuer-specific reporting
differences.  Normalizing by each fund's prior shares avoids treating the
larger fund as automatically more informative.

An institutional ETF desk would monitor creation orders, premiums, baskets,
authorized-participant identity, settlement, and hedges in real time.  It
might nevertheless investigate whether cross-asset creation pressure persists
into the next cash session.  Passing this public-data experiment would support
that question; it would not prove a bilateral transfer or identify the
initiator.

## Adversarial internal critique

### Creations are not synonymous with end-investor buying

An AP can create shares to close a short, arbitrage a premium, seed inventory,
or facilitate customer demand.  A redemption can likewise be an arbitrage or
inventory event.  The relative HYG/IEF construction is more specific than one
fund's flow, but it still does not prove that the same allocator sold one asset
to buy the other.

Consequence: V79 must be materially different from both HYG-only and
IEF-only signs before P&L, and its return must beat both controls afterward.
The language remains “relative primary flow,” not “observed customer
rotation.”

### Credit and Treasury risk are not exact opposites

HYG combines credit spreads, rates, liquidity, and equity beta.  IEF is mostly
duration and collateral demand.  Simultaneous flows can reflect rate hedging,
bond-market basis trades, or independent mandates rather than risk-on/risk-off
allocation.

Consequence: a second frozen representation compares NAV-dollar creation
flows normalized by combined prior assets.  It is a measurement robustness
check, not an alternative selected after returns.  Percentage-flow and
dollar-flow directions must agree on at least 70% of active primary states.

### The workbook is a mutable historical download

The official iShares workbook is authentic and contains dated Historical
sheets, but it is retrieved now rather than from a point-in-time archive.
Values may have been corrected after their as-of date.

Consequence: save the exact raw responses and hashes, exclude all post-2023
rows from every signal calculation, and impose a full next-session delay.
Even a passing result remains public-history evidence requiring later locked
years and prospective collection.

### Publication time is not established by the as-of date

Same-day use could look ahead.  The next-session mapping is deliberately
conservative.  A one-additional-session-lag control tests whether any result is
merely a slow risk regime rather than a fresh primary-flow transfer.

### Flow may be anticipated or fully hedged

Creation activity can be visible through premiums and secondary volume before
shares outstanding update.  APs and issuers can complete the economic hedge on
the source date, leaving no next-session obligation.  This is the central
economic reason V79 may fail despite clean data.

### The outright actuator may be too broad

HYG-versus-IEF allocation is not a pure S&P 500 position.  Credit risk has an
equity beta, but a relative bond flow can be driven by rates or issuance.  The
price-only HYG-minus-IEF control and prior-SPY control must not explain the
result.

### SPXU remains an expensive falsifier

The inverse wrapper has repeatedly erased weak signals.  Both UPRO and SPXU
must be independently positive; no UPRO-only rescue is allowed.

### Multiple testing remains cumulative

This is V79.  Exact freezing prevents local repair but does not make
2021--2023 pristine.  Recent years remain locked unless every development,
cost, control, and inference gate passes.

## Returns-blind data and construction gates

Before reading any 09:31--15:30 strategy return:

- exact raw-source hashes and one unique official observation per fund/date;
- at least 98% source coverage of expected 2020--2023 cash-session dates;
- positive NAV and shares values, monotonic dates, and no post-2023 signal row;
- source-date changes mapped only to the next U.S. cash session;
- at least 2.0 signals per week and 100 signals in each development year;
- minority direction at least 30% and at least 25 direction switches per year;
- no calendar month containing more than 6% of signals;
- percentage-flow versus normalized dollar-flow action agreement at least 70%;
- action agreement with HYG-only and inverse-IEF-only each below 80%;
- action agreement with prior-session SPY direction below 80%;
- primary entry/exit quote coverage at least 95% and independent overlap quote
  coverage at least 90%; and
- no post-entry return, P&L, or recent-year outcome read.

Any failure rejects V79 before P&L.

## Frozen development gates if admitted

All must pass on 2021--2023:

1. at least two executed trades per week;
2. profit factor strictly above 1.10;
3. positive fixed-notional P&L in 2021, 2022, and 2023 separately;
4. positive UPRO and SPXU sleeves separately;
5. compounded ending cash above adjusted buy-and-hold SPY;
6. positive after one extra cent per share at entry and exit;
7. positive after a five-minute entry delay;
8. positive after deleting the ten best source sessions;
9. positive five-session-block bootstrap 95% lower mean-return bound;
10. direction-permutation p-value at most 0.05;
11. positive independent-feed overlap; and
12. primary mean trade return above HYG-only, IEF-only, normalized-dollar-flow,
    extra-lag, price-only HYG/IEF, and prior-SPY controls.

No sign flip, threshold, fund substitution, sleeve deletion, source-date
repair, alternate clock, or favorable subset is permitted.
