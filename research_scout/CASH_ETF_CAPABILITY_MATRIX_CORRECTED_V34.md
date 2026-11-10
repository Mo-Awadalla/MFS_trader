# Corrected Cash-ETF Capability Matrix v34

## Why this correction exists

V31 and V33 correctly described the data available at those checkpoints. Their factual assertions that SPY auction-imbalance messages and synchronized event-time cash-ETF quote evidence were absent are now superseded by `external_artifacts/databento_cash_etf_budget_v1/`. Their failed-strategy conclusions are not erased.

The new fields are new causal observables. The historical price outcomes are not new, and prior exposure still creates familywise contamination.

## Corrected matrix

| Capability | V33 status | v34 package status | Research consequence | Remaining limitation |
|---|---|---|---|---|
| Exchange-published SPY auction imbalance | Absent | Resolved, with a documented 2025-11-13 measurement break | Actual pressure trajectory, side changes, paired absorption, indicative displacement, collars, freeze/extension fields, and opening/closing handoff can be measured | Paired/total/market quantities use `ind_match_price` before 2025-11-13 and `ref_price` thereafter; public information may already be incorporated |
| Opening/closing auction schedule and projected time | Absent | Resolved | Publication can be ordered against New York cutoffs without using post-event states | `auction_time` is an exchange-local projected wall clock, not publication time or a realized print; do not timezone-convert its DBN pretty representation |
| Official auction outcome/print | Absent | Resolved for ARCX crossing outcomes | `OPENING_PRICE`, `CLOSE_PRICE`, and `UNCROSSING_PRICE` can be used as outcomes or post-auction diagnostics | Cannot initiate a pre-auction trade; `UNCROSSING_PRICE` is Early Open and halt/re-open, not Core Open |
| Event-time SPY/SSO/UPRO/SH/SDS/SPXU BBO at trades | Absent | Materially resolved from 2023-03-28 | Marketable execution and cross-leverage reaction can be reconstructed at eligible trade events | EQUS.MINI is derived/anonymized and is not official SIP NBBO |
| Every quote update / quote-only lead-lag | Absent | Unresolved | None | TBBO is trade-event-conditioned and does not contain every quote update |
| True standing-quote age | Absent | Unresolved | Event wait and capture latency can be measured and capped | No timestamp states when each standing bid or ask was established |
| Crossed/nonpositive quote rejection | Coarse minute implementation | Resolved at TBBO records | Invalid execution observations can be deterministically rejected | Does not prove unobserved quote-only states were valid |
| 1 s / 5 s / 60 s latency stress | Not defensible at minute resolution | Partially resolved from 2023-03-28 | First eligible trade-event ask/bid after each delayed target can be used | If no trade event occurs, the contemporaneous standing quote is unknown rather than safely forward-filled |
| Venue-level routing and official consolidated NBBO | Absent | Unresolved | None | Supplied view is anonymized multi-venue data without an official SIP-NBBO claim |
| Queue position and passive-fill probability | Absent | Unresolved | Marketable fills only | No queue/order-book message model |
| ARCX trading/quoting/halt/SSR status | Absent as a dedicated integrity feed | Resolved for the listed ARCX instruments | Halts, pauses, quoting interruptions, and SSR can be excluded or diagnosed | ARCX status is not a consolidated all-venue market-state feed |
| Instrument definitions and mappings | Partial/inferred | Resolved for both datasets | Instrument IDs, symbols, ticks, and definition updates can be audited point in time | Definitions do not provide fund NAV, AUM, baskets, or dealer inventory |
| Corporate-action integrity | Weak | Improved, not complete economic fund history | Definition changes and identifier continuity can be checked | Full split/distribution total-return treatment still requires explicit outcome-series handling |
| ARCX statistics | Not inventoried as causal support | Available and venue-documented | `OPENING_PRICE` and `CLOSE_PRICE` each cover all six symbols across 1,395 sessions; `UNCROSSING_PRICE` has partial Early Open/halt coverage | These are final outcomes and cannot be pre-auction predictors |
| Intraday iNAV/NAV | Absent | Unresolved | No direct ETF premium/discount signal | Still a primary blocker for true wrapper mispricing |
| Shares outstanding, AUM, creations/redemptions, baskets | Absent | Unresolved | No direct primary-market inventory or rebalance-demand identification | Still a primary blocker |
| AP/dealer identity and hedge flow | Absent | Unresolved | No attribution of observed pressure to APs or dealers | Still a primary blocker |
| Point-in-time S&P 500 constituent event data | Absent | Unresolved | No unbiased constituent-breadth mechanism | Still a primary blocker |
| Options surface/flow/greeks | Absent | Unresolved | No dealer-gamma identification | Still a primary blocker |
| 2021–2022 event-level ETF execution | Absent | Unresolved | Auction features can be measured but not executed from this TBBO feed | EQUS.MINI logical coverage starts 2023-03-28 |
| Genuinely prospective untouched sessions | Absent | Unresolved | Historical survivors remain research evidence only | Forward paper trading must be reserved before rule changes |

## V33 conclusions that are superseded

1. “Auction imbalance is absent” is false for the new package. ARCX.PILLAR supplies 10,838,203 SPY imbalance records with clean EOF from 2021-01-04 through 2026-07-24.
2. “No synchronized event-level SPY/leveraged/inverse ETF quote evidence is present” is materially superseded from 2023-03-28. The six-symbol EQUS.MINI ladder is available with the mandatory prefix/tail boundary.
3. “Event-time marketable lead/lag cannot be studied at all” is superseded in a bounded form: trade-event pre-trade BBOs permit latency-stressed marketable fills when an eligible event appears.
4. Dedicated definition and status records now improve identifier, halt, quoting, and SSR integrity.

## V33 conclusions that remain valid

1. Minute-bar and sampled-BBO strategy failures in V1–V33 remain failures. New data does not authorize sign, clock, side, threshold, or execution repairs to them.
2. V20 remains rejected by its original concentration gate. A TBBO rebuild is an execution-fidelity audit, not a pristine rerun.
3. Passive fills remain indefensible without queue and fill models.
4. Primary-market ETF inventory remains unidentified without iNAV/NAV, AUM, shares, creations/redemptions, baskets, and hedge flow.
5. Dealer gamma, constituent breadth, and AP/dealer attribution remain unavailable.
6. Historical outcomes remain multiply exposed; no backtest on these dates establishes production readiness.
7. Cross-regime comparisons of `paired_qty`, `total_imbalance_qty`, and `market_imbalance_qty` require an explicit 2025-11-13 measurement-break control.

## Correct operating boundary

The new package reopens exactly two research territories:

- exchange-published SPY auction state and its handoff into continuous cash-ETF trading;
- trade-event-level transmission across the 1x/2x/3x long and inverse ETF ladder.

It does not reopen generic opening momentum, gap continuation, ordinary mean reversion, minute-bar wrapper geometry, signed last-sale relay, passive execution, or primary-market premium/discount stories without their defining data.
