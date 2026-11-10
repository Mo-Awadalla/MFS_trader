# Microstructure research roadmap — 2026-09-25

## Decision

Run the three BTC mechanisms as separate research questions, then test transfer to the SPY cash open and finally cross-market timing. Start with a returns-blind inventory and timestamp audit. Historical data already used by this repository are development evidence; any trading claim needs a frozen rule and a genuinely forward test.

No result below is a newly measured edge, and none authorizes trading or paid data acquisition.

## What is already available

| Question | Local evidence | Readiness |
| --- | --- | --- |
| Leverage instability | Binance BTCUSDT perpetual 30-minute price, premium, funding, and five-minute OI metrics through 2025-12-31; integrity report documents timing and gaps | The existing crowded-long development test failed. Liquidation prints are needed to call an event a forced unwind. |
| Liquidity withdrawal | Twenty Binance BTCUSDT days with aggregate trades and bookTicker; only one day with bookDepth; one older Tardis incremental L2 day; SPY-family MBP-1 opening windows | BBO withdrawal can be measured on the twenty days. Cancellation and full-depth withdrawal need better overlapping L2. The existing SPY MBP-1 concentration pilot failed its forward ranking gate. |
| Aggressive flow | Binance BTCUSDT aggregate-trade archives on selected dates; 30-minute perp klines also contain taker-flow summaries | Ready for a short-horizon microstructure pilot on sampled dates; bar summaries cannot identify a seconds-scale sequence. |
| SPY cash open | ARCX.PILLAR opening imbalance messages, ETF MBP-1 opening windows, and EQUS.MINI TBBO | Ready for a new causal-object audit. Earlier opening-imbalance variants are heavily tested; TBBO alone cannot reconstruct standing quote age. |
| ES at 09:30 ET | Existing ES research artifacts, but no audited synchronized ES book/auction feed is established by this inventory | Verify the ES feed and contract roll before a joint SPY/ES test. Treat 09:30 as the US cash-market opening boundary, not an ES auction print. |
| BTC ↔ Polymarket | Polymarket five-minute contract and sampled price data; Binance research price panel ends in 2025 | Blocked for lead/lag: stored Polymarket sampled prices are June–July 2026, with no matched stored BTC tick/quote series in this audit. |
| BTC ↔ SPY | Historical BTC and SPY inputs exist | The prior BTC-spot attention and BTC-perpetual OI transfer strategies failed development gates. A new test needs a distinct mechanism or untouched forward data. |

Key local evidence: [Binance integrity](../data/parquet/binance_bitcoin_derivatives_public_v1/integrity_report.json), [Polymarket manifest](../data/parquet/polymarket_bitcoin_5m_public_v1/manifest.json), [crowded-long development result](../data/parquet/bitcoin_crowded_long_unwind_binance_v1/development/report.md), [SPY auction data audit](NEW_DATA_TECHNICAL_AUDIT_V34.md), [SPY failure synthesis](SPY_CASH_ETF_FAILURE_SYNTHESIS_V54.md), [BTC/SPY prior result](SPY_BTC_PERPETUAL_FRESH_POSITION_REPORT_V44.md), and [MBP-1 pilot](../docs/research_scout/NavierStokesLiquidityFeasibilityV1.md).

## Phase 1 — BTC

### Track 1: When does leverage become unstable?

**Object:** the hazard of a large, rapid move conditional on a *known-at-decision* leverage state. Use settled funding only after its publication guard; timestamp OI by its actual `create_time`; use completed premium-index and price bars. A candidate crowded-long state is unusually positive funding and premium with rising BTC-denominated OI and positive prior return. Mirror the construction for crowded shorts. Funding and OI do not reveal individual positions or liquidation prices.

**First outcome:** future downside/upside excursion over prespecified 30-minute and two-hour windows, plus OI contraction. **Stronger outcome:** synchronized liquidation trades, if an audited liquidation source is available. Label a forced unwind only with this stronger evidence. Compare with matched prior return, realized volatility, clock, and OI-only/funding-only/premium-only controls. Test both continuation and reversal; do not assume an extreme funding state must reverse.

**Prior result and decision gate:** the existing [crowded-long specification](bitcoin_crowded_long_unwind_binance_v1.json) fired on only 15 of 849 complete development days. Its gross short mean was +58.8 bps, but the 95% interval crossed zero and the minimum-event gate failed; later partitions stayed locked. That exact rule is closed. A genuinely new leverage mechanism would need distinct evidence such as synchronized liquidation prints and must add forward, date-blocked predictive value beyond price/volatility and each component, with enough independent events and stable year/regime effects. Only then examine entry/exit prices, actual funding cash flow, fees, spread, and slippage.

### Track 2: When does liquidity disappear?

**Object:** visible book withdrawal *before* a price move. Reconstruct ordered BBO updates from gap-checked bookTicker and aggregate-trade files. Measure spread widening, near-touch depth loss, and failed replenishment. Cancellation-versus-execution share requires overlapping incremental L2; it is not identified by the twenty BBO days. Use only the book state available at decision time; never infer a cancellation from two snapshots if intervening trades or updates are missing.

**First outcome:** next 30- and 60-second midpoint excursion and direction. Compare against spread, depth, imbalance, realized volatility, trade intensity, and contemporaneous price movement. Separate two claims: (1) higher move hazard and (2) signed direction. These may have different answers. Require improvement across held-out calendar days and a quote-age/freshness audit. A single venue's displayed depth is not total market liquidity.

