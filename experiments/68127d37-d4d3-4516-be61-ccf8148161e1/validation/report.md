============================================================
  BB Validation Report: AAPL 1d
============================================================
  Params: {'window': 20, 'std_mult': 2.0, 'width_percentile_low': 25, 'width_percentile_high': 75, 'width_mode': 'normal', 'width_lookback': 252, 'long_only': True, 'mean_reversion': True}
  Research Sharpe: 0.5609
  Research trades: 15
  Sweep rows: 189
  Gauntlet passed: False
  Failures:
    - WFA: oos_sharpe -0.03 < 0.8
    - WFA: oos_sortino 0.01 < 1.0
    - WFA: single fold contributes 100% of profit > 60%
    - MC: 5th pct CAGR = -0.053 <= 0
    - DSR: DSR p-value (M_eff_corr) = 0.1364 >= 0.05
    - DSR: DSR collapses under M_raw: p = 0.9689 >= 0.10
    - Stability: plateau_within_pct 0.69 < required 0.70
============================================================
