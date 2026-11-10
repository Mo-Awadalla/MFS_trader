# SPY / IEF Joint Macro-Impulse Persistence — Preimplementation Critique v56

## Frozen hypothesis

When intermediate Treasuries and broad equities move in the same direction
during a completed U.S. session, the common component is more likely to be a
discount-rate, liquidity, or systematic-allocation shock than an isolated
equity move. Slow portfolio rebalancing may carry that joint impulse into the
next cash session.

For each common SPY/IEF session:

1. Compute split/dividend-adjusted close-to-close SPY and IEF returns using
   only the completed session and the immediately preceding common session.
2. If both returns are strictly positive, buy UPRO on the next SPY session.
3. If both returns are strictly negative, buy SPXU on the next SPY session.
4. If the signs disagree, either return is zero, or an input is missing, remain
   in cash.
5. Enter at the exact 09:31 observed ask and exit at the exact 15:30 observed
   bid. Hold no overnight position.

There is no return-magnitude, yield-level, volatility, weekday, gap, trend,
calendar, or regime threshold.

## Market mechanism

IEF is a liquid duration proxy. A joint stock/bond rally is consistent with an
easing discount-rate or liquidity impulse; a joint decline is consistent with
a tightening or inflation-risk impulse. Risk-parity, volatility-control,
balanced-fund, and macro portfolios do not necessarily complete all exposure
changes at one closing auction. The next regular session is a deliberately
slow test of whether the common impulse persists.

This is not an ETF-relative-value trade and does not claim that IEF leads SPY
tick by tick. The hypothesis is that agreement identifies the type and
persistence of the prior session's shock.

## Would a high-end trading firm take it seriously?

A systematic macro desk would recognize stock/bond covariance and joint
discount-rate shocks as real portfolio-state variables. The rule is simple,
causal, liquid, and easy to falsify against SPY-only and IEF-only controls.

A high-end desk would not accept the exact rule without qualification. It
would normally use futures, a yield-curve model, macro-announcement controls,
and intraday flow or options information. It would also expect the stock/bond
relationship to change across inflation and growth regimes. V56 is therefore a
bounded mechanism test, not a professional production specification.

## Hard internal critique

1. **Same sign does not identify one shock.** Stocks and bonds can rally
   together in disinflation, fall together in inflation, or move together for
   unrelated asset-specific reasons.
2. **The information may be stale.** ES and Treasury futures trade overnight;
   a next-day 09:31 entry may arrive after reconciliation.
3. **IEF moves are small.** A strict sign rule treats a one-basis-point price
   change like a major duration shock. Adding a magnitude threshold after
   returns would be overfitting, so none is allowed.
4. **SPY may do all the work.** The joint rule must beat prior-SPY-direction
   continuation on mean trade P&L.
5. **Adjusted-price revisions matter.** Yahoo adjusted history is convenient
   but not point-in-time vendor data. A separate unadjusted Alpaca action
   reconstruction must show that distribution adjustments do not define the
   rule.
6. **The stock/bond covariance regime changes.** Inflation-dominant and
   growth-dominant periods can imply different meanings. No post-result regime
   filter is permitted.
7. **2022 can dominate.** A joint tightening rule may look strong because one
   bear year supplies most bearish P&L. Every year, both sleeves, and deletion
   of the ten best trades must pass.
8. **SPXU friction remains asymmetric.** A valid macro state may still be too
   weak to overcome inverse-ETF spread and path drag.
9. **Lineage is adjacent to rejected generic composites.** The repo previously
   rejected mining a multi-asset risk-on/risk-off score. V56 is admissible only
   as one threshold-free, two-asset coherence state with predeclared controls;
   no extra assets may be added after outcomes.

## Decision before implementation

Advance only to a returns-blind feasibility and source-invariance audit.

Development is 2021-2023. The 2024-2025 target-return partition remains locked
unless all development gates pass. The IEF duration, sign mapping, clocks,
actuators, controls, and gates are frozen. No magnitude threshold, TLT/SHY
substitution, additional asset, inversion, side deletion, or regime filter may
repair a failure.

