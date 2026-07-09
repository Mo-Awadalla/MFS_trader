========================================================================
  Opening Range Breakout ETF v1 Validation Report
========================================================================
  Experiment UUID: b561f4a3-d360-4e1e-b663-a81a54e63375
  Params: {'bars_per_session': 13, 'opening_range_bars': 2, 'exit_before_close_bars': 1, 'breakout_buffer_pct': 0.0, 'min_price': 5.0, 'min_opening_range_volume': 100000.0, 'max_gross': 1.0, 'max_symbol_weight': 0.5, 'allow_short': False}
  Research Sharpe: -1.8083
  Research total return: -0.4700
  Rebalances: 17825
  Skipped rebalances: 2
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe -0.49 < 0.8
    - WFA: oos_sortino -1.57 < 1.0
    - WFA: frac_negative_folds 0.81 > 0.5
    - MC: P(ruin) = 0.993 >= 0.05
    - MC: 5th pct CAGR = -0.012 <= 0
    - MC: 95th pct max DD = -0.572 < -0.2
    - DSR: no positive Sharpe to deflate
========================================================================
Intraday gates:
  passed: True
  metrics: {'trading_sessions': 1376, 'trade_count': 3249, 'max_single_session_profit_share': 0.03418338390132245, 'max_trades_per_session': 8, 'max_turnover_per_session': 2.6666666666666665, 'exposure_fraction': 0.3200561009817672, 'max_abs_exposure': 1.0, 'has_short_exposure': False, 'flat_by_session_close': True, 'max_holding_period_bars': 9, 'profit_factor': 1.278415334333496, 'expectancy_per_trade': 5.012193420419962e-05}
