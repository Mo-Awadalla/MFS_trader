# Data gaps for intraday strategies that can challenge SPY

**Research-priority update:** The subsequent [complete hypothesis postmortem](../postmortem_20260907/POSTMORTEM.md) supersedes this document's ranking of company-event information as the first priority. The inventory and SIP-access probe remain evidence; a missing dataset alone did not establish its research value. The revised priority is to reconcile exact historical blockers with newer data/access before selecting an acquisition.

Audit date: September 6, 2026 US Eastern / September 7 UTC. Universe: unrestricted by the user; individual stocks and ETFs are eligible. This is a research-priority assessment, not evidence that any proposed strategy is profitable.

## Principal finding

The most valuable missing research layer is **company-specific information available at the time, joined to broad intraday stock prices and executable quotes**. Within that layer, the hardest informational gap is historical announcements and expectations: what was released, when the market first received it, and how it differed from what investors already expected.

The immediate engineering gap is broad full-session stock data. A new paid stock-data subscription is not established as necessary: tiny historical requests using existing Alpaca credentials successfully returned SIP bars, quotes, and trades. These are different findings. Access is available; the local historical panel and its quality controls still need to be built.

This priority is a judgment based on our inventory and research failures. It is not a measured comparison of future returns from competing data purchases. More granular data cannot guarantee an edge over SPY.

## Audit scope and reproducibility

The local inventory scanned `data/parquet`, `data/raw`, and `external_artifacts`: 12,123 files in 45 storage groups, about 7.064 GiB. Parquet footers and schemas were inspected with zero read errors. Selected panels were loaded to verify dates, symbols, fields, and time-of-day coverage. Existing acquisition audits and experiment reports supply the DBN coverage and historical research findings below.

This is not a full record-by-record revalidation of every dataset. File counts include manifests, derived panels, overlapping downloads, and validation caches. Bytes and rows are not measures of independent information. A readable Parquet footer does not establish timestamp accuracy, completeness, or freedom from survivorship bias. DBN records are not included in the inventory's Parquet row totals.

Reproducible outputs in this directory:

- `local_inventory.json`: storage groups, schemas, row counts, sampled coverage, daily equity file lists.
- `historical_sip_probe.json`: sanitized API status and field names; no credentials or raw market rows.
- Parent scripts: `audit_data_gap_inventory_20260907.py` and `probe_historical_sip_access_20260907.py`.

## What we actually have

| Domain | Observed local coverage | What it supports and what remains missing |
|---|---|---|
| SPY and inverse/leveraged ETFs | SPY/SH/UPRO/SPXU minute bars across 2021–2025, quote datasets and separate 2026 extensions; exact coverage varies by instrument/feed | Strong base for selected intraday ETF tests. These are closely related exposures, not four independent economic markets. Minute BBO snapshots do not show every intervening quote. |
| Six-ETF trade-associated quotes | SPY, SSO, UPRO, SH, SDS, SPXU EQUS.MINI TBBO, March 28, 2023–July 24, 2026; about 37.08 million logical records | Broad trade-event coverage. TBBO records accompany trades; they do not provide a complete quote-update path or standing-quote age. EQUS.MINI is a derived feed, not official SIP. |
| Complete opening quote updates | Six-ETF MBP-1 acquisition, 09:20–09:40 Eastern; 806 valid sessions of 836 requested | Useful for opening liquidity dynamics. It is a 20-minute window, not full-day depth or order-level queue history. Thirty requested sessions are absent. |
| Auctions | SPY Arca imbalance history: about 10.84 million rows, 1,395 sessions, January 2021–July 2026; official statistics and status files also present | Strong auction measurement. It does not identify beneficial owners, dealer inventory, or the motive behind orders. A November 2025 quantity-reference change requires separate handling. |
| Individual stocks | 85 Alpaca daily files, 136 SIP daily files, seven Yahoo daily files; these overlap and include ETFs. A static 20-name SIP hourly collection also exists | Some full-session intraday stock history exists, but hourly observations are too coarse for many entries, stops, and execution checks. Current/static lists are not a verified historical eligible universe. |
| Broad stock opening panel | 134 symbols; 199,831 IEX rows, 2021–2023; bar timestamps only 09:30 and 10:00 | Two half-hour bars per day cover the first hour. They cannot test stock-specific afternoon behavior or consolidate market-wide volume. V75/V77 panels reuse this underlying information. |
| IEX tick samples | About 22.2 million raw and derived rows under `alpaca_iex_orderflow_v1`; sampled ETF quote/trade datasets | Additional useful microstructure samples, but not a broad consolidated stock-event database. Aggregate row counts include features and panels. |
| SEC filings | 20,107 filing-event rows for 133 symbols; December 2017–July 2026. Includes 15,252 8-Ks and other periodic/amended filings | Metadata contains acceptance time, form, items, accession and document pointers. It is not a normalized archive of first public news, earnings surprises, guidance changes, or prior analyst expectations. |
| ES/MES | ES minute bars, 2021–2025, about 1.77 million rows; about 38.9 million targeted ES trade/MES quote event rows across 3,761 session files | Supports existing time-window futures studies. Does not establish simultaneous full-day executable quotes for front and next maturities. |
| Other futures and volatility | Daily carry inputs for 15 markets, 2010–March 2024; 63 VX raw files | Useful daily context. Daily futures/volatility history cannot substitute for intraday options surfaces or executable calendar spreads. The public carry source is stale. |
| Fund NAV, AUM and flows | Complete 2021–2023 UPRO/SPXU daily NAV/share coverage; four-fund AUM inputs, selected iShares history | Supports flow proxies. Historical daily derivative holdings were present for only three of 753 days in the earlier inventory audit. Neither holdings nor creations directly reveal actual dealer hedges. |
| Public macro and funding | CFTC categories/trader counts, Treasury auctions, NY Fed lending, RRP, TGA | Useful context, but frequency and publication/revision timing limit intraday use. Treasury and NY Fed candidate signals remain blocked on historical availability evidence. |
| Bitcoin | Spot/perpetual/mark/index/premium bars, funding and selected positioning series; multi-year history with mixed frequencies | Distinct economic domain. Our tested funding strategy used 30-minute bars and assumed friction, not observed execution quotes. Derived crypto panels do not create new source information. |
| Polymarket | 54,626 BTC five-minute contracts in the existing audit; about 1.55 million sampled prices | Sampled prices do not establish simultaneous executable YES/NO asks or depth. Complete-set arbitrage remains untestable with this cache. |

