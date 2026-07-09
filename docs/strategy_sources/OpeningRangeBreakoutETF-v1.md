# OpeningRangeBreakoutETF-v1

Status: predeclared candidate before implementation/validation

## Source basis

- Ulf Holmberg, Carl Lonnback, Christian Lundstrom, "Assessing the profitability of intraday opening range breakout strategies", Finance Research Letters, 2013. DOI: https://doi.org/10.1016/j.frl.2012.09.001
- Yi-Cheng Tsai, Mu-En Wu, Jia-Hao Syu, Chin-Laung Lei, "Assessing the Profitability of Timely Opening Range Breakout on Index Futures Markets", IEEE Access, 2019. DOI: https://doi.org/10.1109/access.2019.2899177

## Frozen hypothesis

For liquid US index ETFs, a break above the first-hour regular-session range can mark same-day continuation pressure. A long-only strategy that waits for a 30-minute close above the opening-range high, enters no earlier than the next 30-minute bar, and exits before the close can produce positive out-of-sample risk-adjusted returns after conservative ETF trading costs.

This is an ETF proxy for opening-range breakout research, not futures evidence. If it fails, do not claim the futures literature failed; only this ETF proxy Experiment failed.

## Frozen universe

- SPY
- QQQ
- IWM

No post-result symbol additions, substitutions, or sector expansion. A sector ETF ORB variant requires a new source memo and Experiment.

## Frozen data plan

- Bar frequency: 30-minute regular-session OHLCV bars.
- Preferred source: Alpaca SIP adjusted 30-minute bars.
- Storage: `data/parquet/opening_range_breakout/alpaca_sip/*_30min.parquet`.
- Required synchronized panel: all three ETFs must have complete regular-session bars for a timestamp; missing bars block validation rather than being silently forward-filled.
- Regular session only, expected 13 bars/session for US equities.

## Frozen canonical rules

- Opening range window: first two regular-session 30-minute bars, approximately 09:30-10:30 ET.
- Signal formation: opening-range high is the max high across those first two bars.
- Breakout signal: after the opening range is complete, if a later 30-minute bar closes above the opening-range high, that ETF becomes eligible for a long position.
- Execution: no same-bar execution; target weights written on the breakout signal bar are held from the next bar by the shared vectorized backtester.
- Re-entry: once an ETF has triggered during a session, it remains long until the flat-by-close exit; no repeated entries for the same symbol in the same session.
- Exit: write zero target weights before the final regular-session bar so the strategy is flat by close and carries no overnight exposure.
- Shorts: none.
- Stops/targets: none in v1. Do not add stop-loss, take-profit, ATR filters, volume filters beyond frozen eligibility, or breakout buffers after seeing results.
- Costs/slippage: use conservative intraday ETF cost/slippage assumptions in the validation pipeline; do not relax costs after results.

## Frozen default parameters

- bars_per_session = 13
- opening_range_bars = 2
- exit_before_close_bars = 1
- breakout_buffer_pct = 0.0
- min_price = 5.0
- min_opening_range_volume = 100_000.0
- max_gross = 1.0
- max_symbol_weight = 0.50
- allow_short = false

## Predeclared stability grid

No tuning grid in v1. The first test uses the single canonical configuration above. A different opening range length, breakout buffer, stop/target, universe, or short side is a new hypothesis and must be predeclared separately before implementation.

## Falsification criteria

The candidate is not eligible for paper ops unless the frozen Experiment passes:

1. Standard Validation Gauntlet: WFA, Monte Carlo, DSR, and stability/no-tuning checks.
2. Intraday gates: session-aware validation, flat-by-close, maximum holding period, minimum trades/sessions, max trades/session, turnover/session, day-level profit concentration, positive expectancy/profit factor after costs, and no short exposure.
3. SPY comparison: report SPY buy-and-hold over the same dates. If the strategy is long-only, it needs higher CAGR, materially lower drawdown for similar return, higher Sharpe with useful drawdown reduction, or demonstrated portfolio utility as a SPY blend before paper-ops discussion.

Any failure is terminal for this exact Experiment. Do not rescue by changing windows, symbols, thresholds, exits, or costs after seeing results.
