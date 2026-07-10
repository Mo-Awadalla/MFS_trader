# Bitcoin Crowded-Long Observation — Logical-End Audit

Status: **SUGGESTIVE DEVELOPMENT-SAMPLE INTERACTION; NOT ACTIONABLE**

Scope: the already-consumed 2020-09-01 through 2022-12-31 development panel only. No 2023–2025 outcomes were opened. No threshold, sign, OI definition, horizon, cost, or execution rule was changed.

Reproducible diagnostics:

- Script: `scripts/analyze_bitcoin_crowded_long_unwind_development.py`
- Machine output: `data/parquet/bitcoin_crowded_long_unwind_binance_v1/development/descriptive_audit.json`

## Question

The frozen scout produced a potentially interesting observation:

> Some extreme positive-funding events with expanding OI in late 2020 and 2021 preceded large seven-hour Bitcoin declines.

The logical follow-up is not to optimize it. It is to ask whether the consumed development evidence behaves like a repeatable funding/OI interaction or like a small cluster of regime-specific tail events.

## What remains after stricter diagnostics

Primary combined state:

- Events: 15
- Wins/losses for the short: 8/7
- Mean: +58.82 bps
- Median: +90.91 bps
- IID bootstrap 95% interval: [-57.62, +177.31] bps
- Month-block bootstrap 95% interval: [-28.64, +177.51] bps
- One-sample t-test p-value: 0.355
- Exact sign-test p-value: 1.000

The positive point estimate survives neither individual-event nor month-block uncertainty. Directional frequency is indistinguishable from chance.

## Did rising OI add anything to extreme funding?

Within the 49 frozen extreme-funding days:

| State | Events | Mean short return |
|---|---:|---:|
| Funding extreme + rising OI | 15 | +58.82 bps |
| Funding extreme + non-rising OI | 34 | -14.42 bps |

Observed difference: +73.23 bps in favor of the interaction.

But:

- Welch test p-value: 0.340
- Random-label permutation p-value: 0.356
- Permutation null 95% interval: [-144.16, +155.77] bps
- Spearman correlation between OI change and subsequent short return within extreme-funding days: 0.266, p=0.065

The continuous OI association is the most suggestive diagnostic, but it is still weak and was measured on only 49 funding-extreme observations. It cannot establish that expanding OI caused or reliably forecast the decline.

## Concentration and clustering

- Largest profitable day supplied 34.01% of all positive profits.
- Top three profitable days supplied 66.51%.
- Eight of fourteen event-to-event gaps were seven days or less.
- Median event gap: 5.5 days.
- Maximum gap: 236 days.

This is consistent with episodes, not an evenly recurring daily effect. The rule largely captured a few clusters during highly speculative markets.

## Leave-one-out behavior

Removing each event one at a time produced mean estimates from +20.91 to +92.92 bps.

That means no single observation alone flips the gross sign. However, this does not solve the inference problem: several correlated events occurred in the same late-2020/early-2021 regimes, so treating all 15 as independent overstates effective sample size. The month-block bootstrap remains below zero at its lower bound.

## The 2022 structural break

| Year | Funding-extreme days | Rising-OI days | Combined events |
|---|---:|---:|---:|
| 2020 partial | 14 | 33 | 5 |
| 2021 | 35 | 75 | 10 |
| 2022 | 0 | 82 | 0 |

In the daily 00:00 funding observations used by the frozen rule:

- 2020 maximum settled rate: 0.101151%
- 2021 maximum settled rate: 0.213517%
- 2022 maximum settled rate: 0.010000%
- 2022 median rolling threshold: 0.010000%
- 2022 observations strictly above the threshold: zero

The strategy did not become quietly unprofitable in 2022; its funding trigger became structurally unreachable because the maximum observed rate equaled, but never strictly exceeded, the rolling threshold.

This separates mechanism from implementation:

- Mechanism possibility: unusually expensive long leverage plus expanding exposure may sometimes precede deleveraging.
- Frozen implementation failure: the strict 90th-percentile trigger became dead under the 2022 funding-rate distribution/cap.

Changing `>` to `>=`, changing the percentile method, or redefining “extreme” would repair activity after seeing the failure. That would be post-hoc tuning and is not permitted on this sample.

## Event-level reality

The strongest favorable short events included:

- 2020-11-26: +589.50 bps
- 2021-01-05: +384.77 bps
- 2020-11-22: +178.49 bps

Large adverse events also occurred:

- 2021-01-06: -418.63 bps
- 2020-12-30: -252.61 bps

The consecutive 2021-01-05 and 2021-01-06 outcomes are especially informative: nearly identical broad “crowded long” logic produced a large short gain followed immediately by a larger short loss. The state variable did not identify the timing of an unwind reliably.

## What can and cannot be concluded

Reasonable conclusion:

> In the consumed Binance development period, rising OI appeared to separate extreme-positive-funding days into a more negative subsequent-return subset, but the evidence came from 15 clustered events, was statistically inconclusive, and disappeared operationally when the funding distribution changed.

Unsupported conclusions:

- extreme funding plus rising OI is a validated short signal;
- the interaction works outside late 2020/2021;
- the relationship is causal;
- a different percentile or tie rule would work;
- ML could identify the “good” 8 of 15 events;
- the 2023–2025 holdout should be opened despite failed gates.

## Logical end

The exact strategy is finished and rejected.

The broader economic mechanism remains plausible but unproven. It should be retained as a research observation, not traded and not optimized. A legitimate future revisit would require a separately justified definition of crowding fixed without reference to these 15 outcomes, plus genuinely independent data. The current Binance holdout remains sealed for this family because the frozen development rule failed.

There is no honest ML training set here: 15 positives/negatives are far below what is needed, clustered by regime, and rich in hidden degrees of freedom. An ML model would learn the specific 2020–2021 episodes rather than a stable risk process.
