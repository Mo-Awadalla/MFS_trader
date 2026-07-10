# Free Public Bitcoin Derivatives Dataset v1

Status: **DOWNLOADED, CHECKSUM-VERIFIED, NORMALIZED, AND INTEGRITY-AUDITED**

Purpose: assemble the minimum honest public dataset needed to formulate a new, non-latency Bitcoin derivatives hypothesis after rejection of the price-only U.S.-session timing strategy. This artifact does **not** test a return hypothesis and does not tune a trading rule.

## Scope

- Venue: Binance only
- Instrument family: BTCUSDT spot and USDⓈ-M perpetual
- Raw source: <https://data.binance.vision/>
- Source documentation: <https://github.com/binance/binance-public-data>
- Period: 2020-01-01 through 2025-12-31
- Base research interval: 30 minutes
- Positioning metrics interval: native 5 minutes plus a point-in-time 30-minute last-observation view
- Funding interval: 8 hours
- Access: no account, API key, or paid subscription used

“Public” means anonymously downloadable from Binance. It does **not** mean the repository states an open-data license. Binance terms still apply, and this dataset should not be represented as openly licensed or consolidated market data.

## Dataset location

Root:

`data/parquet/binance_bitcoin_derivatives_public_v1/`

Key evidence:

- `manifest.json`: every archive URL, official checksum text, verified SHA-256, byte count, local path, and normalized-file hash
- `integrity_report.json`: coverage, gaps, duplicates, null fields, synchronization, and point-in-time usage rules
- `raw/`: official ZIP and `.CHECKSUM` files
- `normalized/`: typed Parquet datasets

Downloader:

`scripts/download_binance_bitcoin_derivatives_dataset.py`

Independent integrity audit:

`scripts/validate_binance_bitcoin_derivatives_dataset.py`

## What was collected

| Product | Native frequency | Coverage | Rows | Why it is needed |
|---|---:|---|---:|---|
| BTCUSDT spot klines | 30m | 2020-01-01–2025-12-31 | 105,135 | Executable spot price, spot volume, trades, taker-buy volume, and a venue-local spot/perp basis |
| BTCUSDT perpetual klines | 30m | 2020-01-01–2025-12-31 | 105,216 | Executable perpetual price, volume, trades, and taker-buy volume |
| Mark-price klines | 30m | 2020-01-01–2025-12-31 | 104,832 | Liquidation/funding reference distinct from trade price |
| Index-price klines | 30m | 2020-01-01–2025-12-31 | 104,640 | Binance reference index and mark/index dislocation |
| Premium-index klines | 30m | 2020-01-01–2025-12-31 | 104,877 | Direct measure used in the perpetual funding mechanism |
| Settled funding rates | 8h | 2020-01-01–2025-12-31 | 6,576 | Realized carrying payment, usable only at/after settlement timestamp |
| Futures metrics | 5m | 2020-09-01–2025-12-31 | 560,389 | Open interest/value plus Binance-defined crowding and taker-ratio aggregates |
| Futures metrics, point-in-time view | 30m | 2020-09-01–2025-12-31 | 93,447 | Last observation in `(t-30m, t]`, labeled at availability time `t` |

The raw archives occupy about 50 MB, normalized Parquet about 68 MB, and the complete evidence tree about 119 MB. There are 2,380 official archives totaling 42,880,038 compressed bytes. Every archive matched its official Binance SHA-256 checksum.

## Fields now available

### Spot and perpetual trade-price klines

- open, high, low, close
- base volume and quote volume
- trade count
- taker-buy base and quote volume
- exact open and close timestamps

These permit fixed-horizon execution and coarse flow diagnostics without downloading event-level trades.

### Reference-price products

- mark-price OHLC
- index-price OHLC
- premium-index OHLC

These are not executable prices. They are reference/state variables. Any strategy must execute against spot or perpetual trade prices and apply fees, spread/slippage, and funding separately.

### Funding

