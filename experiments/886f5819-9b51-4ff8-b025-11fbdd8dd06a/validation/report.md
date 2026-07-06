========================================================================
  Residual Reversal Stat Arb v1 Validation Report
========================================================================
  Experiment UUID: 886f5819-9b51-4ff8-b025-11fbdd8dd06a
  Params: {'regression_lookback_days': 60, 'residual_vol_lookback_days': 20, 'liquidity_lookback_days': 20, 'min_history_days': 120, 'min_regression_obs': 45, 'min_price': 5.0, 'min_median_dollar_volume': 20000000.0, 'min_eligible_symbols': 60, 'selection_count': 10, 'long_gross': 1.0, 'short_gross': 1.0, 'max_symbol_weight': 0.1, 'factor_symbols': ['SPY', 'QQQ', 'IWM']}
  Research Sharpe: -5.5304
  Research total return: -0.9997
  Rebalances: 2136
  Skipped rebalances: 120
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe -5.68 < 0.8
    - WFA: oos_sortino -8.88 < 1.0
    - WFA: frac_negative_folds 1.00 > 0.5
    - MC: P(ruin) = 1.000 >= 0.05
    - MC: 5th pct CAGR = -0.662 <= 0
    - MC: 95th pct max DD = -1.000 < -0.3
    - DSR: no positive Sharpe to deflate
========================================================================
