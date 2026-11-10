# Institutional Cash-ETF and SPY-Auction Research Report v36

## Decision

**No new strategy P&L was opened.** V35 and V36 both passed a serious institutional-mechanism critique but failed frozen returns-blind gates. Calculating their returns after failure would add contamination without producing an admissible candidate. There is no historical survivor and no production-readiness claim.

V20 remains the strongest prior margin-free reference candidate, but it remains rejected by its original winner-concentration gate. Its event-level TBBO work below is an execution-fidelity audit only.

## 1. New-data technical evidence

- SPY ARCX.PILLAR imbalance: 10,838,203 records, 1,395 sessions per observed O/M/C type, clean EOF.
- Auction types are venue-documented: O Early Opening, M Core Opening, H Halt Resume, C Closing. This file contains O/M/C and no H.
- Core signal ordering uses `ts_event` converted to America/New_York. `auction_time` is an exchange-local projected wall clock and is not the publication timestamp.
- Documented measurement break: from 2025-11-13, paired, total-imbalance, and market-imbalance quantities are measured at `ref_price`; before that date they are measured at `ind_match_price`.
- TBBO logical decode obeyed the mandatory boundary: 18,255,888 prefix records through 2024-10-02 and 18,823,909 clean-tail records from 2024-10-03.
- Valid trade-event TBBO rows after rejecting crossed/nonpositive quotes: SPY 29,714,433; SSO 751,719; UPRO 2,461,989; SH 805,355; SDS 1,275,993; SPXU 2,003,153.
- EQUS.MINI is a derived anonymized multi-venue product, not official SIP NBBO. It samples BBO immediately before trades and does not contain every quote update. True standing-quote age and quote-only lead/lag remain unobservable.
- The exact 20 ARCX and 15 EQUS degraded dates are loaded from the condition files and excluded by union in primary eligibility.
- ARCX statistics identify Core Open, Closing, and Early Open/halt-reopen outcomes. They are post-cross outcomes and are prohibited as pre-auction signal inputs.
- Publication-time proof: all 57 V35 and 809 V36 candidate signals had `ts_recv` before both the 09:29:50 cutoff and the earliest 09:30:01 order. Minimum observed lead to that order was 11.234 seconds.

Detailed evidence: `research_scout/NEW_DATA_TECHNICAL_AUDIT_V34.md`, `research_scout/new_data_technical_audit_v34.json`, and `research_scout/CASH_ETF_CAPABILITY_MATRIX_CORRECTED_V34.md`.

## 2. Corrected V33 conclusion

V33's data-absence premise is superseded for exchange-published SPY auction state and trade-event cash-ETF TBBO from 2023-03-28. Its strategy-failure registry, passive-fill objection, historical-contamination warning, and primary-market-data blockers remain valid. The new package still lacks official SIP NBBO, every quote update, standing quote age, queue/depth, NAV/iNAV, AUM/shares, creation/redemption baskets, AP/dealer identity, and hedge flow.

## 3. V20 execution-fidelity audit

The V20 rule was unchanged. Entry uses the first valid ask after 10:01 plus 1, 5, or 60 seconds; exit uses the first valid bid after the unchanged structural-exit target; event wait is capped at 60 seconds; position size is fixed at $100.

- development_overlap_2023, 1s: 79 trades, fixed-$100 P&L $9.06, PF 1.395, spread drag $3.76, one-cent stress P&L $1.55.
- development_overlap_2023, 5s: 79 trades, fixed-$100 P&L $9.50, PF 1.425, spread drag $3.77, one-cent stress P&L $1.99.
- development_overlap_2023, 60s: 69 trades, fixed-$100 P&L $8.65, PF 1.368, spread drag $3.38, one-cent stress P&L $1.83.
- historical_validation_2024_2025, 1s: 162 trades, fixed-$100 P&L $9.15, PF 1.157, spread drag $5.04, one-cent stress P&L $0.11.
- historical_validation_2024_2025, 5s: 165 trades, fixed-$100 P&L $10.85, PF 1.184, spread drag $5.11, one-cent stress P&L $1.68.
- historical_validation_2024_2025, 60s: 146 trades, fixed-$100 P&L $7.18, PF 1.126, spread drag $4.50, one-cent stress P&L $-1.00.
- temporal_extension_2026, 1s: 0 trades.
- temporal_extension_2026, 5s: 0 trades.
- temporal_extension_2026, 60s: 0 trades.

These outcomes are historically contaminated execution diagnostics. They cannot rescue V20 or authorize parameter changes. Full details: `research_scout/V20_TBBO_EXECUTION_FIDELITY_AUDIT_V34.md`.

