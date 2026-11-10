# Treasury Dealer Dollar-Years Overhang v66

## Verdict

**Rejected in 2021–2023; recent years remain locked.**

## Frozen development result

- Trades: 564 (3.745/declared week)
- Fixed-$100 P&L: $19.70
- Ending compounded cash: $99.96
- Adjusted SPY ending value: $132.40
- Profit factor: 1.036
- Annual P&L: 2021=$-13.21, 2022=$34.81, 2023=$-1.90
- UPRO / SPXU P&L: $38.32 / $-18.62
- Extra-cent stress: $-27.94
- Five-minute-delay stress: $23.87
- Delete five event clusters: $-30.87
- Cluster bootstrap lower mean: -0.001992
- Direction permutation p: 0.2500
- Independent overlap: 150 trades, $13.70, PF 1.127

## Controls

- accepted_notional_only: 564 trades, $-52.65, mean $-0.0934
- fixed_coupon_only: 271 trades, $37.88, mean $0.1398
- extra_session_lag: 555 trades, $-12.99, mean $-0.0234
- flipped_direction: 562 trades, $-72.81, mean $-0.1295

## Gates

- more_than_two_executed_trades_per_declared_week: PASS
- execution_coverage_at_least_95_percent: PASS
- profit_factor_strictly_above_1_10: FAIL
- positive_each_development_year: FAIL
- both_upro_and_spxu_positive: FAIL
- compounded_ending_cash_above_adjusted_spy: FAIL
- positive_after_one_extra_cent_each_fill: FAIL
- positive_after_five_minute_entry_delay: PASS
- positive_after_deleting_best_five_clusters: FAIL
- cluster_bootstrap_lower_above_zero: FAIL
- event_direction_permutation_p_below_0_05: FAIL
- independent_positive_pf_above_one_both_sleeves: PASS
- actual_mean_above_frozen_controls: FAIL

Failed gates: profit_factor_strictly_above_1_10, positive_each_development_year, both_upro_and_spxu_positive, compounded_ending_cash_above_adjusted_spy, positive_after_one_extra_cent_each_fill, positive_after_deleting_best_five_clusters, cluster_bootstrap_lower_above_zero, event_direction_permutation_p_below_0_05, actual_mean_above_frozen_controls

Recent-year status: locked_not_read.
