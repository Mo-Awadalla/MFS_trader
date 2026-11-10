# Navier–Stokes market hypotheses: data utility audit

Date: 2026-09-13

## Decision

Do not buy QQQ depth yet. The highest-utility next dataset is available free:
Tardis downloadable samples for Binance USDT futures on the first day of every
month. Start with BTCUSDT incremental L2, snapshots, trades, derivative ticker,
and the exchange-wide liquidation file. Add Binance spot and Coinbase BTC spot
only after the single-market pipeline passes its integrity checks.

This changes the first scientific target from “does the effect exist in US equity
openings?” to “does the proposed concentration mechanism exist anywhere in a
highly leveraged continuous limit-order market?” That is the cheaper and more
informative ordering of questions.

## What the repository already has

| Existing data | What it can test | Important limitation |
| --- | --- | --- |
| 806 Databento EQUS.MINI MBP-1 opening sessions for six SPY/leverage ETFs | top-of-book temporal concentration, spread, BBO depth, imbalance, aggressive flow | one price level; 20-minute opening window; no spatial book field |
| Binance spot/perpetual/index/mark/premium 30-minute bars | slow regimes, basis, returns and volatility | no microstructure |
| Binance funding and futures metrics/open interest | leverage/crowding controls | too slow to identify liquidation feedback locally |
| ETF and futures bars/BBO datasets | cross-asset context and coarse execution controls | generally minute-level or top-of-book |

The completed MBP-1 pilot rejected the implemented temporal concentration proxies
for the five-minute US-equity opening task. It did not test spatial concentration.

## Missing measurement primitives

| Primitive | Needed for | Minimum acceptable data |
| --- | --- | --- |
| Liquidity density across price, rho(p,t) | norms, gradients, curvature, core width, self-similarity | event-synchronized L2 with at least 10 levels; 25+ preferable |
| Add/cancel/modify/trade flux by side and price, J(p,t) | velocity, shear, enstrophy, quadratic flow, spectral cascades | incremental L2; MBO only if queue/order identity is required |
| Recovery after local depletion | replenishment coefficient and transport/restoration ratio | continuous deltas plus valid initial snapshots and gap detection |
| Aggressor trades | impact, amplification and adverse selection | tick trades synchronized to book receipt time |
| Liquidations, funding and open interest | hypotheses 66–68 | tick liquidations plus slower leverage state |
| Synchronized venue books | hypotheses 8 and 55–65 | L2 plus trades for the same asset on at least two venues |
| Parent/child execution identity | metaorder hypotheses 36–44 and 81–85 | proprietary execution records; public feeds cannot identify parent orders reliably |
| Options chain, OI and Greeks assumptions | hypotheses 69–75 | synchronized options chain and underlying L2; dealer sign remains inferred |
| Timestamped standardized news surprises | hypotheses 31–35 | licensed news/macro feed with release and revision timestamps |
| Long multi-instrument panel | hypotheses 58–65 and 86–88 | normalized depth/events across instruments and market structures |

## Hypothesis families and the best data

| Hypotheses | Measurement | Best immediate source | Status |
| --- | --- | --- | --- |
| 1–16, 45, 51–54, 89–94 | spatial concentration, gradients, recovery and thresholds | Binance-futures BTCUSDT incremental L2 + trades | free monthly samples |
| 17–30 | second-order flow and spectral cascades | incremental L2 actions + trades | free monthly samples |
| 31–35 | endogenous versus news-triggered moves | L2/trades plus news surprise feed | microstructure free; news missing |
| 36–44 | state-dependent child-order impact | L2/trades; own executions for true metaorders | child-event tests free; metaorder claims unavailable |
| 46–50 | continuum-versus-discrete model residual | long clean L2 event history | free monthly samples can prototype; continuous data preferable |
| 55–65 | cross-venue/cross-asset circulation and contagion | synchronized Binance futures, Binance spot and Coinbase spot | free monthly samples on common dates |
| 66–68 | liquidation feedback | futures L2/trades + tick liquidations + OI/funding | strongest free test family |
| 69–75 | gamma/options feedback | Deribit options chain + underlying/perpetual L2 | free monthly prototype; dealer positioning not observed |
| 76–80 | passive market-making/adverse selection | L2 queue dynamics and fills | L2 partial; MBO or own quote logs for queue priority |
| 81–85 | optimal execution | own child orders/fills against L2 | cannot be established from public data alone |
| 86–88 | cross-sectional gain and universal scaling | many symbols/venues with consistent L2 | free monthly expansion after the core test |

## Free alternatives, ranked

### 1. Tardis first-of-month historical samples — recommended

Tardis documents free, no-key downloads for the first day of every month. For
Binance USDT futures it provides incremental L2, 25-level snapshots, trades,
derivative ticker data and liquidations. High-cap futures history begins in 2019;
the vendor flags pre-2020-05-14 collection issues, so use 2020-06-01 onward.

That produces approximately 76 monthly BTCUSDT depth/trade days through
2026-09-01. Liquidations are available from 2021-09, producing approximately 61
monthly liquidation days. Each is a full 24-hour crypto session, so this is much
richer intraday coverage than 80 fifteen-minute equity windows.

Advantages:

- zero data fee and immediately historical;
- full spatial L2 and event flow;
- liquidations make the nonlinear-feedback hypotheses directly observable;
- spot, perpetual and multiple venues can share the same sampled dates;
- existing repository funding/OI/bar data supplies slower state variables.

