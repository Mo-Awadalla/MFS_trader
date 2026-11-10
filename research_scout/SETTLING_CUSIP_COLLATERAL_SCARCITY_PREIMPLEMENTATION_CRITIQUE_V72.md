# Settling-CUSIP Collateral Scarcity: Preimplementation Critique v72

## Hypothesis

On a Treasury security's official issue/settlement date, primary dealers must
finance and deliver the new auction allocation.  If demand to borrow that exact
CUSIP in the New York Fed's securities-lending operation rises relative to both
its own latest observation and the same-day cross-section of non-settling
Treasuries, the change is evidence of security-specific collateral scarcity
rather than a generic move in Treasury financing demand.

The proposed equity transmission is not “Treasuries predict stocks.”  The
specific claim is narrower: an unresolved delivery/collateral shortage consumes
dealer balance-sheet and intermediation capacity after the noon lending
operation, so same-day equity risk absorption should be weaker into the close.
Positive settlement-specific scarcity therefore selects SPXU; a release of
scarcity selects UPRO.

## Would an ETF or market-making desk take it seriously?

It is credible enough to investigate because:

1. It uses the exact settling CUSIP and the Treasury's official issue date.
2. It measures submitted borrowing demand against contemporaneous lendable
   capacity, rather than inferring dealer inventory from price.
3. It differences each CUSIP against its own prior operation and removes the
   same-day median change in non-settling CUSIPs.
4. The New York Fed operation is designed to support Treasury clearing, and its
   historical result is timestamped before the proposed entry.
5. Direction, clock, aggregation, and controls are fixed without reading a
   post-entry return.

A serious desk would still regard the equity leg as the weak link.  Treasury
specialness is often issue-specific, can reflect relative-value positioning
rather than system-wide balance-sheet stress, and may be resolved inside the
repo complex without affecting SPY.  The noon result can also describe pressure
that equity prices already absorbed.  This is a falsifiable microstructure
hypothesis, not an asserted causal fact.

## Frozen measurement

For every lending-auction row:

`demand_pressure = Par Amt Submitted / Actual Available To Borrow`

`demand_change = current demand_pressure - latest strictly prior demand_pressure
for the same CUSIP`

On an official Treasury issue date, retain only auction CUSIPs present in that
day's lending details and published strictly before 12:20 ET.  This point-in-time
rule excludes any later supplementary operation rather than combining future
records into the noon state.  Define the day's common financing change as the
median `demand_change` among all other, non-settling CUSIPs in that lending
operation.

`settlement_scarcity = sum(demand_change - nonsettling_median_change)`

- positive: SPXU
- negative: UPRO
- exact zero: cash

The sum is in equal capacity units.  There are no duration, issue-size, coupon,
security-type, fee, or outcome-fitted weights.

## Returns-blind falsification

The hypothesis is rejected before P&L unless all of the following hold:

- at least 2 signals per week and 100 in every year;
- both actions are at least 30% and switch at least 20 times per year;
- all signal rows have a strictly prior observation of the same CUSIP;
- the median absolute settling-CUSIP change is at least 1.05 times its own
  immediately prior absolute change, showing event amplification;
- action agreement is at least 70% when submitted demand is replaced by
  accepted utilization;
- action agreement is no more than 85% with the unadjusted matched-CUSIP sum,
  proving the non-settling common-mode removal is material;
- action agreement is no more than 80% with v66 and v71;
- no security bucket supplies more than 60% of absolute feature contribution,
  no CUSIP more than 10%, and no month more than 6% of signals;
- all operation close/update times precede a 12:20 ET entry;
- exact 12:20/15:30 primary BBO coverage is at least 95%, and independent-feed
  coverage is at least 90%.

No post-entry price, P&L, or 2024–2025 outcome may be read if any gate fails.

## Ex ante failure interpretations

- **No event amplification:** ordinary repo specialness, not settlement stress.
- **High raw-sum agreement:** the cross-sectional control adds no identification.
- **Low accepted-utilization agreement:** the sign depends on submitted orders
  that do not translate into executable collateral allocation.
- **Security or CUSIP concentration:** isolated specials, not broad dealer
  capacity.
- **Blind gates pass but P&L fails:** the Treasury-clearing state is real but
  does not transmit predictably to leveraged equity ETFs after publication.

## Forbidden repairs

No sign inversion, magnitude threshold, fee threshold, duration weighting,
security-type deletion, CUSIP deletion, settlement-calendar subset, month-end
filter, alternative common-mode statistic, alternate entry/exit, or selection
of agreement/disagreement states.  A failure consumes this specification.
