# TGA Realized Reserve Transfer v74

## Verdict

**Rejected in 2021–2023; recent years remain locked.**

- Trades: 727 (4.827/declared week)
- Fixed-$100 P&L: $-35.59
- Ending cash / adjusted SPY: $55.09 / $132.40
- Profit factor: 0.950
- Annual P&L: 2021=$-5.42, 2022=$-56.35, 2023=$26.18
- UPRO / SPXU: $22.65 / $-58.23
- Extra-cent / 09:38 delay: $-97.00 / $-19.02
- Delete ten: $-105.56
- Bootstrap lower mean: -0.002497
- Month-stratified permutation p: 0.6557
- Independent overlap: 188 trades, $0.34, PF 1.003
- Extra-lag / prior-SPY control means: $0.0329 / $-0.0795

Failed gates: profit_factor_at_least_1_10, positive_each_development_year, both_upro_and_spxu_positive, ending_cash_above_adjusted_spy, positive_after_one_extra_cent_each_fill, positive_after_09_38_entry_delay, positive_after_deleting_best_10_sessions, block_bootstrap_lower_mean_above_zero, month_stratified_permutation_p_below_0_05, mean_above_extra_publication_session_lag

Recent-year status: locked_not_read.
