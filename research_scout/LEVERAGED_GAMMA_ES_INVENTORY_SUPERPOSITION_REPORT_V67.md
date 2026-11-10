# Leveraged-Fund Gamma / ES Inventory Superposition v67

## Verdict

**Rejected in 2021–2023; recent years remain locked.**

## Frozen result

- Trades: 733 (4.867/declared week)
- Fixed-$100 P&L: $-22.86
- Ending compounded cash: $77.89
- Adjusted SPY ending value: $132.40
- Profit factor: 0.890
- Annual P&L: 2021=$-11.79, 2022=$-1.88, 2023=$-9.18
- UPRO / SPXU P&L: $-20.21 / $-2.65
- Extra-cent stress: $-88.24
- Five-minute delay: $-40.38
- Delete ten best sessions: $-51.95
- Bootstrap lower mean: -0.000801
- Direction permutation p: 0.2917
- Independent overlap: 180 trades, $-15.25, PF 0.612

## Controls

- fund_only: 733 trades, $-28.24, mean $-0.0385
- es_only: 732 trades, $-33.74, mean $-0.0461
- fixed_aum_coefficient: 733 trades, $-23.53, mean $-0.0321
- one_session_shifted_es: 732 trades, $-48.54, mean $-0.0663

## Gates

- at_least_two_executed_trades_per_declared_week: PASS
- execution_coverage_at_least_95_percent: PASS
- profit_factor_at_least_1_10: FAIL
- positive_each_development_year: FAIL
- both_upro_and_spxu_positive: FAIL
- compounded_ending_cash_above_adjusted_spy: FAIL
- positive_after_one_extra_cent_each_fill: FAIL
- positive_after_five_minute_entry_delay: FAIL
- positive_after_deleting_ten_best_sessions: FAIL
- moving_block_bootstrap_lower_mean_above_zero: FAIL
- independent_2023_overlap_positive: FAIL
- combined_mean_trade_above_all_controls: PASS

Failed gates: profit_factor_at_least_1_10, positive_each_development_year, both_upro_and_spxu_positive, compounded_ending_cash_above_adjusted_spy, positive_after_one_extra_cent_each_fill, positive_after_five_minute_entry_delay, positive_after_deleting_ten_best_sessions, moving_block_bootstrap_lower_mean_above_zero, independent_2023_overlap_positive

Recent-year status: locked_not_read.
