# Alpaca IEX Order-Flow Scout — development

Verdict: **FAIL**

This is a frozen venue-local information-content scout, not a Strategy or executable P&L claim.

- Valid rows: 792
- Selected rows: 370
- Mean signed midpoint return: -11.4183 bps
- Directional accuracy: 0.4622
- Mean IEX crossing return: -39.9389 bps
- Mean IEX crossing after extra friction: -41.9389 bps
- Session-block bootstrap 95% interval: [-21.8089, -2.1626] bps
- Trimmed mean: -10.8136 bps

## Gates

- PASS — minimum_selected_rows
- FAIL — minimum_mean_signed_midpoint_bps
- FAIL — bootstrap_lower_above_zero
- FAIL — positive_each_symbol
- FAIL — positive_after_top_5pct_sessions_removed
- FAIL — positive_iex_crossing_after_extra_friction

## By symbol

- IWM: n=130, midpoint=-7.2204 bps, net IEX=-30.3520 bps
- QQQ: n=134, midpoint=-22.0990 bps, net IEX=-43.8399 bps
- SPY: n=106, midpoint=-3.0647 bps, net IEX=-53.7460 bps

If the verdict is FAIL, the frozen stopping rule prohibits opening the next partition or trying nearby variants.
