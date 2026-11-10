# UPRO/SPXU Leverage-Spectrum v14: Preimplementation Critique

Saved before any v14 outcome was calculated.

## The institutional-interest test

Would a serious ETF market-making or index-arbitrage desk listen?

**Yes, as a falsifiable research question.** UPRO (+3), SPY (+1), SH (-1), and
SPXU (-3) form an unusually symmetric leverage ladder. That makes the common
S&P factor overidentified: the odd part of the +/-1 pair and the odd part of the
+/-3 pair should estimate the same directional move, while their even parts
encode path-dependent convexity. A persistent difference between the two odd
estimates is therefore not another price oscillator; it is a leverage-spectrum
residual with a specific replication interpretation.

The desk should not accept the idea without the tests below.

## Structural decomposition

For an ETF targeting daily leverage `L`, a continuous approximation is:

`d log(V_L) approximately L dX - 0.5 L^2 d<X>`

For a completed interval, define:

- low-leverage odd mode: `(r_SPY - r_SH) / 2`;
- high-leverage odd mode: `(r_UPRO - r_SPXU) / 6`;
- odd residual: high-leverage odd mode minus low-leverage odd mode;
- normalized even residual:
  `(r_UPRO + r_SPXU) / 18 - (r_SPY + r_SH) / 2`.

The odd residual cancels the first-order S&P move. The normalized even residual
is directionless and is retained only as a diagnostic; using it to select trades
after outcomes is prohibited.

## Variants rejected before implementation

### Single-snapshot residual convergence

Buy the apparently cheap leveraged ETF against the residual.

Rejected because a real tradable basis should converge on a much shorter
horizon than one-minute bars can validate. A one-legged UPRO/SPXU trade is also
not a proper delta-neutral relative-value implementation.

### Sign inversion

Trade against the odd residual on the theory that arbitrage removes it.

Rejected because convergence of the ETF basis does not imply an opposite move
in the S&P factor. Choosing continuation or reversal from historical P&L would
be post-hoc sign selection.

### Even-mode convexity filter

Trade morning direction only when the normalized even residual has a favorable
sign.

Rejected because the even residual has no directional content. Turning it into
a direction filter would repeat the failed pair-retention and variance-state
families.

### Residual multiplied by ETF volume

Treat residual times volume as signed informed flow.

Rejected because reported volume has no aggressor sign and is not creation-unit
flow or AUM. The available data cannot support that interpretation.

## Hypothesis that survives

Calculate the odd residual separately over 09:30-09:59 and 10:00-10:29 using
ARCX.PILLAR one-minute trade bars. Trade only when both block residuals have the
same nonzero sign:

- positive in both blocks: buy UPRO;
- negative in both blocks: buy SPXU;
- otherwise: hold cash.

Wait through 10:30, enter at the observed 10:31 ask, and exit at the observed
15:55 bid.

## Why persistence changes the interpretation

A one-block residual can be stale prints, spread bounce, or an arbitrageable
tracking discrepancy. Persistence across two non-overlapping half-hours is too
slow to claim a latency edge. The proposed mechanism is sustained directional
demand in the higher-leverage products. Authorized participants and market
makers hedging that inventory can transmit pressure into futures and the cash
index, allowing the state to persist into the afternoon.

## Why it may still fail

- UPRO/SPXU demand is largely endogenous to an S&P move rather than causal.
- ARCA-only bars may create a venue-specific residual; consolidated signals
  could disagree.
- Fund fees, financing, dividends, and imperfect leverage make the simple
  spectrum identity approximate.
- Persistent residuals may reflect stale or asynchronous trades rather than
  client flow.
- Without aggressor-side or creation/redemption data, the hedging channel is
  inferred rather than observed.
- A one-legged directional actuator is a constrained implementation of what an
  institutional desk would normally study as a hedged relative-value signal.

## Required falsification

The rule is rejected unless it:

- trades at least twice weekly;
- beats price-only SPY with the simulated $100 account;
- is positive in every development and holdout year and in both instruments;
- survives one extra cent at every fill, a five-minute entry delay, and removal
  of its largest sessions;
- beats simple low-leverage market direction on the identical selected dates;
- defeats its exact sign-flipped placebo;
- remains positive when both signal and execution are rebuilt from the
  consolidated dataset; and
- produces at least 90% ARCA/consolidated signal agreement on common eligible
  dates.

## Decision before implementation

Implement exactly this persistent odd-mode hypothesis. Do not test a residual
threshold, magnitude rank, even-mode filter, alternative block length, clock,
direction, or instrument subset.