The inventory did not establish a local, normalized historical options-chain panel; broad point-in-time security membership and delisting coverage; a first-publication news archive; or historical analyst-consensus vintages. This is a statement about audited research assets, not a claim that every external account or provider lacks access.

## Existing historical SIP access changes the acquisition priority

Three read-only requests for AAPL on January 4, 2023 returned HTTP 200: six minute bars, ten quotes, and ten trades. Quotes and trades were deliberately limited and had additional pages. Quote fields include bid/ask prices, sizes, exchange identifiers, conditions, and timestamps. No subscription or billing changes were made.

Alpaca documents historical SIP access without a subscription when the request end is at least 15 minutes old; recent/live SIP has different requirements. The probe confirms this account's historical access, not its billing tier, all-symbol completeness, download throughput, or live entitlement. [Alpaca Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq).

Consequently, first test a bounded stock-history collection using existing access. Do not buy redundant stock bars before measuring what this access supplies. The remaining work includes pagination, symbol history, timestamp normalization, conditions, session calendars, gaps, corporate actions, quote freshness and reproducible caching.

## Ranked gaps

### 1. Company events and expectations, available before the decision

This offers the best potential expansion in hypothesis quality when individual stocks are allowed. Most of our detailed information concerns the same index exposure. A company announcement can instead supply a localized economic event, a defined clock, and a comparison against previous expectations.

Required fields include source text/exhibits, first-publication time with provenance, revisions, event identity, actual results, previous guidance, and—where the hypothesis needs it—consensus snapshots saved before the announcement. Financial period, currency, units, and GAAP/non-GAAP basis must match. A current consensus number attached retrospectively to an old event is unusable.

