# Funding Distribution Study

This is a read-only descriptive study of settled Binance USDⓈ-M perpetual funding
rates. It does not inspect returns after settlement, assess an edge, select a
threshold, or change an Experiment.

## Source semantics and units audit

The ingestion boundary preserves Binance's `fundingRate` value as a decimal
fraction. It does not interpret the field as a percentage and does not rescale it
while writing Parquet. The reporting conversion is:

```text
funding_rate_decimal * 10,000 = funding_rate_bps
```

Worked example: Binance `fundingRate = "0.00010000"` is
`0.00010000 * 10,000 = 1.0000 bp`, equivalently `0.01%`. Thus a 20 bp screen
corresponds to a raw absolute rate of `0.00200000`, not `0.00002000` or
`0.20000000`.

Binance documents `GET /fapi/v1/fundingRate` as the USDⓈ-M settled funding-rate
history endpoint. Its response carries `symbol`, the string-valued decimal
`fundingRate`, millisecond `fundingTime`, and the associated `markPrice`.
`startTime` is inclusive, results are returned in ascending order, and the endpoint
pages at up to 1,000 records. Binance separately documents
`GET /fapi/v1/fundingInfo` for symbols whose funding cap, floor, or interval has
been adjusted; therefore an unconditional fixed-eight-hour assumption is not a
valid description of every historical settlement sequence.

Sources:

