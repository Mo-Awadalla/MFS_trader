# FreePublicMicrostructureData-v1

Status: data-feasibility research; no strategy implementation or validation approval.

## Executive answer

Some non-HFT microstructure information is free publicly, but the complete US-equity dataset needed for broad order-flow research is not freely available.

The free options divide into three categories:

1. **Free but incomplete US-equity feeds**: Alpaca Basic/IEX gives live and historical data for one exchange, not consolidated US equity flow.
2. **Free SEC market-structure analytics**: SEC MIDAS exposes visualizations and downloadable aggregate datasets, but not the raw per-order/order-book records used internally by the SEC.
3. **Free full-depth data in another market**: Binance publishes crypto trade/aggregate-trade data and public market-data APIs, but crypto is not a valid substitute for US-equity market microstructure.

The exact target—broad historical US equity trades/quotes and full depth/order events across venues—is not free at institutional breadth.

## Source matrix

| Source | Free publicly? | Data exposed | Historical/breadth | Fit |
| --- | --- | --- | --- | --- |
| SEC MIDAS public pages | Yes | Daily aggregate market-structure metrics, quote-lifetime distributions, public visualizations | Current public CSVs observed from 2012 onward; market/decile aggregates, not symbol-level raw events | Useful for market-regime features, not stock-level intraday order-flow signals |
| Alpaca Basic/IEX | Yes | IEX trades, top-of-book quotes, bars, snapshots, websocket streams | Historical data since 2016; one exchange; free websocket symbol limit; recent SIP access restricted | Good plumbing and venue-local experiment; not consolidated US flow |
| Alpaca SIP / Algo Trader Plus | No, currently listed at $99/month | Consolidated US trades and quotes from CTA/UTP, 100% market coverage | Historical since 2016; no free-plan recent-data restriction | Best affordable first Level-1 research path; still not full depth |
| Nasdaq U.S. Equity Tick History | No public free access identified | Consolidated Level-1 tick quotes/trades, normalized, cloud/API/bulk access | Commercial product | Stronger Level-1 source; paid/contact-sales product |
| Nasdaq TotalView / ITCH | No public free broad history identified | Nasdaq depth/order messages depending on product | Commercial/exchange-specific | Relevant for order book research; not free broad data |
| LOBSTER | No, except limited samples tied to book ownership or academic access | Reconstructed Nasdaq limit order books | Historical academic product | High-quality book research; not free general access |
| Binance public data | Yes | Crypto trades, aggregate trades, klines; public live market-data APIs | Broad crypto history | Good engineering sandbox; not evidence for US equities |
| Academic datasets | Sometimes | Small/static LOB or trade/quote samples | Usually narrow symbols and periods | Useful for parser/unit tests, not production research |

## 1. SEC MIDAS: free analytics, not free raw MIDAS

Official SEC page:

- https://www.sec.gov/securities-topics/market-structure-analytics/midas-market-information-data-analytics-system

The SEC states that MIDAS internally collects and processes:

- posted orders and quotes on national exchanges;
- order modifications and cancellations;
- trade executions against posted orders;
- off-exchange trade executions;
- equity, ETP, options, and futures data;
- exchange timestamps and collection-point timestamps.

The SEC says its internal MIDAS system processes roughly one billion records per day from 13 national equity exchanges and can analyze thousands of stocks across six months or a year.

This is exactly the class of data we would want. However, the public page does not provide the raw order-level MIDAS feed.

Public SEC market-structure analytics include:

- interactive visualizations;
- daily aggregate trade-to-order volume;
- cancel-to-trade ratios;
- hidden volume/rate;
- odd-lot volume/rate;
- quote-life distributions;
- stock/ETP and market-cap/price/turnover/volatility aggregates.

Official visualization page:

- https://www.sec.gov/securities-topics/market-structure-analytics/market-activity-data-visualizations

Example public CSVs verified:

