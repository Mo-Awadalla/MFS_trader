# Decompose Turnover And Cost Drag Before Strategy Verdicts

Every strategy validation report that shows a catastrophic terminal equity result must be decomposed before interpreting the alpha. A final equity number alone can hide whether the strategy was anti-predictive, structurally overtrading, or simply being crushed by the repo cost model.

This became explicit during the `ResidualReversalStatArb-v1-LiquidLargeCapDaily-AlpacaSIP` validation, Experiment `886f5819-9b51-4ff8-b025-11fbdd8dd06a`. The headline result was a collapse from `$10,000` to about `$3.02`, with research Sharpe `-5.5304` and max drawdown `-99.97%`. The decomposition showed that the collapse was mostly cost/turnover compounding, not a pure "coin flip went wrong" alpha result.

Measured diagnostics from that run:

- Trading days: `2,136`.
- Trades: `69,388`, about `32.5` changed symbol weights per day.
- Average daily turnover: `3.4216x` equity, about `342%` of equity per day.
- Average gross signal return before costs: `-0.9079` bps/day.
- Repo default average daily cost drag: `36.3887` bps/day.
- Daily loss needed to turn `$10,000` into `$3.02` over `2,136` days: about `-37.87` bps/day.

So the terminal equity was explained by approximately:

```text
weak gross signal  ~=  -0.91 bps/day
default costs      ~= -36.39 bps/day
combined drag      ~= -37.3 to -37.9 bps/day compounded for 2,136 days
```

Cost sensitivity from the same run:

| Assumption | Avg cost/day | Final equity | Sharpe |
| --- | ---: | ---: | ---: |
| 0 bps per dollar traded | `0.0000` bps | `$7,295.81` | `-0.1351` |
| 0.5 bps per dollar traded | `1.7108` bps | `$5,062.03` | `-0.3896` |
| 1 bps per dollar traded | `3.4216` bps | `$3,511.94` | `-0.6441` |
| 2 bps per dollar traded | `6.8433` bps | `$1,690.07` | `-1.1530` |
| 5 bps per dollar traded | `17.1081` bps | `$188.05` | `-2.6786` |
| 10 bps per dollar traded | `34.2163` bps | `$4.81` | `-5.2104` |
| repo default cost model | `36.3887` bps | `$3.02` | `-5.5304` |

Interpretation:

- A normal no-cost coin flip would not produce this collapse.
- A no-edge strategy with the same `3.4216x` daily turnover and repo default-like costs would also be nearly destroyed.
- The residual reversal signal was still not attractive: even at true gross/no explicit cost, the run ended around `$7,295.81` with Sharpe `-0.1351`.
- The correct failure mode is: weak/slightly negative signal plus extreme daily turnover plus punitive/default costs.

Cost-model pitfall:

- `CostModelConfig(slippage_fixed_pct=0, commission_pct=0, sec_fee_per_dollar_sold=0, finra_taf_per_share_sold=0, borrow_cost_annual_pct=0)` does not necessarily mean "zero effective trading costs" in repo diagnostics if the helper still contains hardcoded sell-side cost or variable-cost logic.
- In `research/cross_sectional_pipeline.py`, inspect `trade_costs()` before calling any run "zero cost".

Required future diagnostics before paper-ops discussion:

- Gross return before costs.
- Explicit trading-cost drag.
- Explicit borrow-cost drag.
- Average daily turnover and turnover distribution.
- Cost sensitivity table, at least 0, 0.5, 1, 2, 5, and 10 bps per dollar traded.
- Rank IC for the intended holding horizon.
- Same-day versus next-bar alignment check when the signal is short-horizon reversal.
- Final verdict that separates alpha quality from implementation/cost feasibility.

Consequence:

High-turnover strategies must not be judged or promoted from headline final equity alone. If a strategy only survives under zero or near-zero costs, archive it or redesign the hypothesis around lower turnover before any paper trading. Do not rescue a failed Experiment by tuning parameters after seeing the decomposition.
