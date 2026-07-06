# GlobalDualMomentumDefensive-v1

Status: predeclared candidate before implementation/validation

## Source basis

- Gary Antonacci, "Risk Premia Harvesting Through Momentum", SSRN, 2012. DOI: https://doi.org/10.2139/ssrn.2042750
- Mebane T. Faber, "A Quantitative Approach to Tactical Asset Allocation", Journal of Wealth Management, 2007. DOI: https://doi.org/10.3905/jwm.2007.674809
- Tobias J. Moskowitz, Yao Hua Ooi, Lasse Heje Pedersen, "Time Series Momentum", Journal of Financial Economics, 2012. DOI: https://doi.org/10.1016/j.jfineco.2011.11.003

## Frozen hypothesis

A simple monthly dual-momentum rule can avoid weak equity regimes by holding the strongest risk ETF only when its own 12-month absolute momentum is positive; otherwise it rotates into the strongest defensive Treasury/cash ETF. This should improve downside consistency versus always holding a diversified top-N trend basket.

## Frozen universe

Risk assets:

- SPY
- QQQ
- IWM
- EFA
- EEM

Defensive assets:

- IEF
- TLT
- SHY

No GLD in v1. No post-result universe edits.

## Frozen canonical rules

- Bar frequency: daily OHLCV.
- Rebalance frequency: monthly, first trading session of each month.
- Signal formation: all signal inputs use data strictly before the rebalance timestamp.
- Momentum score: 252-trading-day close-to-close return.
- Risk-on rule: rank risk assets by 252-day return. If the best risk asset has positive 252-day return and passes tradability checks, hold only that asset at 100% target weight.
- Risk-off rule: if no eligible risk asset has positive 252-day return, rank defensive assets by 252-day return and hold the strongest eligible defensive asset at 100% target weight.
- If neither risk nor defensive assets are eligible, hold cash.
- Long-only.
- No shorts.
- No volatility targeting in v1.
- No inverse-vol weighting in v1.
- Costs/slippage: use the repo validation pipeline cost/slippage model; do not relax after results.

## Frozen default parameters

- momentum_lookback_days = 252
- liquidity_lookback_days = 20
- min_history_days = 252
- min_price = 5.0
- min_median_dollar_volume = 5_000_000.0
- top_risk_n = 1
- defensive_n = 1
- target_gross = 1.0

## Predeclared stability grid

This grid is for robustness/stability only, not selection after seeing validation results:

1. default parameters above
2. momentum_lookback_days = 189
3. momentum_lookback_days = 252, top_risk_n = 2, target_gross split equally across top positive risk assets
4. momentum_lookback_days = 189, top_risk_n = 2, target_gross split equally across top positive risk assets

The canonical Experiment uses the default parameters. If the canonical row fails, do not switch to another grid row; create a new source memo and Experiment only if there is a genuinely new predeclared hypothesis.

## Falsification criteria

The candidate is not eligible for paper ops unless the frozen Experiment passes the repo Validation Gauntlet: WFA, Monte Carlo, DSR, and stability. Any failure is terminal for that Experiment.
