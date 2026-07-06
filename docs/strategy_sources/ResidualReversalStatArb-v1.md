# ResidualReversalStatArb-v1

Status: predeclared candidate before implementation/validation

## Source basis

- Narasimhan Jegadeesh, "Evidence of Predictable Behavior of Security Returns", Journal of Finance, 1990. DOI: https://doi.org/10.1111/j.1540-6261.1990.tb05110.x
- Bruce Lehmann, "Fads, Martingales, and Market Efficiency", Quarterly Journal of Economics, 1990. DOI: https://doi.org/10.2307/2937816
- Andrew W. Lo and A. Craig MacKinlay, "When Are Contrarian Profits Due to Stock Market Overreaction?", Review of Financial Studies, 1990. DOI: https://doi.org/10.1093/rfs/3.2.175
- Marco Avellaneda and Jeong-Hyun Lee, "Statistical arbitrage in the US equities market", Quantitative Finance, 2010. DOI: https://doi.org/10.1080/14697680903124632

## Frozen hypothesis

Recent idiosyncratic residual losers revert relative to recent idiosyncratic residual winners after common market/factor movement is removed. A daily dollar-neutral long/short portfolio formed from liquid US equities can produce positive low-beta returns after costs and improve a SPY-plus-strategy blend.

## Frozen universe

Use the bounded Alpaca daily US equity parquet files already present in the repo for first validation.

- Include liquid common-stock symbols in `data/parquet/equity/alpaca/*_1d.parquet`.
- Use factor ETFs only as regression factors, not tradable strategy legs.
- Factor symbols: SPY, QQQ, IWM when present.
- No post-result universe expansion or deletion.

## Frozen canonical rules

- Bar frequency: daily OHLCV.
- Rebalance frequency: daily.
- Signal formation: all inputs use data strictly before the rebalance timestamp.
- Factor model: rolling OLS of each stock's daily returns on available SPY, QQQ, and IWM daily returns.
- Regression lookback: 60 trading days.
- Minimum regression observations: 45.
- Residual score: latest residual return divided by trailing 20-day residual volatility.
- Eligibility: price >= 5, trailing 20-day median dollar volume >= 20,000,000, minimum 120 days of history, finite residual score.
- Minimum eligible symbols: 60.
- Selection: long the 10 most negative residual scores and short the 10 most positive residual scores.
- Weights: equal-weight per side, long gross 100%, short gross 100%, maximum symbol weight 10%.
- Execution: no same-bar execution; target weights are held from the next bar by the shared vectorized backtester.
- Costs/slippage: use the repo validation pipeline cost/slippage model; do not relax after results.

## Frozen default parameters

- regression_lookback_days = 60
- residual_vol_lookback_days = 20
- liquidity_lookback_days = 20
- min_history_days = 120
- min_regression_obs = 45
- min_price = 5.0
- min_median_dollar_volume = 20_000_000.0
- min_eligible_symbols = 60
- selection_count = 10
- long_gross = 1.0
- short_gross = 1.0
- max_symbol_weight = 0.10
- factor_symbols = SPY, QQQ, IWM

## Predeclared stability grid

No tuning grid for v1. Adjacent lookbacks, thresholds, volatility scaling, sector neutralization, or alternative factor models require a new source memo and Experiment.

## Utility criteria

The candidate is not a SPY replacement. It only has practical utility if it behaves as a diversifying alpha sleeve.

Before paper ops, require the normal repo Validation Gauntlet plus a utility review:

- Strategy beta to SPY should be low in magnitude.
- Net Sharpe and total return should be positive after costs.
- A SPY + 20% strategy blend should improve Sharpe versus SPY alone without materially worsening drawdown.
- Results should survive conservative cost stress.
- Profits should not be dominated by a single month or tiny number of days.

## Falsification criteria

Any Validation Gauntlet failure is terminal for this Experiment. Do not rescue by changing lookbacks, factor symbols, selection count, liquidity threshold, cost model, or universe after seeing results.
