# Navier–Stokes liquidity hypotheses: exploratory crypto results

Date: 2026-09-13

## Bottom line

The preregistered primary gate failed in both available one-day tests. Adding
the concentration features did not improve average precision for future
60-second BTCUSDT jumps. No targeted feature had a positive 10-minute-block
bootstrap confidence interval on the untouched test segment.

This is evidence against the implemented signals, not a definitive rejection
of the conceptual research program. The full-depth day is before Tardis's
stated data-quality cutoff, and the clean 2024 replication observes BBO rather
than full spatial depth.

## Locked design

- 10-second signal intervals and 60-second forward outcomes.
- First 60% train, next 20% validation, final 20% untouched test.
- Jump threshold fixed from the training period's 95th percentile.
- Baseline: spread, depth, imbalance, realized volatility, trade activity and
  event rate.
- Primary gate: augmented test average-precision improvement greater than 0.02
  and positive Brier improvement.
- Targeted comparisons used non-overlapping 10-minute test blocks and 1,000
  deterministic block-bootstrap resamples.

## Full-depth Tardis day

Source: Binance Futures BTCUSDT, 2020-02-01; 27,199,023 L2 updates reduced to
8,640 ten-second observations using 25 levels per side.

| Test metric | Baseline | Augmented | Increment |
| --- | ---: | ---: | ---: |
| Test average precision | 0.1179 | 0.1160 | -0.0019 |
| Test ROC-AUC | 0.5899 | 0.6095 | +0.0196 |
| Test Brier score | 0.2006 | 0.1937 | +0.0069 improvement |

The ROC and calibration changes were favorable, but the locked primary ranking
metric was not. None of the norm concentration, core contraction, gradients,
curvature, opposing flow, spectral migration, event acceleration,
transport/replenishment, price sensitivity or trajectory tests survived block
resampling. The price-sensitivity comparison was significantly opposite the
proposed direction in this test segment (high-minus-low excursion -0.50 bps;
95% block interval -0.93 to -0.08 bps).

Small-trade impact was 2.11 times larger in the high-gradient subset, but its
block interval for the difference was -49.75 to 139.28, so the apparent effect
is not robust. The stress-conditioned tiny-imbalance slope also failed block
resampling.

## Clean-date Binance BBO replication

Source: Binance public BTCUSDT USD-M futures, 2024-01-15; 19,881,490 BBO events
reduced to 8,641 observations. The parser found zero event-timestamp
backtracks.

| Test metric | Baseline | Augmented | Increment |
| --- | ---: | ---: | ---: |
| Test average precision | 0.1518 | 0.1416 | -0.0102 |
| Test ROC-AUC | 0.5604 | 0.5492 | -0.0112 |
| Test Brier score | 0.2515 | 0.2455 | +0.0060 improvement |

Raw rank correlations for opposing-flow stress and event acceleration were
positive, but every block-bootstrap interval crossed zero. The BBO replication
therefore failed both the primary gate and all targeted directional gates.

## Hypothesis disposition

| Hypotheses | Result under current implementation |
| --- | --- |
| #2 norm concentration | Not supported in either test |
| #4–5 shrinking core / sensitivity | Not supported; price-sensitivity result was opposite in the full-depth holdout |
| #11–14 gradients and curvature | Not supported in the full-depth test |
| #17–18, #22 quadratic or opposing flow | Suggestive raw correlations, not block-robust |
| #21, #39 small-trade amplification | Large point estimate, uncertainty spans both signs |
| #23–24 spectral migration / event acceleration | Not block-robust in either test |
| #45 transport versus replenishment | Not supported |
| #51 displacement per volume | Not supported; full-depth directional test was opposite |
| #52 stress-conditioned tiny imbalance | Not block-robust |
| #53 path dependence / contraction | Not supported |

## Decision

Do not treat these features as an alpha signal and do not spend the remaining
$24 Databento balance based on these results. The final post-cutoff spatial
replication below also failed, so this branch should now be closed unless a new,
independently motivated specification is proposed. The current negative
artifacts should remain frozen so future definitions are not retrofitted to
these days.

