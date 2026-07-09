# Point-in-Time Earnings and Futures-Curve Data Feasibility v1

Date: 2026-07-09

Outcome update: the frozen public-data `CrossAssetCarryTrendScout-v1` was implemented, independently audited, rerun, and passed all 13 predeclared gates. This advances only the predeclared five-market raw-contract replication for ES, ZN, CL, GC, and ZC; it does not constitute validation or trading approval. The earnings-revision candidate remains blocked pending genuine point-in-time consensus-vintage data.

## Decision

1. **Do not implement `PointInTimeEarningsRevisionDrift-v1` yet.** The event-surprise portion is attainable, but the exact historical consensus-revision panel is not proven by any currently accessible endpoint. Intrinio's Zacks API exposes a pre-release consensus for each reported event and current estimate records with fixed-lag comparison fields, but its published estimate schema does not expose a consensus observation timestamp suitable for reconstructing a daily point-in-time revision history.
2. **Advance the futures path with a zero-cost public mechanism scout.** The `pst-group/pysystemtrade` repository has 3,381 GitHub stars, GPL-3.0 licensing, and ships curated price/carry/forward contract series plus back-adjusted prices. A 15-market panel pinned to commit `883c8681cf880d83acad5c39b842403a8eac5676` has been downloaded and validated locally for 2010-01-04 through 2024-03-28.
3. Treat the public panel as a **cheap falsification dataset, not final validation evidence**. It lacks volume, open interest, first-notice dates, and the complete set of individual contracts, and its source documentation warns that the shipped data are stale and may include manual curation.
4. Use Databento only if the public-data scout shows a predeclared gross edge. Its GLBX.MDP3 dataset can then validate official settlements, open interest, definitions, and actual rolls. Keep full paid Norgate as a second-vendor fallback; its restricted Silver Trial remains unsuitable.
5. If Stevens grants suitable Bloomberg BEst historical access when the MFE begins, re-open the earnings/revision candidate. The Hanlon Financial Systems Center publicly confirms Bloomberg terminals, but public Stevens pages and the library A-Z list do not establish WRDS/CRSP/I/B/E/S access or bulk point-in-time export rights.

## Exact data contract: earnings/revision candidate

A defensible implementation needs all of the following:

- permanent security identifier and historical symbol mapping;
- historical investable-universe membership or an all-listed point-in-time universe;
- delisted securities and delisting returns/prices;
- actual earnings-release date and release session/time;
- fiscal period and actual EPS;
- consensus mean, dispersion, and analyst count immediately before release;
- **consensus observation timestamp for every historical snapshot** used to form revisions;
- vendor revision/restatement policy and a reproducible data-vintage rule;
- split-adjusted point-in-time prices and corporate actions.

A table that has one final consensus value per historical earnings event can test earnings surprise/PEAD. It cannot test a revision-history hypothesis unless it also preserves the successive consensus snapshots that were visible at each historical decision time.

## Earnings/revision providers audited

### Intrinio + Zacks: partial pass

Public price on 2026-07-09:

- Individual plan: **$150/month**;
- Startup: **$333/month to start**;
- the pricing page lists EPS estimates, EPS surprises, sales estimates/surprises, long-term growth, ratings, and target prices under Estimate Data;
- free trial is offered.

Verified Zacks EPS-surprise fields in Intrinio's current official Python SDK:

- `actual_reported_date`;
- `actual_reported_time`;
- `actual_reported_code` (`BTO`, `DTM`, or `AMC`);
- fiscal/calendar quarter and year;
- `eps_actual` and Zacks-adjusted actual;
- `eps_mean_estimate`, explicitly described as the **pre-earnings-release mean**;
- estimate count and standard deviation;
- amount and percentage surprise.

This is sufficient in principle for a timestamped earnings-surprise event panel. It is not enough by itself for daily analyst-revision history. The EPS-estimate model uses `date` as the fiscal period end and includes current and fixed-lag means, but does not expose an observation/as-of timestamp for a succession of archived snapshots. Before buying, Intrinio must answer in writing whether a bulk historical-vintage product exists outside the standard endpoint and whether cancelled subscriptions permit continued internal use of downloaded history.

Result: **PASS for surprise events; UNPROVEN/FAIL for exact historical revision paths.**

### Norgate US Stocks: pass for universe, membership, delistings, and prices

Public annual prices on 2026-07-09:

