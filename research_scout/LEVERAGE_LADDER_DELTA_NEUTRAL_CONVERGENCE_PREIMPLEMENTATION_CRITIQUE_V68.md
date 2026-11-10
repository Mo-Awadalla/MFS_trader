# Same-Issuer Leverage-Ladder Delta-Neutral Convergence — Critique v68

## Decision before implementation

Advance to a returns-blind measurement audit only. No post-entry return may be
read until the four-leg state is shown to be causal, frequent, balanced,
clock-stable, independently reproducible, and executable.

## Frozen hypothesis

ProShares supplies two same-benchmark leverage ladders:

- positive: SSO (+2×) and UPRO (+3×);
- inverse: SDS (-2×) and SPXU (-3×).

For each fund, use its official prior-session NAV and the exact 09:32 midpoint.
Calculate its return from prior NAV and divide by target leverage. Within each
ladder, the two resulting implied S&P returns should agree apart from financing,
fees, portfolio differences, and tracking noise.

Define:

- `positive_basis = UPRO_return / 3 - SSO_return / 2`;
- `inverse_basis = SPXU_return / -3 - SDS_return / -2`.

At 09:33:

- positive basis above zero: short UPRO and buy SSO;
- positive basis below zero: buy UPRO and short SSO;
- inverse basis above zero: buy SPXU and short SDS;
- inverse basis below zero: short SPXU and buy SDS.

Each pair receives $50 gross. Within a pair, allocate 40% of its gross to the
3× fund and 60% to the 2× fund. This makes the first-order S&P exposure zero:
`0.40 × 3 = 0.60 × 2`. Exit every leg at 10:30. Exact zero in one ladder leaves
that $50 sleeve in cash.

Longs cross the ask and later sell at the bid. Shorts sell at the bid and cover
at the ask. No passive fill, short-sale price improvement, or short rebate is
assumed. Intraday borrow cost is conservatively treated as zero, but the rule
is not operationally suitable unless both funds are locatable.

## Why this is closer to an ETF-desk trade

The previous wrapper studies used a residual to choose a one-legged
directional ETF position. That is not how a high-end arbitrage desk would
normally express a leverage-scaling discrepancy. It would hedge the common
index delta and trade convergence between replicating wrappers.

The 40/60 weights follow directly from the stated leverage objectives. The
direction follows the replication identity. The hypothesis does not ask a
correlation to predict the S&P; it asks whether two claims on the same
benchmark reconcile after a temporary opening dislocation.

Authorized participants and market makers can create, redeem, short, and hedge
these products. Their activity supplies a concrete convergence mechanism. The
opening is a plausible place for transient dislocation because official NAVs
reset overnight, different products have different auctions and client flow,
and continuous-market quotes must be re-anchored to the same underlying.

## Would a Jane-Street-quality desk take it seriously?

Yes as a low-frequency proxy for a real relative-value object, with major
reservations.

The desk would care about the leverage-scaled basis and would express it
delta-neutrally. It would also calculate executable fair value from live
futures, swaps, baskets, dividends, financing, creation costs, and complete
books at subsecond horizons. This public-data implementation lacks those
advantages and therefore must earn a large margin over four marketable
spreads.

## Hard internal critique

1. **The identity is approximate.** The funds can hold different swaps,
   futures, collateral, fees, and financing terms.
2. **Prior NAV is not live iNAV.** SPY and futures may move overnight; dividing
   each wrapper's prior-NAV return by leverage cancels the common move only to
   first order.
3. **A real basis may be gone before 09:33.** The rule intentionally waits one
   minute after the observation. If the edge requires faster reaction, the
   available history cannot support it.
4. **Four crossed spreads are expensive.** Two legs per ladder can consume a
   small convergence premium.
5. **Shorting is a real constraint.** Historical BBO does not prove locate
   availability, stock-loan fees, queue position, or short-sale restriction
   handling.
6. **Arca BBO is not the SIP NBBO.** Independent EQUS execution must be
   positive and signal directions must agree.
7. **Midpoint is used only for the signal.** It is not an assumed fill.
8. **Corporate actions can corrupt prior-NAV comparisons.** Historical splits
   must be undone point in time and implausible 25% wrapper returns rejected.
9. **No threshold means tiny discrepancies are traded.** This avoids
   optimization but may guarantee that costs dominate. A failed no-threshold
   rule cannot be repaired with a fitted basis cutoff.
10. **Capital accounting matters.** Gross exposure is capped at $100, not $100
    plus recycled short proceeds. This is deliberately conservative.
11. **Benchmark mismatch is demanding.** A market-neutral strategy must still
    compound above adjusted SPY because that is the user's required economic
    hurdle.

## Relationship to prior failures

- v14 studied persistent odd-mode residuals but used a one-legged UPRO/SPXU
  directional actuator and explicitly rejected slow single-snapshot
  convergence.
- v48 studied a one-legged official-open 3× basis and failed returns-blind
  cadence/timing gates.
- v49 proposed a six-fund long-only simplex but could not reconstruct a
  five-second synchronized state from trade-event TBBO.
- v62 bought only a created 3× wrapper when it appeared discounted and found
  weak gross mean reversion that failed costs, controls, sleeves, and the
  independent feed.

V68 is allowed only because it changes the economic implementation: each
discrepancy is traded against its same-sign 2× replicating hedge, with no S&P
direction forecast and no creation condition.

## Binding falsification

The construction fails if:

- either ladder is sparse or one convergence direction dominates;
- neighboring-minute basis signs are unstable;
- ARCX and independent-feed basis signs disagree;
- four-leg quote coverage is inadequate;
- either ladder loses money;
- long-basis and short-basis convergence states do not both contribute;
- four marketable fills per active pair erase the result;
- the delta-neutral weights do not beat equal-dollar weights;
- sign-flipped divergence does as well or better;
- one extra cent per fill, a five-minute delay, or deleting ten best sessions
  removes profit;
- the block-bootstrap lower mean is nonpositive;
- compounded cash does not beat adjusted SPY.

## Anti-repair rule

Do not add a basis threshold, select a ladder, drop short-basis observations,
change 40/60 weights, use midpoint fills, choose a faster favorable clock,
extend the exit, add creations/redemptions, or open recent years after a failed
gate.