## Final free post-cutoff spatial replication

A final official Tardis sample was downloaded for Binance Futures BTCUSDT on
2020-09-01. It contains 5,206,603 reconstructed 25-level snapshots and is after
the vendor's stated collection-quality cutoff. The same locked 10-second /
60-second / 60-20-20 design was applied without trade-flow features.

| Test metric | Baseline | Augmented | Increment |
| --- | ---: | ---: | ---: |
| Test average precision | 0.3238 | 0.3122 | -0.0116 |
| Test ROC-AUC | 0.7686 | 0.7543 | -0.0144 |
| Test Brier score | 0.1105 | 0.1066 | +0.0039 improvement |

The primary gate failed. Norm concentration, gradients, curvature and
core-width trajectory were not supported. Two results were block-robust in the
opposite direction:

- core contraction: high-minus-low future excursion -0.85 bps, 95% block
  interval -1.83 to -0.15 bps;
- event localization: high-minus-low future excursion -1.77 bps, 95% block
  interval -3.62 to -0.18 bps.

This clean spatial result materially strengthens the negative conclusion. Do
not spend the remaining Databento balance on the proposed equity transfer test.

## Measurement-corrected executable-liquidity test

The clean 2020-09-01 snapshot day was then joined to 688,368 matching Tardis
trades. Before running, a new specification froze minimum-side quantity within
1/2/5/10 bps, fixed 1/3/5 BTC sweep costs, impact-curve convexity, 5-bps depth
depletion and recovery, small-trade amplification, and signed-flow/sweep-cost
interaction. The outcome, split, threshold, and primary gate were unchanged.

| Test metric | Baseline | Corrected | Increment |
| --- | ---: | ---: | ---: |
| Test average precision | 0.3047 | 0.3061 | +0.0014 |
| Test ROC-AUC | 0.7384 | 0.7358 | -0.0026 |
| Test Brier score | 0.1156 | 0.1136 | +0.0021 improvement |

The average-precision improvement was far below the preregistered +0.02 gate,
so the primary test failed. None of eight targeted corrected features had both
a positive rank relationship and a strictly positive 10-minute-block bootstrap
interval. The two largest directionally favorable point estimates were also
uncertain:

- small-trade amplification: +0.49 bps high-minus-low excursion, 95% block
  interval -0.40 to +1.38 bps;
- signed flow times 5-BTC sweep cost: +0.71 bps, 95% block interval -0.26 to
  +1.97 bps.

Five-bps executable scarcity was significantly opposite the proposed direction
on the blocked high-minus-low comparison (-1.10 bps, 95% interval -2.80 to
-0.01 bps), although its test rank correlation was also slightly negative and
not significant. A descriptive depletion study found 2,892 depth drops of at
least 20%, with a median 20 seconds to recover 90% of prior depth (censored at
five minutes); this was not used as a predictive feature.

This independently motivated measurement correction therefore does not rescue
the hypothesis family on the available clean day. Close the branch and retain
the frozen artifacts. Do not use the remaining Databento credit for it.

## Next multiscale hypothesis batch

A separate frozen batch tested hypotheses #3, #6, #7, #16, #25, #27–30, #93,
and #94 on the clean 2020-09-01 snapshot/trade day. These definitions had not
been used in the earlier concentration tests. Because this day had already
been inspected for other hypotheses, all results remain exploratory.

| Test metric | Baseline | Multiscale augmented | Increment |
| --- | ---: | ---: | ---: |
| Test average precision | 0.3047 | 0.2738 | -0.0309 |
| Test ROC-AUC | 0.7384 | 0.7071 | -0.0313 |
| Test Brier score | 0.1156 | 0.1054 | +0.0102 improvement |

The combined ranking gate failed. Higher norms did not become progressively
more informative, gradients did not add meaningful lead time, and the
power-law, profile-collapse, shortening-microburst, fine-to-coarse volatility,
regularity-region, and critical-time implementations failed their locked
gates. The proposed safe region was not safe: its jump rate was 3.93% versus
4.24% outside it, with a 6.29% Wilson upper bound.

