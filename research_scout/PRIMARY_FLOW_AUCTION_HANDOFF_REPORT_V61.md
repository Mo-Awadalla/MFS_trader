# Primary-Flow / Opening-Auction Handoff v61

## Verdict

**Rejected in development; 2024-2025 remains locked.**

## Development: 2021-2023

- Trades: 373 (2.406/week)
- Fixed-$100 P&L: $-23.89
- Compounded ending cash: $76.15
- Profit factor: 0.882
- Adjusted SPY ending cash: $132.40
- P&L without ten best sessions: $-53.04
- Extra-cent stress P&L: $-58.20
- Five-minute-delay P&L: $-27.12

Failed development gates: profit_factor_strictly_above_1_10, fixed_notional_pnl_positive_each_year, both_upro_and_spxu_fixed_notional_pnl_positive, compounded_ending_cash_above_adjusted_spy, positive_after_one_extra_cent_each_fill, positive_after_five_minute_entry_delay, positive_after_deleting_ten_best_sessions, moving_block_bootstrap_lower_mean_above_zero, independent_feed_overlap_positive, mean_trade_return_above_every_control

## Integrity boundary

The official-flow definition, auction cutoff, clocks, sleeves, controls, and gates were frozen before return inspection. No threshold, sign, horizon, or sleeve repair was made.
