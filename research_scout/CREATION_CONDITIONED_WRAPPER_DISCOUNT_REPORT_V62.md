# Creation-Conditioned Wrapper Discount v62

## Verdict

**Rejected in 2021-2023 development; 2024-2025 remains locked.**

## Development result

- Executed trades: 315 (2.092/declared week)
- Fixed-$100 P&L: $10.85
- Ending compounded cash: $108.84
- Adjusted SPY ending value: $132.40
- Profit factor: 1.077
- Annual P&L: 2021=$10.97, 2022=$5.41, 2023=$-5.53
- UPRO / SPXU P&L: $12.21 / $-1.36
- Extra-cent stress: $-16.87
- Five-minute-delay stress: $7.13
- Delete ten best: $-19.36
- Block-bootstrap 95% lower mean return: -0.001109
- Independent 2023 overlap: 75 trades, $-5.55, PF 0.783

## Controls

- discount_only: $14.12, mean $0.0205
- creation_only: $-12.29, mean $-0.0231
- redemption_conditioned_discount: $14.74, mean $0.0426
- extra_lag_creation_discount: $-11.49, mean $-0.0367
- creation_conditioned_premium_continuation: $-44.41, mean $-0.1276

## Gates

- minimum_two_executed_trades_per_declared_week: PASS
- signal_execution_coverage_at_least_95_percent: PASS
- profit_factor_strictly_above_1_10: FAIL
- fixed_notional_pnl_positive_each_year: FAIL
- both_upro_and_spxu_fixed_notional_pnl_positive: FAIL
- compounded_ending_cash_above_adjusted_spy: FAIL
- positive_after_one_extra_cent_each_fill: FAIL
- positive_after_five_minute_entry_delay: PASS
- positive_after_deleting_ten_best_sessions: FAIL
- moving_block_bootstrap_lower_mean_above_zero: FAIL
- independent_feed_overlap_positive_and_pf_above_one: FAIL
- mean_trade_return_above_every_control: FAIL

Failed gates: profit_factor_strictly_above_1_10, fixed_notional_pnl_positive_each_year, both_upro_and_spxu_fixed_notional_pnl_positive, compounded_ending_cash_above_adjusted_spy, positive_after_one_extra_cent_each_fill, positive_after_deleting_ten_best_sessions, moving_block_bootstrap_lower_mean_above_zero, independent_feed_overlap_positive_and_pf_above_one, mean_trade_return_above_every_control

Recent-year status: locked_not_read.
