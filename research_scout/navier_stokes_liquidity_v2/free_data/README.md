# Free market-data pilot

This directory holds public, no-key datasets used to prototype the
Navier–Stokes liquidity hypotheses. No paid API requests are permitted in this
acquisition stage.

## Tardis sample

- Exchange: Binance USDS-M futures
- Symbol: BTCUSDT
- Date: 2020-02-01
- License/access route: Tardis documented first-of-month sample, downloaded
  without an API key
- Caveat: Tardis flags collection quality issues before 2020-05-14, so this
  file is for schema and pipeline validation, not inference

The acquisition manifest records hashes, sizes, schemas, and source URLs.

## Binance public synchronized day

- Exchange: Binance USD-M futures
- Symbol/date: BTCUSDT, 2024-01-15
- Files: aggregate trades, event-level best bid/offer, 30-second depth
  distribution, and five-minute futures metrics
- Integrity: every ZIP matches Binance's accompanying SHA-256 checksum
- Caveat: `bookDepth` is a coarse percentage-band summary, not reconstructable
  incremental L2. The event-level `bookTicker` file is BBO only.

This day is usable for order-flow/BBO/leverage prototyping, but it does not
replace post-cutoff multi-level incremental data for the central spatial test.

## Multi-day Binance BBO/trade panel

- Symbol: BTCUSDT USD-M futures
- Dates: monthly 15th from 2023-08-15 through 2024-03-15
- Files: official daily `bookTicker` and `aggTrades` ZIPs plus checksums
- Integrity: all 16 archives match their official SHA-256 checksum files
- Cost: free public archives; no paid request

The 2024-02-15 `bookTicker` archive contains 30,515,198 interleaved rows whose
timestamps jump far forward and then backward. The pipeline preserves the raw
archive and reports the anomaly. Its corrected cache rejects BBO rows that move
backward or jump more than 60 seconds beyond the last accepted event. Results
involving that date must retain this caveat.

## ETH cross-symbol replication panel

- Symbol: ETHUSDT USD-M futures
- Dates: the same monthly 15th dates from 2023-08-15 through 2024-03-15
- Files: official daily `bookTicker` and `aggTrades` ZIPs plus checksums
- Integrity: all 16 ETH archives match their official SHA-256 checksum files
- Cost: free public archives; no paid request

The ETH 2024-02-15 `bookTicker` archive has the same ordering defect as the BTC
archive. The frozen timestamp guard rejected 25,539,609 rows and retained
18,728,016 BBO rows. The other seven ETH dates had no timestamp-row rejection.

## Local-versus-global concentration holdout

- Symbols: BTCUSDT and ETHUSDT USD-M futures
- Dates: 2024-01-31, 2024-02-07, 2024-02-21, 2024-03-06, 2024-03-20, and
  2024-03-27
- Files: official daily `bookTicker` and `aggTrades` ZIPs plus checksums
- Integrity: all 24 new archives match their official SHA-256 files
- Cost: free public archives; no paid request

The 2024-02-07 and 2024-02-21 BBO archives have the same month-level ordering
defect for both BTC and ETH. January 31 and all three March dates had zero rows
rejected by the frozen timestamp guard. February results must not be described
as clean confirmation.

## Joint-cascade clean holdout

- Symbols: BTCUSDT and ETHUSDT USD-M futures
- Dates: 2024-01-21, 2024-01-28, 2024-03-03, 2024-03-10, 2024-03-17, and
  2024-03-24
- Files: official daily `bookTicker` and `aggTrades` ZIPs plus checksums
- Integrity: all 24 archives match their official SHA-256 files
- Timestamp quality: zero rejected rows across all twelve symbol-days
- Cost: free public archives; no paid request

February was excluded before these dates were chosen because the earlier panel
had established a month-level ordering defect. This is the cleanest multi-day,
cross-symbol BBO/trade holdout in the program.

## Post-cutoff 25-level replication

- Exchange/symbol/date: Binance USDS-M futures BTCUSDT, 2020-09-01
- Dataset: Tardis `book_snapshot_25`, linked directly from its official data-type documentation
- Size: 199,978,111 bytes compressed; 3,989,831,091 bytes expanded
- Rows: 5,206,603
- SHA-256: `c9ce8ae07da3fe22ed2b8bca00290c8875f9234cbe9e7734ff3ef662eb4d4712`
- Integrity: full gzip CRC passed

This file is after Tardis's stated May 2020 collection-quality cutoff. It
supports the spatial profile tests but not add/cancel-flow reconstruction.

## Matching post-cutoff trades

- Exchange/symbol/date: Binance USDS-M futures BTCUSDT, 2020-09-01
- Dataset: Tardis `trades`, downloaded without an API key
- Size: 8,299,661 bytes compressed; 59,643,178 bytes expanded
- Rows: 688,368
- SHA-256: `3441921db5e41014735ab9b3b7ff53a87feffe59db057c51251830c81b3cfa7d`
- Integrity: full gzip CRC passed

This file is synchronized to the 25-level snapshot day and permits the
measurement-corrected executable-liquidity and trade-flow test.
