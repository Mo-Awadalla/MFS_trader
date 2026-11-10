# Research reset completed — September 7, 2026

The requested configuration repair, common evaluation contract, synthetic calibration and frozen cross-family replay are complete. **No validated strategy that beats SPY emerged.** The replay found real data/reporting defects, but did not reveal a universal accounting setting suppressing profitable strategies. Several strategies make money under stated assumptions; that is different from meeting the SPY-outperformance objective.

This is a diagnostic sample of six families, not a certification of every historical hypothesis. Its historical periods were already exposed. No new confirmation period was opened, no new market data was acquired and no purchase or order was placed.

## Changes implemented

- Equity date-only requests now include the entire final New York date, with daylight-saving handling. Explicit timestamp requests retain their stated boundaries. Alpaca results are checked for complete requested exchange sessions, including wholly missing days and early closes. Incomplete coverage cannot be published through the standard storage pipeline.
- The cached stock runner now rejects an incomplete requested calendar instead of silently proceeding with a shortened cache. Old data files remain preserved; future acquisitions need a new, complete data version.
- Yahoo downloads now require valid adjusted-close data. Missing adjusted values no longer silently substitute raw prices. This protects future total-return comparisons; it does not prove that an old cache's adjustment history was correct.
- `research/intraday_contract.py` now provides shared same-day accounting, explicit missing-data states, allocation checks, signal-before-entry checks, consistent benchmark comparison, separate spread/slippage diagnostics, cost stress and preliminary economic checks.
- The replay uses this contract while preserving original signals, clocks and historical results. Original admission gates remain separate. Historical scout engines and the central/live strategy configuration have not all been migrated.
- Regression testing also exposed and fixed a small existing CCXT compatibility issue: a null Coinbase sandbox endpoint was incorrectly treated as available. This change affects the public historical-data client; it does not change an execution adapter.

See [the working contract](../../research/INTRADAY_RESEARCH_CONTRACT.md) for exact assumptions and future runner requirements. The date-boundary implementation is compatible with Alpaca's documented inclusive RFC3339 end parameter; the New York interpretation of date-only values is now an explicit local policy. [Alpaca historical stock bars](https://docs.alpaca.markets/us/reference/stockbars)

## Frozen sample and results

All dollar values below start from $100. The primary period is January 4, 2021–December 29, 2023: 753 exchange sessions. The SPY adjusted-price benchmark proxy ends at **$132.40**. The quote cases use actual UPRO/SPXU prices: leverage is already embedded and is not multiplied again.

The common quote scenario crosses the observed bid/ask, adds 1bp per side, and applies the explicitly recorded sell-fee approximations. These are standardized assumptions, not proof of actual historical fill costs. The midpoint column is a frictionless movement diagnostic; it is not an executable result.

| Family | Midpoint/reference | Observed bid/ask only | Common net | Assessment |
|---|---:|---:|---:|---|
| V83 calendar rebalancing | $126.39 | $119.22 | **$116.56** | Original net result reproduced exactly. Positive, but below SPY. |
| V56 stock/bond transmission | $143.02 | $117.80 | **$108.72** | Original quote-only result reproduced exactly. Common costs reduce the gain. Eligibility mismatch also requires disclosure. |
| V76 constituent dispersion | $146.41* | $123.29* | **$114.13*** | Original available-case result reproduced exactly. One missing exit prevents a complete equity claim. |
| V45 post-release macro response | $81.71 | $68.13 | **$62.93** | Loses even before crossing spreads. Original quote-only result reproduced to rounding precision. |

*V76 values describe only the available cases. The formal ending-equity field is null. On November 26, 2021, the exchange closed at 13:00; the original strategy requested a 15:55 exit and retained no qualifying exit. A different early-close rule would be a separately specified change, not a silently repaired fill.*

These calculations preserve 15 originally excluded degraded-data dates as declared no-trade dates. “Complete” for the other quote cases means complete accounting under that historical exclusion policy, not certification that those exclusions or prices were implementable in real time. The benchmark retains the full calendar. All historical SPY comparisons remain explicitly labeled an adjusted-price total-return proxy.

The other two frozen families exercise different failure stages:

| Family | Replay result | Meaning |
|---|---|---|
| V49 leveraged-ETF fair-value signal | Same 12 of 13 gates passed; adjacent-clock agreement remains **49.17%**, below 60% | Signal-stability rejection. No economic result was manufactured; P&L remains unopened under the original rule. |
| V94 individual-stock reversal | Available-case net **$62.75** in development; **$53.71** in the later, already exposed period | The original 5bp-per-side bar scenario reproduces. Six development and three later dates are missing, so complete equity is withheld. Static-universe and bar-execution limitations remain. |

V94's later benchmark is $148.00. Its later reference-price result is already negative before assumed costs. Neither its incomplete curves nor V49's stability failure should be described as a complete, validated losing backtest.

## What the reporting reconciliation changed

**V56 had inconsistent eligibility between feasibility and economics.** The feasibility audit excluded degraded ARCA signal dates as well as execution dates. The economic run excluded execution dates only, although its signal actually came from Yahoo daily SPY/IEF prices. Five economic trades therefore lie outside the feasibility audit's count:

| Signal date | Trade date |
|---|---|
| 2022-07-18 | 2022-07-19 |
| 2022-08-22 | 2022-08-23 |
| 2022-12-05 | 2022-12-06 |
| 2022-12-27 | 2022-12-28 |
| 2023-12-11 | 2023-12-12 |

The original economic ledger contains 382 trades; the audit-aligned diagnostic contains 377 and ends at **$103.73** under common costs. Both histories are retained. This establishes a protocol mismatch, not corrupted Yahoo values, and neither policy beats SPY. The reconciliation rule was saved before inspecting that supplemental outcome; it is still a post-replay diagnostic, not an original preregistration.

