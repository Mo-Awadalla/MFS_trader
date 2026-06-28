========================================================================
  Residual Vol Momentum v1 Validation Report
========================================================================
  Experiment UUID: 5b8514cc-5f1b-4c63-b815-6f90a26c5aba
  Params: {'formation_lookback_days': 252, 'skip_recent_days': 21, 'residual_vol_lookback_days': 63, 'liquidity_lookback_days': 20, 'min_history_days': 252, 'min_regression_obs': 126, 'min_price': 5.0, 'min_median_dollar_volume': 20000000.0, 'min_eligible_symbols': 50, 'long_gross': 1.0, 'short_gross': 1.0, 'risk_off_gross_scalar': 0.5, 'max_symbol_weight': 0.08}
  Research Sharpe: -0.6302
  Research total return: -0.4219
  Rebalances: 76
  Skipped rebalances: 34
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe -0.65 < 0.8
    - WFA: oos_sortino -1.17 < 1.0
    - WFA: frac_negative_folds 0.73 > 0.5
    - MC: P(ruin) = 0.908 >= 0.05
    - MC: 5th pct CAGR = -0.139 <= 0
    - MC: 95th pct max DD = -0.449 < -0.3
    - DSR: no positive Sharpe to deflate
========================================================================