- `https://www.sec.gov/marketstructure/datavis/csv/mar_graph_data.csv`
- `https://www.sec.gov/marketstructure/datavis/csv/stocks_canceltotrade.csv`
- `https://www.sec.gov/marketstructure/datavis/csv/condfreq_largestocks_1.csv`

The observed files provide daily aggregate series. For example, `mar_graph_data.csv` contains date-level stock and ETP metrics for cancel/trade, trade/order, hidden, and odd-lot activity. `stocks_canceltotrade.csv` contains date-level decile aggregates.

What we can do with these free SEC files:

- form market-wide microstructure-regime variables;
- test whether high odd-lot, hidden-volume, cancel/trade, or quote-life states predict next-day or next-session market behavior;
- build descriptive market-structure reports;
- test broad regime conditioning for SPY/QQQ rather than stock-level order-flow selection.

What we cannot honestly do with these files:

- reconstruct a stock’s order book;
- calculate stock-level order-flow imbalance;
- identify trade direction from raw quote/trade sequence;
- model venue-level queue state;
- test cross-sectional order-flow signals across individual stocks;
- claim the result represents the SEC’s raw MIDAS data.

Verdict: **free and valuable, but aggregate and too coarse for the original stock-level microstructure plan**.

## 2. Alpaca Basic/IEX: free venue-local market data

Official documentation:

- https://docs.alpaca.markets/docs/about-market-data-api
- https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data
- https://docs.alpaca.markets/us/docs/historical-stock-data-1
- https://alpaca.markets/data

Alpaca’s current documentation states:

- Basic is free;
- Basic equity real-time coverage is IEX only;
- IEX is approximately 2.5% of US market volume according to the historical-data documentation;
- historical data is available since 2016;
- Basic has a latest-15-minute restriction for SIP data;
- Basic websocket subscriptions are limited compared with Algo Trader Plus;
- SIP covers all US stock exchanges and 100% of market volume, but requires the paid plan;
- Algo Trader Plus is currently listed at $99/month.

The real-time stock stream exposes trades and quotes with fields such as:

- symbol;
- exchange;
- price;
- size;
- trade condition;
- timestamp;
- quote bid price/size;
- quote ask price/size;
- quote timestamp.

This is enough to build a venue-local Level-1 experiment:

- signed IEX trade imbalance;
- quote midpoint returns;
- spread state;
- bid/ask size imbalance;
- trade intensity;
- short-horizon realized volatility;
- 5–30 minute aggregated features.

It is not enough to claim full-market US-equity order-flow alpha. A stock’s IEX flow can differ substantially from consolidated flow, and a venue-local signal may be a routing or venue artifact.

Verdict: **free for engineering and a narrowly labeled IEX experiment; insufficient for broad US-equity discovery**.

## 3. Alpaca SIP: affordable, but not free and not full depth

The paid SIP feed is materially better for a first serious experiment because it combines CTA and UTP data from all US exchanges.

It provides consolidated Level-1 trades and quotes, not a full market-by-order book. It can support:

- consolidated trade imbalance;
- NBBO spread and midpoint features;
- quote-size imbalance at the best bid/ask;
- trade/quote intensity;
- liquidity and volatility state;
- broad multi-symbol 5–30 minute panels.

It cannot by itself support:

- full depth beyond the best bid/offer;
- queue position;
- cancellation dynamics at every price level;
- complete order-book reconstruction;
- venue-specific order-placement optimization.

Verdict: **the most plausible affordable first step, but not free and not full depth**.

## 4. Nasdaq products

Nasdaq’s official U.S. Equity Tick History page states that the product provides historical tick-by-tick quotes and trades for Nasdaq-, NYSE-, NYSE American-, regional-, and OTC-listed securities. It describes the product as consolidated Level-1 tick data accessible through Nasdaq Data Link APIs, SQL, and bulk download.

Source:

- https://www.nasdaq.com/solutions/US-Equity-Tick-History

