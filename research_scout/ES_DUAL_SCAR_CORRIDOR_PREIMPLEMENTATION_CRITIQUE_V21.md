# ES Dual-Scar Corridor Completion — Preimplementation Critique v21

## Frozen hypothesis

The prior session's 15:00–15:29 ES volume scar is old accepted value. The
current 09:30–09:59 volume-weighted center is new accepted value. Their absolute
distance is one cross-participant inventory-displacement unit.

Use the unchanged prior-scar opening confirmation. Then:

1. New center above old scar and 09:59 close above the scar is bullish; the
   symmetric state is bearish.
2. Structural invalidation is one ES tick through the new opening center.
3. Structural objective is one additional scar-to-center distance beyond the
   new center: `2 * opening_center - prior_scar`.
4. The 10:00 ES bar is a causal dead minute. Cancel if it touches either the
   invalidation or objective.
5. Enter UPRO/SPXU at the 10:01 observed ask.
6. Exit at the following ETF BBO minute after ES first touches the invalidation
   or objective; if neither occurs, exit at 15:30.

## Why a high-end desk might care

The rule converts two independently formed auction anchors into a unit of
inventory displacement. It does not predict an arbitrary number of points or
use ATR. The target asks whether cash-session price discovery completes a
second equal displacement after moving accepted value across the prior closing
scar. This directly tests whether auction memory propagates geometrically.

Unlike V20's close-carry payoff, both loss and ordinary gain are structural.
That is an ex-ante reason to expect less dependence on a handful of trend-day
survivors.

## Hard critique

- Equal displacement is a geometric convention, not a market law.
- The continuous volume center is not on the ES tick grid; invalidation and
  objective must be rounded adversely for executable triggering.
- The causal dead minute may reduce frequency below two trades weekly.
- A target can cap the rare winners that made the original scar signal viable
  without improving ordinary trades.
- ETF exits occur after an ES trigger and can suffer basis movement and a
  one-minute response delay.
- The family was motivated by V20's known tail dependence. It is admissible
  only because the dual-scar corridor was documented as the next untouched
  research family before V20; no target multiple, stop alternative, or retest
  count may be searched.
- Historical ES and ETF years are heavily researched. Any survivor is
  historical evidence, not authorization for live capital.

## Admission

Advance first to a returns-blind feasibility audit. Require at least two causal
entries weekly, both directions at least 20%, every development year represented,
and at least 95% ETF entry-quote availability. No post-entry ES or ETF price is
read during that audit.

