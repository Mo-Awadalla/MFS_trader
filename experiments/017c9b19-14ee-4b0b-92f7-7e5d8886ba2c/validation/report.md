========================================================================
  ETF Tactical Momentum v1 Validation Report
========================================================================
  Experiment UUID: 017c9b19-14ee-4b0b-92f7-7e5d8886ba2c
  Params: {'short_lookback_days': 126, 'long_lookback_days': 252, 'trend_ma_days': 200, 'vol_lookback_days': 63, 'liquidity_lookback_days': 20, 'min_history_days': 252, 'min_price': 5.0, 'min_median_dollar_volume': 5000000.0, 'min_eligible_symbols': 4, 'top_n': 3, 'defensive_top_n': 2, 'long_gross': 1.0, 'max_symbol_weight': 0.6}
  Research Sharpe: 0.4628
  Research total return: 0.3214
  Rebalances: 73
  Skipped rebalances: 14
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe 0.52 < 0.8
    - WFA: oos_sortino 0.83 < 1.0
    - DSR: DSR p-value (M_eff_corr) = 0.0605 >= 0.05
    - DSR: DSR collapses under M_raw: p = 0.5590 >= 0.10
========================================================================