### Track 3: Who is aggressive?

**Object:** buyer-initiated minus seller-initiated notional from aggregate trades, using the exchange maker-side flag with its sign checked against sample prints. Aggregate within frozen 10-second windows; also record burst concentration and whether trades move the prevailing quote. An aggregate trade can include multiple fills from a taker order, so count it according to its actual quantity rather than as one raw execution.

**First outcome:** next 30- and 60-second midprice return, excluding the contemporaneous impact window. Compare with prior return, total trade volume, volatility, spread, and book imbalance. Test continuation and reversal separately. If signed flow predicts only an immediately executable midpoint move but cannot beat the spread and fees at delayed bid/ask entry, classify it as price discovery, not a tradeable signal.

## Phase 2 — SPY / ES opening boundary

SPY has an ARCX opening cross and venue-specific indicative imbalance messages. ES trades in a separate futures market around the cash open. The test is whether pre-09:30 SPY auction information explains **post-open** SPY price or liquidity after controlling for the SPY premarket move and contemporaneous ES move.

Freeze one pre-open observation rule (for example, last eligible SPY auction message strictly before 09:29 ET), the 09:30 event-time boundary, and outcome windows before inspecting returns. Use MBP-1 to measure the post-open quote path and trade flow; TBBO is a trade-conditioned subset and cannot support quote-withdrawal claims. Check official auction message semantics, degraded dates, DST, and the documented 2025-11-13 field-definition break. An imbalance is evidence of orders at the auction, not a verified institutional identity.

Prior SPY auction sign, revision, pair-consensus, and neighboring-clock families are consumed in the local archive. Admit a fresh hypothesis only if it introduces a distinct observed object or prospectively collected untouched data. Require a SPY-only baseline, ES-only baseline, and joint incremental test before trading analysis.

## Phase 3 — cross-market

**BTC ↔ Polymarket:** first acquire or identify contemporaneous BTC spot/perp trades or quotes covering the stored June–July 2026 Polymarket sampled-price window. Audit clock precision, stale quote duration, market start/end, exact settlement/reference source, and YES/NO bid/ask. A raw change in YES price can simply reflect the current BTC price, distance to the strike, and time remaining. Test incremental *residual* Polymarket information after those controls, in both directions, with deliberately lagged and shifted-clock placebos. Sampled mid/probability history alone cannot establish an executable lead.

**BTC ↔ SPY:** begin with a descriptive regime-transmission test around the US cash open, not another BTC-sign-to-UPRO/SPXU rule. Define a pre-open BTC leverage/liquidity shock before 09:30 ET and ask whether it changes SPY opening volatility or spread conditional on ES, overnight SPY/ETF movement, macro-release times, and prior volatility. A BTC effect that disappears after ES and common-news controls is a common-risk proxy. The failed [V32](BTC_SPOT_RISK_ATTENTION_SPY_GAP_REPORT_V32.md) and [V44](SPY_BTC_PERPETUAL_FRESH_POSITION_REPORT_V44.md) results remain part of the multiple-testing record.

## Shared research contract

1. Inventory exact files, hashes, coverage, gaps, clock semantics, and publication delays without opening future returns. A series is eligible only when its observation was public and available before the decision.
2. Freeze instruments, direction, windows, exclusions, controls, costs, and a date-blocked chronological split. Keep every instrument on a shared date in the same split; purge overlapping labels.
3. Report event counts and effect sizes with date-cluster intervals. Include simple baselines, component ablations, time-shift placebos, year/regime breakdowns, and sensitivity to realistic latency.
4. Separate prediction, mechanism, and execution claims. Predicting a move does not identify a forced liquidation, institution, or fillable order.
5. Treat previously viewed 2021–2026 outcomes as development evidence. A historical survivor needs a prospective, untouched confirmation period and after-cost bid/ask execution before promotion.

## Immediate next step

The completed [returns-blind admission audit](BTC_MICROSTRUCTURE_ADMISSION_AUDIT_2026-09-25.md) found twenty dates from 2023-08-15 to 2024-03-27 with BTCUSDT aggregate trades and bookTicker together. All 42 local archives passed SHA-256 and ZIP reads, and the Binance five-minute OI series was eligible at all 5,760 five-minute decisions under a five-minute lag. Three February bookTicker archives have severe event-order defects and are quarantined, leaving 17 ordered BBO/trade days for an exploratory pilot. Only 2024-01-15 has a local bookDepth snapshot archive, and the lone Tardis incremental L2 day is 2020-02-01, before the five-minute OI series begins. No local liquidation file was found in these sample directories. The next research step is a frozen, limited BBO-withdrawal and signed-flow feasibility test on the 17 admitted dates; full-depth cancellation and confirmed forced-liquidation questions require new overlapping observations. Do not buy data or widen hypotheses based on observed returns.

Official schema references: [Binance USD-M aggregate-trade fields](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data), [Databento MBP-1](https://databento.com/docs/schemas-and-data-formats/mbp-1), [Databento TBBO versus MBP-1](https://databento.com/docs/faqs), and [ARCX.PILLAR auction fields](https://databento.com/docs/venues-and-datasets/arcx-pillar).
