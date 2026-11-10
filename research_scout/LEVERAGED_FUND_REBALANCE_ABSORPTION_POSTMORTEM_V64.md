# Leveraged-Fund Rebalance Absorption Postmortem v64

## Decision

V64 is rejected returns-blind. No post-15:51 return, strategy P&L, or
2024-2025 outcome was opened.

## Construction

V64 separated the economically meaningful subset that broad V63 obscured:

1. Estimate four-fund rebalance demand from prior-session official AUM and the
   completed SPY 15:49 return.
2. Require the published SPY closing-auction imbalance to be strictly opposite
   modelled demand.
3. Require absolute model-equivalent SPY shares to be strictly larger than that
   opposing auction quantity.
4. Trade the model direction no earlier than 15:51; otherwise remain in cash.

The model-versus-auction comparison is a structural zero-net-capacity test, not
a fitted historical magnitude cutoff.

## What passed

- 733 eligible development sessions, or 97.34% coverage.
- 335 signals, or 2.224 per week.
- 175 UPRO and 160 SPXU signals.
- 45.70% selection share.
- The AUM capacity comparison rejected 7.71% of opposing-auction sessions,
  proving that magnitude—not only direction—changed the state.
- Neighboring-cutoff exact-action stability was 80.08% and 77.49%.
- ARCX/EQUS 2023 action agreement was 100%.
- Exact 15:51 selected-wrapper quote coverage was 100% on both feed views.
- Agreement with broad rejected V63 was 49.66%; agreement with failed Closing
  Rebalance Torque was 44.88%.

## Failed gate

Signals by year were:

- 2021: 73;
- 2022: 129;
- 2023: 133.

The preregistration-admission rule required at least 90 in every development
year. V64 therefore failed before P&L despite passing the overall two-trades-
per-week target.

The 2021 miss is substantial, not a rounding issue. Lowering the gate, selecting
2022-2023, broadening to same-side auctions, or changing the cutoff would be a
post-audit repair.

## Boundary

V64's exact opposition/capacity construction is consumed. It may not be rescued
by:

- reducing the annual minimum;
- deleting the opposing-auction requirement;
- admitting same-side auctions;
- changing total imbalance to market imbalance after seeing the count;
- moving the SPY bar, auction cutoff, entry, or exit;
- adding an AUM, return, or auction-size threshold;
- inspecting any post-entry price.

The official-AUM audit remains valuable evidence that the data can now support
mechanical rebalance research. Neither V63 nor V64 earned permission to open
returns.

