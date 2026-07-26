========================================================================
  Global Dual Momentum Defensive v1 Validation Report
========================================================================
  Experiment UUID: 33e52c7b-fd04-4679-8125-17aec1d3063d
  Params: {'momentum_lookback_days': 252, 'liquidity_lookback_days': 20, 'min_history_days': 252, 'min_price': 5.0, 'min_median_dollar_volume': 5000000.0, 'top_risk_n': 1, 'defensive_n': 1, 'target_gross': 1.0}
  Research Sharpe: 0.6311
  Research total return: 0.7217
  Rebalances: 73
  Skipped rebalances: 14
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe 0.59 < 0.8
    - WFA: oos_sortino 0.88 < 1.0
    - DSR: DSR collapses under M_raw: p = 0.2797 >= 0.10
========================================================================