**V45's “378 sessions” were event trades across 306 distinct days.** The independent reconstruction confirms that sequential trades compound correctly. This is a labeling/cadence issue, not a demonstrated compounding bug in its original final cash.

**V76 and V94 now expose incomplete paths explicitly.** Available-case values remain for diagnosis, but missing dates cannot silently become zero-return days or receive a formal economic pass.

## Cost and latency stress

The doubled-cost stress doubles only the added bps, retaining observed spreads and the base fee assumptions. The one-minute delay changes entry by exactly one minute while retaining the original direction and exit; it does not choose a favorable delay. It was specified before these additional outcomes were read.

| Case | Common base | Doubled added bps | One-minute later entry |
|---|---:|---:|---:|
| V83 | $116.56 | $114.09 | $115.56 |
| V56, original economic eligibility | $108.72 | $100.72 | $106.52 |
| V76, available cases only | $114.13* | $106.03* | $117.13* |
| V45 | $62.93 | $58.35 | $66.62 |

No stress result establishes SPY outperformance. No minute-delay result is fabricated for V94's hourly bars, and V49 remains subject to its original signal gate. These stresses do not replace original controls, other delay tests or source-robustness requirements.

## Verification

- **47 focused tests passed** across the equity downloader, Yahoo parser, exchange calendar, cached runner, storage pipeline, common accounting, CCXT downloader and resampling. They include DST boundaries, holidays, early closes, missing complete sessions, adjusted-price failures, duplicate benchmark dates, invalid costs, look-ahead, overnight positions, over-allocation and sequential cash reuse.
- **Targeted lint passed** for the changed code and new runners.
- The controlled positive signal passed the common preliminary checks; **0 of 20 shuffled null signals passed**. The deliberately strong planted signal verifies that the pipeline can recover an obvious edge after costs. It does not measure power for small market edges or establish a universal false-positive rate.
- An independent Decimal calculation purchases fractional shares, applies sale proceeds and fees, and releases cash between trades. It imports no evaluator code and reconciles **all 11 exported evaluations**, with a maximum ending-cash difference below **$0.000000000006** per $100 start.
- Original quote-only results reproduce for V56/V76/V45; V83's original net daily returns reproduce exactly. V49's gates and actions match its previous replay. V94's available-case net results reproduce.
- The six selected historical result-file hashes are unchanged. Earlier reports remain available; this report supplies the corrected current interpretation.

The regression run initially encountered an inaccessible default Windows temporary directory; the successful run used a dedicated workspace test directory. No permission exception or network access was needed to finish validation.

## Current position and research decision

**Research infrastructure is more reliable; the investable-strategy count remains zero.** This sample does not support the explanation that one broken leverage multiplier, cost unit or compounding switch caused the repeated failures. It does support three narrower conclusions:

1. There are positive gross effects. V56 and V76 exceed the benchmark in their frictionless midpoint diagnostics, then fall below it after observed spread crossing. Execution drag is material for these cases; adding leverage again cannot cure it.
2. Positive net return is insufficient for the stated goal. V83 remains profitable with relatively modest drawdown but trails SPY even in its frictionless diagnostic. Changing the objective to risk-adjusted performance would be a separate decision.
3. Some apparent failures were never economic tests, and some reported curves were conditional or incomplete. Reporting those distinctions correctly prevents bad research decisions, but does not itself establish alpha.

The next research direction is **cost-aware testing of genuinely incremental information on liquid ETFs**, using existing data and this common contract. A new predictor must first beat a simple matched-time price-only control and retain a margin over observed trading costs. The historical stock/bond and breadth results do not justify cloning their failed features, and V83 does not earn special status merely for being positive. Opening signals should only be studied where quote timing resolves their intended horizon; the hourly stock panel cannot establish a fleeting opening effect.

**Stop decision:** no further tests or rescue variants are scheduled for these six cases. The user instructed that clear failures should be aborted. For future candidates, once the failure is verified, record its stage and stop; do not consume further confirmation data or computation trying to salvage it. V49 remains a recorded gate rejection and the incomplete cases retain their qualified status.

The practical order is to freeze one information-based hypothesis and its controls, measure incremental predictive value and execution drag on exposed development data, then spend further validation effort only if those diagnostics justify it. For broad stock research, point-in-time membership and suitable intraday coverage remain prerequisites. Repair any specifically needed cache into a new version; the present evidence does not justify a generic data purchase or another mass batch of small indicator variations. Any eventual claim of outperformance still needs appropriate selection-bias controls and genuinely new confirmation data.

## Artifacts and reproduction

- `specification.json`: six-case scope frozen before standardized replay outcomes.
- `summary.json`, `*_evaluation.json`, `*_legs.json`: common results, available-case flags and accounting exports.
- `reproduction.json`, `historical_preservation.json`: original-result reconciliation and preservation.
- `diagnostic_supplement_specification.json`, `protocol_reconciliation.json`: V56 eligibility mismatch and early-close/cadence findings.
- `latency_stress_summary.json`: fixed one-minute entry-delay results.
- `synthetic_calibration.json`: planted-signal and null outcomes.
- `verification.json`, `quality_checks.json`: independent reconstruction and focused validation record.

From the repository root, use the local environment's Python to run these modules in order: `research_scout.research_reset_20260907`, `research_scout.calibrate_intraday_contract_20260907`, `research_scout.reconcile_reset_diagnostics_20260907`, `research_scout.verify_research_reset_20260907`. They use existing files. Output files in this reset directory are reproducible artifacts; selected original strategy results are guarded by hashes.