Two exploratory targeted comparisons survived the clean-day block rule:

- #28 high-to-low Haar signed-flow energy: +0.58 bps high-minus-low excursion,
  95% block interval +0.07 to +1.12 bps, but essentially zero rank correlation;
- #30 cross-scale signed-flow coupling: +1.10 bps, 95% block interval +0.01 to
  +2.50 bps.

Their exact definitions were frozen and replicated without modification on the
already-downloaded 2020-02-01 day. #28 failed and reversed direction. #30
survived: rank correlation +0.070 and high-minus-low excursion +1.28 bps, with
a 95% block interval of +0.46 to +2.18 bps. Adding both candidates to the model
still did not improve ranking (average-precision increment -0.0008).

At that stage #30 was the only surviving candidate, but the 2020-02-01 day
predates Tardis's May 2020 quality cutoff. Its definition was therefore frozen
again and tested on the already-downloaded official Binance 2024-01-15
aggregate trades with event-level BBO midpoint outcomes. On that cleaner date,
the high-minus-low excursion was only +0.15 bps and the 95% block interval was
-0.81 to +1.03 bps. Incremental average precision was effectively zero
(+0.0000005) and Brier score deteriorated by 0.0004.

#30 consequently failed clean-date replication. This next batch has no
surviving replicated signal under its locked implementations. No paid request
was made.

## State-dependent impact batch

Hypotheses #36–38 and #41 were frozen as a causally aligned impact experiment.
Prior-bin spread per displayed near-touch quantity defined liquidity stress;
absolute signed flow normalized by trailing volume defined participation; and
the response was the contemporaneous 10-second midpoint move. Rolling impact
exponents, log-impact curvature, delayed observable permanence, and exponent
change were then used to predict the following 60-second excursion.

On the clean Tardis 2020-09-01 day, the augmented predictive model failed:
average precision changed by -0.0140, ROC-AUC by -0.0163, and Brier score
worsened by 0.0069. #37 impact exponent/convexity, #38 exponent change, and #41
permanence failed their direct gates. #36 state-dependent susceptibility was
the sole exploratory survivor: high prior-stress periods had +0.66 bps greater
susceptibility, with a 95% block interval of +0.23 to +1.14 bps.

The #36 definition was frozen unchanged and tested on the official Binance
2024-01-15 BBO/trade day. The direct effect fell to +0.30 bps with a 95% block
interval of -0.74 to +1.34 bps, so it failed replication. Predictive average
precision improved +0.0127, below the +0.02 gate, while Brier score worsened by
0.0028.

Thus none of #36–38 or #41 survives clean-date replication under these locked
implementations. This result does not test metaorder-level impact because the
free data do not identify parent orders. No paid request was made.

## Conventional-model breakdown test

The research question was reframed to test whether a conventional smooth-state
model becomes systematically wrong when a nonlinear/discrete-feature model
disagrees with it. A ridge regularity model, a nonlinear control using the same
conventional features, and a matched nonlinear model with breakdown features
predicted the next-60-second maximum midpoint excursion. This design separates
extra nonlinear model capacity from extra local/discrete information.

On official Binance 2024-01-15 BBO/trade data, the breakdown model's test MAE
was 3.158 bps versus 2.941 bps for the nonlinear conventional control: 7.4%
worse. High model disagreement did not identify larger conventional errors
(-0.31 bps high-minus-low, 95% block interval -1.24 to +0.47), and the
breakdown model gained no relative advantage there. Lagged observable residual
had a positive raw rank relationship with subsequent excursion but failed
block inference. The breakdown model did reduce top-decile-event MAE from
10.43 to 9.87 bps, but this was not a preregistered pass and required
replication.

The same architecture was mapped to the clean 2020-09-01 25-level
snapshot/trade representation. Breakdown MAE improved only 1.6%, below the 5%
gate. The conventional-error disagreement interval (-0.34 to +1.86 bps),
breakdown-advantage interval (-0.08 to +0.48 bps), and lagged-residual interval
all crossed zero. Its top-decile MAE was slightly worse than the nonlinear
control, so the 2024 tail observation did not replicate.

