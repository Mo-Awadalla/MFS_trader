# BTC Spot Risk-Attention Gate × SPY Gap v32

## Verdict

**REJECTED DEVELOPMENT HOLDOUT LOCKED**

The state sensor uses Binance BTCUSDT spot flow only. Direction comes from SPY's official cash gap. No futures, margin, or crypto derivative field is used.

## Development

| Trades/week | Fixed-$100 P&L | Ending cash | PF | SPY ending cash |
|---:|---:|---:|---:|---:|
| 2.737 | $-30.58 | $64.50 | 0.925 | $126.66 |

## Frozen development gates

- PASS — minimum_two_trades_per_week
- FAIL — profit_factor_strictly_above_one
- FAIL — each_year_positive
- FAIL — both_actuators_positive
- FAIL — ending_cash_above_spy
- FAIL — positive_after_extra_cent_each_fill
- FAIL — positive_after_five_minute_delay
- FAIL — positive_after_removing_best_10
- FAIL — mean_trade_above_unfiltered_spy_gap
- FAIL — winner_deleted_pnl_above_unfiltered_spy_gap
- FAIL — fixed_pnl_above_one_session_shifted_attention
- FAIL — independent_feed_overlap_pnl_positive

Historical results are research evidence, not a profit guarantee or authorization for live capital.
