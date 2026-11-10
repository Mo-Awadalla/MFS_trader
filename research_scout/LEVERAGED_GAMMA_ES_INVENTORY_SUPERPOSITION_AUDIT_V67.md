# Leveraged-Fund Gamma / ES Inventory Superposition Audit v67

## Verdict

**Every returns-blind gate passed. The frozen 2021–2023 P&L test is authorized; recent years remain locked.**

## Frozen construction

- Add first-order four-fund rebalance demand through SPY 15:29 to completed 15:00–15:30 ES aggressor inventory transfer.
- Both terms are signed S&P-dollar exposure.
- Positive net pressure selects UPRO; negative selects SPXU.
- Planned execution is 15:31 ask to 15:59 bid.

## Reachability and balance

- Eligible states: 733 (97.344%)
- Signals: 733 (4.867/week)
- UPRO / SPXU: 347 / 386
- By year: 2021=249, 2022=246, 2023=238
- Direction switches: 2021=129, 2022=117, 2023=115

## Stability and distinctness

- 15:28 neighboring action agreement: 99.727%
- Agreement with fund-only action: 74.079%
- Agreement with ES-only action: 81.719%
- Agreement with first-2021 fixed AUM coefficient: 97.408%
- Agreement with one-session-shifted ES term: 65.164%

## Quote evidence

- Primary entry+exit coverage: 100.000%
- Independent-overlap entry+exit coverage: 100.000%

## Gates

- eligible_coverage_at_least_95_percent: PASS
- signal_frequency_at_least_2_per_week: PASS
- at_least_100_signals_each_year: PASS
- both_sleeves_and_minority_at_least_35_percent: PASS
- at_least_20_action_switches_each_year: PASS
- adjacent_15_28_action_stability_at_least_85_percent: PASS
- combined_distinct_from_fund_only_below_90_percent: PASS
- combined_distinct_from_es_only_below_90_percent: PASS
- primary_entry_exit_quote_coverage_at_least_95_percent: PASS
- independent_entry_exit_quote_coverage_at_least_90_percent: PASS
- all_aum_source_dates_strictly_before_signal_dates: PASS
- no_fitted_threshold_or_rescaling: PASS
- no_post_entry_return_or_recent_outcome_read: PASS

Failed gates: none

No entry-to-exit return, P&L, or 2024–2025 strategy outcome was calculated.
