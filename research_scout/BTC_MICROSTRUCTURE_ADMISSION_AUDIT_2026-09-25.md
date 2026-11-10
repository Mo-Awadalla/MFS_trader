# BTC microstructure data admission audit — 2026-09-25

## Decision

**Admit 17 of 20 shared Binance BTCUSDT days for a returns-blind BBO/trade feasibility pilot. Quarantine 2024-02-07, 2024-02-15, and 2024-02-21 for causal BBO replay.** Their quote files contain 41,676,789 backward event-time steps in total, with the same number of nonincreasing update IDs. Sorting those archives after the fact is not an audited repair.

The 17 admitted days are a selected historical sample, not a confirmatory holdout. No future return, strategy P&L, or signal threshold was computed here.

## Inputs and checks

The audit streamed every local `BTCUSDT-aggTrades` and `BTCUSDT-bookTicker` ZIP on the 20 shared dates from 2023-08-15 through 2024-03-27. It also scanned the single `bookDepth` and `metrics` ZIP on 2024-01-15. All 42 SHA-256 values matched their adjacent `.CHECKSUM` files; reading every ZIP member also completed its decompression and CRC check. The audit examined 422,281,805 BBO rows and 30,231,994 aggregate-trade rows. The empty 2024-04-15 directory was excluded.

| Check | Result |
| --- | ---: |
| Archives with matching SHA-256 | 42 / 42 |
| Aggregate-trade timestamp backtracks, nonincreasing IDs, malformed rows, invalid price/quantity, or wrong-date rows | 0 |
| BBO malformed rows, crossed/nonpositive quotes, or transaction time after event time | 0 |
| BBO dates with monotonic event time and update ID | 17 / 20 |
| BBO backward steps on three quarantined February dates | 41,676,789 |
| BBO rows just outside archive UTC date on otherwise ordered days | 38 |
| Forward BBO gaps over five seconds on ordered days | 5 total; longest 7.776 seconds |

The 38 boundary rows occur on 2024-01-15, 2024-03-03, 2024-03-20, and 2024-03-24. A downstream replay must filter by the actual UTC event date and enforce quote freshness at each decision. A forward gap is not proof that liquidity vanished; it may reflect no BBO update, a feed interruption, or an archive boundary.

## OI availability

The authoritative normalized `futures_metrics_5m.parquet` was checked at all 288 five-minute UTC decision points on each of the 20 dates. A row was eligible only when `create_time + 5 minutes <= decision_time`; its available age had to be at most ten minutes and its BTC-denominated OI positive. **All 5,760 decision points had eligible OI.** The largest within-date gap between OI observations was 5.05 minutes. This checks timestamp availability under a conservative fixed lag, not actual historical publication latency.

## Per-date BBO order and gaps

| UTC date | BBO rows | Backward event-time steps | Rows outside date | Forward gaps >5s | Longest forward gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2023-08-15 | 9,904,366 | 0 | 0 | 1 | 5.059s |
| 2023-09-15 | 12,583,798 | 0 | 0 | 1 | 5.922s |
| 2023-10-15 | 7,613,922 | 0 | 0 | 1 | 5.310s |
| 2023-11-15 | 11,714,235 | 0 | 0 | 1 | 7.776s |
| 2023-12-15 | 13,814,038 | 0 | 0 | 0 | 3.498s |
| 2024-01-15 | 19,881,490 | 0 | 34 | 0 | 3.900s |
| 2024-01-21 | 14,836,148 | 0 | 0 | 0 | 3.978s |
| 2024-01-28 | 23,941,048 | 0 | 0 | 0 | 1.467s |
| 2024-01-31 | 34,897,622 | 0 | 0 | 0 | 2.445s |
| 2024-02-07 | 28,468,392 | 9,740,376 | 6 | 9,740,376* | 63,666.656s* |
| 2024-02-15 | 49,243,214 | 18,728,015 | 0 | 18,728,016* | 66,758.214s* |
| 2024-02-21 | 31,936,414 | 13,208,398 | 5 | 13,208,398* | 50,929.748s* |
| 2024-03-03 | 30,366,437 | 0 | 1 | 0 | 0.829s |
| 2024-03-06 | 24,006,279 | 0 | 0 | 0 | 1.405s |
| 2024-03-10 | 12,541,001 | 0 | 0 | 0 | 2.355s |
| 2024-03-15 | 26,651,695 | 0 | 0 | 1 | 5.100s |
| 2024-03-17 | 16,828,710 | 0 | 0 | 0 | 3.400s |
| 2024-03-20 | 23,727,779 | 0 | 2 | 0 | 3.014s |
| 2024-03-24 | 13,510,787 | 0 | 1 | 0 | 2.936s |
| 2024-03-27 | 15,814,430 | 0 | 0 | 0 | 4.280s |

`*` The forward-gap measures on the disordered February streams are artifacts of file ordering and must not be interpreted as market gaps.

## Scope of the next test

The 17 ordered days can support an exploratory BBO withdrawal and signed aggregate-trade study with explicit decision latency, quote-age limits, and date-blocked evaluation. They cannot identify individual cancellations, full-depth withdrawal, forced liquidations, or an executable edge. The single local `bookDepth` file is a percentage-depth snapshot, not an incremental L2 book. A stronger leverage-unwind test needs synchronized liquidation observations; a cancellation test needs gap-checked incremental L2 on overlapping dates. Earlier development outcomes remain part of the multiple-testing record.

Reproduce with `python -m research_scout.audit_btc_microstructure_admission --workers 4`. Machine-readable [per-date measurements](btc_microstructure_admission_20260925.json) include all archive hashes, row counts, timestamp checks, gap counts, and OI availability.
