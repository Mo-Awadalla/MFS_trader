# New Cash-ETF Data Technical Audit v34

## Scope and evidence boundary

This is a returns-blind decode and capability audit. It makes no paid API calls and calculates no post-signal strategy return. The package inventory and validation report are authoritative for file identity, hashes, row counts, and clean/partial EOF status.

Historical fields are new, historical price outcomes are not. Auction measurement in 2021–2023 is development/measurement evidence; 2024–2025 is historically contaminated validation; 2026 is a temporal extension, not automatically pristine.

## File integrity and bounded decoding

- Files inventoried: 7.
- Clean EOF overall: False because the prefix is intentionally partial.
- Prefix boundary observed and logical consumption stopped at 2024-10-02: True.
- The SDK explicitly reported and trimmed the incomplete terminal record while yielding preceding complete records: True.
- Prefix records consumed through 2024-10-02: 18,255,888.
- Clean-tail records consumed from 2024-10-03: 18,823,909.
- No segment concatenation was performed without the mandatory New York date partition.

## Timestamp semantics

- `ts_event` is the matching-engine-received timestamp and is the causal ordering clock.
- The DataFrame index is `ts_recv`, the capture-server-received timestamp. It is audited only; it never makes a signal earlier.
- `auction_time` is a projected auction timestamp, not the message-publication time and not a realized auction print.
- All session boundaries and cutoffs are converted from UTC to `America/New_York`, including DST.

## SPY ARCX.PILLAR imbalance

- Decoded records: 10,838,203.
- Auction-type counts: {"C": 4961479, "M": 5821122, "O": 55602}.
- Session counts by auction type: {"C": 1395, "M": 1395, "O": 1395}.
- Databento's ARCX.PILLAR venue documentation defines `O` as Early Opening, `M` as Core Opening, `H` as Halt Resume, and `C` as Closing. This SPY file contains O/M/C and no H messages.
- `auction_time` is an exchange-local wall-clock field. The DBN pretty representation's `+00:00` label must not be timezone-converted; doing so would create false 04:30/05:30 clocks from a 09:30 Core Open.
- Snapshot artifacts select the latest `M` message strictly before each cutoff. No final match or post-auction state is used to initiate a pre-auction order.

Field interpretation follows Databento's ARCX.PILLAR venue documentation: `ref_price` is the imbalance calculation price; `cont_book_clr_price` includes cross and continuous orders; `auct_interest_clr_price` uses eligible auction-only interest; and `ind_match_price` maximizes matched shares subject to collars and includes reserve quantity. **There is a documented semantic break on 2025-11-13:** `paired_qty`, `total_imbalance_qty`, and `market_imbalance_qty` are measured at `ref_price` from that date onward, but were measured at `ind_match_price` before it. Cross-regime level comparisons require an explicit break control.

ARCX documentation also defines auction status 0/1/2/3, freeze status 0/1, extension count, and the significant-imbalance flag. Opening/closing statistics are final auction outcomes published after the cross and cannot be used for a pre-auction order.

## EQUS.MINI TBBO semantics and quality

EQUS.MINI is not described here as official SIP NBBO. It is a derived, anonymized multi-venue product. TBBO records occur on trades and carry the BBO immediately before each trade's effect; they do not contain every quote update.

True standing-quote age cannot be reconstructed because the record does not timestamp when each bid or ask was established. The executable policy therefore records the wait from simulated order target to the first valid trade-event BBO and rejects waits beyond a frozen limit. Capture latency (`ts_recv - ts_event`) is reported separately.

| Symbol | Valid rows | Crossed rejected | Nonpositive rejected | RTH session coverage vs SPY |
|---|---:|---:|---:|---:|
| SPY | 29,714,433 | 49,645 | 7,193 | 100.00% |
| SSO | 751,719 | 440 | 424 | 100.00% |
| UPRO | 2,461,989 | 5,347 | 894 | 100.00% |
| SH | 805,355 | 322 | 123 | 100.00% |
| SDS | 1,275,993 | 997 | 237 | 100.00% |
| SPXU | 2,003,153 | 1,175 | 358 | 100.00% |

Missing-session lists and coverage by premarket/open/midday/close window are machine-readable in `research_scout/new_data_technical_audit_v34.json`.

## Definitions, status, and statistics

Definitions verify the requested symbol/instrument mappings and expose definition updates, minimum ticks, and activation metadata. Status records are decoded into trading, quoting, halt/pause/suspend, and SSR states; flagged dates are exclusions or explicit diagnostics, never silent inclusions.

Statistics are not used merely because they exist. ARCX venue documentation maps `OPENING_PRICE` to the Core Opening auction, `CLOSE_PRICE` to the Closing auction, and `UNCROSSING_PRICE` to Early Opening and halt/re-opening auctions. These are final outcomes: useful for integrity and post-event measurement, prohibited as pre-auction predictors.

Venue source: https://databento.com/docs/venues-and-datasets/arcx-pillar (accessed 2026-07-28).

## Degraded dates

- ARCX.PILLAR degraded dates (20): 2021-01-21, 2022-07-18, 2022-08-22, 2022-12-05, 2022-12-27, 2023-06-26, 2023-09-22, 2023-11-21, 2023-12-01, 2023-12-04, 2023-12-05, 2023-12-06, 2023-12-07, 2023-12-08, 2023-12-11, 2024-04-19, 2024-06-18, 2024-11-19, 2026-06-24, 2026-07-14.
- EQUS.MINI degraded dates (15): 2025-03-24, 2025-04-04, 2025-05-06, 2025-06-04, 2025-06-16, 2025-07-09, 2025-08-08, 2025-08-13, 2025-08-19, 2025-08-25, 2025-09-03, 2025-09-08, 2025-09-12, 2025-10-10, 2025-10-13.
- Primary results must exclude the union applicable to signal and execution. Sensitivity results may report degraded sessions separately but may not choose inclusion based on P&L.

## What the package resolves

The package resolves V33's factual absence of official primary-listing SPY auction-imbalance messages and materially improves synchronized event-time cash-ETF execution measurement across SPY/SSO/UPRO/SH/SDS/SPXU. It also supplies status and definition integrity records.

## What remains unresolved

- EQUS.MINI is not official SIP NBBO and has no venue identifiers in the supplied logical TBBO view.
- TBBO is trade-event-conditioned, not a complete quote-update history; standing quote age and quote-only lead/lag are unobservable.
- No queue position, passive-fill probability, order-book depth, dealer/AP identity, iNAV/NAV, shares outstanding, AUM, creation/redemption basket, or primary-market hedge flow is present.
- Auction type/status/freeze/significance codes are venue-specific where the installed generic schema does not define their ARCX meaning.
- The package begins TBBO on 2023-03-28, so 2021–2022 auction signals cannot receive event-level ETF execution reconstruction from this feed.
- Historical outcomes remain multiply exposed; any survivor requires prospective forward paper trading.

## Generated machine-readable evidence

- `research_scout/new_data_technical_audit_v34.json`
- `research_scout/spy_auction_snapshots_v34.json`
- `research_scout/cash_etf_tbbo_target_quotes_v34.json`

