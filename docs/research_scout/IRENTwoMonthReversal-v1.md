# IREN: is the apparent two-month boom-bust pattern stable?

Date: 2026-07-23

## Verdict

The one-year chart makes a roughly two-month reversal story visually plausible, but the frozen historical test **does not validate a stable or timeable cycle**.

On pre-discovery data from 2021-11-18 through 2025-07-22, consecutive 42-trading-day returns had essentially zero correlation (`+0.003`, one-sided permutation `p=0.599`). Only 9 of 20 transitions changed sign (45%; exact 95% binomial interval 23%-69%). After contemporaneous adjustment for Bitcoin and QQQ returns, correlation was `-0.175`, but it was not statistically distinguishable from chance (`p=0.288`). The full predeclared gate failed.

This result argues against trading IREN as if it has a dependable calendar-like up/down rhythm. It does not prove that individual rallies cannot overshoot or reverse.

## Chart observation, then hypothesis

I first used only the latest one-year adjusted-close chart, 2025-07-23 through 2026-07-22. IREN ranged from $15.40 to $76.41. Several large legs looked unusually regular:

| Swing | Approximate move | Calendar duration |
|---|---:|---:|
| 2025-08-01 low to 2025-11-05 high | +396% | 96 days |
| 2025-11-05 high to 2025-12-17 low | -55.8% | 42 days |
| 2025-12-17 low to 2026-01-28 high | +86.3% | 42 days |
| 2026-01-28 high to 2026-03-30 low | -49.8% | 61 days |
| 2026-03-30 low to 2026-05-27 high | +114.5% | 58 days |
| 2026-05-27 high to 2026-07-17 low | -50.4% | 51 days |

That led to one frozen hypothesis:

> IREN has a stable roughly two-month boom-bust tendency: a 42-trading-day return predicts an opposite-signed next 42-trading-day return, including after adjustment for Bitcoin and QQQ returns.

The hypothesis, horizon, statistics, success gate, random seed, and robustness checks were written to `research_scout/iren_two_month_reversal_prereg_v1.json` before older IREN or benchmark history was tested. The one-year discovery window was excluded from the primary test.

## Test design

- Public adjusted closes: IREN, BTC-USD, and QQQ from Yahoo Finance's chart endpoint.
- Untouched test window: 2021-11-18 to 2025-07-22, ending immediately before the discovery chart.
- Primary horizon: 42 trading days, chosen in advance as approximately two months.
- Sampling: 21 non-overlapping blocks, giving 20 adjacent transitions.
- Primary statistic: lag-1 correlation between consecutive block log returns.
- Inference: 50,000 one-sided permutations with seed `20260723`.
- Factor diagnostic: regress daily IREN log returns on same-interval BTC and QQQ returns, then repeat the block test on residual returns.
- Success required all four conditions: significant negative raw correlation; significant negative factor-adjusted correlation; at least 60% sign alternation; negative correlation in both chronological halves.
- Fixed robustness checks: 21- and 63-trading-day horizons, plus all 42 possible block-start phases. These could not rescue a failed primary test.

## Results

### Primary 42-day test

| Measure | Raw IREN | BTC/QQQ-adjusted |
|---|---:|---:|
| Blocks / transitions | 21 / 20 | 21 / 20 |
| Lag correlation | +0.003 | -0.175 |
| One-sided permutation p-value | 0.599 | 0.288 |
| Opposite-sign transitions | 9/20 (45%) | 13/20 (65%) |
| First-half correlation | +0.199 | -0.131 |
| Second-half correlation | -0.112 | -0.091 |

Every predeclared raw-series gate failed. The adjusted sign-alternation rate looks better, but its exact 95% interval is wide (41%-85%), and the correlation test remains non-significant.

### Factor exposure

The full historical daily regression estimated:

- BTC beta: `0.69`
- QQQ beta: `1.33`
- Daily R-squared: `25.3%`

So broad crypto and growth-equity moves explain a meaningful portion of IREN's daily variation, but about three quarters of daily variance remained unexplained by this simple two-factor model. The chart should not be reduced to “Bitcoin with fixed leverage.” IREN's current business positioning also includes AI cloud and power-dense data centers, making company news and changing narrative exposure plausible sources of regime shifts.

### Robustness, reported without selecting a winner

- 21-day raw correlation: `+0.110` (`p=0.809`); adjusted: `-0.176` (`p=0.161`).
- 63-day raw correlation: `+0.096` (`p=0.735`); adjusted: `-0.427` (`p=0.079`).
- Across all 42 block-start phases, 41 of 42 raw correlations were negative; the median was `-0.243`, with a range from `-0.391` to `+0.003`.

The phase diagnostic is the only suggestive evidence for medium-horizon mean reversion. It is not an independent set of 42 tests: phases reuse nearly all the same returns, no phase-level significance rule was preregistered, and choosing the best phase after seeing results would be overfitting. A truly stable calendar-like cycle should not require choosing a favorable starting day.

## Interpretation

The latest year contains a striking sequence of roughly 40%-55% declines and 85%-115% rebounds. The historical record, however, does not show that “up for about two months” reliably forecasts “down for about two months,” or vice versa. The visual pattern is likely a small-sample combination of:

1. high sensitivity to crypto and growth-equity risk appetite;
2. company-specific repricing around Bitcoin-mining economics, AI infrastructure, financing, capacity, and contracts; and
3. volatility clustering, which produces visually compelling waves without a fixed periodic clock.

The disciplined conclusion is **weak/inconclusive evidence of medium-horizon mean reversion, no validated two-month cycle**. This analysis does not provide a buy or sell signal at the current price.

## Limitations

- IREN has only been public since late 2021, leaving 21 independent 42-day blocks and low statistical power.
- Yahoo Finance is a convenient public source, not an exchange-grade research feed; the script downloads the data again on each run.
- The BTC/QQQ regression is descriptive, uses constant full-period betas, and does not capture changing Bitcoin-mining versus AI exposure.
- BTC trades continuously while IREN and QQQ do not; the aligned returns accumulate BTC moves between equity sessions but do not model intraday timing.
- No earnings, contract, financing, power-price, hash-price, dilution, options, or short-interest event data were tested. Adding those after seeing this result would require a new frozen hypothesis and a new untouched sample.
- This tests predictability, not a costed trading strategy. Statistical mean reversion would still need execution, borrow, gap, and risk analysis.

## Reproduction and sources

Run:

Frozen-input replay:

`python research/iren_two_month_reversal_scout.py --input-prices experiments/iren_two_month_reversal_v1/input_prices.csv --output experiments/iren_two_month_reversal_v1/results.json`

Omit `--input-prices` to refresh the public Yahoo data. The preserved input file has SHA-256 `29e641fc4fb1b20fb06aaa2ca6189615f6077987361be1f3ea2e287de56e5d7d`.

Artifacts:

- Frozen specification: `research_scout/iren_two_month_reversal_prereg_v1.json`
- Analysis code: `research/iren_two_month_reversal_scout.py`
- Preserved aligned public inputs: `experiments/iren_two_month_reversal_v1/input_prices.csv`
- Full machine-readable output: `experiments/iren_two_month_reversal_v1/results.json`

Public sources:

- Yahoo Finance IREN chart: https://finance.yahoo.com/quote/IREN/chart/
- Yahoo Finance chart endpoint used by the script: https://query2.finance.yahoo.com/v8/finance/chart/IREN
- IREN company site (current AI cloud/data-center positioning): https://iren.com/
- SEC issuer page, CIK 1878848: https://www.sec.gov/edgar/browse/?CIK=1878848&owner=exclude
