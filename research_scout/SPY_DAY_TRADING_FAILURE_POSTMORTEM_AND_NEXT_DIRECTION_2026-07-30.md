# SPY Day-Trading Failure Postmortem and Next-Direction Decision

## Decision

Do not generate or backtest V59 from the existing price, volume, daily
cross-asset, auction-snapshot, VX, BTC, or trade-event TBBO fields.

The next direction is a **returns-blind availability and semantics audit of
official leveraged-ETF portfolio inventory**, starting with historical
ProShares daily holdings for UPRO and SPXU during 2021-2023. The intended new
causal object is predictable leveraged-fund rebalance demand, not another
price-pattern label.

This audit is not permission to test a strategy. A return hypothesis may be
written only if the inventory data pass all coverage, timestamp, field, and
corporate-action gates below.

## Evidence reviewed

The postmortem includes:

- implemented and outcome-exposed families V1-V34;
- returns-blind auction and cross-wrapper screens V35-V43;
- BTC, official macro, and VX candidates V44-V47;
- cash-ETF continuation V48-V54;
- external macro sensors V55-V58;
- the signal-free UPRO/SPXU actuator hurdle;
- both ARCX and independent-feed execution evidence;
- every available development/holdout report and the cumulative failure
  registry.

No new strategy return was calculated during this review.

## Failure taxonomy

| Failure class | Representative evidence | What it rules out |
|---|---|---|
| Gross edge below marketable friction | Several V1 candidates were profitable at midpoint and negative at observed ask-to-bid execution; V56 changed from +$29.64 to -$2.86 under one extra cent at each fill | Marginal chart or sign effects and midpoint-only strategies |
| SPXU structural burden | Signal-free 2021-2025 SPXU lost $177.93 and had roughly 2.5 times UPRO's mean spread drag; V57 SPXU lost $46.51 and V58 SPXU lost $51.54 | Symmetric classifiers with only modest downside accuracy |
| Winner concentration | Always-UPRO +$65.20 became -$28.81 without ten best sessions; V16 +$60.32 became -$5.69; V20 +$48.02 became -$2.14; V56 +$29.64 became -$29.51 | Strategies whose expectancy is a handful of trend or shock days |
| Regime instability | Opening-Center, Silence Entropy, flow geometry, and V47 all passed or looked strong in development and failed later years; V47 moved from +$164.41 to -$102.60 | Promotion based only on 2021-2023 historical robustness |
| 2022 episode concentration | V47 made about 68% of development P&L in 2022; V56's only strong year was 2022; V58 was positive only in 2022 | Inflation/bear-regime classifiers presented as permanent alpha |
| Mechanistic specificity destroys cadence | V31 0.67/week, V35 0.135/week, V41 0.276/week, V48 1.982/week, V51 0.633/week, V53 1.342/week, V55 0.179/week | Deleting conditions after a sparse result |
| Measurement/endpoint instability | V36 neighboring-clock action agreement fell below 54%; V52 transition-only agreement was 36.7%; V53 adjacent-clock agreement was 48.4% and 21.9% | Selecting the favorable snapshot, endpoint, or one-tick threshold |
| Incomplete quote-state reconstruction | Trade-event TBBO repeatedly plateaued around 87-89% multi-clock coverage; V49 had zero fully synchronized six-fund 2023 states | Quote-age, stale-quote, convergence, or passive-fill claims from TBBO |
| Cleanly measured but economically wrong | V32 and V33 had approximately 96-100% cross-feed action agreement and still lost on independent execution; V57 and V58 also lost independently | Explaining failures away as ARCA-only noise |
| Controls beat the mechanism | V32's shifted placebo beat the contemporaneous gate; V34's lagged placebo was positive; V58 lost to IEF, SHY, SPY, and lagged-spread controls | Promoting a story when simpler or noncausal rules do better |
| Asset substitution/multiplicity | V56-V58 exhausted three plausible daily stock/bond, commodity/bond, and maturity-spread labels without stable identified value | More GLD/DBC/IEF/SHY/QQQ/IWM sign combinations |

## What the failures do not show

They do not show that intraday opportunity is absent.

The signal-free actuator audit showed substantial midpoint UPRO drift, and an
impossible look-ahead wrapper selector was extremely profitable. The missing
object is a causal pre-entry predictor with enough amplitude to survive
marketable execution and the SPY hurdle.

They also do not show that better execution assumptions would solve the
problem. Queue position and passive-fill probability are unobserved, so
replacing asks and bids with midpoint or favorable limit fills would move the
edge into an assumption.

## Primary diagnosis

The research program has mostly observed **prices reacting to unidentified
flows**. It has rarely observed the institutional obligation that creates the
flow.

