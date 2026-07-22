# Bitcoin U.S.-Session Close Momentum — Binance Spot v1

Status: frozen falsification scout; not an Experiment, validated Strategy, or trading authorization.

Frozen: 2026-07-10, before downloading the declared development partition.

## Primary source

Shen, Urquhart, and Wang, “Bitcoin intraday time series momentum,” *Financial Review* 57 (2022), DOI `10.1111/fire.12290`.

Accepted manuscript: `https://centaur.reading.ac.uk/100181/3/21Sep2021Bitcoin%20Intraday%20Time-Series%20Momentum.R2.pdf`

The paper aggregates tick data to one-minute observations for BTC/USD on Bitfinex, Bitstamp, CEX.IO, Coinbase, and Kraken through 2020. Exchange-specific openings are selected from volume spikes; the close is 17:00 EST, aligned with the CME Bitcoin-futures daily break. The paper defines:

- ONFH: prior day close to the end of the current first half-hour;
- SLH: second-to-last half-hour return;
- LH: final half-hour return.

It estimates pooled predictive regressions and a recursive out-of-sample forecast. Its first sign strategy takes a long final-half-hour position when ONFH is positive and a short position otherwise, then closes at the session close. The paper reports a positive pooled ONFH coefficient, positive out-of-sample R-squared, and positive timing performance. Its strongest conditional results sort on opening volume or one-minute volatility.

## What this scout does—and does not replicate

This is a single-venue BTCUSDT proxy. It deliberately differs from the source in four ways:

1. Binance spot BTCUSDT is not one of the paper's five BTC/USD series.
2. Public 30-minute klines replace tick-to-one-minute reconstruction.
3. `America/New_York` civil time handles DST; the paper labels its clocks EST.
4. The repository/user preference is long/flat v1. The source timing rule is long/short.

Those choices were frozen before returns were downloaded. A positive result would support only this proxy. A negative result cannot be repaired by silently claiming the source's short side, conditional volume result, or another exchange.

## Frozen rule

- Instrument: Binance spot BTCUSDT.
- Frequency: official public 30-minute klines.
- Opening proxy: 09:00 New York time.
- Signal: 09:30 close today divided by 17:00 close from the prior New York session minus one.
- Trigger: signal strictly greater than zero.
- Entry: open of the 16:30-17:00 kline, many hours after signal formation.
- Exit: close of that kline at 17:00.
- Position: long 1.0 when triggered, flat otherwise.
- Maximum one round trip per New York session.
- No shorts, leverage, stops, targets, volume/volatility filters, weekdays, funding, alternate clocks, or other coins.

The signal and held interval do not overlap. The scout uses the explicit 16:30 kline open and 17:00 kline close and does not rely on a generic one-bar shift. An initial development run incorrectly used the preceding kline's 16:30 close as entry; independent review identified the execution mismatch, and the run was corrected without opening later partitions. The correction worsened rather than improved the result.

## Frozen data partitions

- Development: 2017-09-01 through 2020-12-31.
- Internal validation: 2021-01-01 through 2023-12-31.
- Final holdout: 2024-01-01 through 2025-12-31.

The development period overlaps the paper's source sample but uses a different venue/pair. Later partitions stay locked unless every preceding gate passes.

## Costs

Report three layers:

- gross;
- fee-only: 10 bps per side, 20 bps round trip;
- conservative repository-style: 10 bps taker fee plus 5 bps slippage per side, 30 bps round trip.

Costs apply once per triggered session, not continuously while flat. Actual historical Binance fee tiers and BNB discounts vary; using one conservative frozen rate is an implementation assumption, not a historical fee reconstruction.

## Progression gates

All must pass:

1. At least 500 triggered development sessions.
2. Positive mean gross return.
3. Directional accuracy above 50%.
4. Positive gross mean in each chronological half.
5. Session-bootstrap 95% lower bound above zero.
6. Positive mean after the conservative 30 bps round trip.
7. Positive gross mean after removing the 5% largest absolute held-session returns.
8. Top 5% of profitable sessions contribute no more than 50% of total positive P&L.
9. Complete, unique, correctly aligned timestamps with no signal/holding overlap.

If development fails, stop. Do not inspect later partitions, invert the sign, add shorts, condition on volume/volatility, move the session clocks, use futures, change coins, or tune costs on this consumed sample.

## Public data and reproducibility

Use Binance's official public archive: `https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/30m/`.

For every month, preserve:

- source URL;
- source-provided `.CHECKSUM` text;
- locally computed SHA-256;
- byte size;
- normalized row count and timestamp range.

Historical exchange outages may create whole 30-minute gaps, truncated klines, or emergency off-grid klines. Preserve and count gaps, exclude truncated/off-grid bars, and never fill them. A session is eligible only when all four required price boundaries are present.

Binance documents that spot archive timestamps from 2025 onward may use microseconds. Parsing must detect timestamp units rather than assuming milliseconds.

## Interpretation

This is a slow session-boundary hypothesis, not a latency strategy. The morning signal is known roughly seven hours before entry. The mechanism proposed by the paper is final-session inventory/liquidity behavior and reluctance to carry risk across a conventional close. Binance trades continuously, so the 17:00 boundary is an economic proxy, not an exchange shutdown.
