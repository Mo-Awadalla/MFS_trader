# Databento acquisition audit for SPY / leveraged-inverse-SPY research

**Verified:** 2026-07-27 against official Databento documentation and pricing pages.  
**Decision objective:** data that can support non-latency mechanisms trading at least twice weekly, preferably daily, rather than HFT/queue-position strategies.

## Bottom line

Buy the smallest event-level panels that introduce genuinely new information, in this order:

1. **NYSE Arca auction/market data (`ARCX.PILLAR`)** — `imbalance` + `statistics`, then `mbp-1`/`trades`, for `SPY, SSO, SDS, UPRO, SPXU, SH` (and any other explicitly verified Arca-listed S&P-500 ETF share classes). This is the best first purchase because NYSE Arca is the relevant listing/auction venue for many ETFs and the feed exposes scheduled opening/closing auction imbalance, indicative prices, collars, paired quantity, side, status, and realized auction prices. Candidate mechanisms: close-auction pressure/next-session reversal or continuation, close-vs-continuous dislocation, and execution-aware overnight allocation. Frequency: daily opportunities; no nanosecond reaction is required if signals are frozen before a declared cutoff or used for next-session positions.
2. **CME equity-index futures (`GLBX.MDP3`)** — start with `mbp-1`, `trades`, `ohlcv-1s`/`1m`, `statistics`, and `definition` for actual `ES` and `MES` contracts; add `mbp-10` only if L1 features pass; defer `mbo`. Candidate mechanisms: overnight futures lead into ETF open, Globex/RTH inventory and liquidity regimes, basis/dislocation, and opening-gap continuation/reversal. Frequency: daily. Use actual contracts and lifecycle/definition records; do not validate on a back-adjusted continuous series alone.
3. **SPY options (`OPRA.PILLAR`)** — `definition` plus narrowly filtered SPY chain data: `cmbp-1` (consolidated BBO), `trades`, `tcbbo` where available, and `statistics`; limit initially to liquid expiries and a predeclared moneyness band. Candidate mechanisms: put/call pressure, skew/term-structure changes, 0DTE/near-expiry demand, and option-to-underlying information diffusion. Frequency: daily. Do **not** acquire the full OPRA universe first; Databento itself recommends batch delivery for historical `cmbp-1` due to volume.
4. **CFE volatility futures (`XCBF.PITCH`)** — `mbp-1`, `trades`, `statistics`, and `definition` for actual `VX` and `VXM` contracts; add depth only after a Level-1 scout passes. Candidate mechanisms: VIX-futures curve slope/roll, front-vs-second-month stress transitions, and equity/volatility divergence. Frequency: daily to several times weekly. This is CFE futures/order-book data, **not** a Cboe spot-index feed.
5. **Derived multi-venue US-equity L1 (`EQUS.MINI`)** — `tbbo`, `mbp-1`, `trades`, or sampled `bbo-1s`; universe `SPY, SSO, SDS, UPRO, SPXU, SH` plus predeclared controls such as `QQQ, IWM, TLT, HYG` if needed. Candidate mechanisms: ETF-family relative pressure, stale/dislocated quotes, and risk-on/risk-off diffusion. Frequency: daily/intraday. It is useful breadth, but it is not documented as the official SIP NBBO and venue identity is anonymized.
6. **Reference data (required hygiene, not primary alpha):** security master PIT history, corporate actions, and adjustment factors. Use to verify ETF identity/listing, avoid ticker/identifier breaks, preserve delistings, and adjust prices. Corporate actions and factors begin 2018-05-01; security master begins 2005-01-01.
7. **`EQUS.SUMMARY`** — cheap low-frequency complement: consolidated US volume in `statistics`, NLS+ end-of-day summary in `ohlcv-1d`, and definitions. Useful for daily liquidity/volume regimes, but it contains no intraday quote/depth stream.
8. **Other single-venue equity depth (`XNAS.ITCH`, BZX/EDGX/BYX/EDGA, MEMX, etc.)** — acquire only after the Arca/ES/options scouts identify a venue-specific hypothesis. `XNAS.ITCH` does have NOII auction imbalance and cross statistics, but it is Nasdaq venue-local, not a consolidated US-equity book and is less directly tied to Arca-listed SPY-family auctions.

## What the schemas contain

