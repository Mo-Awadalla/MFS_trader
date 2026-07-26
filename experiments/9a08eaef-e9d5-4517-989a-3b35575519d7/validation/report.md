========================================================================
  Same-Clock Intraday Seasonality ETF v1 Validation Report
========================================================================
  Experiment UUID: 9a08eaef-e9d5-4517-989a-3b35575519d7
  Params: {'bars_per_session': 13, 'lookback_sessions': 20, 'min_same_clock_mean_return': 0.0, 'skip_opening_bars': 1, 'exit_before_close_bars': 1, 'min_price': 5.0, 'min_bar_volume': 100000.0, 'max_gross': 1.0, 'max_symbol_weight': 0.5, 'allow_short': False}
  Research Sharpe: -5.0944
  Research total return: -0.7468
  Rebalances: 17825
  Skipped rebalances: 222
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe -1.51 < 0.8
    - WFA: oos_sortino -4.34 < 1.0
    - WFA: frac_negative_folds 0.98 > 0.5
    - WFA: single fold contributes 100% of profit > 60%
    - MC: P(ruin) = 1.000 >= 0.05
    - MC: 5th pct CAGR = -0.023 <= 0
    - MC: 95th pct max DD = -0.907 < -0.2
    - DSR: no positive Sharpe to deflate
    - Intraday: max_trades_per_session 25 > 20
    - Intraday: max_turnover_per_session 9.00 > 8.00
    - Intraday: max_holding_period_bars 5 > 1
    - Intraday: profit_factor 0.97 < 1.05
    - Intraday: expectancy_per_trade -0.000009 < 0.000000
========================================================================
Intraday gates:
  passed: False
  metrics: {'trading_sessions': 1376, 'trade_count': 4261, 'max_single_session_profit_share': 0.037106867957284184, 'max_trades_per_session': 25, 'max_turnover_per_session': 9.0, 'exposure_fraction': 0.1164656381486676, 'max_abs_exposure': 1.0, 'has_short_exposure': False, 'flat_by_session_close': True, 'max_holding_period_bars': 5, 'profit_factor': 0.9704536487925678, 'expectancy_per_trade': -9.393831503366378e-06}
  failures:
    - max_trades_per_session 25 > 20
    - max_turnover_per_session 9.00 > 8.00
    - max_holding_period_bars 5 > 1
    - profit_factor 0.97 < 1.05
    - expectancy_per_trade -0.000009 < 0.000000
