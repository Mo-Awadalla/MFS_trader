========================================================================
  Pairs v1 Validation Report
========================================================================
  Experiment UUID: f034ab13-523c-402d-9425-9ef9234add26
  Params: {'candidate_pool_size': 150, 'formation_window_days': 252, 'liquidity_lookback_days': 20, 'min_history_days': 60, 'min_eligible_universe': 100, 'min_price': 5.0, 'min_median_dollar_volume': 20000000.0, 'coint_pvalue_threshold': 0.05, 'entry_zscore': 2.0, 'exit_zscore': 0.5, 'stop_zscore': 4.0, 'max_holding_days': 60, 'max_active_pairs': 20, 'one_active_position_per_symbol': True, 'equal_gross_budget_per_pair': True}
  Research Sharpe: 0.0000
  Research total return: 0.0000
  Rebalances: 72
  Skipped rebalances: 72
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe 0.00 < 0.8
    - WFA: oos_sortino 0.00 < 1.0
    - MC: 5th pct CAGR = 0.000 <= 0
    - DSR: no positive Sharpe to deflate
========================================================================
