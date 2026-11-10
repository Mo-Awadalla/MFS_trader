# Treasury Dealer Dollar-Years Overhang Postmortem v66

## Decision

**Rejected in 2021–2023. Recent years remain locked.**

## Frozen result

- 572 feature signals; 564 executable trades.
- 3.745 executed trades per declared week.
- Fixed-$100 P&L: +$19.70.
- Compounded ending cash: $99.96 versus adjusted SPY at $132.40.
- Profit factor: 1.036.
- Annual P&L: 2021 -$13.21, 2022 +$34.81, 2023 -$1.90.
- UPRO +$38.32; SPXU -$18.62.
- Extra-cent-each-fill stress: -$27.94.
- Five-minute entry delay: +$23.87, but the same year and sleeve failures
  remained.
- Delete five best mapped auction clusters: -$30.87.
- Event-cluster bootstrap 2.5th percentile: -0.001992.
- Event-direction permutation p-value: 0.2500.

The 2023 independent-feed overlap was positive, but it cannot override the
cross-year, side, cost, concentration, and inference failures.

## Mechanism result

The primary-market inventory story had some directional content: the flipped
rule lost $72.81 and the accepted-notional-only control lost $52.65. That is
not enough. The dollar-years construction still failed to distinguish a
repeatable next-day equity payoff from a small, winner-dependent gross effect.

The extra-session-lag control lost, supporting the chosen causal clock, but
the actual rule did not survive realistic friction or cross-year validation.

## Outcome-exposed near-miss

The fixed-coupon-only diagnostic produced:

- 271 trades;
- 1.799 trades per declared week;
- +$37.88 fixed-notional P&L;
- PF 1.142;
- positive P&L in all three years and both sleeves;
- compounded ending cash $130.25, still below adjusted SPY at $132.40.

This diagnostic was opened as a control after the full rule was frozen. It
missed the cadence and benchmark gates and may not be promoted, widened, or
combined with bills to manufacture frequency.

## Failure lesson

Actual dealer allocation is a better-defined state than generic bond returns,
but “dealer received more duration” is not equivalent to “dealer still owns
unhedged duration next morning.” Bills and floating-rate paper diluted the
rate-risk mechanism, while the cleaner coupon slice was too sparse and remains
outcome-exposed.

## Prohibited repairs

- No fixed-coupon-only promotion.
- No adding selected bill terms to the coupon control.
- No dropping 2021, 2023, or SPXU.
- No moving to the auction-release window.
- No when-issued-tail addition, yield threshold, term weighting change, or
  auction-size filter.
- No promotion of the independent 2023 overlap.

The Treasury-auction weighting family is consumed.