- `calc_time`
- `funding_interval_hours`
- `last_funding_rate`

All 6,576 normalized rows have a non-null rate and an eight-hour interval. Historical settled funding is not allowed to appear before `calc_time`. To anticipate a settlement, a hypothesis must use the already-observed premium index or a documented contemporaneous estimate—not the future settled rate.

### Futures positioning metrics

- aggregate open interest in BTC
- aggregate open-interest value
- top-trader long/short account ratio
- top-trader long/short position ratio
- global long/short account ratio
- taker long/short volume ratio

The ratios are exchange-defined aggregates, not trader-level positions. Open interest does not reveal whether newly opened exposure is long or short; direction must come from a separate point-in-time variable such as price, premium, or taker imbalance.

## Integrity findings

### Kline coverage

The full six-year grid contains 105,216 half-hour timestamps.

- Perpetual trade-price klines: complete, with zero missing half-hours.
- Spot klines: 81 missing half-hours.
- Mark price: 384 missing half-hours.
- Index price: 576 missing half-hours.
- Premium index: 339 missing half-hours.
- All five required products are simultaneously present for 104,316 timestamps, or **99.1446%** of the full grid.
- There are 900 timestamps not common to every product.

The gaps include whole-day/multi-day holes in some reference-price archives, especially during 2021–2023. They are preserved as missing. They must not be forward-filled. A strategy requiring all five products should admit only common timestamps and require complete formation/execution windows.

### Futures metrics coverage

- Aggregate open-interest fields: no null rows.
- Top-trader account-ratio nulls: 92,226 native rows.
- Top-trader position-ratio nulls: 92,192 rows.
- Global account-ratio nulls: 5,797 rows.
- Taker-ratio nulls: 37,271 rows.
- 3,048 observations have actual timestamps that are not exactly on the five-minute grid.
- 3,683 exact grid timestamps are absent, but many are replaced by nearby off-grid observations rather than true missing periods.

The actual `create_time` is preserved. Off-grid observations may be used only after their real timestamp; they must not be rounded backward. The crowding-ratio fields do not support a clean full-period test without a declared missing-data policy. Open interest does.

### Timestamp format changes

Binance archives contain:

- old headerless CSVs
- newer CSVs with documented headers
- millisecond epochs
- microsecond epochs
- archives that span the millisecond-to-microsecond migration

The parser now handles documented headers and mixed timestamp units row by row. It rejects unknown schemas, malformed OHLC, duplicates, off-grid kline bars, checksum mismatches, oversized archives, redirects, and unexpected ZIP members.

## Data deliberately not downloaded

### Event-level trades and aggregate trades

They are publicly available but unnecessary for a 30-minute-to-eight-hour non-latency hypothesis and much larger than kline data. The 30-minute spot/perpetual klines already contain trade count, volume, and taker-buy volume. Event-level data would be justified only for a separately frozen execution/microstructure hypothesis.

### `bookTicker`

Public futures history begins only around May 2023 and can be roughly tens of megabytes per day for BTCUSDT. A sampled day was about 54 MB compressed. It would create a very large, short-history dataset and is not necessary for the proposed mechanism.

### `bookDepth`

Public futures percentage-depth snapshots begin in 2023. They report cumulative depth at ±1% through ±5%; they are not a reconstructable full order-event book. They could support a separate 2023+ liquidity hypothesis, not the current six-year derivatives-state study.

### Liquidations

No BTCUSDT files were found under the official USDⓈ-M `liquidationSnapshot` archive prefix. Claims based on historical liquidation events would require a different provider or an unverifiable reconstruction. Therefore liquidation data is **not** part of the next hypothesis.

### Cross-exchange data

No Bybit, Deribit, Coinbase, CME, or consolidated spot data was collected. A Binance-only result cannot be called a global Bitcoin derivatives effect or cross-exchange price discovery.

## What this data can honestly support

The dataset supports formulation of a Binance-specific hypothesis involving:

1. spot/perpetual trade-price dislocation;
2. mark/index/premium state;
3. settled funding as lagged information;
4. changes in open interest;
5. coarse, Binance-defined taker or trader-ratio diagnostics where available;
6. fixed delayed entries and 30-minute-to-eight-hour holding periods.

It does not, by itself, establish whether crowded premium predicts continuation or reversal. Funding exists to anchor perpetuals to spot, but a positive premium can mean either persistent demand/risk compensation or unstable leveraged crowding. The expected sign must come from source evidence and be frozen before return inspection.

## Provisional next-hypothesis shape—not yet tested

A defensible family is **post-settlement crowded-long risk**:

- At one predeclared daily decision time, observe only information available at the completed funding settlement.
- Primary falsification claim: unusually positive **already-settled** funding combined with elevated or expanding OI predicts a lower subsequent 24-hour BTC spot return or a worse downside-tail probability.
- Run funding-only, OI-only, and basis-only controls. Do not hide them inside a weighted “crowding score.”
- Delay execution until the next complete bar; never trade on the same bar that finalized a feature.
- Execute against perpetual or spot trade prices, not mark/index prices.
- Include round-trip fees, slippage, and any funding payment crossed by a perpetual position.
- Use a simple rule before any ML model.

The expected sign is intentionally labeled **weak evidence** rather than a published anomaly. Positive funding can accompany persistent bullish demand, and OI is not directional because every contract has a long and a short. The proposed negative sign is therefore a preregistered falsification claim, not something the literature has established. Exact decision time, expanding-window threshold, OI representation, outcome, trade expression, costs, and partitions still need to be frozen before any return inspection.

## Point-in-time rules for the eventual scout

1. Kline features become available only after their close boundary.
2. Entry must use a later bar open, never the bar whose close produced the feature.
3. Settled funding becomes available only at/after `calc_time`.
4. Metrics become available only at/after actual `create_time`.
5. Missing reference-price products invalidate the required window; do not fill.
6. Ratio nulls are missing, not neutral values.
7. Funding crossed while holding must be applied with the correct payer/receiver sign.
8. Preserve and report both BTC open interest and USD notional open interest. BTC OI avoids mechanically embedding the contemporaneous price in the primary change variable; USD notional better represents capital exposure. The eventual spec must predeclare which is primary rather than selecting whichever backtests better.
9. Spot/perpetual basis must use synchronized timestamps and separately account for the executable leg(s).
10. Data from 2024–2025 should remain an untouched final holdout once the hypothesis and development partition are frozen.

## Source basis and limits

- Ackerer, Hugonnier, and Jermann, “Perpetual Futures Pricing,” NBER Working Paper 32936, DOI `10.3386/w32936`: establishes the anchoring role of periodic funding and formal perpetual pricing. It does not establish a retail after-cost directional rule.
- Makarov and Schoar, “Trading and Arbitrage in Cryptocurrency Markets,” JFE 2020, DOI `10.1016/j.jfineco.2019.07.001`: establishes persistent segmentation and arbitrage frictions across crypto markets. It does not prove a Binance-only intraday basis-reversal strategy.
- Alexander and Heck, “Price discovery in Bitcoin: The impact of unregulated markets,” Journal of Financial Stability 2020, DOI `10.1016/j.jfs.2020.100776`: supports studying spot/derivatives price discovery, but venue/sample transfer must be explicit.

These sources motivate the state variables. They do not yet justify a specific threshold, holding period, or expected sign. Any stronger claim would be dishonest.

## Readiness verdict

**Data readiness: PASS for a bounded Binance BTCUSDT derivatives-state scout.**

**Hypothesis readiness: PASS only for freezing a weak-evidence crowded-long falsification spec; no source proves the expected sign.**

**ML readiness: NOT YET.** A simple expected-sign scout must establish gross information first. ML may later be tested as a separately registered risk/skip model, not as a way to discover filters in this consumed dataset.
