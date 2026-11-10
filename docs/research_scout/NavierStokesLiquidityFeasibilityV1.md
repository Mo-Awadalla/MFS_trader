# Navier–Stokes-inspired liquidity concentration: repository feasibility

## Decision

This repository can test the proposal in two stages. The existing Databento MBP-1
package supports an immediate top-of-book, event-time pilot. A decisive test of
price-space concentration requires new MBP-10 or MBO data.

The OpenAI result motivates the feature family; it does not imply that markets
satisfy the Navier–Stokes equations. The falsifiable market claim is that local
concentration adds out-of-sample predictive information beyond aggregate activity.

## Stage 1 implemented here

The runner uses the existing 09:20–09:40 ET files for SPY, SSO, UPRO, SH, SDS,
and SPXU. It measures state during 09:25–09:30 and predicts the maximum absolute
midpoint excursion during 09:30–09:35.

The baseline contains spread, best-level depth and imbalance, realized volatility,
trade volume, signed imbalance, and event rate. The augmented model adds norm-ratio,
temporal shear, concentration, quadratic-flow, spectral-cascade, price-sensitivity,
and transport/restoration proxies. Calendar-year forward tests prevent random-row
leakage. All six symbols from a date remain on the same side of a split.

Run a small plumbing check:

```powershell
.\.venv\Scripts\python.exe -m research_scout.test_navier_stokes_liquidity_concentration_v1 --max-files 10 --workers 2 --rebuild
```

Run the complete local evaluation:

```powershell
.\.venv\Scripts\python.exe -m research_scout.test_navier_stokes_liquidity_concentration_v1 --workers 4 --rebuild
```

The complete run writes a compact feature panel and JSON results under
`research_scout/navier_stokes_liquidity_v1/` without making paid API calls.

## What MBP-1 cannot establish

MBP-1 reports every event affecting the best price level and the resulting BBO. It
does not expose the liquidity profile across price levels. Therefore it cannot test
literal spatial gradients, curvature, shrinking price-space core width, profile
self-similarity, or continuum-versus-discrete residuals. Temporal proxies must not
be relabeled as those quantities.

## Stage 2 data contract

Acquire consolidated MBP-10 (minimum) or MBO (preferred) for liquid instruments,
covering ordinary days and stressed/news days. Store every event with receive and
event timestamps, venue, action, side, price, size, order count/identity where
licensed, and at least ten reconstructed levels per side. Include a news-release
calendar only for the endogenous-versus-news hypothesis.

With full depth, define liquidity density as displayed shares per tick, signed flux
from additions, cancellations and aggressive executions, and velocity as flux over
lagged density. Estimate replenishment from post-depletion recovery without using
future observations. Then preregister:

1. spatial norm ratios and gradient energy versus future jumps;
2. effective core width and impact per unit volume;
3. separate directional and replenishment Reynolds-like ratios;
4. profile collapse and power-law acceleration only as secondary diagnostics;
5. baseline versus augmented hazard/impact models with purged date blocks;
6. date-cluster bootstrap intervals, symbol leave-one-out tests, latency, and costs.

The research program should be killed if the concentration family fails to improve
strict forward performance, if the effect is a spread/volatility proxy, or if it
does not survive independent full-depth data.

## First frozen result

The complete local run decoded 806 sessions and produced 4,657 symbol-session rows.
The concentration family failed the primary ranking metric in both forward folds:

| Forward year | Baseline AP | Augmented AP | Increment |
| --- | ---: | ---: | ---: |
| 2025 | 0.4894 | 0.4882 | -0.0011 |
| 2026 | 0.4154 | 0.3871 | -0.0283 |

ROC AUC also declined in both years. Brier score improved by 0.0001 and 0.0111,
respectively, but calibration improvement does not satisfy the preregistered
average-precision gate. The correct Stage-1 verdict is therefore
`FAIL_STAGE_1_NO_INCREMENTAL_JUMP_RANKING_VALUE`.

This rejects the implemented top-of-book temporal proxies for this opening-window
task. It does not test—and therefore cannot reject—the proposal's literal
full-depth spatial concentration hypotheses. The next rational spend is a bounded
MBP-10 feasibility sample, not feature tuning on these same outcomes.