- [Binance USDⓈ-M Futures market-data API: funding history and funding info](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)
- [Binance public funding-history page](https://www.binance.com/en/futures/funding-history/perpetual/funding-fee-history)
- [CoinGlass funding-rate chart methodology](https://www.coinglass.com/FundingRate)
- [CoinGlass historical funding-rate API](https://docs.coinglass.com/reference/fr-ohlc-histroy)

## External extreme-print cross-check record

The intended comparison was the ten largest positive and ten most negative lake
prints for each symbol against a timestamped external history. It could not be
completed independently in this environment:

- CoinGlass's public chart describes its displayed values as eight-hour rates but
  did not expose timestamped historical rows to the page reader. Its historical
  OHLC endpoint requires a paid API plan/key, which was not available.
- Direct, unauthenticated calls to Binance's official
  `GET https://fapi.binance.com/fapi/v1/fundingRate` endpoint returned HTTP 451
  from this execution location for every requested extreme timestamp.
- A public Xoomar cross-exchange history endpoint was accessible without a key,
  but `history=all` returned only 5,000 interleaved rows across venues. Its
  retained Binance overlap did not reach the historical top-extreme dates in the
  lake, so it could not independently verify those prints.
- A public Binance-mirror endpoint documented by Primit was also tried. It
  returned HTTP 503 and then timed out. Because it is a transparent Binance
  proxy, even a successful comparison would have been a transport-path check,
  not an independent-provider check.

Accordingly, no external values are represented as verified and no fabricated
side-by-side matches are shown. The generated extreme tables below are lake
observations only until a CoinGlass credential or a non-region-blocked official
Binance request path is supplied. A later audit should record provider, access
time, exact UTC settlement timestamp, our decimal/bps value, external displayed
value, its stated interval normalization, and the signed difference.

Supporting accessibility/methodology references:

- [Xoomar no-key funding-rate API](https://xoomar.com/markets/api/funding-rates)
- [Primit Binance funding-history mirror documentation](https://docs.pipai.org/market-data/rest/funding-rate/)

## Generated results

### Coverage

| symbol | requested_listing_start | observed_start | observed_end | scheduled_rows | listing_complete | rest_status |
|---|---|---|---|---|---|---|
| BTCUSDT | 2019-09-01 | 2020-01-01 | 2026-06-30 | 7119 | False | not requested |
| ETHUSDT | 2019-11-01 | 2020-01-01 | 2026-06-30 | 7119 | False | not requested |
| SOLUSDT | 2020-09-01 | 2020-09-13 | 2026-06-30 | 6349 | False | not requested |

Rows before 2021-12-21 are outside the OI-testable window. `full_history` means all funding observations currently recovered in the lake; `oi_testable` begins after the 20-day OI z-score warmup.

### Signed distribution

| symbol | window | year | n | min_bps | max_bps | mean_bps | p0.1_bps | p1_bps | p5_bps | p25_bps | p50_bps | p75_bps | p95_bps | p99_bps | p99.9_bps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT | full_history | ALL | 7119 | -30.000000 | 30.000000 | 1.088931 | -6.319266 | -1.698482 | -0.527340 | 0.263750 | 0.958200 | 1.000000 | 4.794990 | 10.633334 | 17.324612 |
| BTCUSDT | full_history | 2020 | 1098 | -30.000000 | 30.000000 | 1.570102 | -8.900611 | -4.140514 | -1.296265 | 1.000000 | 1.000000 | 1.333100 | 6.828015 | 10.677266 | 16.164091 |
| BTCUSDT | full_history | 2021 | 1095 | -8.969700 | 24.899300 | 2.795290 | -5.465902 | -2.291154 | -0.520010 | 1.000000 | 1.000000 | 3.768300 | 10.985010 | 15.644694 | 23.432329 |
| BTCUSDT | full_history | 2022 | 1095 | -11.917200 | 1.000000 | 0.380358 | -10.537695 | -1.699678 | -0.778870 | 0.058450 | 0.513500 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| BTCUSDT | full_history | 2023 | 1095 | -1.100600 | 5.517000 | 0.718330 | -1.077777 | -0.497992 | -0.159520 | 0.288850 | 0.826500 | 1.000000 | 1.467260 | 3.476914 | 5.012944 |
| BTCUSDT | full_history | 2024 | 1098 | -1.123500 | 8.814800 | 1.088969 | -0.892836 | -0.686647 | -0.160320 | 0.518225 | 1.000000 | 1.000000 | 3.442885 | 6.443212 | 8.252852 |
| BTCUSDT | full_history | 2025 | 1095 | -1.223200 | 1.000000 | 0.468167 | -1.083698 | -0.582892 | -0.241660 | 0.185900 | 0.482600 | 0.830000 | 1.000000 | 1.000000 | 1.000000 |
| BTCUSDT | full_history | 2026 | 543 | -1.517800 | 1.000000 | 0.102932 | -1.437042 | -1.017076 | -0.736540 | -0.199200 | 0.151900 | 0.426500 | 0.834860 | 1.000000 | 1.000000 |
| BTCUSDT | oi_testable | ALL | 4959 | -11.917200 | 8.814800 | 0.604612 | -2.127897 | -0.937562 | -0.436720 | 0.176650 | 0.599000 | 1.000000 | 1.229210 | 3.923070 | 7.249115 |
| BTCUSDT | oi_testable | 2021 | 33 | -0.310200 | 1.000000 | 0.938848 | -0.287416 | -0.082360 | 0.711760 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| BTCUSDT | oi_testable | 2022 | 1095 | -11.917200 | 1.000000 | 0.380358 | -10.537695 | -1.699678 | -0.778870 | 0.058450 | 0.513500 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| BTCUSDT | oi_testable | 2023 | 1095 | -1.100600 | 5.517000 | 0.718330 | -1.077777 | -0.497992 | -0.159520 | 0.288850 | 0.826500 | 1.000000 | 1.467260 | 3.476914 | 5.012944 |
| BTCUSDT | oi_testable | 2024 | 1098 | -1.123500 | 8.814800 | 1.088969 | -0.892836 | -0.686647 | -0.160320 | 0.518225 | 1.000000 | 1.000000 | 3.442885 | 6.443212 | 8.252852 |
| BTCUSDT | oi_testable | 2025 | 1095 | -1.223200 | 1.000000 | 0.468167 | -1.083698 | -0.582892 | -0.241660 | 0.185900 | 0.482600 | 0.830000 | 1.000000 | 1.000000 | 1.000000 |
| BTCUSDT | oi_testable | 2026 | 543 | -1.517800 | 1.000000 | 0.102932 | -1.437042 | -1.017076 | -0.736540 | -0.199200 | 0.151900 | 0.426500 | 0.834860 | 1.000000 | 1.000000 |
| ETHUSDT | full_history | ALL | 7119 | -35.633200 | 37.500000 | 1.295298 | -7.737711 | -1.642946 | -0.531530 | 0.313800 | 1.000000 | 1.000000 | 5.799240 | 13.613494 | 25.190985 |
| ETHUSDT | full_history | 2020 | 1098 | -28.177800 | 36.719000 | 2.503639 | -2.750028 | -0.640872 | 0.738290 | 1.000000 | 1.000000 | 3.064575 | 9.016580 | 14.194029 | 29.460527 |
| ETHUSDT | full_history | 2021 | 1095 | -35.633200 | 37.500000 | 3.428060 | -4.041222 | -1.200724 | 0.135840 | 1.000000 | 1.000000 | 4.312700 | 14.320600 | 21.016748 | 33.629454 |
| ETHUSDT | full_history | 2022 | 1095 | -30.193700 | 1.000000 | 0.071896 | -21.374579 | -3.936508 | -1.562720 | -0.275950 | 0.387600 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| ETHUSDT | full_history | 2023 | 1095 | -1.749800 | 7.113100 | 0.754293 | -1.260921 | -0.702028 | -0.128140 | 0.307500 | 0.825200 | 1.000000 | 1.642490 | 4.417336 | 6.121925 |
| ETHUSDT | full_history | 2024 | 1098 | -1.066700 | 10.172400 | 1.183690 | -0.686013 | -0.367767 | 0.054840 | 0.639850 | 1.000000 | 1.000000 | 3.689805 | 6.095895 | 8.176085 |
| ETHUSDT | full_history | 2025 | 1095 | -2.512100 | 1.000000 | 0.450111 | -1.632208 | -0.698936 | -0.263290 | 0.142150 | 0.480000 | 0.843400 | 1.000000 | 1.000000 | 1.000000 |
| ETHUSDT | full_history | 2026 | 543 | -3.652600 | 1.000000 | 0.039161 | -3.174719 | -1.739966 | -0.952440 | -0.298150 | 0.114000 | 0.454900 | 0.875870 | 1.000000 | 1.000000 |
| ETHUSDT | oi_testable | ALL | 4959 | -30.193700 | 10.172400 | 0.553864 | -8.100332 | -1.778534 | -0.696650 | 0.139750 | 0.599900 | 1.000000 | 1.519230 | 4.314960 | 6.823305 |
| ETHUSDT | oi_testable | 2021 | 33 | -0.076400 | 1.000000 | 0.851742 | -0.070845 | -0.020848 | 0.174120 | 0.923200 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| ETHUSDT | oi_testable | 2022 | 1095 | -30.193700 | 1.000000 | 0.071896 | -21.374579 | -3.936508 | -1.562720 | -0.275950 | 0.387600 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| ETHUSDT | oi_testable | 2023 | 1095 | -1.749800 | 7.113100 | 0.754293 | -1.260921 | -0.702028 | -0.128140 | 0.307500 | 0.825200 | 1.000000 | 1.642490 | 4.417336 | 6.121925 |
| ETHUSDT | oi_testable | 2024 | 1098 | -1.066700 | 10.172400 | 1.183690 | -0.686013 | -0.367767 | 0.054840 | 0.639850 | 1.000000 | 1.000000 | 3.689805 | 6.095895 | 8.176085 |
| ETHUSDT | oi_testable | 2025 | 1095 | -2.512100 | 1.000000 | 0.450111 | -1.632208 | -0.698936 | -0.263290 | 0.142150 | 0.480000 | 0.843400 | 1.000000 | 1.000000 | 1.000000 |
| ETHUSDT | oi_testable | 2026 | 543 | -3.652600 | 1.000000 | 0.039161 | -3.174719 | -1.739966 | -0.952440 | -0.298150 | 0.114000 | 0.454900 | 0.875870 | 1.000000 | 1.000000 |
| SOLUSDT | full_history | ALL | 6349 | -200.000000 | 33.246900 | 0.345764 | -78.362951 | -14.040924 | -2.304320 | -0.122900 | 0.923200 | 1.000000 | 4.697860 | 12.437800 | 25.204668 |
| SOLUSDT | full_history | 2020 | 328 | -41.916400 | 12.973700 | -1.143256 | -36.672824 | -24.897965 | -13.872720 | -0.019875 | 1.000000 | 1.000000 | 2.986105 | 8.415893 | 12.070886 |
| SOLUSDT | full_history | 2021 | 1095 | -75.000000 | 33.246900 | 2.611388 | -75.000000 | -24.110942 | 0.141380 | 1.000000 | 1.000000 | 4.005750 | 13.252710 | 24.372572 | 31.705178 |
| SOLUSDT | full_history | 2022 | 1095 | -200.000000 | 1.000000 | -1.506567 | -195.300000 | -26.388296 | -6.667260 | -0.890650 | 0.250000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| SOLUSDT | full_history | 2023 | 1095 | -92.707800 | 8.629700 | 0.118402 | -77.591888 | -9.272866 | -2.164220 | -0.194400 | 1.000000 | 1.000000 | 2.400050 | 5.027812 | 8.282920 |
| SOLUSDT | full_history | 2024 | 1098 | -1.862500 | 11.926100 | 1.243809 | -1.385346 | -0.829853 | -0.277090 | 0.456925 | 1.000000 | 1.000000 | 4.689880 | 7.552742 | 11.303953 |
| SOLUSDT | full_history | 2025 | 1095 | -30.276100 | 2.587600 | 0.032028 | -19.963164 | -2.806908 | -1.307580 | -0.359150 | 0.210500 | 0.842000 | 1.000000 | 1.000000 | 1.262740 |
| SOLUSDT | full_history | 2026 | 543 | -6.921200 | 1.000000 | -0.313002 | -6.158714 | -4.208652 | -2.128940 | -0.792650 | -0.142400 | 0.411800 | 1.000000 | 1.000000 | 1.000000 |
| SOLUSDT | oi_testable | ALL | 4959 | -200.000000 | 11.926100 | -0.051669 | -82.461128 | -9.735162 | -2.120210 | -0.290950 | 0.508000 | 1.000000 | 1.870580 | 5.302214 | 8.641053 |
| SOLUSDT | oi_testable | 2021 | 33 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| SOLUSDT | oi_testable | 2022 | 1095 | -200.000000 | 1.000000 | -1.506567 | -195.300000 | -26.388296 | -6.667260 | -0.890650 | 0.250000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| SOLUSDT | oi_testable | 2023 | 1095 | -92.707800 | 8.629700 | 0.118402 | -77.591888 | -9.272866 | -2.164220 | -0.194400 | 1.000000 | 1.000000 | 2.400050 | 5.027812 | 8.282920 |
| SOLUSDT | oi_testable | 2024 | 1098 | -1.862500 | 11.926100 | 1.243809 | -1.385346 | -0.829853 | -0.277090 | 0.456925 | 1.000000 | 1.000000 | 4.689880 | 7.552742 | 11.303953 |
| SOLUSDT | oi_testable | 2025 | 1095 | -30.276100 | 2.587600 | 0.032028 | -19.963164 | -2.806908 | -1.307580 | -0.359150 | 0.210500 | 0.842000 | 1.000000 | 1.000000 | 1.262740 |
| SOLUSDT | oi_testable | 2026 | 543 | -6.921200 | 1.000000 | -0.313002 | -6.158714 | -4.208652 | -2.128940 | -0.792650 | -0.142400 | 0.411800 | 1.000000 | 1.000000 | 1.000000 |

### Threshold feasibility

| symbol | window | year | threshold_bps | positive_count | negative_count |
|---|---|---|---|---|---|
| BTCUSDT | full_history | ALL | 2.500000 | 693 | 36 |
| BTCUSDT | full_history | ALL | 5.000000 | 329 | 12 |
| BTCUSDT | full_history | ALL | 7.500000 | 173 | 6 |
| BTCUSDT | full_history | ALL | 10.000000 | 89 | 3 |
| BTCUSDT | full_history | ALL | 15.000000 | 17 | 1 |
| BTCUSDT | full_history | ALL | 20.000000 | 5 | 1 |
| BTCUSDT | full_history | 2020 | 2.500000 | 215 | 23 |
| BTCUSDT | full_history | 2020 | 5.000000 | 103 | 7 |
| BTCUSDT | full_history | 2020 | 7.500000 | 46 | 3 |
| BTCUSDT | full_history | 2020 | 10.000000 | 15 | 1 |
| BTCUSDT | full_history | 2020 | 15.000000 | 2 | 1 |
| BTCUSDT | full_history | 2020 | 20.000000 | 1 | 1 |
| BTCUSDT | full_history | 2021 | 2.500000 | 353 | 9 |
| BTCUSDT | full_history | 2021 | 5.000000 | 200 | 3 |
| BTCUSDT | full_history | 2021 | 7.500000 | 123 | 1 |
| BTCUSDT | full_history | 2021 | 10.000000 | 74 | 0 |
| BTCUSDT | full_history | 2021 | 15.000000 | 15 | 0 |
| BTCUSDT | full_history | 2021 | 20.000000 | 4 | 0 |
| BTCUSDT | full_history | 2022 | 2.500000 | 0 | 4 |
| BTCUSDT | full_history | 2022 | 5.000000 | 0 | 2 |
| BTCUSDT | full_history | 2022 | 7.500000 | 0 | 2 |
| BTCUSDT | full_history | 2022 | 10.000000 | 0 | 2 |
| BTCUSDT | full_history | 2022 | 15.000000 | 0 | 0 |
| BTCUSDT | full_history | 2022 | 20.000000 | 0 | 0 |
| BTCUSDT | full_history | 2023 | 2.500000 | 27 | 0 |
| BTCUSDT | full_history | 2023 | 5.000000 | 2 | 0 |
| BTCUSDT | full_history | 2023 | 7.500000 | 0 | 0 |
| BTCUSDT | full_history | 2023 | 10.000000 | 0 | 0 |
| BTCUSDT | full_history | 2023 | 15.000000 | 0 | 0 |
| BTCUSDT | full_history | 2023 | 20.000000 | 0 | 0 |
| BTCUSDT | full_history | 2024 | 2.500000 | 98 | 0 |
| BTCUSDT | full_history | 2024 | 5.000000 | 24 | 0 |
| BTCUSDT | full_history | 2024 | 7.500000 | 4 | 0 |
| BTCUSDT | full_history | 2024 | 10.000000 | 0 | 0 |
| BTCUSDT | full_history | 2024 | 15.000000 | 0 | 0 |
| BTCUSDT | full_history | 2024 | 20.000000 | 0 | 0 |
| BTCUSDT | full_history | 2025 | 2.500000 | 0 | 0 |
| BTCUSDT | full_history | 2025 | 5.000000 | 0 | 0 |
| BTCUSDT | full_history | 2025 | 7.500000 | 0 | 0 |
| BTCUSDT | full_history | 2025 | 10.000000 | 0 | 0 |
| BTCUSDT | full_history | 2025 | 15.000000 | 0 | 0 |
| BTCUSDT | full_history | 2025 | 20.000000 | 0 | 0 |
| BTCUSDT | full_history | 2026 | 2.500000 | 0 | 0 |
| BTCUSDT | full_history | 2026 | 5.000000 | 0 | 0 |
| BTCUSDT | full_history | 2026 | 7.500000 | 0 | 0 |
| BTCUSDT | full_history | 2026 | 10.000000 | 0 | 0 |
| BTCUSDT | full_history | 2026 | 15.000000 | 0 | 0 |
| BTCUSDT | full_history | 2026 | 20.000000 | 0 | 0 |
| BTCUSDT | oi_testable | ALL | 2.500000 | 125 | 4 |
| BTCUSDT | oi_testable | ALL | 5.000000 | 26 | 2 |
| BTCUSDT | oi_testable | ALL | 7.500000 | 4 | 2 |
| BTCUSDT | oi_testable | ALL | 10.000000 | 0 | 2 |
| BTCUSDT | oi_testable | ALL | 15.000000 | 0 | 0 |
| BTCUSDT | oi_testable | ALL | 20.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2021 | 2.500000 | 0 | 0 |
| BTCUSDT | oi_testable | 2021 | 5.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2021 | 7.500000 | 0 | 0 |
| BTCUSDT | oi_testable | 2021 | 10.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2021 | 15.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2021 | 20.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2022 | 2.500000 | 0 | 4 |
| BTCUSDT | oi_testable | 2022 | 5.000000 | 0 | 2 |
| BTCUSDT | oi_testable | 2022 | 7.500000 | 0 | 2 |
| BTCUSDT | oi_testable | 2022 | 10.000000 | 0 | 2 |
| BTCUSDT | oi_testable | 2022 | 15.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2022 | 20.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2023 | 2.500000 | 27 | 0 |
| BTCUSDT | oi_testable | 2023 | 5.000000 | 2 | 0 |
| BTCUSDT | oi_testable | 2023 | 7.500000 | 0 | 0 |
| BTCUSDT | oi_testable | 2023 | 10.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2023 | 15.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2023 | 20.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2024 | 2.500000 | 98 | 0 |
| BTCUSDT | oi_testable | 2024 | 5.000000 | 24 | 0 |
| BTCUSDT | oi_testable | 2024 | 7.500000 | 4 | 0 |
| BTCUSDT | oi_testable | 2024 | 10.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2024 | 15.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2024 | 20.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2025 | 2.500000 | 0 | 0 |
| BTCUSDT | oi_testable | 2025 | 5.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2025 | 7.500000 | 0 | 0 |
| BTCUSDT | oi_testable | 2025 | 10.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2025 | 15.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2025 | 20.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2026 | 2.500000 | 0 | 0 |
| BTCUSDT | oi_testable | 2026 | 5.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2026 | 7.500000 | 0 | 0 |
| BTCUSDT | oi_testable | 2026 | 10.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2026 | 15.000000 | 0 | 0 |
| BTCUSDT | oi_testable | 2026 | 20.000000 | 0 | 0 |
| ETHUSDT | full_history | ALL | 2.500000 | 846 | 35 |
| ETHUSDT | full_history | ALL | 5.000000 | 448 | 11 |
| ETHUSDT | full_history | ALL | 7.500000 | 238 | 8 |
| ETHUSDT | full_history | ALL | 10.000000 | 144 | 7 |
| ETHUSDT | full_history | ALL | 15.000000 | 59 | 6 |
| ETHUSDT | full_history | ALL | 20.000000 | 18 | 4 |
| ETHUSDT | full_history | 2020 | 2.500000 | 302 | 2 |
| ETHUSDT | full_history | 2020 | 5.000000 | 177 | 1 |
| ETHUSDT | full_history | 2020 | 7.500000 | 88 | 1 |
| ETHUSDT | full_history | 2020 | 10.000000 | 38 | 1 |
| ETHUSDT | full_history | 2020 | 15.000000 | 9 | 1 |
| ETHUSDT | full_history | 2020 | 20.000000 | 3 | 1 |
| ETHUSDT | full_history | 2021 | 2.500000 | 398 | 5 |
| ETHUSDT | full_history | 2021 | 5.000000 | 241 | 1 |
| ETHUSDT | full_history | 2021 | 7.500000 | 147 | 1 |
| ETHUSDT | full_history | 2021 | 10.000000 | 105 | 1 |
| ETHUSDT | full_history | 2021 | 15.000000 | 50 | 1 |
| ETHUSDT | full_history | 2021 | 20.000000 | 15 | 1 |
| ETHUSDT | full_history | 2022 | 2.500000 | 0 | 25 |
| ETHUSDT | full_history | 2022 | 5.000000 | 0 | 9 |
| ETHUSDT | full_history | 2022 | 7.500000 | 0 | 6 |
| ETHUSDT | full_history | 2022 | 10.000000 | 0 | 5 |
| ETHUSDT | full_history | 2022 | 15.000000 | 0 | 4 |
| ETHUSDT | full_history | 2022 | 20.000000 | 0 | 2 |
| ETHUSDT | full_history | 2023 | 2.500000 | 36 | 0 |
| ETHUSDT | full_history | 2023 | 5.000000 | 5 | 0 |
| ETHUSDT | full_history | 2023 | 7.500000 | 0 | 0 |
| ETHUSDT | full_history | 2023 | 10.000000 | 0 | 0 |
| ETHUSDT | full_history | 2023 | 15.000000 | 0 | 0 |
| ETHUSDT | full_history | 2023 | 20.000000 | 0 | 0 |
| ETHUSDT | full_history | 2024 | 2.500000 | 110 | 0 |
| ETHUSDT | full_history | 2024 | 5.000000 | 25 | 0 |
| ETHUSDT | full_history | 2024 | 7.500000 | 3 | 0 |
| ETHUSDT | full_history | 2024 | 10.000000 | 1 | 0 |
| ETHUSDT | full_history | 2024 | 15.000000 | 0 | 0 |
| ETHUSDT | full_history | 2024 | 20.000000 | 0 | 0 |
| ETHUSDT | full_history | 2025 | 2.500000 | 0 | 1 |
| ETHUSDT | full_history | 2025 | 5.000000 | 0 | 0 |
| ETHUSDT | full_history | 2025 | 7.500000 | 0 | 0 |
| ETHUSDT | full_history | 2025 | 10.000000 | 0 | 0 |
| ETHUSDT | full_history | 2025 | 15.000000 | 0 | 0 |
| ETHUSDT | full_history | 2025 | 20.000000 | 0 | 0 |
| ETHUSDT | full_history | 2026 | 2.500000 | 0 | 2 |
| ETHUSDT | full_history | 2026 | 5.000000 | 0 | 0 |
| ETHUSDT | full_history | 2026 | 7.500000 | 0 | 0 |
| ETHUSDT | full_history | 2026 | 10.000000 | 0 | 0 |
| ETHUSDT | full_history | 2026 | 15.000000 | 0 | 0 |
| ETHUSDT | full_history | 2026 | 20.000000 | 0 | 0 |
| ETHUSDT | oi_testable | ALL | 2.500000 | 146 | 28 |
| ETHUSDT | oi_testable | ALL | 5.000000 | 30 | 9 |
| ETHUSDT | oi_testable | ALL | 7.500000 | 3 | 6 |
| ETHUSDT | oi_testable | ALL | 10.000000 | 1 | 5 |
| ETHUSDT | oi_testable | ALL | 15.000000 | 0 | 4 |
| ETHUSDT | oi_testable | ALL | 20.000000 | 0 | 2 |
| ETHUSDT | oi_testable | 2021 | 2.500000 | 0 | 0 |
| ETHUSDT | oi_testable | 2021 | 5.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2021 | 7.500000 | 0 | 0 |
| ETHUSDT | oi_testable | 2021 | 10.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2021 | 15.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2021 | 20.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2022 | 2.500000 | 0 | 25 |
| ETHUSDT | oi_testable | 2022 | 5.000000 | 0 | 9 |
| ETHUSDT | oi_testable | 2022 | 7.500000 | 0 | 6 |
| ETHUSDT | oi_testable | 2022 | 10.000000 | 0 | 5 |
| ETHUSDT | oi_testable | 2022 | 15.000000 | 0 | 4 |
| ETHUSDT | oi_testable | 2022 | 20.000000 | 0 | 2 |
| ETHUSDT | oi_testable | 2023 | 2.500000 | 36 | 0 |
| ETHUSDT | oi_testable | 2023 | 5.000000 | 5 | 0 |
| ETHUSDT | oi_testable | 2023 | 7.500000 | 0 | 0 |
| ETHUSDT | oi_testable | 2023 | 10.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2023 | 15.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2023 | 20.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2024 | 2.500000 | 110 | 0 |
| ETHUSDT | oi_testable | 2024 | 5.000000 | 25 | 0 |
| ETHUSDT | oi_testable | 2024 | 7.500000 | 3 | 0 |
| ETHUSDT | oi_testable | 2024 | 10.000000 | 1 | 0 |
| ETHUSDT | oi_testable | 2024 | 15.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2024 | 20.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2025 | 2.500000 | 0 | 1 |
| ETHUSDT | oi_testable | 2025 | 5.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2025 | 7.500000 | 0 | 0 |
| ETHUSDT | oi_testable | 2025 | 10.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2025 | 15.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2025 | 20.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2026 | 2.500000 | 0 | 2 |
| ETHUSDT | oi_testable | 2026 | 5.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2026 | 7.500000 | 0 | 0 |
| ETHUSDT | oi_testable | 2026 | 10.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2026 | 15.000000 | 0 | 0 |
| ETHUSDT | oi_testable | 2026 | 20.000000 | 0 | 0 |
| SOLUSDT | full_history | ALL | 2.500000 | 575 | 294 |
| SOLUSDT | full_history | ALL | 5.000000 | 302 | 165 |
| SOLUSDT | full_history | ALL | 7.500000 | 171 | 126 |
| SOLUSDT | full_history | ALL | 10.000000 | 96 | 92 |
| SOLUSDT | full_history | ALL | 15.000000 | 36 | 56 |
| SOLUSDT | full_history | ALL | 20.000000 | 15 | 41 |
| SOLUSDT | full_history | 2020 | 2.500000 | 24 | 66 |
| SOLUSDT | full_history | 2020 | 5.000000 | 9 | 51 |
| SOLUSDT | full_history | 2020 | 7.500000 | 4 | 40 |
| SOLUSDT | full_history | 2020 | 10.000000 | 3 | 27 |
| SOLUSDT | full_history | 2020 | 15.000000 | 0 | 13 |
| SOLUSDT | full_history | 2020 | 20.000000 | 0 | 6 |
| SOLUSDT | full_history | 2021 | 2.500000 | 354 | 27 |
| SOLUSDT | full_history | 2021 | 5.000000 | 229 | 21 |
| SOLUSDT | full_history | 2021 | 7.500000 | 153 | 19 |
| SOLUSDT | full_history | 2021 | 10.000000 | 91 | 16 |
| SOLUSDT | full_history | 2021 | 15.000000 | 36 | 14 |
| SOLUSDT | full_history | 2021 | 20.000000 | 15 | 13 |
| SOLUSDT | full_history | 2022 | 2.500000 | 0 | 125 |
| SOLUSDT | full_history | 2022 | 5.000000 | 0 | 64 |
| SOLUSDT | full_history | 2022 | 7.500000 | 0 | 50 |
| SOLUSDT | full_history | 2022 | 10.000000 | 0 | 35 |
| SOLUSDT | full_history | 2022 | 15.000000 | 0 | 20 |
| SOLUSDT | full_history | 2022 | 20.000000 | 0 | 15 |
| SOLUSDT | full_history | 2023 | 2.500000 | 53 | 43 |
| SOLUSDT | full_history | 2023 | 5.000000 | 12 | 16 |
| SOLUSDT | full_history | 2023 | 7.500000 | 2 | 12 |
| SOLUSDT | full_history | 2023 | 10.000000 | 0 | 9 |
| SOLUSDT | full_history | 2023 | 15.000000 | 0 | 6 |
| SOLUSDT | full_history | 2023 | 20.000000 | 0 | 5 |
| SOLUSDT | full_history | 2024 | 2.500000 | 143 | 0 |
| SOLUSDT | full_history | 2024 | 5.000000 | 52 | 0 |
| SOLUSDT | full_history | 2024 | 7.500000 | 12 | 0 |
| SOLUSDT | full_history | 2024 | 10.000000 | 2 | 0 |
| SOLUSDT | full_history | 2024 | 15.000000 | 0 | 0 |
| SOLUSDT | full_history | 2024 | 20.000000 | 0 | 0 |
| SOLUSDT | full_history | 2025 | 2.500000 | 1 | 15 |
| SOLUSDT | full_history | 2025 | 5.000000 | 0 | 9 |
| SOLUSDT | full_history | 2025 | 7.500000 | 0 | 5 |
| SOLUSDT | full_history | 2025 | 10.000000 | 0 | 5 |
| SOLUSDT | full_history | 2025 | 15.000000 | 0 | 3 |
| SOLUSDT | full_history | 2025 | 20.000000 | 0 | 2 |
| SOLUSDT | full_history | 2026 | 2.500000 | 0 | 18 |
| SOLUSDT | full_history | 2026 | 5.000000 | 0 | 4 |
| SOLUSDT | full_history | 2026 | 7.500000 | 0 | 0 |
| SOLUSDT | full_history | 2026 | 10.000000 | 0 | 0 |
| SOLUSDT | full_history | 2026 | 15.000000 | 0 | 0 |
| SOLUSDT | full_history | 2026 | 20.000000 | 0 | 0 |
| SOLUSDT | oi_testable | ALL | 2.500000 | 197 | 201 |
| SOLUSDT | oi_testable | ALL | 5.000000 | 64 | 93 |
| SOLUSDT | oi_testable | ALL | 7.500000 | 14 | 67 |
| SOLUSDT | oi_testable | ALL | 10.000000 | 2 | 49 |
| SOLUSDT | oi_testable | ALL | 15.000000 | 0 | 29 |
| SOLUSDT | oi_testable | ALL | 20.000000 | 0 | 22 |
| SOLUSDT | oi_testable | 2021 | 2.500000 | 0 | 0 |
| SOLUSDT | oi_testable | 2021 | 5.000000 | 0 | 0 |
| SOLUSDT | oi_testable | 2021 | 7.500000 | 0 | 0 |
| SOLUSDT | oi_testable | 2021 | 10.000000 | 0 | 0 |
| SOLUSDT | oi_testable | 2021 | 15.000000 | 0 | 0 |
| SOLUSDT | oi_testable | 2021 | 20.000000 | 0 | 0 |
| SOLUSDT | oi_testable | 2022 | 2.500000 | 0 | 125 |
| SOLUSDT | oi_testable | 2022 | 5.000000 | 0 | 64 |
| SOLUSDT | oi_testable | 2022 | 7.500000 | 0 | 50 |
| SOLUSDT | oi_testable | 2022 | 10.000000 | 0 | 35 |
| SOLUSDT | oi_testable | 2022 | 15.000000 | 0 | 20 |
| SOLUSDT | oi_testable | 2022 | 20.000000 | 0 | 15 |
| SOLUSDT | oi_testable | 2023 | 2.500000 | 53 | 43 |
| SOLUSDT | oi_testable | 2023 | 5.000000 | 12 | 16 |
| SOLUSDT | oi_testable | 2023 | 7.500000 | 2 | 12 |
| SOLUSDT | oi_testable | 2023 | 10.000000 | 0 | 9 |
| SOLUSDT | oi_testable | 2023 | 15.000000 | 0 | 6 |
| SOLUSDT | oi_testable | 2023 | 20.000000 | 0 | 5 |
| SOLUSDT | oi_testable | 2024 | 2.500000 | 143 | 0 |
| SOLUSDT | oi_testable | 2024 | 5.000000 | 52 | 0 |
| SOLUSDT | oi_testable | 2024 | 7.500000 | 12 | 0 |
| SOLUSDT | oi_testable | 2024 | 10.000000 | 2 | 0 |
| SOLUSDT | oi_testable | 2024 | 15.000000 | 0 | 0 |
| SOLUSDT | oi_testable | 2024 | 20.000000 | 0 | 0 |
| SOLUSDT | oi_testable | 2025 | 2.500000 | 1 | 15 |
| SOLUSDT | oi_testable | 2025 | 5.000000 | 0 | 9 |
| SOLUSDT | oi_testable | 2025 | 7.500000 | 0 | 5 |
| SOLUSDT | oi_testable | 2025 | 10.000000 | 0 | 5 |
| SOLUSDT | oi_testable | 2025 | 15.000000 | 0 | 3 |
| SOLUSDT | oi_testable | 2025 | 20.000000 | 0 | 2 |
| SOLUSDT | oi_testable | 2026 | 2.500000 | 0 | 18 |
| SOLUSDT | oi_testable | 2026 | 5.000000 | 0 | 4 |
| SOLUSDT | oi_testable | 2026 | 7.500000 | 0 | 0 |
| SOLUSDT | oi_testable | 2026 | 10.000000 | 0 | 0 |
| SOLUSDT | oi_testable | 2026 | 15.000000 | 0 | 0 |
| SOLUSDT | oi_testable | 2026 | 20.000000 | 0 | 0 |

Counts are strict: `positive_count` is F > t and `negative_count` is F < −t.

### Extreme clustering

| symbol | window | sign | threshold_bps | events | clusters | mean_run | max_run | lag1_autocorr | max_30d_clusters |
|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT | full_history | positive | 2.500000 | 693 | 149 | 4.651007 | 65 | 0.761802 | 14 |
| BTCUSDT | full_history | negative | 2.500000 | 36 | 19 | 1.894737 | 7 | 0.469539 | 7 |
| BTCUSDT | full_history | positive | 5.000000 | 329 | 97 | 3.391753 | 27 | 0.690879 | 13 |
| BTCUSDT | full_history | negative | 5.000000 | 12 | 9 | 1.333333 | 3 | 0.248733 | 5 |
| BTCUSDT | full_history | positive | 7.500000 | 173 | 58 | 2.982759 | 21 | 0.656389 | 11 |
| BTCUSDT | full_history | negative | 7.500000 | 6 | 5 | 1.200000 | 2 | 0.165964 | 3 |
| BTCUSDT | full_history | positive | 10.000000 | 89 | 41 | 2.170732 | 7 | 0.533493 | 11 |
| BTCUSDT | full_history | negative | 10.000000 | 3 | 2 | 1.500000 | 2 | 0.333052 | 1 |
| BTCUSDT | full_history | positive | 15.000000 | 17 | 14 | 1.214286 | 3 | 0.174499 | 8 |
| BTCUSDT | full_history | negative | 15.000000 | 1 | 1 | 1.000000 | 1 | -0.000141 | 1 |
| BTCUSDT | full_history | positive | 20.000000 | 5 | 5 | 1.000000 | 1 | -0.000703 | 3 |
| BTCUSDT | full_history | negative | 20.000000 | 1 | 1 | 1.000000 | 1 | -0.000141 | 1 |
| BTCUSDT | oi_testable | positive | 2.500000 | 125 | 35 | 3.571429 | 28 | 0.712758 | 12 |
| BTCUSDT | oi_testable | negative | 2.500000 | 4 | 2 | 2.000000 | 3 | 0.499596 | 1 |
| BTCUSDT | oi_testable | positive | 5.000000 | 26 | 16 | 1.625000 | 6 | 0.381371 | 11 |
| BTCUSDT | oi_testable | negative | 5.000000 | 2 | 1 | 2.000000 | 2 | 0.499798 | 1 |
| BTCUSDT | oi_testable | positive | 7.500000 | 4 | 3 | 1.333333 | 2 | 0.249394 | 3 |
| BTCUSDT | oi_testable | negative | 7.500000 | 2 | 1 | 2.000000 | 2 | 0.499798 | 1 |
| BTCUSDT | oi_testable | positive | 10.000000 | 0 | 0 | 0.000000 | 0 | 0.000000 | 0 |
| BTCUSDT | oi_testable | negative | 10.000000 | 2 | 1 | 2.000000 | 2 | 0.499798 | 1 |
| BTCUSDT | oi_testable | positive | 15.000000 | 0 | 0 | 0.000000 | 0 | 0.000000 | 0 |
| BTCUSDT | oi_testable | negative | 15.000000 | 0 | 0 | 0.000000 | 0 | 0.000000 | 0 |
| BTCUSDT | oi_testable | positive | 20.000000 | 0 | 0 | 0.000000 | 0 | 0.000000 | 0 |
| BTCUSDT | oi_testable | negative | 20.000000 | 0 | 0 | 0.000000 | 0 | 0.000000 | 0 |
| ETHUSDT | full_history | positive | 2.500000 | 846 | 174 | 4.862069 | 48 | 0.766584 | 18 |
| ETHUSDT | full_history | negative | 2.500000 | 35 | 17 | 2.058824 | 12 | 0.511886 | 3 |
| ETHUSDT | full_history | positive | 5.000000 | 448 | 127 | 3.527559 | 22 | 0.697477 | 16 |
| ETHUSDT | full_history | negative | 5.000000 | 11 | 5 | 2.200000 | 5 | 0.544751 | 1 |
| ETHUSDT | full_history | positive | 7.500000 | 238 | 85 | 2.800000 | 20 | 0.630502 | 15 |
| ETHUSDT | full_history | negative | 7.500000 | 8 | 4 | 2.000000 | 5 | 0.499437 | 1 |
| ETHUSDT | full_history | positive | 10.000000 | 144 | 57 | 2.526316 | 15 | 0.595993 | 13 |
| ETHUSDT | full_history | negative | 10.000000 | 7 | 3 | 2.333333 | 5 | 0.571007 | 1 |
| ETHUSDT | full_history | positive | 15.000000 | 59 | 31 | 1.903226 | 4 | 0.470185 | 11 |
| ETHUSDT | full_history | negative | 15.000000 | 6 | 3 | 2.000000 | 4 | 0.499578 | 1 |
| ETHUSDT | full_history | positive | 20.000000 | 18 | 13 | 1.384615 | 2 | 0.275947 | 6 |
| ETHUSDT | full_history | negative | 20.000000 | 4 | 3 | 1.333333 | 2 | 0.249578 | 1 |
| ETHUSDT | oi_testable | positive | 2.500000 | 146 | 39 | 3.743590 | 27 | 0.724772 | 12 |
| ETHUSDT | oi_testable | negative | 2.500000 | 28 | 12 | 2.333333 | 12 | 0.568994 | 3 |
| ETHUSDT | oi_testable | positive | 5.000000 | 30 | 19 | 1.578947 | 4 | 0.362811 | 11 |
| ETHUSDT | oi_testable | negative | 5.000000 | 9 | 3 | 3.000000 | 5 | 0.666060 | 1 |
| ETHUSDT | oi_testable | positive | 7.500000 | 3 | 2 | 1.500000 | 2 | 0.332930 | 2 |
| ETHUSDT | oi_testable | negative | 7.500000 | 6 | 2 | 3.000000 | 5 | 0.666263 | 1 |
| ETHUSDT | oi_testable | positive | 10.000000 | 1 | 1 | 1.000000 | 1 | -0.000202 | 1 |
| ETHUSDT | oi_testable | negative | 10.000000 | 5 | 1 | 5.000000 | 5 | 0.799798 | 1 |
| ETHUSDT | oi_testable | positive | 15.000000 | 0 | 0 | 0.000000 | 0 | 0.000000 | 0 |
| ETHUSDT | oi_testable | negative | 15.000000 | 4 | 1 | 4.000000 | 4 | 0.749798 | 1 |
| ETHUSDT | oi_testable | positive | 20.000000 | 0 | 0 | 0.000000 | 0 | 0.000000 | 0 |
| ETHUSDT | oi_testable | negative | 20.000000 | 2 | 1 | 2.000000 | 2 | 0.499798 | 1 |
| SOLUSDT | full_history | positive | 2.500000 | 575 | 158 | 3.639241 | 36 | 0.697849 | 14 |
| SOLUSDT | full_history | negative | 2.500000 | 294 | 106 | 2.773585 | 19 | 0.621947 | 14 |
| SOLUSDT | full_history | positive | 5.000000 | 302 | 85 | 3.552941 | 21 | 0.704484 | 11 |
| SOLUSDT | full_history | negative | 5.000000 | 165 | 57 | 2.894737 | 18 | 0.645327 | 17 |
| SOLUSDT | full_history | positive | 7.500000 | 171 | 61 | 2.803279 | 20 | 0.633400 | 15 |
| SOLUSDT | full_history | negative | 7.500000 | 126 | 50 | 2.520000 | 10 | 0.595139 | 19 |
| SOLUSDT | full_history | positive | 10.000000 | 96 | 42 | 2.285714 | 11 | 0.555782 | 12 |
| SOLUSDT | full_history | negative | 10.000000 | 92 | 39 | 2.358974 | 9 | 0.569853 | 14 |
| SOLUSDT | full_history | positive | 15.000000 | 36 | 22 | 1.636364 | 6 | 0.385403 | 12 |
| SOLUSDT | full_history | negative | 15.000000 | 56 | 27 | 2.074074 | 9 | 0.513566 | 9 |
| SOLUSDT | full_history | positive | 20.000000 | 15 | 7 | 2.142857 | 5 | 0.532228 | 6 |
| SOLUSDT | full_history | negative | 20.000000 | 41 | 18 | 2.277778 | 9 | 0.558122 | 5 |
| SOLUSDT | oi_testable | positive | 2.500000 | 197 | 61 | 3.229508 | 33 | 0.677543 | 14 |
| SOLUSDT | oi_testable | negative | 2.500000 | 201 | 78 | 2.576923 | 19 | 0.595543 | 14 |
| SOLUSDT | oi_testable | positive | 5.000000 | 64 | 19 | 3.368421 | 19 | 0.699243 | 7 |
| SOLUSDT | oi_testable | negative | 5.000000 | 93 | 33 | 2.818182 | 11 | 0.638378 | 17 |
| SOLUSDT | oi_testable | positive | 7.500000 | 14 | 9 | 1.555556 | 4 | 0.355322 | 6 |
| SOLUSDT | oi_testable | negative | 7.500000 | 67 | 29 | 2.310345 | 9 | 0.561235 | 19 |
| SOLUSDT | oi_testable | positive | 10.000000 | 2 | 1 | 2.000000 | 2 | 0.499798 | 1 |
| SOLUSDT | oi_testable | negative | 10.000000 | 49 | 21 | 2.333333 | 7 | 0.567151 | 14 |
| SOLUSDT | oi_testable | positive | 15.000000 | 0 | 0 | 0.000000 | 0 | 0.000000 | 0 |
| SOLUSDT | oi_testable | negative | 15.000000 | 29 | 13 | 2.230769 | 7 | 0.549087 | 7 |
| SOLUSDT | oi_testable | positive | 20.000000 | 0 | 0 | 0.000000 | 0 | 0.000000 | 0 |
| SOLUSDT | oi_testable | negative | 20.000000 | 22 | 8 | 2.750000 | 7 | 0.634743 | 4 |

Runs use consecutive scheduled settlements. `max_30d_clusters` counts distinct run starts in a trailing 30-day window.

### Top extreme prints

| symbol | sign | rank | timestamp_utc | funding_bps |
|---|---|---|---|---|
| BTCUSDT | positive | 1 | 2020-02-12T00:00:00+00:00 | 30.000000 |
| BTCUSDT | positive | 2 | 2021-02-08T16:00:00+00:00 | 24.899300 |
| BTCUSDT | positive | 3 | 2021-01-04T08:00:00+00:00 | 23.648200 |
| BTCUSDT | positive | 4 | 2021-01-08T00:00:00+00:00 | 21.351700 |
| BTCUSDT | positive | 5 | 2021-01-06T08:00:00+00:00 | 21.000800 |
| BTCUSDT | positive | 6 | 2021-02-09T08:00:00+00:00 | 18.657300 |
| BTCUSDT | positive | 7 | 2021-02-10T08:00:00+00:00 | 17.535000 |
| BTCUSDT | positive | 8 | 2021-02-11T16:00:00+00:00 | 17.411000 |
| BTCUSDT | positive | 9 | 2021-01-29T16:00:00+00:00 | 16.678900 |
| BTCUSDT | positive | 10 | 2021-01-04T00:00:00+00:00 | 16.412600 |
| BTCUSDT | negative | 1 | 2020-03-13T08:00:00+00:00 | -30.000000 |
| BTCUSDT | negative | 2 | 2022-11-10T00:00:00+00:00 | -11.917200 |
| BTCUSDT | negative | 3 | 2022-11-10T08:00:00+00:00 | -11.195300 |
| BTCUSDT | negative | 4 | 2020-03-16T16:00:00+00:00 | -9.035800 |
| BTCUSDT | negative | 5 | 2021-05-19T16:00:00+00:00 | -8.969700 |
| BTCUSDT | negative | 6 | 2020-03-14T00:00:00+00:00 | -7.642100 |
| BTCUSDT | negative | 7 | 2020-03-13T16:00:00+00:00 | -6.537800 |
| BTCUSDT | negative | 8 | 2020-03-30T00:00:00+00:00 | -6.431000 |
| BTCUSDT | negative | 9 | 2021-07-26T00:00:00+00:00 | -5.484100 |
| BTCUSDT | negative | 10 | 2020-03-15T08:00:00+00:00 | -5.420800 |
| ETHUSDT | positive | 1 | 2021-01-04T08:00:00+00:00 | 37.500000 |
| ETHUSDT | positive | 2 | 2020-02-12T08:00:00+00:00 | 36.719000 |
| ETHUSDT | positive | 3 | 2021-01-10T00:00:00+00:00 | 34.052200 |
| ETHUSDT | positive | 4 | 2020-02-10T16:00:00+00:00 | 29.569400 |
| ETHUSDT | positive | 5 | 2021-01-04T00:00:00+00:00 | 29.554900 |
| ETHUSDT | positive | 6 | 2020-02-12T00:00:00+00:00 | 28.447000 |
| ETHUSDT | positive | 7 | 2021-02-08T16:00:00+00:00 | 28.440800 |
| ETHUSDT | positive | 8 | 2021-01-06T16:00:00+00:00 | 25.331700 |
| ETHUSDT | positive | 9 | 2021-01-29T16:00:00+00:00 | 24.139200 |
| ETHUSDT | positive | 10 | 2021-02-17T16:00:00+00:00 | 23.228200 |
| ETHUSDT | negative | 1 | 2021-05-19T16:00:00+00:00 | -35.633200 |
| ETHUSDT | negative | 2 | 2022-09-15T00:00:00+00:00 | -30.193700 |
| ETHUSDT | negative | 3 | 2020-03-13T08:00:00+00:00 | -28.177800 |
| ETHUSDT | negative | 4 | 2022-09-15T08:00:00+00:00 | -21.698700 |
| ETHUSDT | negative | 5 | 2022-09-14T08:00:00+00:00 | -18.250600 |
| ETHUSDT | negative | 6 | 2022-09-14T16:00:00+00:00 | -17.213400 |
| ETHUSDT | negative | 7 | 2022-09-14T00:00:00+00:00 | -11.114200 |
| ETHUSDT | negative | 8 | 2022-05-12T08:00:00+00:00 | -7.968200 |
| ETHUSDT | negative | 9 | 2022-11-10T00:00:00+00:00 | -6.014900 |
| ETHUSDT | negative | 10 | 2022-11-09T16:00:00+00:00 | -5.468200 |
| SOLUSDT | positive | 1 | 2021-02-10T08:00:00+00:00 | 33.246900 |
| SOLUSDT | positive | 2 | 2021-01-10T00:00:00+00:00 | 31.831100 |
| SOLUSDT | positive | 3 | 2021-02-09T08:00:00+00:00 | 30.491500 |
| SOLUSDT | positive | 4 | 2021-02-09T16:00:00+00:00 | 28.669000 |
| SOLUSDT | positive | 5 | 2021-02-13T00:00:00+00:00 | 26.051000 |
| SOLUSDT | positive | 6 | 2021-02-14T16:00:00+00:00 | 25.741900 |
| SOLUSDT | positive | 7 | 2021-02-14T08:00:00+00:00 | 25.233100 |
| SOLUSDT | positive | 8 | 2021-02-14T00:00:00+00:00 | 25.151400 |
| SOLUSDT | positive | 9 | 2021-02-05T08:00:00+00:00 | 25.040900 |
| SOLUSDT | positive | 10 | 2021-02-05T16:00:00+00:00 | 24.884900 |
| SOLUSDT | negative | 1 | 2022-11-10T00:00:00+00:00 | -200.000000 |
| SOLUSDT | negative | 2 | 2022-11-10T08:00:00+00:00 | -200.000000 |
| SOLUSDT | negative | 3 | 2022-11-09T16:00:00+00:00 | -150.000000 |
| SOLUSDT | negative | 4 | 2022-11-11T16:00:00+00:00 | -113.973100 |
| SOLUSDT | negative | 5 | 2023-01-04T08:00:00+00:00 | -92.707800 |
| SOLUSDT | negative | 6 | 2023-01-03T16:00:00+00:00 | -82.011900 |
| SOLUSDT | negative | 7 | 2022-11-10T16:00:00+00:00 | -80.157900 |
| SOLUSDT | negative | 8 | 2021-01-06T00:00:00+00:00 | -75.000000 |
| SOLUSDT | negative | 9 | 2021-01-06T08:00:00+00:00 | -75.000000 |
| SOLUSDT | negative | 10 | 2021-01-06T16:00:00+00:00 | -75.000000 |

### Factual summary

At the strict 20 bp threshold, full recovered-history positive/negative counts are: BTCUSDT +5/−1, ETHUSDT +18/−4, SOLUSDT +15/−41. In the OI-testable window they are: BTCUSDT +0/−0, ETHUSDT +0/−2, SOLUSDT +0/−22. The clustering table reports consecutive-settlement runs and the observed maximum number of distinct run starts in any trailing 30 days. This document makes no threshold recommendation and does not assess conditional strategy outcomes.
