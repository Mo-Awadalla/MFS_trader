# Bitcoin 5m Probability Model v1

## Scope

This is a research-only probability model for the next BTCUSDT perpetual five-minute bar. It estimates:

```text
P(close of the next 5m bar > open of the next 5m bar | information available before the bar)
```

It is an exchange proxy for a BTC five-minute binary event. It is not a Polymarket execution validation because the repository does not contain historical Polymarket quotes, order books, fees, or fills for these contracts.

## Frozen experiment

Specification: `research_scout/bitcoin_5m_probability_binance_v1.json`

- Price source: official Binance public BTCUSDT perpetual 5m klines
- Derivatives source: official Binance public 5m futures metrics
- Label: `1` if close > open, `0` if close < open
- Ties: excluded
- Price features: prior-bar returns, range, candle body, volume/trade-count z-scores, taker flow
- Derivatives features: lagged open-interest changes and long/short ratios
- Availability: derivatives observations are restricted to `create_time <= decision_time - 5 minutes`
- Model: standardized L2 logistic regression, `C=0.1`
- Calibration: separate Platt logistic calibrator
- Model trials: one; no post-result parameter search

Partitions:

- Training: 2020-09-01 through 2023-06-30
- Calibration: 2023-07-01 through 2023-12-31
- Internal validation: 2024
- Final holdout: 2025

## Data and artifacts

The downloader fetched 64 official monthly archives from 2020-09 through 2025-12 and verified every archive checksum.

- Raw/cache and manifest: `data/parquet/bitcoin_5m_probability_binance_v1/`
- Normalized bars: `data/parquet/bitcoin_5m_probability_binance_v1/bars_5m.parquet`
- Eligible feature panel: `data/parquet/bitcoin_5m_probability_binance_v1/panel.parquet`
- Predictions: `data/parquet/bitcoin_5m_probability_binance_v1/predictions.parquet`
- Serialized model: `data/parquet/bitcoin_5m_probability_binance_v1/model.pkl`
- Machine report: `data/parquet/bitcoin_5m_probability_binance_v1/report.json`
- Human report: `data/parquet/bitcoin_5m_probability_binance_v1/report.md`

## Reproduction

```bash
python scripts/download_bitcoin_5m_probability_data.py --workers 8
python scripts/run_bitcoin_5m_probability_model.py
```

The existing derivatives metrics dataset is used from:

```text
data/parquet/binance_bitcoin_derivatives_public_v1/normalized/futures_metrics_5m.parquet
```

## Actual result

The panel contains 465,750 eligible observations.

| Split | Rows | Brier | Log loss | Direction accuracy | Confident coverage | Confident accuracy |
|---|---:|---:|---:|---:|---:|---:|
| Calibration | 52,644 | 0.249411 | 0.691966 | 0.5165 | 0.0307 | 0.5604 |
| Internal validation | 104,370 | 0.249619 | 0.692383 | 0.5162 | 0.0377 | 0.5518 |
| Final holdout | 104,752 | 0.249802 | 0.692750 | 0.5119 | 0.0414 | 0.5471 |

On the final holdout, the constant training-rate baseline had Brier `0.249998` and log loss `0.693144`. The model improved those metrics by only `0.000196` and `0.000394`, respectively.

## Interpretation

The model produces real calibrated probability estimates and modestly beats a constant prior on the final holdout, but the result is weak. A 51.19% directional accuracy with only 4.14% of rows outside the 45%-55% confidence band is not enough to claim a tradable edge.

There is no Polymarket trade result here. To turn this into a prediction-market system, the next separate data step is to record or acquire historical contract-level YES/NO bid/ask and depth data, then compare `p_up` with executable prices after fees, spread, and fill uncertainty.
