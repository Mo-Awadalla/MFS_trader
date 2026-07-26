# SPY/SH $100 Fractional Hypotheses — Results v1

Saved: 2026-07-26

## Verdict

No new hypothesis passed the preregistered development gates. The five new rules
were evaluated on 2021-2023 only; none was allowed to inspect 2024-2025.

The previously frozen opening-center benchmark was evaluated in both partitions
for translation diagnostics. Its direction retains a small gross effect, but the
effect is too small for the assumed fractional-share execution costs.

This pass produced no deployable or paper candidate.

## Account and execution model

- Starting cash and maximum gross exposure: $100.
- Planned-loss ceiling: $10 per trade.
- Bullish signals buy fractional SPY; bearish signals buy fractional SH.
- No leverage, shorting, or overnight exposure.
- Baseline adverse slippage at every fill: 3 bps for SPY and 10 bps for SH.
- Entries use the first observed ETF trade-bar open at or within five minutes
  after the decision time.
- Stops are triggered causally from completed SPY minutes; the ETF exits at its
  next observed trade-bar open.
- Eighteen Databento-degraded dates were excluded.

Every simulated position used the full $100. The $10 loss budget never constrained
size because each structural stop was less than 10% from entry.

## Development results

| Hypothesis | Trades/week | Constant-$100 net | Actual ending cash | Gross net at zero slippage | Profit factor | Decision |
|---|---:|---:|---:|---:|---:|---|
| Counterauction Effort Failure | 0.603 | -$11.05 | $89.45 | +$1.30 | 0.530 | Reject: sparse, negative in all years after costs |
| Opening Volume-Scar Parallax | 1.282 | -$26.61 | $76.38 | +$0.76 | 0.533 | Reject: sparse and economically null |
| Premarket False-Probe Relay | 2.846 | -$59.66 | $54.81 | -$4.51 | 0.468 | Reject: frequency passes, direction does not |
| Rejected Excursion Transfer | 0.064 | -$1.85 | $98.16 | -$0.69 | 0.000 | Reject: only 10 trades |
| Center/Close Disagreement Snapback | 0.801 | -$16.78 | $84.54 | -$0.47 | 0.062 | Reject: target too small and signal wrong |

The constant-$100 column redeploys a fixed research notional. Actual ending cash
starts at $100, never replenishes losses, and deploys at most the remaining
equity. Profit factors use baseline costs. The zero-slippage column distinguishes
a bad signal from a potentially valid signal overwhelmed by implementation drag.
The worst baseline fixed-notional trade among the five candidates lost $1.19, so
the $10 planned-loss ceiling was never approached.

## Frozen benchmark translation

The benchmark follows the opening direction when both the 09:59 close and the
09:30-09:59 volume-weighted center lie on the same side of the cash open. It
enters at 10:00, stops at the opening center, and exits survivors at 15:30.

| Sample | Trades/week | Zero-cost ending cash | Baseline-cost ending cash | Zero-slippage mean/trade |
|---|---:|---:|---:|---:|
| 2021-2023 | 3.346 | $118.12 | $63.26 | +$0.0347 |
| 2024-2025 | 3.260 | $103.26 | $67.28 | +$0.0097 |

At zero slippage, the benchmark was positive in every year and both directions
during development. Its gross effect then weakened sharply in 2024-2025. Removing
the five best trades reduced holdout gross net from +$3.29 to -$3.95.

The central economic problem is scale, not the $10 stop budget. A $100 unlevered
position earned only about 3.5 cents per development trade and 1 cent per
secondary-holdout trade before fill costs. This cannot support ordinary market
order friction.

## What each failure taught us

1. **Effort without result was not absorption.** Volume per counter-move point
   reduced frequency below the mandate and produced no stable directional edge.
2. **A highest-volume minute is not a true volume scar.** Minute OHLCV loses the
   price-level transaction distribution. The bar approximation was essentially
   flat before costs and should not be refined.
3. **A premarket probe does not transfer ownership by itself.** This was the only
   new rule meeting the frequency floor, but it lost before costs in 2022 and
   2023 and on bearish signals.
4. **Opposite-side rejected excursions are exceptionally rare under strict
   accepted-value confirmation.** Relaxing the inequalities would be a post-hoc
   frequency repair and is prohibited.
5. **Fast fair-value targets are unsuitable for a tiny account.** The
   center/close snapback target was often reached, but its move was too small and
   the underlying directional premise was negative even before costs.
6. **Inverse ETF execution is the expensive side of a symmetric signal.** SH's
   sparse trade bars created longer observed exit delays and the assumed SH
   friction was materially larger than SPY's. Bid/ask data is required before
   treating any SH result as executable.

## Next untouched hypotheses

These are conceptual successors, not historical findings. Their exact rules must
be frozen before calculation.

### 1. Accepted-Value Retest Rent

Do not buy the initial 10:00 migration. Wait for price to revisit the opening
volume center, then require a completed fixed clock bar to close back on the
original side. The center is “charging rent”: a successful defense should create
a better entry and remove the many immediate full-stop losses. This attacks
execution margin rather than adding a regime filter.

### 2. Delayed Ownership Lease

Compare the opening center with a separately computed 10:00-10:29 center. Trade
only when the second center migrates farther in the opening direction and its
terminal close agrees. Enter at 10:30 and hold toward the close. This asks whether
inventory survives a second participant handoff, not whether the opening bar
looks attractive.

### 3. Inverse-ETF Tracking Relay

Use synchronized SPY and SH bid/ask midpoints to measure which instrument is
temporarily lagging the inverse relationship. Trade only when the instrument that
must be bought—SPY for bullish or SH for bearish—is the laggard, and exit when the
tracking residual closes. This seeks execution-relative convergence instead of
predicting the market. It must not be tested with sparse trade bars because stale
SH prints can manufacture the effect.

### 4. Closing Liquidity Memory Reset

Measure whether the current afternoon revisits both the prior closing
volume-weighted center and the current opening center in a fixed order. A completed
round trip through both anchors may erase inherited inventory; failure to complete
the second traversal may indicate which participant group still owns price. The
sequence, clocks, and invalidation must be preregistered without inspecting
historical winners.

## Research decision

Do not repair or combine any v1 candidate. The next rational action is to test the
Accepted-Value Retest Rent and Delayed Ownership Lease as a separately frozen
pass. Before testing Inverse-ETF Tracking Relay, obtain narrowly targeted
consolidated BBO data; trade bars are not adequate for that mechanism.

Machine-readable results are in
`research_scout/spy_sh_fractional_hypotheses_results_v1.json`.
