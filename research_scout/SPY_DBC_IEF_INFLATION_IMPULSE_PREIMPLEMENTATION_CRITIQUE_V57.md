# DBC / IEF Inflation-Impulse Persistence — Preimplementation Critique v57

## Frozen hypothesis

An opposing move in broad commodities and intermediate Treasuries can identify
an inflation-discount-rate impulse without using SPY itself as a signal.
Commodity strength with Treasury weakness is the bearish state; commodity
weakness with Treasury strength is the bullish state.

For each common DBC/IEF session:

1. Compute split/dividend-adjusted close-to-close DBC and IEF returns using
   only the completed session and the immediately preceding common session.
2. If DBC is strictly positive and IEF is strictly negative, buy SPXU on the
   next SPY session.
3. If DBC is strictly negative and IEF is strictly positive, buy UPRO on the
   next SPY session.
4. If their signs agree, either return is zero, or an input is missing, remain
   in cash.
5. Enter at the exact 09:31 observed ask and exit at the exact 15:30 observed
   bid. Hold no overnight position.

There is no return-magnitude, yield-level, volatility, weekday, gap, trend,
calendar, or regime threshold.

## Market mechanism

DBC is a liquid broad-commodity proxy and IEF is a liquid intermediate-duration
Treasury proxy. DBC up plus IEF down is consistent with an inflation or
tightening impulse that raises discount rates and pressures equity duration.
DBC down plus IEF up is consistent with disinflation or easing relief. Commodity
and rates exposures are distributed across futures, ETF, risk-parity, CTA, and
balanced portfolios; the next cash session tests whether slow allocation and
hedging flows continue the prior session's cross-asset impulse.

The signal deliberately excludes SPY. It is not a commodity-growth continuation
rule and it is not an ETF-relative-value trade.

## Would a high-end trading firm take it seriously?

A systematic macro desk would recognize the commodity/rates inflation mix as a
real state variable and would consider the mapping economically legible. The
rule is causal, liquid, threshold-free, and falsifiable against commodity-only,
Treasury-only, lagged-confirmation, and sign-flipped controls.

A high-end desk would not accept this exact daily sign rule as a production
model. It would normally decompose energy and non-energy commodities, use
Treasury futures or a yield-curve model, distinguish inflation from real-growth
news, control for scheduled macro releases and the dollar, and examine
overnight price discovery. V57 is a deliberately sparse mechanism scout.

## Hard internal critique

1. **DBC is not a clean inflation surprise.** Energy weights, futures-curve
   roll, collateral return, and commodity-specific supply shocks can dominate.
2. **IEF is not a pure inflation sensor.** Growth expectations, Fed policy,
   duration supply, convexity hedging, and safe-haven demand all move it.
3. **Opposition is not uniquely directional for equities.** Commodity strength
   can accompany healthy nominal growth, while commodity weakness can signal
   recession rather than relief.
4. **The information may be stale.** Commodity and Treasury futures trade
   outside the equity cash session; a next-day 09:31 trade may arrive after
   reconciliation.
5. **Strict signs amplify tiny moves.** A negligible adjusted-price change has
   the same action as a major shock. No magnitude threshold may be introduced
   after observing returns.
6. **Adjusted-price revisions matter.** Yahoo adjusted history is not
   point-in-time vendor data. An unadjusted Alpaca reconstruction must show
   that distribution adjustments do not define the actions.
7. **2022 can manufacture the result.** That year contained unusually
   persistent commodity strength, bond weakness, and falling equities. Every
   year, both sleeves, and deletion of the ten best trades must pass.
8. **The inverse sleeve remains expensive.** SPXU spread and path drag can
   defeat a valid bearish state.
9. **The mapping may just recover one input's continuation.** Candidate mean
   trade P&L must exceed DBC-direction continuation and IEF-direction
   continuation separately.
10. **This is adjacent to rejected generic cross-asset composites.** V57 is
    admissible only as one predeclared two-asset opposition state. No third
    asset, score, threshold, side deletion, inversion, or regime repair is
    allowed.

## Decision before implementation

Advance only to a returns-blind feasibility and source-invariance audit.

Development is 2021-2023. The 2024-2025 target-return partition remains locked
unless every development gate passes. The assets, sign mapping, clocks,
actuators, controls, and gates are frozen before any candidate P&L is computed.

