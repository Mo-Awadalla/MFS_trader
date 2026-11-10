# SPY / Leveraged-ETF Day-Trading Research v58

## Outcome

No additional strategy qualifies for 2024–2025 testing, paper trading, or live
trading.

After V47's promising 2021–2023 result failed in untouched 2024–2025, four
sequential hypotheses were handled without repairing an outcome-exposed rule:

- V55 failed returns-blind cadence and never opened P&L.
- V56 produced positive aggregate development P&L but failed the benchmark,
  annual, cost, and winner-deletion gates.
- V57 lost money across the primary and independent execution feeds.
- V58 lost money and failed to outperform any substantive component or lagged
  control.

V56–V58 therefore kept 2024–2025 locked. No recent-year return was used to
choose an asset, sign, threshold, sleeve, clock, or filter.

## Sequential evidence

| Candidate | Frozen causal sensor | Trades/week | Fixed-$100 development P&L | PF | Annual P&L 2021 / 2022 / 2023 | Independent overlap | Decision |
|---|---|---:|---:|---:|---|---:|---|
| V47 | Change in front/second standard-monthly VX slope | 4.682 | +$164.41 | 1.273 | +$2.56 / +$111.90 / +$49.96 | +$28.66 | Passed development; rejected after 2024–2025 collapse |
| V55 | Front VX settlement direction gated by expanding open interest | 0.179 | Not opened | — | 8 / 7 / 13 signals | Not opened | Rejected returns-blind |
| V56 | Same-sign SPY/IEF adjusted returns | 2.476 | +$29.64 | 1.080 | −$6.05 / +$32.77 / +$2.93 | +$1.82 | Rejected development; holdout locked |
| V57 | Opposing DBC/IEF adjusted returns | 2.363 | −$32.18 | 0.911 | −$19.80 / +$2.27 / −$14.65 | −$15.37 | Rejected development; holdout locked |
| V58 | IEF-minus-SHY adjusted return | 4.722 | −$7.46 | 0.989 | −$9.89 / +$16.65 / −$14.22 | −$8.10 | Rejected development; holdout locked |

The adjusted buy-and-hold SPY hurdle for 2021–2023 ended at $132.40 from $100.
V56 ended at $117.80, V57 at $64.37, and V58 at $73.01.

## What V56 taught

The joint stock/bond state was the only new candidate with positive aggregate
P&L, but it failed exactly where the repo's older work warned it might:

- 2021 was negative.
- Compounded wealth did not beat adjusted SPY.
- One extra cent at entry and exit changed P&L to −$2.86.
- Deleting the ten best trades changed P&L to −$29.51.
- Most profit came from the 2022 tightening episode.

This is not close enough to repair. It is evidence that a plausible macro label
can still be an episode classifier rather than stable alpha.

## What V57 taught

Commodity strength with Treasury weakness is economically compatible with
inflation pressure, but it is not uniquely bearish for equities. DBC also mixes
energy supply shocks, futures roll, and collateral return. The candidate lost
$32.18, and its SPXU sleeve lost $46.51. The separately reconstructed 2023
execution overlap lost $15.37.

The sign-flipped control also lost on the primary development sample. This
rules out the tempting interpretation that the mapping was merely backward.

## What V58 taught

The IEF/SHY relative return had excellent availability and source stability,
but economic identification failed. The candidate's mean trade P&L was below:

- IEF-direction continuation;
- SHY-direction continuation;
- SPY-direction continuation; and
- the one-session-lagged IEF/SHY spread.

The result confirms the preregistered concern that an unweighted ETF return
spread is not a clean DV01-neutral curve shock. Fitting duration weights after
seeing this outcome would be a new optimization, not validation.

## Why no immediate V59

The remaining seven daily ETF histories support many easy combinations:
substitute GLD for DBC, add QQQ/IWM breadth, replace SHY with another maturity,
flip a sign, require three-way agreement, or threshold a return. Those are
cheap degrees of freedom, not independent evidence.

The repo already shows that:

1. generic close-to-close direction controls have small gross effects;
2. SPXU friction repeatedly consumes those effects;
3. apparent robustness frequently comes from 2022;
4. later years reverse even a candidate that passed every development gate;
5. conjunctions improve the story while destroying cadence; and
6. asset substitution after a failed result increases multiple-testing risk.

The honest stopping boundary is to require a new point-in-time causal
measurement before another historical candidate: for example complete
multi-year quote updates, audited primary-market ETF creations/redemptions,
point-in-time options-surface data, or genuinely untouched prospective
sessions. The existing MBP-1 package begins in March 2023 and cannot support
the required 2021–2023 development mandate for a quote-age-native strategy.

## Reproducibility

- V56 critique: `SPY_IEF_JOINT_MACRO_IMPULSE_PREIMPLEMENTATION_CRITIQUE_V56.md`
- V56 result: `spy_ief_joint_macro_impulse_results_v56.json`
- V57 critique: `SPY_DBC_IEF_INFLATION_IMPULSE_PREIMPLEMENTATION_CRITIQUE_V57.md`
- V57 result: `spy_dbc_ief_inflation_impulse_results_v57.json`
- V58 critique: `SPY_IEF_SHY_DURATION_IMPULSE_PREIMPLEMENTATION_CRITIQUE_V58.md`
- V58 result: `spy_ief_shy_duration_impulse_results_v58.json`
- Cumulative registry: `CASH_ETF_HYPOTHESIS_REGISTRY_V34.md`

All development evaluations use observed asks for entry, observed bids for
exit, fractional $100 notional, no overnight position, an additional-cent
stress, a five-minute delay, winner deletion, both actuator sleeves, and an
independent execution-feed overlap.