- Bronze: $270/year;
- Silver: $360/year;
- Gold: $450/year;
- Platinum: **$630/year**;
- Diamond: $1,260/year.

Platinum is the relevant level. The public product table includes:

- delisted US securities back to 1990;
- historical index constituents, including Russell 1000 history from July 1990 and S&P 500 history from January 1950;
- survivorship-bias-free watchlists and point-in-time membership functions;
- Python access on Windows.

Norgate explicitly states that its LSEG-sourced fundamentals and broker forecasts are **current only; historical data is not available**. It solves the universe/membership/delisting side, not the earnings-revision side.

A full-year Intrinio Individual plus Norgate Platinum stack would be **$2,430/year** before taxes. This is not justified until the missing historical revision-vintage question is resolved.

### Bloomberg through Stevens: potentially best incremental-cost route, but deferred

Stevens publicly documents Bloomberg terminals in the Hanlon Financial Systems Center. Once access begins, ask the lab or program data administrator:

1. Is historical Bloomberg BEst consensus available with explicit as-of dates?
2. Can data be exported programmatically through the Excel/API tools for research?
3. What are the row/security limits and retention rights?
4. Are delisted US securities and historical index constituent dates available?
5. Does Stevens also license WRDS, CRSP, Compustat, or I/B/E/S even though they do not appear in the public library A-Z search?

The public library search returned no WRDS result, so institutional access must not be assumed.

### LSEG I/B/E/S, FactSet Estimates, and WRDS/CRSP: technical gold standard, commercial-access fail

These institutional products can provide historical estimate vintages and, with CRSP or equivalent, delisting and identifier history. Public self-service prices were not found; they require sales or institutional licenses. They are not an actionable personal-data path today.

### Alpha Vantage demo: sample pass, research-data fail

The live demo `EARNINGS` endpoint returned 123 quarterly IBM rows with:

- fiscal date;
- reported date;
- reported EPS;
- estimated EPS;
- surprise and surprise percentage;
- report time (`pre-market`, `post-market`, etc.).

The endpoint does not expose consensus observation timestamps, historical membership, delisted-universe coverage, or a vintage/restatement guarantee. It is useful for prototyping an event schema, not for the final backtest.

### Nasdaq Data Link Zacks/Sharadar and free CHRIS-style alternatives

The premium pages require an authenticated account and public pages did not expose current self-service product prices or enough schema evidence to establish a complete point-in-time revision panel. They are not selected without a trial schema and explicit vintage documentation.

## Exact data contract: futures carry/trend candidate

A daily futures carry study needs:

- every individual contract, not only a vendor-adjusted continuous series;
- root, contract month/year, activation and expiration/last-trade dates;
- first-notice date for deliverable contracts;
- daily official settlement, volume, and open interest;
- tick size, point value/contract multiplier, and currency;
- exchange calendar and session convention;
- an auditable rule for choosing contracts using only information available before trade time;
- roll returns from actual contracts, separate from any back-adjusted research series.

Those remain the requirements for final validation. A zero-cost mechanism scout may use a curated price/carry/forward panel if contract identities are explicit and the result is barred from promotion until independently replicated with raw actual-contract data.

## Futures providers audited

### Public pysystemtrade dataset: pass for a zero-cost scout

The strongest high-star public candidate is `pst-group/pysystemtrade`, the open-source futures system created by Rob Carver and maintained by the pst-group organization. At audit time it had **3,381 stars and 1,042 forks**. The repository is GPL-3.0 licensed and its own backtesting documentation explicitly supports using the shipped CSV files for simulation.

The repository contains:

- 252 `multiple_prices_csv` files, about 465 MB in aggregate;
- 252 back-adjusted price files, about 248 MB in aggregate;
- explicit `PRICE`, `CARRY`, and `FORWARD` values and corresponding contract identifiers;
- roll calendars, point values, currencies, asset classes, roll configuration, and spread-cost configuration.

The selected public panel contains 15 markets spanning equity indices, Treasury futures, currencies, energy, metals, and agriculture. It was pinned to source commit `883c8681cf880d83acad5c39b842403a8eac5676`, downloaded without an account, normalized with the source library's business-day convention, and hash-verified. Carry is retained only when price, carry, and both contract identifiers coexist on one source timestamp; no signal input is forward-filled. Validation produced:

- **55,725 business-day panel rows** from 2010-01-04 through 2024-03-28;
- no duplicate normalized dates;
- valid `YYYYMM00` contract identifiers throughout;
- carry-ready coverage from 69.0% to 98.3% by market, with 13 of 15 markets above 83%;
- 58 selected price contracts since 2010 for most quarterly markets, 156 for natural gas, and 87 for gold.

