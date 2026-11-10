# UPRO/SPXU Cross-Inverse Liquidity Thermostat — Preimplementation Critique v17

## Frozen hypothesis before outcome inspection

UPRO and SPXU carry opposite market exposure but share market makers, hedging
infrastructure, and the same underlying risk factor. A spread change with the
same sign in both products is therefore a direction-neutral **common liquidity
mode**, not ordinary directional ETF demand.

For each ETF:

1. calculate the median proportional quoted spread from 09:45–09:59 ET;
2. calculate it again from 10:00–10:14 ET;
3. label the wrapper as expanding, contracting, or unchanged.

If both wrappers contract, dealer risk capacity is improving and the strategy
buys UPRO. If both expand, the common price of immediacy is rising and the
strategy buys SPXU. Disagreement or a tie means cash. Entry would occur at
10:16 and exit at 15:30.

## Why an ETF desk might listen

The inverse pair creates an internal control. Directional demand should tighten
one wrapper while pressuring the other; a common spread movement is more likely
to reflect the state of the shared risk-transfer machinery. A desk may already
monitor this state for execution. The research question is whether it also
contains a slow risk-direction component: contracting risk capacity is
compatible with positive equity carry, while a joint increase in the price of
immediacy is compatible with the equity volatility/leverage asymmetry.

The rule is parameter-light and measures spreads relative to each instrument's
own immediately preceding window, avoiding the permanent UPRO/SPXU spread-level
difference.

## Why it is not the failed Opening Liquidity Seesaw

The old rule first obtained direction from SPY opening price migration, then
required the selected ETF to have a lower relative spread than the opposite
ETF. V17:

- uses no SPY price or market direction;
- does not choose the relatively cheaper wrapper;
- extracts the same-signed spread-change mode;
- derives direction from common risk-capacity contraction or expansion.

It shares an observable with the old rule but not its state variable or causal
claim.

## Hardest objections

1. **The sign map may be too coarse.** Wider spreads forecast uncertainty, not
   necessarily negative returns. Upside shocks can also widen both products.
2. **Opening normalization can masquerade as risk-on.** The windows deliberately
   start after the first fifteen minutes, but liquidity may still improve
   mechanically through 10:15.
3. **Tick discreteness is severe.** Median proportional spreads can change
   because prices or minimum-tick occupancy change, not because dealer risk
   capacity changes.
4. **One-minute BBO is a sampled state.** It observes the final BBO in each
   minute rather than the time-weighted spread.
5. **Common market makers are an inference.** The data does not identify dealer
   accounts. Same-mode movement is consistent with—but does not prove—shared
   balance-sheet repricing.
6. **ARCA may not represent executable national liquidity.** The hypothesis is
   rejected before P&L if independently sourced EQUS.MINI signals do not agree.
7. **SPXU implementation drag remains material.** A correct risk-off state must
   produce enough movement to overcome the inverse ETF's wider spread.
8. **Positive equity drift is a dangerous hidden factor.** Both directions and
   every development year must be positive, and the rule must beat passive SPY.

## Returns-blind admission gates

- paired valid-window coverage of at least 95% of feed session dates;
- at least two nonzero signals per calendar week;
- the minority direction must be at least 20% of signals;
- at least 65% same-direction agreement when both ARCA and EQUS.MINI signal;
- at least 55% identical actions across all overlap dates, including joint
  no-trades.

Failure means no post-signal return is read. Passing permits exactly one frozen
implementation, with no magnitude threshold, price filter, weekday filter, or
direction deletion.

## Preimplementation decision

**Advance to a returns-blind measurement audit only.** The mechanism is
identifiable from existing quotes and distinct from the prior relative-spread
failure, but its susceptibility to mechanical liquidity normalization makes
cross-feed invariance and direction balance binding requirements.

