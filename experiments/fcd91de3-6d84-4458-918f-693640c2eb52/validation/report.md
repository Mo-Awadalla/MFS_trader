========================================================================
  Momentum v1 Validation Report
========================================================================
  Experiment UUID: fcd91de3-6d84-4458-918f-693640c2eb52
  Params: {'formation_lookback_days': 252, 'skip_recent_days': 21, 'liquidity_lookback_days': 20, 'min_history_days': 60, 'min_price': 5.0, 'min_median_dollar_volume': 20000000.0, 'min_eligible_symbols': 100, 'long_gross': 1.0, 'short_gross': 1.0}
  Research Sharpe: 0.8961
  Research total return: 0.7601
  Rebalances: 42
  Skipped rebalances: 13
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe 0.63 < 0.8
    - WFA: oos_sortino 1.00 < 1.0
    - MC: 5th pct CAGR = -0.060 <= 0
    - DSR: DSR p-value (M_eff_corr) = 0.0611 >= 0.05
    - Stability: isolated_peak_detected — best params not on a stable plateau
========================================================================