The downloader and reproducibility manifest are:

- `scripts/download_public_futures_curve_data.py`;
- `external_artifacts/pysystemtrade_futures_data/883c8681cf88/manifest.json`.

The artifact directory is intentionally gitignored. The script records source URLs, hashes, the pinned commit, normalization rules, and per-market coverage.

Important limitations from the source documentation and local inspection:

- the data end on 2024-03-28;
- these are selected price/carry/forward series, not every raw listed contract;
- volume, open interest, exact first-notice dates, and complete exchange definitions are absent;
- roll calendars and multiple-price construction may contain maintainer judgment or manual edits;
- the source itself describes the shipped CSV data as stale and unsuitable for production;
- the source warns that some historical mini-contract series may use carry offsets differing from current roll configuration.

Result: **PASS for a predeclared zero-cost gross-edge scout; FAIL as sole evidence for validation or live trading.** If the signal fails here, stop without buying data. If it passes, require replication with Databento or another raw-contract source before promotion.

### Norgate Futures: full product passes; trial fails

Public terms on 2026-07-09:

- 6 months: $148.50;
- 12 months: **$270**;
- a Silver Trial is offered, but its authenticated description limits history to two years and advertises pre-built continuous contracts rather than the individual expired-contract history required here;
- around 100 markets across major global exchanges;
- history generally back to around 1980 or the first trading day;
- individual contracts plus unadjusted and arithmetically back-adjusted continuous contracts;
- close is the official settlement unless otherwise noted;
- deliverable continuous contracts roll before first notice; cash-settled contracts roll before last trade.

The live contract-details spreadsheet was downloaded and parsed during this audit. It contained:

- **105 contract families**;
- 27 stock-index, 26 agriculture/livestock, 24 interest-rate, 13 currency, 8 energy, 5 metal, and 2 commodity-index families;
- last-trading-day rules for all 105 families;
- first-notice rules for 32 deliverable families;
- contract size, quotation, tick size/value, point value, and currency.

The current `norgatedata` Python package (v1.0.77) was installed in an isolated run and introspected. It exposes:

- `futures_market_session_contracts`;
- `price_timeseries`;
- `first_notice_date`;
- `last_quoted_date`;
- `point_value`;
- `margin`.

The package initialized correctly but could not retrieve data because Norgate Data Updater and a subscription are not active. The restricted Silver Trial is not accepted as a substitute: two years of pre-built continuous contracts cannot validate historical curves or actual roll P&L.

Result: **PASS for the paid full product; FAIL for the trial. Do not activate the trial for this project.**

### Databento GLBX.MDP3: recommended initial source

Official documentation verified:

- all CME Globex futures and options, including spreads;
- history from **2010-06-06**;
- `statistics` schema includes settlement price, open interest, cleared volume, opening/closing prices, and limits;
- `definition` schema supplies instrument definitions and lifecycle metadata;
- continuous symbology supports calendar, open-interest, and volume ranks (`c`, `n`, `v`) but actual raw contracts remain available;
- continuous records include the underlying actual instrument ID, allowing roll reconstruction.

The current Python/DBN package was introspected. `InstrumentDefMsg` exposes, among other fields:

- raw symbol and asset/root;
- activation and expiration;
- maturity year/month/day/week;
- contract multiplier;
- currency and settlement currency;
- minimum price increment;
- underlying and unit-of-measure fields.

`StatMsg` exposes price, quantity, reference/event timestamps, update action, and statistic type. The current statistic enum includes `SETTLEMENT_PRICE`, `OPEN_INTEREST`, `CLEARED_VOLUME`, and `CLOSE_PRICE`.

Public pricing:

- usage-based historical data by GB;
- **$125 signup credits**;
- Standard subscription: $199/month;
- Plus: $1,750/month plus licenses, annual contract;
- Unlimited: $4,500/month plus licenses, annual contract.

The usage-based route is appropriate for the bounded sample. A precise quote requires a Databento account/API key and `metadata.get_cost`; no key is configured on this machine. Do not start a subscription for the pilot—first request the quote and keep the download within signup credits.

Result: **PASS as the initial source.** CME alone supplies a sufficiently diversified first universe across equity indices, rates, currencies, energy, metals, and agriculture. History from June 2010 is adequate for the first falsification study.

