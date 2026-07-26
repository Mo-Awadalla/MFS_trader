# SameClockIntradaySeasonalityETF-v1

Status: predeclared candidate before implementation/validation

## Source basis

- Steven L. Heston, Robert A. Korajczyk, Ronnie Sadka, "Intraday Patterns in the Cross-Section of Stock Returns", Journal of Finance, 2010. DOI: https://doi.org/10.1111/j.1540-6261.2010.01573.x

## Frozen hypothesis

For liquid ETFs, recent returns in the same intraday clock slot can forecast returns in that same clock slot on later sessions. A long-only 30-minute ETF strategy that uses only prior-session same-clock returns, enters no earlier than the next executable bar, and exits before close can produce positive out-of-sample risk-adjusted returns after conservative ETF costs.

This is an ETF proxy for the intraday seasonal/recurrent-return source literature. If it fails, do not claim the original stock-level cross-sectional literature failed; only this ETF proxy Experiment failed.

## Frozen universe

- SPY
- QQQ
- IWM

No post-result symbol additions, sector expansion, slot filtering, or ETF substitutions. A broader sector-ETF version requires a new memo and Experiment.

## Frozen data plan

- Bar frequency: 30-minute regular-session OHLCV bars.
- Preferred source: Alpaca SIP adjusted 30-minute bars.
- Available first test may use the existing Alpaca IEX 30-minute cache, but must be labeled as IEX evidence.
- Storage target for this strategy: `data/parquet/same_clock_intraday_seasonality/alpaca_sip/*_30min.parquet`.
- Required synchronized panel: all three ETFs must have complete bars for a timestamp; missing bars block validation rather than being silently forward-filled.
- Regular session only, expected 13 bars/session.

## Frozen canonical rules

- Lookback: prior 20 completed sessions.
- Slot definition: regular-session 30-minute bar number within the trading day.
- Slot return estimate: for each ETF and slot, compute the average close-to-close return for that same slot over the prior 20 sessions only.
- Eligibility: if the prior-20-session same-clock mean return is positive, target a long position for that ETF for the next executable occurrence of that slot; otherwise stay flat for that ETF.
- Execution: no same-bar execution. Because the shared vectorized backtester applies target weights with a one-bar lag, the signal for slot `k` is written at slot `k-1` and earns the close-to-close return of slot `k`.
- Opening slot: skipped in v1 because entering the first regular-session bar without overnight exposure would require open execution support that this vectorized backtester does not provide.
- Closing slot: skipped in v1 so the strategy is flat on the final regular-session bar and carries no overnight exposure.
- Position sizing: equal weight across ETFs with positive same-clock signals, capped at max gross and max symbol weight.
- Shorts: none.
- Threshold tuning: none. Positive mean return is the only trigger.
- Slot filtering: none. All executable intraday slots between the skipped opening and skipped closing bar are included.
- Costs/slippage: use conservative intraday ETF cost/slippage assumptions in the validation pipeline; do not relax costs after results.

## Frozen default parameters

- bars_per_session = 13
- lookback_sessions = 20
- min_same_clock_mean_return = 0.0
- skip_opening_bars = 1
- exit_before_close_bars = 1
- min_price = 5.0
- min_bar_volume = 100_000.0
- max_gross = 1.0
- max_symbol_weight = 0.50
- allow_short = false

## Predeclared stability grid

No tuning grid in v1. The first test uses the single canonical configuration above. Different lookbacks, slot subsets, thresholds, opening-slot handling, sector universes, or shorting are new hypotheses and must be predeclared separately before implementation.

## Falsification criteria

The candidate is not eligible for paper ops unless the frozen Experiment passes:

1. Standard Validation Gauntlet: WFA, Monte Carlo, DSR, and stability/no-tuning checks.
2. Intraday gates: session-aware validation, flat-by-close, maximum holding period, minimum trades/sessions, max trades/session, turnover/session, day-level profit concentration, positive expectancy/profit factor after costs, and no short exposure.
3. SPY comparison: report SPY buy-and-hold over the same synchronized dates. If the strategy is long-only, it needs higher CAGR, materially lower drawdown for similar return, higher Sharpe with useful drawdown reduction, or demonstrated SPY blend utility before paper-ops discussion.

Any failure is terminal for this exact Experiment. Do not rescue by changing lookback, tradable slots, symbols, thresholds, exits, or costs after seeing results.
