========================================================================
  Market Intraday Momentum v1 Validation Report
========================================================================
  Experiment UUID: 004c70b3-81d4-491c-87cf-9a4af22c8574
  Params: {'bars_per_session': 13, 'opening_signal_bars': 1, 'exit_before_close_bars': 1, 'min_opening_return': 0.0, 'min_price': 5.0, 'min_opening_bar_volume': 100000.0, 'max_gross': 1.0, 'max_symbol_weight': 0.5, 'allow_short': False}
  Research Sharpe: -0.4408
  Research total return: -0.1764
  Rebalances: 17825
  Skipped rebalances: 0
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe -0.11 < 0.8
    - WFA: oos_sortino -0.22 < 1.0
    - WFA: frac_negative_folds 0.59 > 0.5
    - MC: P(ruin) = 0.124 >= 0.05
    - MC: 5th pct CAGR = -0.006 <= 0
    - DSR: no positive Sharpe to deflate
    - Intraday: profit_factor 1.04 < 1.05
========================================================================
Intraday gates:
  passed: False
  metrics: {'trading_sessions': 1376, 'trade_count': 1674, 'max_single_session_profit_share': 0.07131331496364154, 'max_trades_per_session': 6, 'max_turnover_per_session': 2.0, 'exposure_fraction': 0.3570266479663394, 'max_abs_exposure': 1.0, 'has_short_exposure': False, 'flat_by_session_close': True, 'max_holding_period_bars': 11, 'profit_factor': 1.0367550843979576, 'expectancy_per_trade': 1.0978341721250591e-05}
  failures:
    - profit_factor 1.04 < 1.05
