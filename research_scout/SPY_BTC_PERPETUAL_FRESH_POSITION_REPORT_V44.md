# SPY BTC-Perpetual Fresh-Position Risk Transfer v44

## Verdict

**REJECTED DEVELOPMENT HOLDOUT LOCKED**

V44 uses the sign of the 16:00-to-09:00 BTCUSDT perpetual move only when BTC-denominated Binance open interest expands. It enters UPRO or SPXU at the observed 09:31 ask and exits at the observed 15:30 bid.

## Development: 2021–2023

| Trades/week | Fixed-$100 P&L | Ending cash | PF | SPY price-only | SPY total-return |
|---:|---:|---:|---:|---:|---:|
| 2.967 | $-74.54 | $40.83 | 0.841 | $126.66 | $132.40 |

## Identification and stress results

- Extra cent at each fill: $-112.51.
- Five-minute entry delay: $-83.18.
- Delete ten best sessions: $-140.30.
- BTC price-only control: $-77.21.
- OI-decreasing control: $-2.66.
- Shifted-expansion control: $-68.38.
- Sign-flipped control: $31.22.
- Independent EQUS development-overlap P&L: $-31.22.

## Frozen development gates

- PASS — minimum_two_trades_per_week
- FAIL — profit_factor_strictly_above_one
- FAIL — each_year_positive
- FAIL — both_actuators_positive
- FAIL — ending_cash_above_spy_price_only
- FAIL — ending_cash_above_spy_total_return
- FAIL — positive_after_extra_cent_each_fill
- FAIL — positive_after_five_minute_entry_delay
- FAIL — positive_after_removing_best_10
- FAIL — mean_trade_above_btc_price_only_control
- PASS — winner_deleted_pnl_above_btc_price_only_control
- FAIL — pnl_above_oi_decreasing_control
- FAIL — pnl_above_shifted_expansion_control
- FAIL — pnl_above_sign_flipped_control
- FAIL — independent_feed_overlap_pnl_positive

No failed direction, threshold, clock, sleeve, or control was selected as a repair. Historical results are research evidence, not authorization for live capital.

Preimplementation critique: `research_scout/SPY_BTC_PERPETUAL_FRESH_POSITION_RISK_TRANSFER_PREIMPLEMENTATION_CRITIQUE_V44.md`.

Machine result: `research_scout/spy_btc_perpetual_fresh_position_results_v44.json`.