The unobserved objects repeatedly named in the failure archive are:

- leveraged-fund exposure and end-of-day rebalance requirements;
- ETF creations, redemptions, shares outstanding, and AP inventory;
- dealer option gamma and hedge demand;
- complete quote updates and replenishment;
- point-in-time constituent membership and breadth.

Another transformation of price history does not reveal who must trade, how
much, or by when.

## Why leveraged-fund inventory is the first next direction

UPRO and SPXU target daily leveraged exposure. Official holdings can contain
swap exposure, futures contracts, collateral, and security positions. At
least one official archived 2022 holdings document visibly contains UPRO and
SPXU positions and swap notionals, while the current ProShares site provides
daily holdings downloads.

This direction is preferred over the alternatives because:

1. it measures a fund-specific institutional obligation rather than another
   market-price state;
2. the mechanism is directly connected to the instruments being traded;
3. the state can potentially occur daily and therefore has a credible path to
   two trades per week;
4. prior-day holdings can be used causally if their publication time is
   verified;
5. a professional ETF or index-arbitrage desk would recognize predictable
   leveraged-fund rebalancing as a serious hypothesis;
6. the archive explicitly rejected this family earlier only because the
   necessary AUM, holdings, shares, and derivative exposure were absent.

## Hard critique before any implementation

1. Public daily holdings may not be historically archived for every session.
2. An “as of” date is not a publication timestamp. Same-day use is prohibited
   unless availability before the trading decision is independently proven.
3. Holdings may be revised or exposed through a mutable current-day URL.
4. Swap notional is not the same as a dealer's immediate hedge order.
5. Creations/redemptions and cash flows can offset mechanical rebalance
   estimates.
6. The direction of a simple leveraged-fund rebalance estimate can collapse
   to ordinary same-day SPY momentum. The inventory variable must add value
   beyond that control.
7. The predictable flow may already be anticipated and traded earlier.
8. A magnitude threshold would create optimization risk. Any normalization
   and threshold must be justified and frozen before return inspection.
9. SPXU remains a difficult actuator even if the underlying flow prediction is
   valid.
10. Public fund inventory is still a proxy. A high-end desk would combine it
    with AP flow, index futures, swaps, closing-auction liquidity, and options
    positioning.

## Returns-blind data-admission audit

Before any strategy specification, verify:

1. at least 98% of U.S. sessions in 2021-2023 have authentic dated UPRO and
   SPXU holdings;
2. every file has a stable source URL, content hash, and unambiguous as-of
   date;
3. publication timing is known, or the audit enforces a one-session delay;
4. net assets or an equivalent denominator can be reconstructed without
   target returns;
5. swap, futures, equity, cash, and other material exposure are separable;
6. share splits and identifier changes are normalized from point-in-time
   records;
7. UPRO and SPXU exposure totals reconcile to their stated daily objectives
   within a frozen tolerance;
8. missing files are not backfilled from later reports;
9. no UPRO/SPXU entry-to-exit return, P&L, winner, or favorable threshold is
   inspected;
10. a second official or regulatory source can validate a sample of dates.

Failure of any coverage, timing, or exposure-reconciliation gate ends the
historical path without P&L.

## Conditional strategy-research path

Only after the audit passes:

1. write one institutional critique and preregistration;
2. estimate rebalance pressure using only information public by the decision
   time;
3. require the inventory estimate to outperform same-clock SPY momentum and
   a constant-AUM rebalance control;
4. retain observed ask-to-bid execution, extra-cent stress, delayed entry,
   annual and sleeve positivity, winner deletion, independent-feed overlap,
   and adjusted-SPY outperformance;
5. keep 2024-2025 locked unless all 2021-2023 gates pass;
6. prohibit threshold search, favorable close-window selection, sign
   inversion, and sleeve deletion.

## If the holdings archive fails

Do not return to daily ETF composites.

The fallback is prospective collection:

- save official UPRO/SPXU holdings, shares, NAV/AUM, and timestamps each day;
- collect complete MBP-1/CMBP-1 quote updates around the intended decision
  and closing windows;
- freeze the future hypothesis before enough outcomes accumulate;
- wait for an untouched sample large enough to evaluate the two-trades-per-week
  mandate.

EQUS.MINI MBP-1 is useful execution and quote-state evidence, but its history
begins on 2023-03-28. It cannot by itself satisfy a 2021-2023 development rule.

## Final next-direction decision

The next task is **data identification, not alpha implementation**:

> Census and authenticate official 2021-2023 UPRO/SPXU daily portfolio
> holdings and determine whether causal leveraged-fund rebalance pressure can
> be reconstructed without reading strategy returns.

Until that audit passes, V59 does not exist.