Nasdaq’s market-data pages separately list TotalView and historical ITCH products. These are exchange-specific depth/order-message products rather than a free public download.

Verdict: **relevant commercial options, not free public data**.

## 5. LOBSTER

LOBSTER provides reconstructed limit-order-book data and is directly relevant to order-book research. The current LOBSTER platform describes its data as premium Nasdaq market data and order-book reconstructions. The current platform offers a book-owner sample request and a sign-in data-download portal rather than a general free historical feed.

Source:

- https://lobsterdata.com/

Verdict: **research-grade but not a free general source**.

## 6. Binance and other crypto exchange data

Binance maintains a public data collection site:

- https://data.binance.vision/
- https://github.com/binance/binance-public-data/

The public collection includes spot and futures market data with daily/monthly trade, aggregate-trade, and kline files, while exchange APIs/websockets provide current market-data streams.

This is genuinely useful for:

- building a parser for event-level trades;
- testing signed-volume and order-book feature construction;
- validating storage and aggregation logic;
- learning how to replay a market-data stream.

It is not a valid substitute for US-equity research because crypto has:

- different venue fragmentation;
- different fee and rebate structures;
- continuous trading;
- different participant composition;
- different market-making economics;
- different corporate/event structure;
- different liquidity and manipulation risks.

Verdict: **free engineering sandbox, not a US-equity alpha-data substitute**.

## 7. What is available for free right now?

### Free immediately

- SEC MIDAS aggregate market-structure CSVs and visualizations.
- Alpaca IEX trades, quotes, bars, snapshots, and websocket data.
- Binance public crypto trade/aggregate-trade datasets.
- Small academic order-book datasets and book samples.

### Not free at the needed breadth

- Consolidated historical US equity trades and quotes without the IEX-only limitation.
- Full US equity order books across venues.
- Historical Nasdaq/NYSE order-message feeds at institutional breadth.
- Vendor-normalized TAQ/order-book data with broad retention and redistribution rights.

## 8. Recommended no-cost experiment

Before paying for data, use the free sources for a data-feasibility and plumbing experiment rather than a trading claim.

### Phase A: SEC aggregate-regime study

Use the public SEC CSVs to create daily variables:

- stock cancel/trade ratio;
- ETP cancel/trade ratio;
- trade/order volume;
- hidden rate and hidden volume;
- odd-lot rate and volume;
- market-cap/turnover/volatility decile metrics;
- quote-life distribution summaries.

Join those variables to SPY/QQQ daily or available intraday returns. Test only predeclared market-regime relationships. This is not a stock-level order-flow strategy.

### Phase B: IEX Level-1 engineering study

Use free Alpaca Basic/IEX data for a small, explicitly labeled venue-local panel.

Build:

- signed trade imbalance using quote-based trade classification;
- bid/ask size imbalance;
- spread in basis points;
- trade intensity and volume shock;
- 5-minute and 30-minute aggregates;
- next-bar returns with a fixed lag.

Do not compare it to full-market SIP results unless the data source is changed and the experiment is labeled as a new source test.

### Phase C: promotion gate

Only consider paying for SIP if the free studies show:

- the data pipeline is correct;
- timestamps and session handling are correct;
- features have reasonable coverage;
- the signal direction is economically interpretable;
- the effect is not obviously an IEX-only artifact;
- storage and compute costs are manageable.

A paid SIP test should then be a source-replication/data-quality experiment, not an invitation to tune the signal.

## Final verdict

The answer to “is the professional-grade microstructure information free?” is:

- **Partly yes for aggregate market structure and single-venue Level-1 data.**
- **No for broad consolidated US equity order-flow and full depth at useful historical scale.**

The most honest free path is not to pretend that IEX is full-market data. It is:

1. use SEC MIDAS aggregate files for market-wide regime research;
2. use Alpaca IEX for a clearly labeled venue-local pipeline test;
3. only buy consolidated SIP if those tests justify the data upgrade;
4. treat full depth/order-book research as a separate paid-data project.
