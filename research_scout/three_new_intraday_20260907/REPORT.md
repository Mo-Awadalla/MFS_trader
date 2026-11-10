# Three new intraday hypotheses — completed results

All three frozen implementations fail the stated SPY-beating objective. These are bar-based cost scenarios, not quote-validated execution tests. No parameters were retuned.

| Hypothesis | 2021–2023 net | 2024–2025 net | Trade days |
|---|---:|---:|---:|
| V93: Pre-FOMC uncertainty premium | -0.87% | -0.56% | 17 |
| V94: Overnight-and-opening stock reversal | -37.25% | -46.29% | 1226 |
| V95: Alphabet share-class premium normalization | -11.81% | -0.55% | 229 |

SPY adjusted-price total-return proxy gained 32.40% and 48.00% across the respective full calendars. V94 has six and three unknown days; V95 has one unknown later-period day. Their affected figures are available-case paths, not complete comparable full-calendar equity. Missing days are explicitly retained in results.json and trigger failure.

## Findings

- V93: only 17 trades; gross performance was slightly negative in both periods. The volatility filter reduced losses relative to unconditional pre-FOMC exposure but did not create a profitable strategy.
- V94: development gross reference equity rose from $100 to $131.39; 10bps modeled round-trip costs reduced net equity to $62.75. Later gross equity fell to $87.42 before costs, and net to $53.71. This is both a cost and temporal failure, with fixed-survivor-universe and missing-data limitations.
- V95: development gross equity ended at $101.85 and net at $88.19; later gross ended at $108.28 and net at $99.45. Choosing a class added little compared with equal-weighting GOOG and GOOGL on the same dates; the control-excess intervals include zero.
- Doubled-cost, delayed-entry and remove-best-five checks did not rescue any primary rule. All controls and confidence intervals are retained, including favorable secondary comparisons; none replaces the primary rule.

## Scope and novelty

V93 is an exact volatility-conditioned implementation related to the prior unimplemented pre-FOMC proposal, distinct from V45 post-release discovery. V94 tests stock selection through the opening half-hour rather than an index breadth vote, but belongs to the broader reversal family. V95 is a specific same-issuer share-class rule, related to broader relative-value work. These are three new frozen implementations, not three claims of worldwide novelty or statistical independence from the archive.

The tests use existing SPY IEX half-hour bars, the static20 SIP hourly stock panel (19 issuers for V94), cached adjusted SPY daily prices, and the existing FOMC calendar. Features use completed bars and entries occur later. The stock rules leave one hour between completed features and entry; this protects chronology but cannot test a fleeting opening edge. V93 exits before the scheduled 14:00 announcement.

Baseline adverse costs are 3bps each side for SPY and 5bps each side for stocks; doubled costs are stress cases. These are assumed all-in spread/fee/slippage scenarios, not measured historical quotes. Fixed stock-universe selection, exposed historical periods, coarse fills, missing bars, fractional execution and daily-only drawdowns limit the conclusions. Bonferroni intervals adjust the three primary comparisons; they do not erase the much larger historical research exposure.

## Verification

Independent signal reconstruction and high-precision cash accounting passed for 1472 portfolio trade-days and 3924 legs. Inputs retained their original hashes; all positions were flat the same day. No orders, purchases or account changes occurred.

Evidence: specification.json, signals.json, results.json, trade_ledger.json, daily_returns.json, verification.json, verified_cash_ledger.json, and control_inference.json.

Official context: [scheduled FOMC release time](https://www.federalreserve.gov/newsevents/pressreleases/monetary20130313a.htm); [Alphabet share-class rights](https://www.sec.gov/Archives/edgar/data/1652044/000165204423000016/googexhibit420q42022.htm). These support institutional descriptions, not predictive claims.
