# ES Creativity Pass v3

Saved: 2026-07-26

## Mandate and research controls

The pass searched for intraday ES/MES mechanisms producing at least two trades per week, using one MES, no overnight positions, conservative spread or adverse-tick fills, and $1.24 round-trip commission. Every exact rule was written before its first calculation.

Development gates were:

1. At least two trades per week.
2. Positive 2021, 2022, and 2023 P&L.
3. Positive long and short P&L.
4. Aggregate profit factor greater than one.
5. No post-result inversion, side selection, time selection, or threshold repair.

The 2024-2025 secondary holdout was accessed only for rules passing all initial development gates.

## Results

| Hypothesis | Development trades/week | Development P&L | PF | Decision |
|---|---:|---:|---:|---|
| Endogenous Impact Half-Life Relay | 4.801 | $826.24 | 1.055 | Reject: 2023 and longs negative |
| Closing Volume-Scar Escape | 3.891 | -$955.18 | 0.927 | Reject |
| Closing Auction-Density Switch | 4.679 | -$5,328.95 | 0.700 | Reject |
| Morning-to-Lunch Anchor Transfer | 2.981 | $2,708.57 | 1.311 | Holdout and fragility failure |
| Opening Participation Confirmation | 0.199 | $171.91 | 1.159 | Reject: sparse and 2021 negative |
| Prior-Close Volume-Scar Handoff | 2.776 | $4,420.03 | 1.479 | Paper candidate; strict fragility failure |
| Opening Boundary Debt Repayment | 1.231 | -$453.14 | 0.854 | Reject |
| Auction Polarity Transfer | 0.782 | -$1,362.53 | 0.664 | Reject |

## Failure-derived lessons

1. **Raw pressure remains unhelpful.** Even when reframed as next-trade causality, timing compression, impact retention, or price-level density, same-window closing information did not produce stable symmetric expectancy.
2. **Same-window acceptance is not enough.** The current closing window's volume scar had no durable escape edge. A price level became useful only when it survived a genuine cross-day participant handoff.
3. **Absolute volume comparisons ignore clock seasonality.** Second-half opening volume exceeded first-half volume only 36 times in 749 sessions. Natural intraday volume decay made the rule structurally sparse.
4. **Anchor reordering is not ownership.** Morning and lunch centers crossing the cash open sounded economically coherent but lost in every development year and direction.
5. **A higher win rate does not remove fragility.** Boundary Debt Repayment won 63.0% of trades, yet occasional structural-stop losses overwhelmed its small center targets.
6. **The recurring positive-skew problem remains.** Every promising anchor-persistence system is paid by a minority of close-carry survivors. The research problem is no longer finding attractive gross backtests; it is proving that those survivor tails recur.

## Strongest new candidate: Prior-Close Volume-Scar Handoff

### Exact mechanism

1. From the prior full session's 15:00-15:30 ES transactions, find the price with the greatest summed trade size. This is the prior closing volume scar.
2. During the current 09:30-09:59 opening, compute the volume-weighted center of one-minute typical prices.
3. Go long when both that center and the 09:59 close are above the prior scar. Go short when both are below.
4. Enter at the 10:00 open plus one adverse tick.
5. Invalidate one tick beyond the current opening center. Exit survivors at 15:30 with one adverse tick.
6. Skip contract-roll mismatches and invalid stop geometry. Use one MES and $1.24 commission.

### Evidence

| Sample | Trades/week | P&L | PF | Max drawdown | Long P&L | Short P&L |
|---|---:|---:|---:|---:|---:|---:|
| Development 2021-2023 | 2.776 | $4,420.03 | 1.479 | -$1,100.09 | $2,812.57 | $1,607.46 |
| Secondary holdout 2024-2025 | 2.673 | $1,206.45 | 1.171 | -$899.26 | $964.22 | $242.23 |

Every calendar year was positive:

- 2021: $2,193.92
- 2022: $1,615.81
- 2023: $610.30
- 2024: $1,043.64
- 2025: $162.81

The holdout remained profitable after an additional $2.50 per trade: $511.45.

### Why it is still paper-only

- Win rate was only 20.1% in holdout.
- Removing the five best holdout trades changed $1,206.45 to -$662.35.
- Five-session block-bootstrap probability of a non-positive holdout total was 21.3%, narrowly missing the predeclared below-20% gate.
- The final year contributed only $162.81.
- The stop is based on a continuous volume center while real futures stops must use tick-grid prices. The additional-cost test covers some but not all live implementation uncertainty.

The rule is therefore the strongest new challenger, not a live-trading recommendation.

## Comparison with the existing three-engine benchmark

The cross-day scar is stronger per trade and more cost-tolerant than the current three-engine portfolio, while the portfolio remains more active:

- Cross-day scar holdout: 2.673 trades/week, $1,206.45, PF 1.171, and +$511.45 after another $2.50 per trade.
- Three-engine holdout: 6.962 trades/week, $1,605.49, PF 1.077, and -$204.51 after another $2.50 per trade.

Both remain tail-dependent after removing five winners. Combining them on already-seen history is prohibited because selecting a portfolio after observing both holdouts would create another layer of overfitting.

## Next creative research family

The next pass should distinguish **persistent cross-day price memory** from an attractive historical coincidence.

1. **Scar-specific negative controls.** Freeze comparison anchors such as the prior terminal price and a deliberately stale scar before calculation. The purpose is causal discrimination, not choosing whichever control performs best.
2. **Anchor-defense failure.** Test whether repeated current-session approaches to a prior closing scar produce shrinking rejection distances before the level breaks. Direction must arise from the predeclared defense sequence, not from a fitted number of retests.
3. **Dual-scar corridor.** Treat the prior closing scar and current opening center as boundaries of an inventory corridor. Test the first completed traversal and retest using a structural target, seeking a less tail-dependent payoff than carrying every survivor to 15:30.

Exact retest counts, clocks, targets, and decision rules remain intentionally unspecified. They must be preregistered in the next pass rather than inferred from this candidate's winners.

## Current decision

Keep the Prior-Close Volume-Scar Handoff as a forward paper candidate. Do not deploy it, combine it with the existing portfolio on historical results, add a side filter, or redesign its exit using the known winning trades. All other rules in this pass are rejected unchanged.
