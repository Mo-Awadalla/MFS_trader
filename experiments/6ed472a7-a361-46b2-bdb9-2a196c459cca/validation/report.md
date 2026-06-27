========================================================================
  CSMR v1 Validation Report
========================================================================
  Experiment UUID: 6ed472a7-a361-46b2-bdb9-2a196c459cca
  Params: {'lookback_days': 5, 'liquidity_lookback_days': 20, 'min_history_days': 60, 'min_price': 5.0, 'min_median_dollar_volume': 20000000.0, 'min_eligible_symbols': 100, 'long_gross': 1.0, 'short_gross': 1.0}
  Research Sharpe: -0.7804
  Research total return: -0.4294
  Rebalances: 182
  Skipped rebalances: 13
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe -0.93 < 0.8
    - WFA: oos_sortino -1.11 < 1.0
    - WFA: frac_negative_folds 0.83 > 0.5
    - WFA: single fold contributes 100% of profit > 60%
    - MC: P(ruin) = 0.136 >= 0.05
    - MC: 5th pct CAGR = -0.224 <= 0
    - DSR: no positive Sharpe to deflate
========================================================================
