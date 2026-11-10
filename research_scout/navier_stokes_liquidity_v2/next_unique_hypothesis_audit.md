# Next discriminating Navier–Stokes market hypothesis

Date: 2026-09-13

## Decision

The next test should be a strengthened version of hypotheses #1/#2:

> Maximum local flow pressure can become extreme while RMS pressure, total
> activity, realized volatility, and average touch liquidity remain ordinary.

This is the cleanest currently feasible test of the assumed mathematical
lesson—local intensity diverging while aggregate quantities remain bounded.
It is materially different from asking whether a generic high-volatility or
thin-liquidity state predicts a move.

## Why the other leading candidates are not next

| Candidate | Disposition |
| --- | --- |
| #10 directional versus replenishment Reynolds numbers | Most theorem-specific remaining idea, but BBO and aggregate trades do not identify price-resolved order flux or cancellations well enough to estimate both quantities faithfully. |
| #40 impact recovery | Partly measured on the full-depth day; without order identities and event types, recovery mixes replenishment with quote relocation. |
| #54 local Lyapunov amplification | Estimable by nearest-neighbor analogues, but matching error and omitted state can look like amplification. It is less discriminating than local-versus-global concentration. |
| #87–88 universal scaling | Requires several comparable, untouched full-depth symbols. The checked free ETH Tardis full-depth URLs returned 404. |
| #31–35 endogenous versus news-triggered moves | Requires a synchronized, quality-controlled news-surprise dataset not currently in the repository. |
| #49, #80–85 queue/execution transition | Requires L3/queue or parent-order information unavailable in the free data. |

The continuum-model family #46–50 and its H47 survivor are closed under the
current operationalization after the controlled ETH replication failed.

## New measurement

For each aggregate trade, use the latest timestamp-eligible BBO and normalize
aggressive quantity by the same-side touch quantity. Aggregate this observable
pressure to one-second intervals. At each ten-second decision point calculate,
over the trailing 60 seconds:

- maximum one-second touch-normalized pressure;
- RMS one-second touch-normalized pressure;
- their maximum-to-RMS concentration ratio;
- total trade volume, realized volatility, mean touch depth, spread, imbalance,
  signed flow, and quote-event rate.

The critical comparison is restricted to an **ordinary aggregate state**:
RMS pressure, total volume, realized volatility, and mean touch depth must lie
between training-set 20th and 80th percentiles. Within that state, the test asks
whether a high maximum-to-RMS ratio predicts the next 60-second maximum
midpoint excursion.

This prevents the result from merely saying that high volume, volatility, or
thin depth predicts price movement.

## Clean evaluation

- Symbols: BTCUSDT and ETHUSDT USD-M futures.
- Training: 2023-08-15 through 2023-11-15 monthly dates already held locally.
- Validation: 2023-12-15 and 2024-01-15 already held locally.
- Originally proposed holdout: monthly 15th from 2024-04-15 through
  2024-09-15. Both symbols returned HTTP 404 on the first date because the
  official daily perpetual `bookTicker` series does not extend into that
  period; no result data were acquired or viewed.
- Source-availability-amended primary holdout, frozen before acquisition:
  2024-01-31, 2024-02-07, 2024-02-21, 2024-03-06, 2024-03-20, and 2024-03-27.
  These are forward of the final validation date, weekly-spaced where possible,
  and exclude both previously inspected 15th dates.
- Previously inspected 2024-02-15 and 2024-03-15 are excluded from the primary
  evaluation.
- BTC and ETH are combined within calendar date before date-cluster inference,
  because their observations are not independent on the same day.

The test passes only if the augmented model improves holdout average precision
by more than 0.02 and Brier score, the high-minus-low excursion interval is
strictly positive, and all six date-level effects are positive. Anything less
closes this local-versus-global implementation.

## Interpretation limit

Passing would establish a distinctive empirical concentration effect, not that
markets literally obey Navier–Stokes or that participants use a particular
incorrect equation. Failing would reject this observable implementation, not
the assumed mathematical result. No paid request is authorized by this plan.

## Result

The frozen gate failed. On the six-date holdout, adding maximum local pressure
and its maximum-to-RMS ratio improved average precision by only 0.0038, below
the required 0.02. Brier score improved by 0.0018 and ROC-AUC by 0.0063, but
these secondary changes do not rescue the primary gate.

Within the ordinary aggregate-state subset, the high-minus-low concentration
effect averaged +0.745 bps, but its six-date interval crossed zero (-1.066 to
+3.478 bps). Three dates had the opposite sign, including clean 2024-01-31 and
2024-03-06. Some March high/low cells were too sparse for useful inference.

Both February holdout dates contained the same Binance month-level ordering
defect in both symbols. They remain in the frozen calculation with the
timestamp guard, but invalidate a clean confirmatory interpretation. A post-hoc
sensitivity excludes defective dates and requires at least 20 observations per
tail per date; too few clean dates meet that requirement for inference.

Hypotheses #1/#2 therefore fail this strengthened free-data implementation.
The result should not be used as an alpha or live-trading signal.