Risks:

- every observation day is the first calendar day of a month;
- calendar time is sparse, with no adjacent-day event studies;
- exchange schema and market structure changed over six years;
- L2 has price-level changes, not individual order identity;
- file sizes may be large. Tardis/Cloudflare rejected header/range probes from
  this environment, so storage must be measured with one explicitly approved
  free sample download before bulk acquisition.

### 2. Record public live crypto depth — best unbiased free confirmation

Binance, Coinbase and Kraken expose public real-time L2 feeds. Coinbase states
that its traditional market-data WebSocket is available without authentication;
its level2 channel supplies a snapshot and updates. Binance provides incremental
depth streams and a REST snapshot procedure; Kraken offers configurable book
depth.

Cost is zero, but the price is waiting and operating a gap-aware collector. Run it
for at least 90 days, then freeze the model and reserve the following 30–60 days
as untouched confirmation. This removes the first-of-month selection problem.

### 3. LOBSTER/Nasdaq samples — equity engineering only

LOBSTER provides free event/message and order-book samples derived from official
Nasdaq TotalView-ITCH. The sample page includes 10-level files for several stocks
and 30/50-level one-hour samples for AAPL, MSFT and SPY. These are excellent for
validating spatial feature code but are a single historical sample period and
cannot support inference.

### 4. FI-2010 — benchmark only

FI-2010 is free and contains ten levels for five Nasdaq Nordic stocks over ten
days. It is useful for testing profile normalization and model plumbing. It is too
short, old and preprocessed for a decisive test, and it does not replace raw
event actions needed to estimate J(p,t) and replenishment honestly.

## Highest-utility free acquisition contract

Phase A should use only:

1. `binance-futures / incremental_book_L2 / BTCUSDT`;
2. `binance-futures / book_snapshot_25 / BTCUSDT`;
3. `binance-futures / trades / BTCUSDT`;
4. `binance-futures / derivative_ticker / BTCUSDT`;
5. `binance-futures / liquidations / PERPETUALS`, filtered to BTCUSDT;
6. first day of each month from 2020-06-01 through 2026-09-01.

Download one recent free day first. Verify gzip integrity, sequence continuity,
snapshot/delta overlap, schemas, row counts, clock ordering and compressed/unpacked
size. Only then estimate the bulk storage and download the historical set.

The first tests should be the smallest defensible subset of the proposal:

- spatial norm divergence and core width versus future excursion;
- gradient/shear energy beyond spread, depth, imbalance and volatility;
- transport time versus depth restoration time;
- gross opposing flow and cancellation/trade covariance near zero net flow;
- state-dependent small-trade amplification;
- liquidation intensity times local impact susceptibility.

These cover the proposal's central mechanism and strongest feedback laboratory.
Do not begin with power-law singular-time fitting, universal exponents or complex
PDE-versus-neural-model comparisons.

## Paid fallback prices

If the mechanism survives free crypto data and equity transfer becomes the next
question, the repository's read-only Databento metadata estimates for QQQ on
XNAS.ITCH are:

| Dataset | 80 x 15-minute sessions | 300 sessions | 500 sessions |
| --- | ---: | ---: | ---: |
| MBP-10 expected | $5.45 | $20.43 | $34.05 |
| MBP-10 with 25% buffer | $6.81 | $25.54 | $42.57 |
| MBO expected | $6.05 | $22.70 | $37.83 |
| MBO with 25% buffer | $7.57 | $28.37 | $47.29 |

The estimate sampled 20 dates, but Databento returned intermittent 500/504 errors:
12 MBP-10 quotes and 7 MBO quotes succeeded. Treat these as budget estimates, not
an executable cost ledger. Exact per-date pricing must be rerun before any purchase.

MBP-10 is the better paid starting point. MBO adds utility mainly for queue priority,
individual-order lifetime and exact market-making tests. It is not necessary for
the first spatial concentration test.

## Go/no-go ordering

1. Free one-day Tardis integrity and storage pilot.
2. Free monthly Binance-futures mechanism test.
3. Free Binance spot/Coinbase cross-venue extension if Phase A is positive.
4. Free live collector for unbiased forward confirmation.
5. Paid 300-session QQQ MBP-10 transfer test only after the crypto mechanism
   survives forward validation.

This ordering maximizes hypotheses tested per dollar while preserving a clean
equity confirmation dataset.

## Sources

- Tardis downloadable CSV API: https://docs.tardis.dev/downloadable-csv-files/api
- Tardis Binance futures coverage: https://docs.tardis.dev/historical-data-details/binance-futures
- Tardis Binance spot coverage: https://docs.tardis.dev/historical-data-details/binance
- Tardis Coinbase coverage: https://docs.tardis.dev/historical-data-details/coinbase
- Coinbase WebSocket feed: https://docs.cdp.coinbase.com/exchange/websocket-feed/channels
- Binance public depth streams: https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md
- Kraken L2 book feed: https://docs-legacy.kraken.com/api/docs/websocket-v1/book/
- LOBSTER samples: https://data.lobsterdata.com/info/DataSamples.php
- LOBSTER event/book structure: https://data.lobsterdata.com/info/DataStructure.php
- Nasdaq TotalView description: https://www.nasdaq.com/products/data/equities/nasdaq-totalview
- FI-2010 paper: https://arxiv.org/abs/1705.03233
