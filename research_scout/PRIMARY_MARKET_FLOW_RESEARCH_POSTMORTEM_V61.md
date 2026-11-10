# Primary-Market Flow Research Postmortem v61

## Decision

The primary-market data are useful, but the first directional interpretation was
wrong. UPRO creations and SPXU redemptions are not identified bets on subsequent
S&P 500 direction. They can reflect authorized-participant arbitrage, dealer
inventory transfer, customer facilitation, or completed hedges.

V61 is rejected. The 2024-2025 holdout remains locked.

## What was learned before V61

### V59: historical holdings inventory

The official ProShares files provided complete daily NAV, AUM, shares, and split
history for the development period, but not a usable daily history of portfolio
inventory:

- UPRO and SPXU each had 753 of 753 NAV/AUM sessions.
- Internet Archive discovery found only 3 dated holdings files across 753
  sessions, or 0.398% coverage.
- The publication time of historical holdings snapshots could not be established.
- SEC N-PORT filings were useful for periodic validation, not for a two-trades-
  per-week day-trading state.

The holdings-inventory hypothesis therefore failed returns-blind and no P&L was
opened.

### V60: estimated creations and redemptions

Split-normalized daily share changes produced a dense, causal primary-market
state:

- UPRO: 686 active sessions, 4.555 per week, median active flow $16.47 million.
- SPXU: 711 active sessions, 4.721 per week, median active flow $12.52 million.
- Paired directional difference: 748 nonzero sessions, 4.967 per week.
- The largest 10 absolute paired observations represented 22.38% of total
  absolute flow, so the state was not dominated by a handful of days.

This established data availability, not predictive direction.

## V61 hypothesis and result

V61 delayed the prior session's paired flow by one trading session and required
its sign to agree with the current SPY Arca opening-auction imbalance:

- positive UPRO-minus-SPXU flow plus buy imbalance bought UPRO;
- negative flow plus sell imbalance bought SPXU;
- disagreement stayed in cash;
- entry was the 09:31 ask and exit the 10:30 bid.

The construction was frequent, balanced enough, and distinct from either input
alone: 373 development trades, 2.406 per week, with 166 UPRO and 207 SPXU
trades. It nevertheless failed economically:

| Test | V61 result |
|---|---:|
| Fixed-$100 P&L | -$23.89 |
| Ending compounded cash | $76.15 |
| Adjusted SPY ending value | $132.40 |
| Profit factor | 0.882 |
| 2021 / 2022 / 2023 P&L | -$1.36 / -$4.84 / -$17.69 |
| UPRO / SPXU P&L | +$5.31 / -$29.20 |
| Extra-cent stress | -$58.20 |
| Five-minute delay | -$27.12 |
| Delete ten best trades | -$53.04 |
| Independent 2023 feed overlap | -$25.16, PF 0.372 |

Agreement did not isolate a stronger state. The actual mean trade P&L was worse
than both the flow-only and auction-only controls.

## Outcome-exposed diagnostic

After rejection, a prior-SPY-direction control was examined only to understand
the failure. Its gross development P&L was positive, but it was not robust:

- an extra cent of entry and exit friction changed +$51.52 to -$8.15;
- deleting the ten best trades changed the five-minute-delay version to
  -$14.91;
- the moving-block bootstrap lower bound remained negative;
- on the independent 2023 overlap it ended at $116.71 versus adjusted SPY at
  $121.46.

This is evidence of a transient, first-minute gross effect, not a promotable
strategy. The control is outcome exposed and cannot become a new candidate.

## Revised market interpretation

The serious institutional use of primary-market flow is wrapper relative value,
not index direction:

1. Creation activity says that the ETF wrapper recently absorbed inventory.
2. SPY supplies an independent, liquid estimate of the underlying index move.
3. A leveraged wrapper can then be evaluated against its approximately
   leverage-scaled fair-value move.
4. Only a created wrapper trading below that fair-value estimate is eligible for
   a long convergence trade.

This does not assume that creations predict the S&P 500. It asks whether recent
wrapper inventory conditions the convergence of an observable ETF discount.

## Prohibited repairs

The following are consumed and may not be used to rescue V61:

- invert the V61 direction;
- delete SPXU or select only UPRO;
- choose 2021, 2022, or any favorable subperiod;
- threshold or rank paired flow magnitude;
- move among neighboring auction cutoffs or exits;
- substitute the positive prior-SPY control as the strategy;
- inspect 2024-2025.

The next candidate must be preregistered as a wrapper-relative convergence rule,
must pass returns-blind coverage/cadence/stability checks, and must retain both
UPRO and SPXU if both receive creation-qualified signals.

