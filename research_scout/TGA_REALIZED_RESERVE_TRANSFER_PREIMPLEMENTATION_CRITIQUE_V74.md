# TGA Realized Reserve Transfer: Preimplementation Critique v74

## Hypothesis

The Treasury General Account is held at the Federal Reserve.  When deposits
into the TGA exceed withdrawals, the TGA rises and reserve balances in the
private banking system fall; when withdrawals exceed deposits, Treasury cash
returns to the private sector and reserves rise.

The Daily Treasury Statement reports the realized deposit and withdrawal flow.
After its publication, a net reserve drain may reduce dealer/intermediary
balance-sheet elasticity during the next cash session; a net injection may
increase it.  Positive `deposits - withdrawals` therefore selects SPXU, and a
negative value selects UPRO.

## Would a high-end desk take it seriously?

The mechanism is institutionally real and measurable:

- it is an actual transfer between the TGA and the private sector, not a price
  correlation;
- the Bureau of the Fiscal Service reports deposits, withdrawals, opening
  balance, and closing balance in one official statement;
- the balance identity provides an outcome-free accounting validation;
- the publication lag is explicit and can be enforced conservatively;
- the state occurs almost daily without a fitted threshold.

The trading implication is much weaker than the accounting mechanism.  In
2021–2023 aggregate reserves were often abundant, Treasury flows were partly
anticipated from tax and debt calendars, Federal Reserve operations could
offset them, and a published realized flow may be stale by the next tradable
session.  A Jane Street-caliber desk would treat reserve scarcity, expectations,
and offsetting facilities as important, but conditioning on those after seeing
returns would overfit.  This specification deliberately tests the unconditional
transmission and is rejected if it collapses to earlier RRP or auction signals.

## Point-in-time rule

Treasury states that the DTS is available by 4:00 p.m. on the following
business day.  For each statement record date:

1. Compute the following U.S. federal business day as its conservative
   publication date.
2. Map the state to the first SPY cash session strictly after that publication
   date.
3. If more than one record maps to a session, sum the realized flows.

This handles market-open federal holidays without using a statement before it
was available.

## Frozen feature and action

All amounts are official rounded millions:

`net_tga_drain = Total TGA Deposits - Total TGA Withdrawals`

- positive: SPXU
- negative: UPRO
- zero: cash

The accounting control is:

`TGA Closing Balance - TGA Opening Balance`

The two signs must agree almost perfectly and dollar differences must be within
the statement's rounding tolerance.  For pre-April-2022 detail rows, the frozen
tolerance is `0.5 million × included category rows + 1.5 million` for the
rounded detail and balance fields; later official total rows use the same
formula with two included rows.  Entry, if admitted, is the exact 09:33 ask and
exit is the exact 15:30 bid.

## Returns-blind rejection gates

- required-field and accounting reconciliation at least 99%;
- every mapped trade date strictly follows the computed publication date;
- at least 2 signals/week and 100/year;
- both actions at least 30%, with at least 20 switches/year;
- accounting-control action agreement at least 99%;
- action agreement no more than 80% with V66, V71, and V71's RRP-only component;
- no month above 6% of signals;
- primary and independent exact quote coverage at least 95% and 90%.

No post-entry return is read unless all gates pass.

## Frozen development hurdles

If admitted, 2021–2023 must clear PF 1.10, every year, both actions, adjusted
SPY, an extra cent at both fills, 09:38 delay, delete-ten, block bootstrap,
month-stratified permutation, and positive independent execution.  Its mean
must exceed an extra-publication-session lag and a same-direction always-available
SPY prior-session control.

## Forbidden repairs

No sign inversion, magnitude threshold, tax-day/month-end/debt-ceiling filter,
reserve-level regime, rescaling, RRP netting, auction netting, selected
deposit/withdrawal categories, alternate publication lag, alternate clock,
year deletion, or SPXU deletion.  Recent years remain locked after any miss.
