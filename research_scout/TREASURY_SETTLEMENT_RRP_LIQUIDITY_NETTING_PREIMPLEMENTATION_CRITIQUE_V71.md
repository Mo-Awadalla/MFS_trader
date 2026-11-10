# Treasury Settlement / ON RRP Liquidity Netting — Critique v71

## Frozen hypothesis

Treasury auction awards create a known cash obligation on the official issue
(settlement) date. For each security-type/term/FRN/TIPS bucket, compare the
current Primary Dealer award dollars with the immediately preceding
like-for-like award dollars:

`dealer_cash_change = current_primary_dealer_accepted
                      - prior_primary_dealer_accepted`.

Aggregate those changes by issue date. After the New York Fed's same-day ON RRP
operation closes, convert its change from billions to dollars:

`rrp_cash_absorption = (current_ON_RRP - prior_ON_RRP) × 1e9`.

The frozen balance-sheet quantity is:

`net_cash_drain = dealer_cash_change + rrp_cash_absorption`.

- Positive net drain: buy SPXU.
- Negative net drain: buy UPRO.
- Exact zero: cash.

The operation normally closes at 13:15 ET. The result is given two minutes of
publication latency: enter the selected wrapper at the exact 13:17 ask and
exit at the exact 15:30 bid. Use fixed $100 fractional notional, no stop,
overnight position, magnitude threshold, or outcome-derived filter.

## Causal mechanism

This is not an assertion that “large Treasury auctions make stocks fall.”
Expected issuance is known, auction awards are known before settlement, and
markets can pre-fund them.

The narrower claim is that the *change in dealer cash obligation* reaches a
hard settlement date. ON RRP usage is a same-unit observation of whether
money-market cash moved into the Fed facility (additional reserve absorption)
or out of it (a buffer). Only after both quantities are public does the rule
ask whether the net balance-sheet drain affects the last part of the equity
session.

The New York Fed explains that an RRP shifts cash to the Fed, reducing reserve
liabilities while increasing RRP liabilities. It also states that operation
results report the accepted amount after completion. Historical 2021 terms
place the normal daily operation at 12:45–13:15 ET.

## Why this is distinct from v66

V66 measured unexpected *duration inventory* on the auction date using dealer
share changes times accepted amount times years, then traded the next cash
session. It failed because auction allocation did not imply an unhedged
next-morning duration position.

V71 measures *cash funding* on the issue date, uses the change in actual dealer
award dollars rather than v66's duration or notional-share weighting, and nets
that obligation against an observed same-day money-market cash movement. The
afternoon clock is dictated by ON RRP publication, not selected from returns.

## Institutional attack

1. Dealer awards can be client facilitation and can be repo financed before
   settlement. Award dollars are not an unhedged proprietary position.
2. ON RRP is used mainly by money funds and government-sponsored enterprises;
   its aggregate change is not a direct ledger of dealer funding.
3. A fall in ON RRP is not automatically a risk-asset inflow. Cash can move
   into Treasury bills or private repo without touching equities.
4. The two terms can share a Treasury-settlement cause without their sum
   identifying the marginal equity flow.
5. Issue-size changes are often scheduled and anticipated. The rule measures
   realized funding load, not news surprise.
6. Quarter-end, month-end, tax dates, and debt-limit regimes can dominate RRP
   changes. Every year, both actions, winner deletion, cluster bootstrap, and
   component controls are therefore binding.
7. A professional desk would also observe repo rates, fails, collateral
   specialness, intraday payments, dealer financing, and Treasury futures
   basis. Those are absent.
8. SPXU spread and decay remain a large implementation burden.
9. The result may already be incorporated before 13:17 because the award and
   settlement calendar were known earlier.
10. V71 is still one experiment in a heavily tested archive. Passing
    2021–2023 would justify only a locked recent-year test, not production.

## Returns-blind admission gates

- At least 95% validity of required auction fields.
- ON RRP and a strictly prior observation on every selected settlement date.
- At least 2.0 signals per week and 100 in each year.
- Minority action at least 30% and at least 20 switches per year.
- At least 70% action agreement when the dealer baseline changes from one
  prior like-for-like issue to the median of the prior three.
- No more than 80% action agreement with dealer-only, RRP-only, or v66
  actions; otherwise the proposed netting adds no distinct state.
- No calendar month contributes more than 6% of signals.
- Exact 13:17 and 15:30 quote coverage at least 95% on ARCX and 90% on the
  independent 2023 overlap.
- No post-entry price, return, P&L, or 2024–2025 strategy outcome is read.

## Frozen return gates if admitted

- Profit factor at least 1.10.
- Positive fixed-$100 P&L in 2021, 2022, and 2023.
- Positive UPRO and SPXU sleeves.
- Compounded ending cash above adjusted SPY.
- Positive with one extra adverse cent at both fills.
- Positive with entry delayed to 13:22.
- Positive after deleting the ten best settlement dates.
- Five-settlement-date moving-block bootstrap 2.5th-percentile mean above zero.
- Settlement-month cluster permutation p-value below 0.05.
- Positive independent-feed overlap with profit factor above one.
- Actual mean return above dealer-only, RRP-only, sign-flipped, and
  one-settlement-shifted controls.

Failure prohibits sign inversion, component rescaling, security-type deletion,
date filtering, thresholds, a different RRP change definition, or clock/exit
selection. Recent years remain locked after any miss.