Hypotheses #46, #47, #48 and #50 therefore fail this operationalization. #49
was not tested because aggregate trades and BBO do not identify child orders,
queue position, or counterfactual single-order movement. Importantly, this does
not show that market participants hold correct assumptions; it shows only that
the selected observable disagreement did not reveal a stable error in the
free data. No paid request was made.

## Multi-day adverse-selection and model-error study

Eight deterministic monthly Binance BTCUSDT dates were acquired from free
official archives and verified against Binance SHA-256 files. Four whole days
were training, two validation, and two holdout. A passive bid or ask was counted
only when a correctly signed aggregate trade reached the most recent timestamp-
eligible quote. Outcomes were BBO midpoint markouts 1, 10, and 60 seconds later;
the primary target was mean 10-second markout per signal bin. These are
touch-qualified hypothetical fills, not actual queue-position fills.

The 2024-02-15 official BBO archive had a severe raw ordering anomaly: 30.5
million rows alternated with far-future timestamps. The raw file was preserved,
the issue was diagnosed before accepting results, and a frozen monotonicity
guard produced the corrected cache from 18.7 million accepted BBO events.

Across 64,088 fill-bearing ten-second bins, the primary #76/model-disagreement
gate failed. On holdout, the conventional model's MAE was 0.970 bps and the
breakdown model's was 0.989 bps, a 1.9% deterioration. High breakdown score was
associated with better, not worse, passive markout on both holdout dates:
+0.21 bps high-minus-low, with the two-date cluster interval +0.06 to +0.36.
Conventional absolute error was also lower in the high-score state. Thus #46,
#50, and #76 are not supported by this implementation.

The preregistered lagged-residual test #47 did survive. When the conventional
model had recently made large, already-observable errors, subsequent passive
markout was 0.46 bps worse, with a two-date cluster interval of -0.55 to -0.36;
both holdout dates had the predicted negative sign. This is the first candidate
in the program to survive two whole holdout dates, but it is not confirmation:
there are only two date clusters, one has the documented timestamp defect, and
ordinary volatility/error clustering is a direct competing explanation. The
next test must freeze controls for lagged absolute markout and realized
volatility and replicate on a different symbol or new untouched dates.

## H47 controlled cross-symbol replication

Before inspecting ETHUSDT results, the BTC candidate was frozen unchanged on
the same eight calendar dates and augmented with market-state controls. The
control set included lagged absolute markout, realized volatility, spread,
depth, imbalance, trade volume, signed flow imbalance, and quote-event rate.
Training errors were constructed out of fold with leave-one-training-day-out
predictions. The primary signal was the portion of lagged conventional-model
error left after a nonlinear model conditioned on those controls.

The uncontrolled ETH result reproduced the BTC pattern: high recent model
error preceded 0.458 bps worse passive markout, with a two-date interval of
-0.492 to -0.424 bps. The controlled result did not. Its high-minus-low effect
was only -0.017 bps and its two-date interval crossed zero (-0.040 to +0.007).
The February date was negative, but March was positive. Adding the error
signals also worsened holdout MAE from 0.9656 to 0.9664 bps rather than meeting
the preregistered 2% improvement gate.

H47 therefore fails the controlled cross-symbol replication. The evidence is
consistent with persistent adverse-selection or volatility states causing both
large conventional-model errors and poor subsequent passive fills; it does not
support a distinct, observable model-breakdown state after those market
conditions are controlled. This remains a test of touch-qualified hypothetical
fills, not queue-position execution. The ETH 2024-02-15 archive had the same
ordering defect as BTC: 25,539,609 rows were rejected by the frozen timestamp
guard and 18,728,016 BBO rows remained. No paid request was made.

## Local-versus-global pressure divergence

