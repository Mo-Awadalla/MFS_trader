========================================================================
  ETF Time-Series Momentum Vol Target v1 Validation Report
========================================================================
  Experiment UUID: aadae37d-192f-41f5-948d-b9bd65d4a7a3
  Params: {'momentum_lookback_days': 252, 'vol_lookback_days': 63, 'liquidity_lookback_days': 20, 'min_history_days': 252, 'min_price': 5.0, 'min_median_dollar_volume': 5000000.0, 'min_eligible_symbols': 1, 'top_n': 3, 'fallback_symbol': 'SHY', 'target_volatility_annual': 0.1, 'min_gross': 0.25, 'max_gross': 1.0, 'max_symbol_weight': 0.5}
  Research Sharpe: 0.8347
  Research total return: 0.5450
  Rebalances: 73
  Skipped rebalances: 14
  Gauntlet passed: False
  Failures:
    - WFA: oos_sortino 0.99 < 1.0
========================================================================
