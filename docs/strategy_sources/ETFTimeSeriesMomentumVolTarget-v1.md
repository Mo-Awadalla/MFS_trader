# ETFTimeSeriesMomentumVolTarget-v1

Status: predeclared candidate before implementation/validation

## Source basis

- Mebane T. Faber, "A Quantitative Approach to Tactical Asset Allocation", Journal of Wealth Management, 2007. DOI: https://doi.org/10.3905/jwm.2007.674809
- Tobias J. Moskowitz, Yao Hua Ooi, Lasse Heje Pedersen, "Time Series Momentum", Journal of Financial Economics, 2012. DOI: https://doi.org/10.1016/j.jfineco.2011.11.003
- Alan Moreira, Tyler Muir, "Volatility-Managed Portfolios", Journal of Finance, 2017. DOI: https://doi.org/10.1111/jofi.12513

## Frozen hypothesis

A small basket of liquid ETFs with positive 12-month absolute momentum will have persistent trend premia. Monthly rebalancing into the strongest positive-trend ETFs, inverse-volatility weighting, and trailing realized-volatility gross scaling should improve downside behavior versus fixed-gross ETF rotation.

## Frozen universe

Initial implementation uses the ETF daily bars already present in the repo unless missing symbols are explicitly downloaded before validation:

- SPY
- QQQ
- IWM
- IEF
- GLD
- DBC
- SHY

If additional history is downloaded before the first validation run, the universe may be expanded only before validation evidence is written, and the exact frozen universe must be recorded in the Experiment metadata. No post-result universe edits.

## Frozen rules

- Bar frequency: daily OHLCV.
- Rebalance frequency: monthly, first trading session of each month.
- Signal formation: all signal inputs use data strictly before the rebalance timestamp.
- Absolute momentum score: 252-trading-day close-to-close return.
- Eligibility: ETF is eligible only if its 252-day return is positive and it passes minimum history/liquidity/price checks.
- Selection: hold the top 3 eligible ETFs by absolute momentum score.
- Defensive fallback: if no ETF has positive absolute momentum, hold SHY if eligible; otherwise hold cash.
- Base weights: inverse 63-day realized-volatility weighting across selected ETFs.
- Single ETF cap: 50%.
- Gross target: 100%, then scale by realized volatility toward a 10% annualized volatility target using trailing 63-day portfolio volatility.
- Gross bounds: min 25%, max 100% when selected assets exist. Cash/SHY fallback may still be below full risk exposure if volatility scaling demands it.
- Shorts: none.
- Costs/slippage: use the repo validation pipeline cost/slippage model; do not relax after results.

## Frozen default parameters

- momentum_lookback_days = 252
- vol_lookback_days = 63
- min_history_days = 252
- liquidity_lookback_days = 20
- min_price = 5.0
- min_median_dollar_volume = 5_000_000.0
- min_eligible_symbols = 1
- top_n = 3
- fallback_symbol = SHY
- target_volatility_annual = 0.10
- min_gross = 0.25
- max_gross = 1.00
- max_symbol_weight = 0.50

## Predeclared stability grid

This grid is for robustness/stability only, not selection after seeing validation results:

1. default parameters above
2. momentum_lookback_days = 189, vol_lookback_days = 63
3. momentum_lookback_days = 252, vol_lookback_days = 126
4. top_n = 2, max_symbol_weight = 0.60

The canonical Experiment uses the default parameters. If the canonical row fails, do not switch to another grid row; create a new source memo and Experiment only if there is a genuinely new predeclared hypothesis.

## Falsification criteria

The candidate is not eligible for paper ops unless the frozen Experiment passes the repo Validation Gauntlet: WFA, Monte Carlo, DSR, and stability. Any failure is terminal for that Experiment.