The program returned to the original list and selected hypotheses #1/#2 as the
best remaining discriminating experiment feasible with free data. Every
aggregate trade was normalized by the latest timestamp-eligible same-side
touch quantity and aggregated to one second. At each ten-second decision point,
the augmented model received the trailing 60-second maximum pressure and its
maximum-to-RMS ratio. The baseline already contained RMS pressure, total trade
volume, realized volatility, depth, spread, imbalance, signed flow, and quote
event rate. Thus the new variables tested local concentration beyond aggregate
market stress.

Six new BTCUSDT and ETHUSDT holdout dates were frozen before acquisition. The
original April–September dates were source-unavailable: both symbols returned
HTTP 404 at the first official daily BBO path, before any result data were
acquired. A recorded source amendment used six forward, previously uninspected
dates from 2024-01-31 through 2024-03-27 and excluded the already inspected
15th dates. All 24 new free archives matched Binance SHA-256 files.

The primary predictive gate failed. Holdout average precision increased from
0.6272 to 0.6310, only +0.0038 versus the required +0.02. Brier score improved
by 0.0018 and ROC-AUC by 0.0063, but neither was sufficient to rescue the
locked gate. Within the subset where RMS pressure, total volume, volatility,
and mean touch depth were ordinary, the high-minus-low concentration effect
averaged +0.745 bps, but its date-cluster interval crossed zero (-1.066 to
+3.478 bps). Three of six dates had the wrong sign, including two clean dates.

Both February holdout dates contained the same month-level BBO ordering defect
in both symbols. They were retained in the frozen guarded calculation but
invalidate a clean confirmatory reading. A post-hoc sensitivity excluded those
dates and required at least 20 observations in each tail; only one clean date
met that minimum, and its effect was opposite the hypothesis (-0.894 bps).

Hypotheses #1/#2 therefore fail this strengthened free-data implementation.
This result does not say local concentration can never matter; it says the
specific touch-normalized maximum-versus-RMS signal added too little stable
out-of-sample information to justify further trading work. No paid request was
made.

## Joint temporal and touch-depth cascade

A final free partial screen tested the genuinely distinct part of the proposed
liquidity-cascade hypothesis: whether temporal order-flow concentration becomes
dangerous specifically when touch liquidity is simultaneously contracting.
The temporal component was trailing maximum one-second touch-normalized
aggressive pressure divided by its RMS. The spatial proxy was the negative log
change in smoothed BBO touch depth over 60 seconds. Both components were
normalized from training only, and their joint score was the product of their
positive standardized parts.

The comparison was deliberately nested. The control model already contained
all conventional features plus the separate temporal and contraction main
effects; the test model added only their joint interaction. Six untouched
Sundays—2024-01-21, 2024-01-28, and four March Sundays—were frozen before
acquisition. February was excluded in advance because its month-level archive
corruption was already documented. All 24 new BTC and ETH archives passed
Binance checksum verification, and all twelve symbol-days had zero timestamp
rejections.

The interaction failed the primary jump gate. Holdout average precision rose
only from 0.3573 to 0.3602 (+0.0029 versus the required +0.02), while Brier
score worsened by 0.0002. More importantly, the direct effect was stable in the
opposite direction: high joint-cascade states preceded 0.570 bps *smaller*
future excursions, with a six-date interval of -0.861 to -0.257 bps. Every
holdout date was negative. The signed score had essentially zero rank relation
to the subsequent signed return (-0.0022) and a 48.9% high-state hit rate.

Secondary interactions were also too small: +0.0080 average precision for
spread widening and +0.0012 for touch-depth depletion relative to their
main-effect controls. Separate temporal and contraction effects did improve
some forecasts over the conventional baseline, especially depth depletion,
but their conjunction did not create the predicted amplified regime.

The proposed joint cascade therefore fails this free BBO implementation. The
economic policy gate was not tested because BBO and aggregate trades cannot
identify cancellations, queue priority, latency-dependent fills, or realized
fees. The stable opposite direct result may describe post-stress recovery, but
it was not a preregistered trading hypothesis and must not be relabeled as an
edge. No paid request was made.