- **`trades` (L1):** every reported trade event, tick by tick. It does not reconstruct the quote/book by itself.
- **`mbp-1` (L1):** every trade and book update at one aggregated price level (BBO) for that dataset/publisher. For a venue feed it is venue-local; for `EQUS.MINI` it is Databento's anonymized aggregate across its component feeds.
- **`tbbo` / options `tcbbo`:** each trade with the BBO immediately before that trade. Good first microstructure schema because it avoids buying every quote update, while preserving a pre-trade spread/context snapshot.
- **`bbo-1s` / `bbo-1m` (L1):** the last BBO and sale on fixed intervals; compact but discards event ordering and within-bin path.
- **`mbp-10` (L2):** every trade and book update with ten aggregated price levels. Larger than L1; useful for depth imbalance, replenishment, and sweep-resilience features.
- **`mbo` (L3):** every displayed order event at every level, including add/modify/cancel/trade/fill semantics where the source protocol supports them. Highest volume; mainly justified for queue/replenishment/order-flow hypotheses. CME `GLBX.MDP3` is derived from MBOFD since May 2017; pre-May-2017 is legacy FIX/FAST.
- **`ohlcv-1s/1m/1h/1d` (L0):** open/high/low/close and volume in fixed bars. Cheap for scouting, but not enough for quote pressure, spreads, auction evolution, or trade classification.
- **`statistics` (L0):** venue-supplied instrument statistics, not generic technical indicators. Examples: official auction/cross prices and quantities on Nasdaq/NYSE feeds; settlement, open interest, limits, session high/low/open/close, and cleared/block volume on CFE/CME where supplied.
- **`imbalance` (labeled L3 in Databento's schema catalog):** auction-specific state such as paired quantity, total/market imbalance, side, reference and indicative-clearing prices, collars/status/type when provided by the venue. It is distinct from `statistics`, which records auction outcomes/official values.
- **`definition`:** instrument metadata such as raw symbol, asset/security type, tick size, expiration, strike, and other contract/listing properties.
- **`status`:** source session/market-state events such as pauses, halts, short-sale restrictions, and auction start when provided.

## Coverage findings

### US equities

Databento's current venue catalog lists individual proprietary equity feeds (Nasdaq, NYSE family, Cboe equity venues, MEMX, IEX, MIAX Pearl, Blue Ocean) plus `EQUS.MINI` and `EQUS.SUMMARY`. I did **not** find a separately listed CTA/UTP SIP dataset providing official consolidated US-equity NBBO and all SIP trades.

- `EQUS.MINI` is explicitly described as a **derived top-of-book** dataset sourced from proprietary ATS and Reg NMS venue feeds. Databento calculates one aggregate BBO, adds quantity including odd lots at the best price, does not provide component-venue quotes, anonymizes trade venue (`publisher_id` always `EQUS.MINI.EQUS`), and sets sequence to zero. Available schemas: `mbp-1`, `bbo`, `tbbo`, `trades`, OHLCV 1s/1m/1h/1d, definitions. Therefore do not label it “SIP NBBO” or use it for venue-routing attribution.
- `EQUS.SUMMARY` is NLS+ consolidated volume and end-of-day summary only (`ohlcv-1d`, `statistics`, `definition`). Consolidated volume is across all US exchanges; it is not an intraday consolidated quote feed.
- `ARCX.PILLAR` is full NYSE Arca depth, with one-second changed imbalance updates during auction periods and outcome records in `statistics`. Documented scheduled windows: Early Open 02:30–04:00 ET (all UTP), Core Open 08:00–09:30 ET (Arca-listed only), Close 15:00–16:00 ET (all UTP).
- `XNAS.ITCH` is full Nasdaq exchange depth. NOII is normalized into `imbalance`; opening/closing/EMC cross outcomes into `statistics`. Nasdaq documents 10-second opening/closing imbalance updates initially, then one-second updates near the cross.

### Equity options

`OPRA.PILLAR` is consolidated US equity-options top-of-book, last sale, and daily statistics covering 18 option venues as of Databento's November-2025 count. It has venue-attributed trades and an OPRA consolidated BBO (`cmbp-1`); Databento does not publish regional-venue BBO records. `tcbbo` gives NBBO at trade time. OPRA trade side is not disseminated (`side=N`), so infer direction with a declared quote rule rather than treating side as observed.

Critical history break: before 2023-02-28 the data came from subsampled data, not OPRA packet captures. `cmbp-1`, `cbbo-1s`, and `tcbbo` are unavailable before that date; `cbbo-1m` is the highest BBO granularity, `ts_recv` is not a genuine capture timestamp, venue-at-NBBO fields are absent, and `statistics` contains only open interest. Do not splice pre/post-2023 quote features as if homogeneous.

Databento's schema catalog contains market-data and reference schemas but no provider-computed implied-volatility or Greeks schema. Treat IV, delta/gamma/vega, skew, and exposure aggregates as derived calculations from option quotes/trades + definitions + an underlying/rate model; confirm any future derived-data entitlement in the portal before assuming otherwise.

### CME ES/MES

`GLBX.MDP3` covers CME/CBOT/NYMEX/COMEX full depth, all futures and options on futures from **June 2010**. Databento states the normalized source is MBOFD (from May 2017), not CME incremental MBP; L1/L2 books are constructed from that event stream. Timestamps include nanosecond `ts_event` (matching-engine received), `ts_in_delta`/sending time, and Databento `ts_recv`. This is appropriate for actual `ES`/`MES` contracts, definitions, settlement/open-interest/volume statistics, and synchronized ETF studies.

### Cboe volatility/index coverage

`XCBF.PITCH` is CFE full depth for futures/options, including `VX`, `VXM`, and options on VX futures. Its `statistics` includes settlement, open interest, price limits, and end-of-day values. The official Databento venue catalog reviewed here does **not** list a Cboe Global Indices/spot-index dataset. Therefore Databento CFE data does not by itself provide the spot VIX index or a historical SPX index feed. If a mechanism requires spot VIX/VIX9D/VVIX/SPX index values, license/verify those separately; otherwise use tradable VX/VXM curve variables.

## Timestamps and leakage controls

Databento generally preserves nanosecond `ts_event` plus capture-server `ts_recv`; some feeds have a source sending timestamp represented by `ts_in_delta`. Semantics are feed-specific:

- CME and NYSE Pillar: `ts_event` = matching-engine received; source sending timestamp also available; `ts_recv` = Databento capture.
- Nasdaq TotalView: one exchange timestamp; `ts_in_delta` is effectively `ts_recv - ts_event`, not a separate source timestamp.
- OPRA: `ts_event` = consolidator-processed block timestamp; `ts_recv` = Databento capture; `ts_in_delta=0`.
- `EQUS.MINI`: `ts_event` is documented as matching-engine received and `ts_recv` as capture; `ts_in_delta=0`.

For non-latency tests, define an observable cutoff and use only records whose appropriate availability timestamp precedes it. Keep exchange event time and capture time; do not sort separately downloaded trade/quote streams on event time and assume equal-timestamp causal order.

## History and cost discipline

Officially documented exact starts found in this audit:

- `GLBX.MDP3`: June 2010.
- Security master: 2005-01-01.
- Corporate actions: 2018-05-01.
- Adjustment factors: 2018-05-01.
- OPRA: exact dataset start not stated on the venue page, but a material quality/schema break is documented at 2023-02-28.
- Exact starts for `ARCX.PILLAR`, `XNAS.ITCH`, `EQUS.MINI`, `EQUS.SUMMARY`, and `XCBF.PITCH` were not stated on the official venue pages reviewed. Query the account's `metadata.get_dataset_range` / portal before budgeting and freeze the returned range; do not infer a venue-specific start from Databento's broad “15+ years” marketing statement.

Pricing is usage-based ($/GB) or subscription; the pricing page provides an estimator and Databento advertises $125 initial credits. Exact cost depends on dataset, schema, symbols, date range, encoding/compression, and licensing, so no unsupported dollar estimate is supplied here. Relative burden is clear:

`ohlcv/statistics/definition` < sampled `bbo`/`tbbo` < event `trades`/`mbp-1` < `mbp-10` < `mbo`; OPRA `cmbp-1` across the whole chain is exceptionally large. Request metadata/cost estimates before download; use DBN + compression + batch jobs for large history; purchase a small locked sample first and promote depth only after an information-content gate.

## Recommended staged purchase

1. **Pilot A:** `ARCX.PILLAR` `imbalance,statistics,mbp-1,trades` for the six core ETFs, plus reference data. Use enough history for multiple market regimes after confirming exact range.
2. **Pilot B:** `GLBX.MDP3` `mbp-1,trades,statistics,definition` for actual ES/MES front and next contracts; add 1-second bars for rapid feature development.
3. **Pilot C:** `OPRA.PILLAR` narrowly filtered SPY options only, post-2023-02-28 first; derive IV/skew and lock model assumptions.
4. **Pilot D:** `XCBF.PITCH` VX/VXM front several contracts, then test whether curve state adds incremental out-of-sample utility over ES/Arca signals.
5. Buy `mbp-10`/`mbo` only when an L1 pilot passes predeclared gross-edge, stability, turnover, and after-cost gates. A data purchase cannot establish “materially outperforming SPY without luck”; that requires chronological holdouts, multiple regimes, realistic spreads/fees/financing, benchmark-relative utility, multiplicity control, and a final untouched test.

## Official sources

- Venue/dataset catalog: https://databento.com/docs/venues-and-datasets
- Schema catalog: https://databento.com/docs/schemas-and-data-formats
- Pricing: https://databento.com/pricing
- `EQUS.MINI`: https://databento.com/docs/venues-and-datasets/equs-mini
- `EQUS.SUMMARY`: https://databento.com/docs/venues-and-datasets/equs-summary
- NYSE Arca Integrated: https://databento.com/docs/venues-and-datasets/arcx-pillar
- Nasdaq TotalView-ITCH: https://databento.com/docs/venues-and-datasets/xnas-itch
- OPRA: https://databento.com/docs/venues-and-datasets/opra-pillar
- CME Globex MDP 3.0: https://databento.com/docs/venues-and-datasets/glbx-mdp3
- CFE: https://databento.com/docs/venues-and-datasets/xcbf-pitch
- Corporate actions: https://databento.com/docs/venues-and-datasets/corporate-actions
- Adjustment factors: https://databento.com/docs/venues-and-datasets/adjustment-factors
- Security master: https://databento.com/docs/venues-and-datasets/security-master
