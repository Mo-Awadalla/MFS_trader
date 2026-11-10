# Research position — September 7, 2026 UTC

**Current position after the cross-family reset:** zero validated SPY-beating intraday strategies. Date/session and benchmark guards are repaired; the shared accounting contract passed 47 focused tests and an independent reconciliation of 11 exports. Six different families were replayed, including profitable-but-below-SPY, economic-loss, signal-stability and incomplete-data cases. V56's eligibility mismatch and V45's trade-day labeling were reconciled. The next research direction is incremental information with enough margin over observed costs, using liquid-ETF data already available. Neither V40 nor V49 remains a priority continuation. See [the completed reset and decision](../research_reset_20260907/REPORT.md). Earlier priorities below are retained as dated history.

**Latest follow-up — V40:** all 14 original feasibility gates pass with full quote updates. The costed development test loses 7.06% versus SPY's 21.46% gain; 2024–2025 and the complete 2026 prefix also lose. All 433 executable trades were independently reconciled. V40 is an economic rejection; V49 remains a stability rejection. See [the V40 backtest report](../v40_mbp_replay_20260907/REPORT.md).

**Follow-up completed:** V49's full-quote replay passed 12 of 13 original gates but failed adjacent-clock action stability (49.17% versus 60% required). All 461 primary signals had complete execution quotes. Its status is now a signal-stability rejection on the available sample, rather than merely data-blocked; no P&L was run. See [the V49 replay report](../v49_mbp_replay_20260907/REPORT.md). The reconciliation below records the earlier data-readiness finding and is retained for provenance.

We have no validated algorithmic day-trading strategy that beats SPY total return after realistic costs. The next-step data reconciliation is complete at the scope below. It materially improves what we can measure; it adds no evidence of profitability.

## Work completed

1. Froze a data-only specification before downloading quotes. No outcome-based date selection, parameter tuning, signals, P&L, orders, or subscription changes.
2. Decoded every existing 2023 opening MBP-1 file: 192 sessions, March 28–December 29, six ETFs, eight exact target times. Required positive bid/ask sizes, positive non-crossed prices, and both event and receive timestamps at or after the target. All 9,216 symbol/session/target combinations had a valid fresh quote within 60 seconds. All six symbols were available within five seconds on all 192 sessions at both V49 observation times, 09:30:01 and 09:30:05.
3. Joined those V49 observation states to the original official-opening uniqueness/completeness, degraded-day exclusions, five-second event-wait/span limits, and receipt before 09:31. **182 sessions pass at each observation time; the other 10 are original degraded-day exclusions.** This is a prerequisite audit, not a replay of rolling features, direction balance, cadence, stability, or execution economics.
4. Queried existing historical Alpaca SIP access for six ETFs (SPY, SSO, UPRO, SH, SDS, SPXU), on 12 calendar-selected dates spanning 2021–2023, in two ten-second windows per date. All 24 windows returned HTTP 200 with pagination exhausted. All 144 symbol/windows contained positive-size non-crossed quotes. Downloaded 171,053 quote records. Maximum wait to the first qualifying quote was 4.803222 seconds. Compressed raw responses are retained beside this report.
5. Investigated official Treasury and NY Fed publication evidence. Neither historical first-release timing blocker is closed. No event P&L was computed using assumed release times.

The initial sandbox network attempt failed before reaching the provider; the authorized read-only network retry succeeded. The final SIP report contains the successful retry. No subscription or billing settings were queried or changed. Successful existing access is not a claim about all historical symbols, a full-calendar coverage rate, or live SIP entitlement.

## What changed for each hypothesis

| Hypothesis | Earlier reason it stopped | New evidence | Current disposition |
|---|---|---|---|
| V37 indicative-price leadership | All-delay quote coverage 88.37%, below 90%; reference-price interpretation also questionable | Required opening/exit quote targets are available in all 192 local 2023 sessions; existing SIP route works in sampled older periods | Quote shortage is repairable. Original full-calendar, signal-conditioned coverage and semantic objection remain. Do not declare a gate pass from a subset. |
| V40 four-wrapper opening-demand consensus | Primary coverage 89.44%; ladder coverage 69.85%, below thresholds | All six ETFs have post-target quotes at 09:31:01, 09:31:05, 09:32 and 09:35 on all 192 local sessions | Good candidate for unchanged full-period data/gate replay. Official quantity signal and original denominators must be retained. |
| V49 six-fund fair-value simplex | Zero 2023 synchronized states with trade-event TBBO | 182 valid quote-and-official-open prerequisite states at both original observation times, with exclusions preserved | **Highest-priority research continuation. The 2023 synchronization blocker is resolved; the hypothesis is not validated.** Next is its unchanged 10/20/40-session and adjacent-clock stability audit. |
| V68 same-issuer 3x/2x convergence | SSO/SDS continuous 2021–2023 quotes and 10:30 exits missing | SIP provides valid SSO/SDS and other ETF quotes in all sampled opening and 10:30 windows | Access/type blocker improved, full 753-session coverage still unverified. Needs original exact-minute construction, point-in-time NAV, short availability, borrow costs and two-leg execution model. Opening MBP alone ends at 09:40 and cannot supply exits. |
| V88 Treasury auction response | Historical first-publication timestamp unverified | Official sources confirm prompt release practice, not a per-auction historical first-publication/revision record | Remains blocked for the original tightly timed event test. Do not substitute auction close for result availability. |
| V89 NY Fed securities-lending response | First-publication/revision timing unverified | Official NY Fed explanation says results appear shortly after the 12:15 close | Remains blocked. Noon is operation launch, not result availability. Detailed transaction disclosures released about two years later are unsuitable for contemporaneous signals. |

