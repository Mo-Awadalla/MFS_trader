# Bitcoin 5m Polymarket Proxy Check v1

## Scope

This check compares the frozen Binance BTCUSDT perpetual five-minute probability model with resolved Polymarket `BTC Up or Down 5m` contracts. It is an outcome-transfer and calibration check, not an executable trading backtest.

Polymarket resolves these contracts from the Chainlink BTC/USD stream. The existing model predicts whether a Binance BTCUSDT perpetual five-minute bar closes above its open, so the labels are related but not identical.

## Public dataset

Downloader: `scripts/download_polymarket_bitcoin_5m_dataset.py`

Local artifacts are written under:

```text
data/parquet/polymarket_bitcoin_5m_public_v1/
```

The generated dataset contains:

- 54,626 five-minute contracts from December 18, 2025 through July 11, 2026
- 54,338 resolved outcomes
- 1,545,307 public sampled-price observations
- 8,920 contracts with both Up and Down sampled prices before the event start
- 31 daily sampled-price partitions, reflecting the public API's observed history window

The downloader records contract metadata, token IDs, resolution outcomes, sampled one-minute token-price history, decision-time price snapshots, artifact hashes, and source URLs. Heavy generated artifacts remain ignored by Git.

## Frozen-model overlap

The existing Binance feature panel and model predictions end on December 31, 2025. Exact timestamp matching therefore produces only a short overlap:

- 3,951 resolved Polymarket contracts
- December 18–31, 2025
- All rows belong to the already-opened final holdout
- Polymarket/Chainlink and Binance directional labels agree on 96.68% of rows

## Result

Against Polymarket outcomes:

| Metric | Result |
|---|---:|
| Rows | 3,951 |
| Up rate | 51.18% |
| Brier score | 0.249392 |
| Constant training-prior Brier | 0.250016 |
| Brier improvement | 0.000624 |
| ROC AUC | 0.5312 |
| Directional accuracy | 51.86% |
| Predictions outside 45%–55% | 147 |
| Confident coverage | 3.72% |
| Confident accuracy | 63.27% |

Using daily blocks, the mean Brier improvement is `0.000605`. Its 95% interval is approximately `[-0.000083, 0.001293]`, with 10 of 14 days positive. The short overlap is therefore suggestive, not conclusive.

## Interpretation

The weak Binance signal transfers in the expected direction to actual Polymarket resolutions. This is encouraging evidence that the model is not purely tied to Binance label noise, but it does not establish tradability.

No historical sampled Polymarket prices are available for the December overlap. The public sampled-price endpoint exposed approximately the most recent 30 days during collection, and sampled prices are not historical executable bid/ask quotes. Consequently, this check cannot measure model edge over the market, fees, spread, depth, queue position, or realized fills.

The model remains research-only. A valid next experiment is forward-only: generate frozen model probabilities from current Binance inputs at each contract start, compare them with fresh Polymarket decision prices, and evaluate probability edge after the documented crypto fee schedule. Promotion requires enough independent days and contracts, stable calibration, and positive net edge without changing the frozen model after observing results.