The zero-trade 2026 rows are not a negative temporal result: the frozen V20 ES source file ends at 2025-12-31, so no 2026 V20 states were available to audit.

## 4. New economic hypotheses and feasibility

### V35 — paired-absorption failure trajectory

Mechanism: same-side unpaired pressure gains share from 09:28 to 09:29:50 while side-signed indicative displacement rises, implying offsetting auction liquidity is losing ground before the continuous handoff.

Result before P&L: 20 development feature signals, 0.135 per week; 7 executable 2023-overlap signals. Failed gates: feature_frequency_at_least_two_per_week_2021_2023, executable_frequency_at_least_two_per_week_2023_overlap, prefer_100_feature_signals_each_full_development_year, minority_executable_side_at_least_20pct, cross_ladder_5s_availability_at_least_80pct, adjacent_09_29_30_identical_action_at_least_60pct, adjacent_09_29_59_identical_action_at_least_60pct. The rule is terminal and was not repaired.

### V36 — price/quantity disagreement

Mechanism: the final published imbalance side and indicative-price displacement disagree, so the opposite limit curve rather than the unpaired-side label appears to control the marginal auction price.

Result before P&L: 486 development feature signals (3.124/week) and 111 executable development-overlap signals (2.815/week). Quote coverage for required UPRO/SPXU targets was 90.48%, but only 244/399 executable signals had all-six-ladder 5-second evidence. Identical action including cash was 53.91% at 09:29:30 and 44.59% at 09:29:59. It produced no 2026 signals. Failed gates: cross_ladder_5s_availability_at_least_80pct, adjacent_09_29_30_identical_action_at_least_60pct, adjacent_09_29_59_identical_action_at_least_60pct.

The V36 preregistration is explicitly **not activated**. It records the frozen rule and failed gates but does not authorize a return calculation.

## 5. Executable result

There is no admissible new-strategy executable result because no candidate crossed the returns-blind gate. Consequently profit factor, fixed-dollar P&L, SPY benchmark comparison, one-cent stress, delay robustness, best-trade deletion, directional contribution, controls, and placebos were not calculated for V35 or V36. Reporting invented zeros or opening returns after rejection would be less honest than stopping.

## 6. Robustness result

The decisive robustness evidence is pre-outcome:

- V35 is structurally too sparse for the required cadence and unstable across adjacent cutoffs.
- V36 has adequate raw cadence and UPRO/SPXU quote coverage but fails preregistered adjacent-cutoff action stability and all-six-ladder evidence coverage.
- V36 has no 2026 participation, so it cannot demonstrate a temporal extension.
- The trade-event TBBO cannot establish true quote freshness or quote-only lead/lag.

Mandatory P&L controls and placebos were deliberately not opened because the candidate did not qualify for an alpha test.

## 7. Contamination risk

The auction fields are newly observed causal variables, but historical price outcomes are not new. 2021–2023 is development/measurement, 2024–2025 is historical validation with familywise contamination, and 2026 is only a temporal extension. V34 was already outcome-exposed and failed. Its prior script also loaded 2024–2025 price files before stopping, even though it did not report holdout returns, so those dates are not claimed untouched. V35 and V36 added to the multiplicity count but stopped before returns.

## 8. What remains unknown

- Whether a stable auction feature can predict post-open executable returns after 60 seconds.
- Whether apparent cross-leverage lags survive a complete quote-update or official consolidated feed.
- Whether wrapper deviations are true NAV/inventory effects without point-in-time NAV/iNAV, shares, AUM, baskets, creations/redemptions, and AP/dealer hedge data.
- Whether any effect survives genuinely prospective sessions.

## 9. Prospective requirement

No V35 or V36 paper rule should be activated. A future candidate must first use a causally different measurement, account for the 2025-11-13 quantity-definition break, pass the same returns-blind cadence/stability/coverage gates, and freeze a full preregistration. Only a historical survivor should enter forward paper trading, with no rule changes and simultaneous 1/5/60-second shadow execution until at least 100 nonoverlapping trades include both directional regimes. Production use would require a later untouched evaluation and data capable of validating quote freshness.

## Reproducibility

- Technical decode: `python research_scout/audit_cash_etf_new_data_v34.py`
- V20 fidelity: `python research_scout/audit_v20_tbbo_execution_fidelity_v34.py`
- V35 feasibility: `python research_scout/audit_spy_auction_absorption_failure_v35.py`
- V36 feasibility: `python research_scout/audit_spy_auction_price_quantity_disagreement_v36.py`
- Final compiler: `python research_scout/compile_cash_etf_research_report_v36.py`

No paid download or API call was made by these scripts.
