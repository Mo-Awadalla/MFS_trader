========================================================================
  ETF Time-Series Momentum Vol Target v1 Validation Report
========================================================================
  Experiment UUID: 8876fbc6-7db3-4996-8fc7-b24b0e55c83c
  Params: {'momentum_lookback_days': 252, 'vol_lookback_days': 63, 'liquidity_lookback_days': 20, 'min_history_days': 252, 'min_price': 5.0, 'min_median_dollar_volume': 5000000.0, 'min_eligible_symbols': 1, 'top_n': 3, 'fallback_symbol': 'SHY', 'target_volatility_annual': 0.1, 'min_gross': 0.25, 'max_gross': 1.0, 'max_symbol_weight': 0.5}
  Research Sharpe: 1.0272
  Research total return: 0.6089
  Rebalances: 61
  Skipped rebalances: 13
  Gauntlet passed: False
  Failures:
    - DSR: DSR collapses under M_raw: p = 0.1367 >= 0.10
========================================================================