### Free continuous-contract sources: reject for the final study

Nasdaq Data Link CHRIS and similar generic front-/second-contract series can be useful for a visual sanity check. They do not by themselves establish the exact underlying contract held each day, delivery/notice handling, or a fully auditable roll-return decomposition. A carry edge can be created or destroyed by those conventions, so these feeds are not accepted as primary evidence.

A live no-account check of Yahoo Finance confirmed the distinction. `ES=F`, `CL=F`, `GC=F`, and `ZN=F` each returned 4,159 daily continuous-series observations for the requested 2010-2026 window. Current individual contracts were also visible, but expired-contract retention was unusable: `CLZ20.NYM` returned no data and `ESZ20.CME` returned only one observation. These endpoints can support a rough trend study, not historical curve reconstruction.

CME's public website shows current settlements and daily bulletins interactively, but its web endpoint returned HTTP 403 with an explicit anti-scraping response during this audit. It is not a stable or permitted substitute for a licensed bulk archive. Publicly viewable data and freely automatable 16-year contract history are different products.

### CME DataMine and institutional vendors

Official exchange history is authoritative, but a cross-asset study would require multiple venue products, contract metadata handling, and commercial terms. It offers no practical advantage over Norgate for the first daily scout, while Databento can independently check the CME portion.

## Bounded acquisition and falsification plan

### Step 1: public data acquisition — completed

The 15-market public panel has been downloaded, normalized, pinned, and hash-verified. No account, subscription, or payment was required.

### Step 2: freeze a public-data scout before viewing returns

Freeze `CrossAssetCarryTrendScout-v1` around the limitations of the available data:

1. use only the 15 preselected markets and the 2010-01-04 through 2024-03-28 window;
2. derive carry only from same-date `PRICE` and `CARRY` values with explicit contract-month spacing;
3. use the supplied back-adjusted series only for trend and return estimation, never to infer the curve;
4. do not forward-fill missing carry observations;
5. predeclare trend horizon, volatility scaling, rebalance frequency, costs, and SPY-combination test;
6. report full-period, pre/post-2017, asset-class, and leave-one-asset-class-out results;
7. reject immediately if gross performance, signal monotonicity, and SPY utility fail.

The scout can reject the mechanism. It cannot validate it for deployment because the public panel lacks raw volume/open-interest roll evidence and may reflect manually curated rolls.

### Step 3: paid-data replication only after a public-data pass

If and only if the frozen scout passes, obtain a Databento cost quote and replicate ES, ZN, CL, GC, and ZC first. Require actual-contract enumeration, official settlements, volume, open interest, definitions, expiry/notice safety, and a previous-session-only roll rule. Explain every mismatch with the public panel before broader validation. Norgate may be added only if a second vendor is still justified.

## Current blocker and next action

There is **no data-account blocker for the mechanism scout**. The next action is to freeze the public-data hypothesis before examining strategy returns, then implement and run that one bounded scout. Do not activate the Norgate trial or create a Databento account yet.

The earnings candidate remains blocked unless Intrinio or Stevens can supply true historical consensus snapshots with observation dates.

## Sources

- Intrinio pricing: https://intrinio.com/pricing
- Intrinio Zacks EPS Surprises: https://data.intrinio.com/data-tags/product/zacks-eps-surprises
- Intrinio Python SDK Zacks models: https://github.com/intrinio/python-sdk/tree/master/intrinio_sdk/models
- Alpha Vantage earnings documentation: https://www.alphavantage.co/documentation/#earnings
- Norgate stock packages: https://norgatedata.com/stockmarketpackages.php
- Norgate futures package: https://norgatedata.com/futurespackage.php
- Norgate data content and contract spreadsheet: https://norgatedata.com/data-content-tables.php#futures
- Norgate Python package: https://pypi.org/project/norgatedata/
- Databento GLBX.MDP3: https://databento.com/docs/venues-and-datasets/glbx-mdp3
- Databento symbology: https://databento.com/docs/standards-and-conventions/symbology
- Databento pricing: https://databento.com/pricing
- pysystemtrade repository: https://github.com/pst-group/pysystemtrade
- pysystemtrade futures-data documentation: https://github.com/pst-group/pysystemtrade/blob/develop/docs/data.md
- Stevens Hanlon facilities: https://www.stevens.edu/school-business/hanlon-financial-systems-center-facilities
- Stevens library A-Z WRDS search: https://library.stevens.edu/az.php?q=WRDS
