# SPYOpeningHourCorrelation-v1 Results

Generated: 2026-06-29T21:09:21-04:00

## Data source

- Instrument: `SPY`.
- Source: Yahoo Chart API `range=730d&interval=60m&includePrePost=false`.
- Data window: 2023-08-01 09:30:00-04:00 to 2026-06-29 15:30:00-04:00.
- Valid sessions evaluated: 721.

## Verdict

SCOUT FAIL

- PASS: `at_least_400_valid_sessions`
- FAIL: `primary_pearson_gt_0_05`
- FAIL: `primary_spearman_gt_0_05`
- FAIL: `positive_bucket_last_hour_mean_gt_negative_bucket`
- FAIL: `positive_vs_negative_last_hour_spread_positive_in_both_halves`


## Primary/secondary correlations

| Relationship | Pearson | Spearman |
|---|---:|---:|
| First hour vs next hour | -0.0067 | 0.0701 |
| First hour vs last hour | 0.0285 | -0.0391 |

## Positive vs negative first hour

| Bucket | Target | N | Mean | Median | Win rate |
|---|---|---:|---:|---:|---:|
| first hour > 0 | next_hour_return | 373 | 0.007% | 0.029% | 56.032% |
| first hour > 0 | last_hour_return | 373 | 0.001% | -0.000% | 49.598% |
| first hour <= 0 | next_hour_return | 348 | -0.018% | -0.018% | 47.701% |
| first hour <= 0 | last_hour_return | 348 | 0.002% | 0.007% | 51.724% |


Last-hour positive-minus-negative mean spread: -0.002%.

## First-hour return quintiles

| First-hour quintile | N | Mean first hour | Mean next hour | Mean last hour |
|---|---:|---:|---:|---:|
| Q1 lowest | 145 | -0.488% | -0.010% | 0.009% |
| Q2 | 144 | -0.146% | -0.049% | -0.014% |
| Q3 | 144 | 0.014% | 0.020% | 0.029% |
| Q4 | 144 | 0.165% | 0.040% | -0.010% |
| Q5 highest | 144 | 0.458% | -0.027% | -0.007% |


## Chronological stability

| Half | N | First-vs-next Pearson | First-vs-last Pearson | Last-hour positive-minus-negative spread |
|---|---:|---:|---:|---:|
| first chronological half | 360 | 0.0931 | -0.0706 | -0.001% |
| second chronological half | 361 | -0.0619 | 0.0994 | -0.003% |


## Interpretation guardrail

This is a descriptive scout only. It does not include trading costs, entry/exit mechanics, WFA, DSR, Monte Carlo, or paper execution checks. If this fails, do not rescue it by changing windows or thresholds inside this hypothesis. If it passes, the next step would be a separate frozen trading-rule Experiment.
