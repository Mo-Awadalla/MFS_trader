# SPY Official Macro-Release Delayed Discovery v45

## Verdict

**Rejected in development. The 2024-2025 return holdout remains locked.**

## Development

- Trades: 378 (2.4320/week)
- Fixed-$100 P&L: $-33.90
- Ending cash: $68.13
- Profit factor: 0.8350
- SPY total-return ending value: $132.40
- Annual P&L: {'2021': 9.436012594528634, '2022': -59.76814212480747, '2023': 16.432131756929596}
- Instrument P&L: {'SPXU': -23.634795238602155, 'UPRO': -10.265202534747072}
- Release-clock P&L: {'08:30:00': -15.245041982274945, '10:00:00': 2.7110426124142935, '14:00:00': -21.36599840348858}
- Independent overlap P&L: $7.28

## Development gates

- PASS — minimum_two_trades_per_week
- FAIL — profit_factor_at_least_1_05
- FAIL — positive_fixed_notional_pnl
- FAIL — each_development_year_positive
- FAIL — both_upro_and_spxu_positive
- FAIL — each_release_clock_positive
- FAIL — ending_cash_above_spy_total_return
- FAIL — positive_after_extra_cent_each_fill
- FAIL — positive_after_five_minute_entry_delay
- FAIL — positive_after_removing_ten_best_trades
- PASS — positive_independent_feed_overlap
- PASS — outperform_next_non_event_same_clock_control
- FAIL — outperform_direction_flipped_control

No event family, clock, year, direction, or threshold may be repaired from these results.
