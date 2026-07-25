# Alpaca IEX Level-1 Microstructure Feasibility v1

Status: data-feasibility scout; not a Strategy, Experiment, validation result, or trading authorization.

## Decision context

Several adjacent intraday OHLCV families in this repository failed, including opening-hour continuation, opening-range breakout, same-clock ETF seasonality, and morning-loss reversal. This scout changes the information source rather than tuning another price window. It measures venue-local trades and quote state before those events are compressed into bars.

## Mechanism evidence

- Rama Cont, Arseniy Kukanov, and Sasha Stoikov, "The Price Impact of Order Book Events," Journal of Financial Econometrics, 2014. DOI: https://doi.org/10.1093/jjfinec/nbt003. The paper supports order-flow imbalance and available depth as short-horizon price-impact mechanisms.
- Joel Hasbrouck, "Measuring the Information Content of Stock Trades," Journal of Finance, 1991. DOI: https://doi.org/10.1111/j.1540-6261.1991.tb03749.x. The paper supports joint analysis of trades and quote revisions, including lagged price impact.

These sources support investigating the mechanism. They do not validate an IEX-only, retail-accessible, 5-30 minute implementation.

## Candidate hypothesis for a later scout

At a 5-30 minute horizon, lagged signed trade imbalance and top-of-book size imbalance may predict the next-interval midpoint return among liquid US equities because aggressive flow and liquidity-provider inventory adjustment can be incorporated gradually.

This remains a candidate hypothesis. It is not frozen as a trading Experiment until the data layer passes and a broader, point-in-time universe and exact feature/portfolio rules are predeclared.

## Frozen feasibility request

- Provider: Alpaca Historical Market Data API.
- Feed: `iex` only.
- Scope label: `IEX venue-local Level-1 feasibility scout`.
- Initial symbol: AAPL, for plumbing only.
- Session: 2026-07-08.
- Window: 09:30-09:35 America/New_York.
- Events: historical trades and IEX top-of-book quotes.
- Authentication: existing local Alpaca credentials, read-only requests only.
- Pagination: ascending timestamps, 10,000 rows per page, maximum 20 pages per event type; repeated tokens, an unconsumed token, schema drift, redirects, or response byte/time caps are failures.
- Storage: normalized Parquet partitioned by provider/feed, symbol, date, and event type, plus a credential-free manifest and SHA-256 hashes.
- Timestamp policy: preserve vendor timestamp text and parse nanosecond UTC timestamps; do not round before later feature construction.
- Event identity: preserve vendor trade IDs, exchange codes, tape codes, conditions, prices, and sizes. Never deduplicate solely by timestamp.

## Data-quality gates

The feasibility request passes only if:

1. Both trade and quote endpoints authorize the explicit `iex` feed.
2. Pagination completes for both event types.
3. Both normalized frames are nonempty and chronologically ordered.
4. Nanosecond UTC timestamps survive Parquet round-trip.
5. Trade prices and sizes are positive.
6. Quote prices/sizes are nonnegative and active sides have positive prices.
7. Vendor trade IDs, exchange codes, and tape codes are preserved.
8. Exact duplicates, duplicate trade IDs, locked quotes, and crossed quotes are counted rather than silently removed.
9. Manifest hashes reproduce and no credential value appears in the manifest.

## Feasibility result

PASS for the frozen request:

- Trades: 762 rows, one page, quality `PASS`.
- Quotes: 38,652 rows, four pages, quality `PASS`.
- Timestamp bounds remained within the requested interval with nanosecond precision.
- No missing timestamps, out-of-order events, invalid prices/sizes, duplicate trade IDs, exact duplicates, locked quotes, or crossed quotes were observed.
- Exchange code `V` and tape code `C` were preserved after a schema correction and complete redownload.
- Stored-file hashes matched the manifest and credential values were absent.

Local ignored evidence:

`data/parquet/alpaca_iex_l1_feasibility/alpaca_iex/equity/AAPL/2026-07-08/manifest.json`

## Feature-plumbing result

A separate 30-minute opening sample was downloaded to exercise the frozen five-minute feature path without treating the six resulting intervals as statistical evidence:

- Source events: 2,657 trades and 226,223 quotes; trade pagination completed in one page and quote pagination in 23 pages.
- Features: six five-minute rows with five contiguous next-interval midpoint targets.
- Trade classification: latest normal quote midpoint strictly before each trade; equal-timestamp ordering is excluded, with no future quote and no tick-rule fallback.
- Minimum per-interval quote-match fraction: `1.0000`.
- Quote states: 226,223 normal; zero locked, crossed, one-sided, or invalid. States are counted rather than silently discarded.
- Feature quality: `PASS`; no negative quote ages or terminal spreads; maximum matched-trade quote age was `1,160.39 ms` and maximum terminal-quote age was `191.61 ms`; stored feature hash reproduced.

Local ignored evidence:

`data/parquet/alpaca_iex_l1_feature_feasibility/alpaca_iex/equity/AAPL/2026-07-08/features_5min_manifest.json`

This pass demonstrates leakage-controlled feature construction only. Six rows from one symbol and one opening window cannot test predictability.

## Interpretation and restrictions

- This proves access, pagination, normalization, validation, and storage for a bounded IEX sample.
- It is not alpha evidence and should not enter the Experiment registry.
- IEX is one venue. Its trades and quotes do not represent consolidated US flow.
- IEX top of book is not SIP NBBO and not full depth.
- AAPL is a current fixed symbol used for plumbing; it is not a survivorship-safe research universe.
- No full-depth orders, cancellations, queue position, or venue-routing state are available.
- Do not infer a US-equity strategy from an IEX-only result. Any later consolidated replication is a new data-source test with unchanged feature definitions.

## Next bounded decision

Before broad downloading, freeze one feature construction and rejection protocol. The cheapest defensible next scout is:

1. Aggregate events into fixed 5-minute intervals.
2. Classify each trade against the latest quote midpoint available at or before the trade timestamp; never use a future quote.
3. Compute signed-volume imbalance, total volume, trade intensity, terminal quote-size imbalance, terminal spread, and terminal midpoint.
4. Predict only the next completed interval's midpoint return.
5. Run gross signal diagnostics before any portfolio simulation: expected-sign Rank IC, monotonic buckets, chronological stability, concentration, coverage, and one-interval-delay sensitivity.
6. Stop if the expected sign is absent or unstable. Do not tune interval length, thresholds, symbols, or filters on the consumed sample.
7. Treat any IEX result as venue-local. Require unchanged-feature replication on consolidated SIP data before promotion research.
