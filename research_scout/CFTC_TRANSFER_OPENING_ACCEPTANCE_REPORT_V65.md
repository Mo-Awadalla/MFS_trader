# CFTC Relative-Transfer / ES Opening Acceptance v65

## Verdict

**Rejected in 2021–2023; recent years remain locked.**

## Frozen development result

- Trades: 372 (2.470/declared week)
- Fixed-$100 P&L: $14.28
- Ending compounded cash: $101.47
- Adjusted SPY ending value: $132.40
- Profit factor: 1.041
- Annual P&L: 2021=$-19.84, 2022=$26.28, 2023=$7.84
- UPRO / SPXU P&L: $25.83 / $-11.55
- Extra-cent stress: $-15.14
- Five-minute-delay stress: $6.47
- Delete best five source reports: $-43.65
- Source-report bootstrap lower mean: -0.004211
- Source-report permutation p: 0.2006
- Independent overlap: 98 trades, $18.34, PF 1.309

## Controls

- es_only_opening_direction: 720 trades, $-30.26, mean $-0.0420
- cot_only_relative_transfer: 728 trades, $30.83, mean $0.0424
- one_report_shifted_transfer: 382 trades, $21.70, mean $0.0568
- asset_manager_only_confirmation: 376 trades, $26.54, mean $0.0706
- leveraged_fund_rejection: 361 trades, $-3.69, mean $-0.0102

## Gates

- more_than_two_executed_trades_per_declared_week: PASS
- execution_coverage_at_least_95_percent: PASS
- profit_factor_strictly_above_1_10: FAIL
- positive_each_development_year: FAIL
- both_upro_and_spxu_positive: FAIL
- compounded_ending_cash_above_adjusted_spy: FAIL
- positive_after_one_extra_cent_each_fill: FAIL
- positive_after_five_minute_entry_delay: PASS
- positive_after_deleting_best_five_source_reports: FAIL
- source_report_block_bootstrap_lower_above_zero: FAIL
- source_report_direction_permutation_p_below_0_05: FAIL
- independent_overlap_positive_pf_above_one_both_sleeves: PASS
- actual_mean_trade_above_shifted_and_cot_only_controls: FAIL

Failed gates: profit_factor_strictly_above_1_10, positive_each_development_year, both_upro_and_spxu_positive, compounded_ending_cash_above_adjusted_spy, positive_after_one_extra_cent_each_fill, positive_after_deleting_best_five_source_reports, source_report_block_bootstrap_lower_above_zero, source_report_direction_permutation_p_below_0_05, actual_mean_trade_above_shifted_and_cot_only_controls

Recent-year status: locked_not_read.
