# Leveraged-Fund Rebalance / Auction-Capacity Postmortem v63

## Decision

V63 is rejected returns-blind. No post-15:51 return or strategy P&L was opened.

## What passed

- Prior-session official AUM was complete for UPRO, SPXU, SSO, and SDS on all
  753 development sessions.
- Joint AUM, SPY-bar, official-close, and auction-state coverage was 97.34%.
- The construction was balanced and executable: 704 signals, 4.675 per week,
  375 UPRO and 329 SPXU.
- Neighboring auction cutoffs agreed on 99.45% of actions.
- ARCX and EQUS feature calculations agreed on 100% of their 2023 overlap.
- Exact 15:51 selected-wrapper quote coverage was 100%.

## Why it failed

The proposed auction-capacity rule selected 96.04% of eligible sessions. Adding
the signed SPY closing-auction imbalance to modelled leveraged-fund demand
blocked only 28 sessions, or 3.82%.

Its action agreed with pure late-day SPY/model direction on 96.18% of sessions,
above the frozen 90% maximum. The auction quantity therefore did not change the
decision often enough to distinguish V63 from generic late-day momentum.

This matters because generic Closing Rebalance Torque already failed. Complete
AUM and an elegant formula do not create a new hypothesis if the resulting
action is almost always the sign of SPY's day return.

## Returns-blind clue and boundary

V63 did reveal a distinct state without exposing P&L: sessions where the
published SPY auction imbalance is opposite modelled geared-fund rebalance
demand. On those sessions, comparing opposite auction capacity with
model-equivalent SPY shares has a direct absorption interpretation.

A separately numbered candidate may test only:

1. auction side strictly opposite the model direction; and
2. absolute model-equivalent shares strictly greater than the opposing
   auction imbalance.

That is not permission to open V63 P&L, change clocks, add a fitted threshold,
or include same-side auction sessions. V63 remains consumed and terminal.

