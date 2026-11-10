# BTC Spot Flow Baton to UPRO/SPXU v26

## Verdict

**REJECTED DEVELOPMENT HOLDOUT LOCKED**

The signal uses BTCUSDT spot taker flow only. No futures, perpetual, funding, margin, or crypto derivative field is used.

## Development

| Trades/week | Fixed-$100 P&L | Ending cash | PF | SPY ending cash |
|---:|---:|---:|---:|---:|
| 2.741 | $-39.76 | $58.57 | 0.905 | $126.66 |

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
- FAIL — outperform_btc_price_persistence
- PASS — outperform_europe_flow_only

Historical results are research evidence, not a profit guarantee or authorization for live capital.
