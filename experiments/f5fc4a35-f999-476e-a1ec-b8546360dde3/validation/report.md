========================================================================
  VS-ICSM v1 Validation Report
========================================================================
  Experiment UUID: f5fc4a35-f999-476e-a1ec-b8546360dde3
  Params: {'momentum_lookback_bars': 6, 'volatility_lookback_bars': 13, 'atr_lookback_bars': 13, 'top_k': 15, 'universe_size': 200, 'transition_buffer_rank': 220, 'min_price': 5.0, 'price_lookback_sessions': 5, 'liquidity_lookback_sessions': 60, 'min_median_dollar_volume': 0.0, 'min_hourly_volume': 10000.0, 'min_history_sessions': 60, 'min_eligible_symbols': 15, 'gross_exposure': 0.98, 'max_position_weight': 0.15, 'trailing_stop_atr_multiple': 3.0, 'max_holding_bars': 39}
  Research Sharpe: 0.3239
  Research total return: 1.7191
  Rebalances: 19833
  Skipped rebalances: 19832
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe 0.39 < 0.8
    - WFA: oos_sortino 0.54 < 1.0
    - Stability: isolated_peak_detected — best params not on a stable plateau
========================================================================