The SIP data schema has quote timestamp, prices, sizes, exchange identifiers, conditions and tape. It does not contain Databento's separate receive timestamp. Changing feeds requires a documented timestamp/latency and condition policy; SIP rows must not silently masquerade as original receive-time observations. A positive-size top-of-book quote is not proof of fill capacity, borrow availability, or executable two-leg arbitrage.

## Publication evidence and limits

- [Treasury today's auction results](https://www.treasurydirect.gov/auctions/announcements-data-results/announcement-results-press-releases/auction-results/) describes real-time updates when results become available. It does not establish each historical first-post timestamp.
- [Treasury 2009 performance report](https://home.treasury.gov/system/files/266/09Treas_APR_full-book_05.pdf) describes measuring auction-close-to-public-release delay and validating system timestamps. This is a lead that timestamp records exist internally, not access to a public 2021–2023 event ledger.
- [Example Treasury result release, November 14, 2024](https://www.treasurydirect.gov/instit/annceresult/press/preanre/2024/R_20241114_2.pdf) has a release date in its visible text, not a precise clock. This single out-of-development-period example does not prove all releases lack clocks. PDF creation metadata, current HTTP last-modified values, and assumed scheduled times would not independently establish historical public availability.
- [NY Fed program explanation](https://libertystreeteconomics.newyorkfed.org/2016/08/a-closer-look-at-the-federal-reserves-securities-lending-program/) puts publication shortly after the 12:15 close; this is a general timing statement, not a per-day upper bound or revision archive.
- [NY Fed securities-lending data overview](https://www.newyorkfed.org/markets/domestic-market-operations/monetary-policy-implementation/securities-lending) distinguishes operation results from detailed transactions disclosed quarterly about two years later.

No verified public first-release/vintage archive was established in this investigation. This is not a claim that none exists. A defensible delayed-entry variant would be a newly registered hypothesis, not a repair silently applied to V88/V89.

## Current research position and order of work

The full postmortem covers 232 records, including variants, aliases and diagnostics; they are not 232 independent experiments. No intraday candidate is validated. The latest V83–V92 batch contains four economic failures, one blind rejection and five blocked candidates. Daily trend/carry results and weak ES positives do not meet the user's intraday SPY-beating objective.

**The immediate constraint is research validity and exact measurement, not a demonstrated need to buy a larger dataset.** We already have usable six-ETF quote information and a working route to fill older historical gaps. Buying generic bars, company-event metadata, or more of a failed signal family is not supported by the postmortem.

The priority is V49's unchanged signal-only gate replay on the newly measurable 2023 period, followed by V40's full-period quote reconstruction if warranted. Only a candidate that passes its original measurement, stability, independence and cadence requirements should receive a costed backtest. Historical periods previously inspected remain exposed; they cannot be relabeled untouched confirmation. V37's semantic issue and V68's shorting/implementation requirements lower their priority. V88/V89 remain on hold pending real publication evidence.

No new profitability test, trading deployment, live monitoring, order, purchase or account modification occurred in this reconciliation. This report describes research readiness; it does not report brokerage holdings or account positions.

## Reproduction and evidence

- `specification.json`: frozen audit scope and deterministic SIP dates.
- `local_exact_targets.json`: per-session quote waits and timestamps.
- `v49_observability.json`: original prerequisite join and exclusions.
- `sip_pilot.json` and `sip_*.json.gz`: sample coverage and raw data.
- `verification.json`: independently checked output counts and raw quote invariants.
- `../reconcile_quote_blockers_20260907.py`: run modes `spec`, `local`, `sip`; rerunning `spec` overwrites its creation timestamp, so preserve this delivered specification.
- `../check_v49_observability_20260907.py`: run as a module from repository root.
- `../postmortem_20260907/POSTMORTEM.md`: complete earlier postmortem; its economic verdicts are unchanged.
