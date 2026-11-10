# Settling-CUSIP Collateral Scarcity Postmortem v72

## Decision

Rejected returns-blind.  No post-entry return or P&L was read, and recent years
remain locked.

## What survived critique

- The source was valid and point-in-time: 121,860 usable New York Fed
  CUSIP-level rows, with 716 rows from later supplementary operations excluded
  because they were not published before 12:20.
- Every retained event used a strictly prior observation of the exact same
  CUSIP.
- Settlement-day absolute demand changes were 2.19 times the immediately prior
  changes, so the official settlement match did expose a real change in
  securities-lending state.
- Submitted-demand and accepted-utilization implementations agreed on every
  action.

Those properties make the Treasury microstructure observation real.  They do
not make it an equity-timing edge.

## Why it failed

- Only 281 signals survived, or 1.866 per week; 2021 and 2022 had only 90 and 88.
- Actions were 261 UPRO versus 20 SPXU.  The 7.12% minority share and only
  22/10/4 annual switches fail the minimum state-diversity requirement.
- The non-settling Treasury common-mode subtraction changed no action at all.
  The rule therefore collapsed to the raw matched-CUSIP change rather than
  identifying a settlement-specific residual.
- Bills supplied 88.24% of absolute feature contribution, above the frozen 60%
  ceiling.

The likely explanation is structural roll-off in bill borrowing utilization or
capacity around issue dates, not a two-sided dealer balance-sheet shock.  A
mostly UPRO rule would also be dangerously close to repackaging the development
period's long-equity drift.

## Binding lessons

1. A causal event match can validate the measurement while failing the proposed
   cross-asset transmission.
2. Settlement-day amplification is insufficient when the state is one-sided
   and one security class dominates.
3. Cross-sectional residualization must alter decisions, not merely decorate a
   raw feature.
4. Point-in-time APIs can include later same-day operations; historical research
   must filter by publication timestamp before forming state.

## Forbidden repairs

Do not invert the sign, remove bills, keep notes/bonds only, threshold the
magnitude or fee, normalize bills separately, select the rare SPXU states,
change the cross-sectional statistic, trade only reopening auctions, alter the
entry clock, or inspect P&L.  Those are post-audit adaptations of the same
failed family.
