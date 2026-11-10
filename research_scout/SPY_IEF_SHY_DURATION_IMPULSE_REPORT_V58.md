# IEF / SHY Duration-Impulse Persistence v58

## Verdict

**Rejected in development; the 2024-2025 return holdout remains locked.**

## Development: 2021-2023

- Trades: 734 (4.722/week)
- Compounded cash: $73.01
- Fixed-$100 P&L: $-7.46
- Profit factor: 0.989
- Split/dividend-adjusted SPY hurdle: $132.40
- P&L after deleting ten best trades: $-87.52
- Extra-cent stress P&L: $-72.68
- Five-minute delay P&L: $-11.20

Failed development gates: profit_factor_at_least_1_05, positive_fixed_notional_pnl, each_development_year_positive, both_upro_and_spxu_positive, ending_cash_above_spy_total_return, positive_after_extra_cent_each_fill, positive_after_five_minute_entry_delay, positive_after_deleting_ten_best_trades, positive_independent_overlap, mean_trade_pnl_above_prior_ief_continuation, mean_trade_pnl_above_prior_shy_continuation, mean_trade_pnl_above_prior_spy_continuation, mean_trade_pnl_above_lagged_relative_direction

## Integrity boundary

The IEF/SHY sensor, direction map, clocks, controls, and gates were frozen before target-return inspection. No DV01 estimate, magnitude threshold, asset addition, regime filter, sign change, sleeve deletion, or timing repair was made.
