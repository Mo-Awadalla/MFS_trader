# FundamentalEventSmartReversal-v1 — Research Lessons

Date: 2026-07-09

## Outcome

The frozen hypothesis was rejected. From 2018-04-02 through 2026-07-02:

- Gross strategy return: -5.56%
- Gross Sharpe: -0.0084
- Mean Rank IC: +0.002384; reversal required a negative sign
- Default-cost return: -43.47%
- Default-cost CAGR: -6.69%
- Default-cost Sharpe: -0.5748
- SPY return: +219.35%
- SPY Sharpe: 0.8421
- SPY plus the predeclared 20%-gross strategy sleeve returned +202.36% with a 0.8013 Sharpe

The result is scout evidence only. The static current-active universe has survivorship bias, but the absence of gross edge is sufficient to reject this version without parameter tuning.

## Why this hypothesis was selected

The choice was reasonable ex ante, though not high confidence:

1. Published research distinguishes news-associated continuation from no-news reversal and supports decomposing short-term moves into fundamental and nonfundamental components.
2. A daily, market-neutral strategy could have provided low-beta utility alongside SPY without requiring latency-sensitive execution.
3. The repository already supported daily cross-sectional panels, stateful holdings, cost analysis, and benchmark comparison.
4. SEC submissions supplied free, timestamped, auditable point-in-time events when historical analyst revisions and a reliable news archive were unavailable.
5. The experiment materially differed from the earlier residual-reversal attempt through a skipped session, stateful median-cross exits, an SEC event veto, forced event exits, and explicit gross/Rank-IC gates.
6. Every important rule was frozen before observing results, making a single trial informative.

## Why it failed

### The core signal lacked predictive power

The decisive failure occurred before costs. Gross return and Sharpe were negative, and Rank IC was close to zero with the wrong sign. Transaction-cost assumptions affected the size of the net loss but did not determine the verdict.

### The SEC veto was an incomplete proxy

The implementation measured whether a material SEC filing had recently become visible. It did not measure whether information was positive, negative, expected, cash-flow relevant, or already disclosed elsewhere. Analyst revisions, earnings releases, litigation, product news, macro news, and industry information can move prices without a contemporaneous filing. Routine filings can also trigger the veto without meaningful new information.

The honest label is therefore “SEC-disclosure-associated move veto,” not “fundamental-news decomposition.”

### Risk reduction did not become alpha

The veto reduced turnover and some losses relative to the diagnostic no-event version. That demonstrated risk reduction, not a profitable signal. A filter cannot manufacture alpha when the underlying ranking has no expected-sign relationship with future returns.

### The effect may decay before executable entry

Short-term reversal can arise from temporary inventory, liquidity, or bid-ask pressure. Any accessible effect may occur before a conservative one-bar-delayed execution. Same-bar accounting would not be an acceptable rescue; failure after executable delay means the effect is not usable through this implementation.

### The liquid large-cap universe is competitive

Liquid stocks reduce trading friction but are highly researched. Moving into smaller stocks might increase apparent reversal while also increasing spread, borrow, capacity, delisting, and point-in-time-universe problems. That is not a free remedy.

### Turnover required an edge that was not present

Drift-adjusted mean daily gross turnover was 0.4583 times equity. Trading costs averaged 2.3082 basis points per day, with another 0.1643 basis points of borrow drag. This turnover might be acceptable with a strong gross edge; it is fatal when gross expected return is approximately zero.

### The symmetric long/short rule simplified distinct mechanisms

The literature suggests loser reversal may be related more to liquidity pressure while winner reversal may involve sentiment and short-sale constraints. The frozen strategy intentionally used a simple symmetric construction to avoid overfitting. Testing many asymmetric variations after this result would consume the sample and constitute post-result tuning.

## What worked in the research process

1. Freeze the hypothesis, data chronology, event policy, holding rule, sizing, and gates before calculating performance.
2. Check expected-sign Rank IC and gross returns before expensive validation.
3. Keep gross evidence separate from cost-model results so cost bugs cannot determine the economic verdict.
4. Compare a market-neutral candidate as an alpha sleeve: beta, alpha, and a predeclared SPY-plus-sleeve blend matter more than standalone statistics alone.
5. State overlay sizing in gross-exposure terms. A 1.0-long/1.0-short strategy is 2.0 gross, so a 20%-gross sleeve scales strategy returns by 0.10.
6. Compute turnover from drifted pre-trade weights, then use those same trades for costs and turnover gates.
7. Audit variable impact, ADV participation, SEC fees, FINRA TAF, borrow, date bounds, cache freshness, and event-count semantics rather than trusting shared helpers.
8. Implement stateful retention literally: universe contraction must not silently truncate valid holdings.
9. Require a complete liquidity window because pandas medians otherwise skip missing observations.
10. Rerun the full historical scout after any logic correction. Several corrections changed net metrics materially while the gross rejection remained stable.
11. Stop after the frozen gross and Rank-IC gates fail. Do not tune lookback, veto window, entry tail, exit rank, form list, or side weights to rescue the experiment.

## Strategy-selection lessons

1. Select by economic mechanism and data fidelity before implementation convenience.
2. Ask whether the available data measures the source paper’s defining variable. A convenient proxy may be suitable for plumbing but too weak for investment inference.
3. Give prior failures in the same repository more weight than generic literature. This materially different reversal hypothesis justified one trial, not a sequence of adjacent variants.
4. Prefer slower signals whose expected return can survive a one-day delay and whose costs consume a small fraction of gross alpha.
5. Define the candidate’s intended utility before implementation: SPY challenger, alpha sleeve, defensive allocator, or execution experiment.
6. Predeclare a falsification rule. For this strategy, nonnegative Rank IC or nonpositive gross return was sufficient rejection evidence.
7. Do not move into less-liquid securities merely to strengthen an in-sample effect without first solving historical membership, delistings, borrow, spreads, and capacity.
8. When the exact required dataset is unavailable, acquiring the right data may be more valuable than testing a weaker strategy that fits existing files.

## Implication for future research

Do not continue tuning this short-term reversal family on the same sample. A more promising, independently motivated direction is slower profitability/quality plus medium-term momentum, potentially as a long-only SPY challenger. It should only be treated as valid after acquiring point-in-time filing fundamentals, historical universe membership, delisted securities, corporate-action handling, and filing availability dates.

The durable conclusion is not that all reversal is impossible. It is that this five-day ranking plus SEC-disclosure veto did not identify an executable edge in the tested universe, and the next candidate should come from a different mechanism rather than another filter or parameter change.