SEC metadata is a starting point. EDGAR submissions and structured company facts are public resources, but our local metadata schema does not supply analyst expectations. Filing acceptance is not automatically the first time news became public; Form 8-K generally allows a reporting interval after an event, subject to item-specific rules. [SEC APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces); [Form 8-K instructions](https://www.sec.gov/files/form8-k.pdf).

Examples this could make measurable: response to an EPS beat accompanied by a revenue/guidance miss; a new guidance revision versus repetition of old guidance; differences between the response to a firm's own announcement and a related firm's earlier announcement. These are hypothesis families, not claims of novelty or profitability. Literature and prior-repository overlap checks would precede a frozen test. We already tested a weaker earnings-network rule and it failed; simply relabeling filing dates would repeat it.

The hard potential acquisition is historical expectations and reliable news availability, not another technical indicator. Some release text and guidance can be reconstructed publicly; complete historical consensus and first-wire timestamps have not been verified as available at no extra cost.

### 2. Broad stock execution history and a historical security universe

This is the immediate implementation dependency for the first priority. Build full-session minute bars and targeted quotes/trades around candidate entries and exits. Include premarket or after-hours observations only where the hypothesis needs them, with separate execution assumptions.

Store stable identifiers, ticker effective dates, listings/delistings, corporate actions and eligibility based only on earlier data. Selecting today's surviving stocks and running them backward introduces selection bias. Missing old or delisted securities must be reported, not silently dropped.

Consolidated quotes improve spread and timing measurement, but displayed size is not a guarantee of a fill. Short-stock tests additionally need defensible borrow availability/costs; existing historical price access does not solve that. Long-only research can proceed without assuming shorts are always available.

### 3. Options information, if the focus returns to index ETFs

A time-aligned SPY/SPX options surface and options trading activity would add a domain missing from the current cash-ETF research. Required components depend on the mechanism: contract definitions, quotes/trades, expiry/strike selection, underlying alignment, and open-interest publication timing. Start with a bounded sample of contracts and dates rather than the full OPRA universe. [Databento OPRA specifications](https://databento.com/docs/venues-and-datasets/opra-pillar).

Options prices and volume do not directly reveal dealer net inventory. Participant and opening/closing classifications are separate data: Cboe's Open-Close product describes these categories for its exchanges. Even that is not every dealer's complete cross-market portfolio. A dealer-hedging hypothesis must specify what is observed and what is inferred. Product access and cost were not tested or purchased. [Cboe Open-Close Volume Summary](https://datashop.cboe.com/cboe-options-open-close-volume-summary).

### 4. Publication timing for the public macro data already cached

Resolve first-publication versus revision times before buying additional macro series. This could unlock the Treasury and NY Fed candidates, but their economic edge remains unknown. The CFTC 2023 reporting outage demonstrates why a generic weekly lag is insufficient. A corrected timing rule must be frozen before inspecting new outcomes.

### 5. Specialized gaps, conditional on a specific mechanism

Examples: actual historical ETF holdings, synchronized futures maturities, and Polymarket order books. These are real deficiencies but not a general first purchase. Each addresses a narrower family and can remain insufficient: fund holdings do not identify executed hedges; sampled binary prices do not establish arbitrage fills.

## What the failed tests imply

The latest ten-candidate batch produced four profitability tests, one pre-return rejection, and five data-blocked candidates. It did not produce ten failed P&L tests.

| Completed test | After-cost ending value from $100 | Matched SPY | Interpretation |
|---|---:|---:|---|
| V83 month-end pressure | $116.56 | $132.37 | Profitable development sample, but failed the stated SPY objective. |
| V84 opening replenishment | $85.03 | $121.43 | Detailed quote paths made the idea testable; they did not make it profitable. |
| V85 earnings network | $104.26 | $132.37 | Existing coarse event/peer proxies did not deliver a robust advantage. |
| V86 BTC funding unwind | $88.02 | $132.37 | Bar-based test failed after assumed costs. |

V84 uses March–December 2023; the other rows use 2021–2023. Comparators match their respective periods. See the [backtest report](../daytrade_batch_v83_v92/artifacts/FINAL_REPORT.md).

Earlier V63 four-fund rebalancing signals agreed with ordinary late SPY momentum about 96.2% of the time. Additional AUM data therefore did not create a distinct mechanism. V64 stopped on a prespecified frequency gate; that is not evidence its economics were disproved. Future gates should suit the hypothesized event frequency, without relaxing old gates after seeing failures.

## A concrete first build

1. **Coverage pilot, before P&L:** select roughly 100 company-event days across several years and sectors using availability criteria, not subsequent returns. Include ticker changes and missing-data cases. This sample is for validating the data join, not demonstrating profitability.
2. **Market leg with existing access:** collect full-session minute bars and tightly scoped SIP quote/trade windows for those events, SPY and appropriate sector controls. Verify pagination, exchange calendars, conditions, duplicates, raw prices versus adjustments, gaps and timestamp ordering. Measure retrieval volume and rate limits.
3. **Information leg:** archive original release/exhibit content and source timestamps; separate first publication, SEC acceptance and later updates. Extract actual results and prior issuer guidance. Any unavailable consensus remains missing; do not substitute today's value or manufacture an earnings-surprise signal.
4. **Data contract:** every feature has `event_time`, `available_at`, `retrieved_at`, source, revision identifier and stable security ID. Entry decisions use only records already available. Keep raw immutable inputs and hashes. End-of-minute features cannot trade at that minute's opening price.
5. **Coverage decision:** publish missingness by year, sector, event type and security status. Measure how many events require paid information before considering a targeted acquisition. A prospective archive can supply future evidence, but it cannot reconstruct unrecorded historical expectations.
6. **Research only after this passes:** freeze a small set of economically distinct rules, same-day exits, sizing, latency, costs and multiple-testing treatment. Group related earnings dates in validation so shared event shocks do not masquerade as independent observations. Keep a record of every attempted variant.

For the goal of beating SPY, compare total portfolio wealth against matched-date SPY total return, including cash outside trades and concurrent-position capital requirements. Also report risk-matched comparisons, drawdown, turnover and net excess-return uncertainty. More leverage or a superior Sharpe alone does not satisfy the wealth objective. Historical periods already inspected throughout this repository are not pristine holdouts; genuinely new prospective observations remain necessary for strong confirmation.

## Decision

First build the joined company-event and stock-execution panel using verified existing access. Treat point-in-time expectations and publication history as the leading potential information acquisition, subject to a coverage pilot. If research is later restricted to SPY-family trading, elevate options information. Do not prioritize more cash-ETF depth solely because it is large or detailed, and do not attribute losing rules to missing data when their inputs were already adequate to test them.
