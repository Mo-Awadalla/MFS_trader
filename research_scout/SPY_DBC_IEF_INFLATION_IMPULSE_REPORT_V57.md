# DBC / IEF Inflation-Impulse Persistence v57

## Verdict

**Rejected in development; the 2024-2025 return holdout remains locked.**

## Development: 2021-2023

- Trades: 367 (2.363/week)
- Compounded cash: $64.37
- Fixed-$100 P&L: $-32.18
- Profit factor: 0.911
- Split/dividend-adjusted SPY hurdle: $132.40
- P&L after deleting ten best trades: $-97.68
- Extra-cent stress P&L: $-68.08
- Five-minute delay P&L: $-40.76

Failed development gates: profit_factor_at_least_1_05, positive_fixed_notional_pnl, each_development_year_positive, both_upro_and_spxu_positive, ending_cash_above_spy_total_return, positive_after_extra_cent_each_fill, positive_after_five_minute_entry_delay, positive_after_deleting_ten_best_trades, positive_independent_overlap, mean_trade_pnl_above_prior_dbc_continuation, mean_trade_pnl_above_prior_ief_continuation, mean_trade_pnl_above_sign_flipped

## Integrity boundary

The DBC/IEF sensor, direction map, clocks, controls, and gates were frozen before target-return inspection. No magnitude threshold, third asset, regime filter, sign change, sleeve deletion, or timing repair was made.
