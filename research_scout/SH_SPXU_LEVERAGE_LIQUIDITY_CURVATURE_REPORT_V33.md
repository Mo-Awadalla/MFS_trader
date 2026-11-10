# SH/SPXU Inverse-Leverage Liquidity Curvature v33

## Verdict

**REJECTED DEVELOPMENT HOLDOUT LOCKED**

The signal and actuator use cash ETFs only. No futures, margin, short sale, or passive-fill assumption is used.

## Development

| Trades/week | Fixed-$100 P&L | Ending cash | PF | SPY ending cash |
|---:|---:|---:|---:|---:|
| 4.478 | $-59.08 | $46.24 | 0.902 | $126.66 |

## Frozen development gates

- PASS — minimum_two_trades_per_week
- FAIL — profit_factor_strictly_above_one
- FAIL — each_year_positive
- FAIL — both_actuators_positive
- FAIL — ending_cash_above_spy
- FAIL — positive_after_extra_cent_each_fill
- FAIL — positive_after_five_minute_delay
- FAIL — positive_after_removing_best_10
- FAIL — outperform_sign_flipped
- PASS — outperform_raw_sh_spread_change
- PASS — outperform_raw_spxu_spread_change
- FAIL — independent_feed_overlap_pnl_positive

Historical results are research evidence, not a profit guarantee or authorization for live capital.
