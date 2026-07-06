# ResidualReversalStatArb-v1-LiquidLargeCapDaily-AlpacaSIP

Status: predeclared internal candidate before first validation run.

## Hypothesis

Recent idiosyncratic residual losers revert relative to recent idiosyncratic residual winners after common market/factor movement is removed. A daily dollar-neutral long/short portfolio formed from a fixed liquid large-cap US equity universe can produce positive low-beta returns after costs and can improve a SPY-plus-strategy blend.

## Source basis

- Narasimhan Jegadeesh, "Evidence of Predictable Behavior of Security Returns", Journal of Finance, 1990. DOI: https://doi.org/10.1111/j.1540-6261.1990.tb05110.x
- Bruce Lehmann, "Fads, Martingales, and Market Efficiency", Quarterly Journal of Economics, 1990. DOI: https://doi.org/10.2307/2937816
- Andrew W. Lo and A. Craig MacKinlay, "When Are Contrarian Profits Due to Stock Market Overreaction?", Review of Financial Studies, 1990. DOI: https://doi.org/10.1093/rfs/3.2.175
- Marco Avellaneda and Jeong-Hyun Lee, "Statistical arbitrage in the US equities market", Quantitative Finance, 2010. DOI: https://doi.org/10.1080/14697680903124632
- Stefan Nagel, "Evaporating Liquidity", Review of Financial Studies, 2012. DOI: https://doi.org/10.1093/rfs/hhs066

## Frozen data plan

- Data source: Alpaca SIP adjusted daily bars.
- Date range: 2018-01-01 through latest available cached bar at validation time.
- Storage: `data/parquet/equity/alpaca_sip/*_1d.parquet`.
- Universe: fixed symbols in `research/universes/residual_reversal_v1.py`.
- Factor symbols: SPY, QQQ, IWM.
- Caveat: this is a current-liquid-large-cap internal universe and is not survivorship-bias-free. A pass here only justifies deeper validation with better historical universe data.

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

## Falsification discipline

Any Validation Gauntlet failure is terminal for this exact experiment. Do not rescue by changing lookbacks, factor symbols, selection count, liquidity threshold, cost model, or universe after seeing results. Adjacent configurations require a new source memo before implementation.

## Post-validation cost and turnover lesson

Experiment `886f5819-9b51-4ff8-b025-11fbdd8dd06a` failed and is not paper-trade eligible. The catastrophic final equity (`$10,000` to about `$3.02`) should not be read as pure anti-alpha. It was mostly the compounding of extreme turnover under the repo default cost model.

Measured decomposition from the run:

- Trading days: `2,136`.
- Trades: `69,388`, about `32.5` changed symbol weights per day.
- Average daily turnover: `3.4216x` equity.
- Average gross signal return before costs: `-0.9079` bps/day.
- Repo default average daily cost drag: `36.3887` bps/day.
- Daily loss needed to turn `$10,000` into `$3.02` over the run: about `-37.87` bps/day.

Cost sensitivity showed the underlying signal was weak but not `$3`-bad on its own:

- `0` bps per dollar traded: final equity about `$7,295.81`, Sharpe `-0.1351`.
- `0.5` bps per dollar traded: final equity about `$5,062.03`, Sharpe `-0.3896`.
- `1` bps per dollar traded: final equity about `$3,511.94`, Sharpe `-0.6441`.
- `2` bps per dollar traded: final equity about `$1,690.07`, Sharpe `-1.1530`.
- `5` bps per dollar traded: final equity about `$188.05`, Sharpe `-2.6786`.
- `10` bps per dollar traded: final equity about `$4.81`, Sharpe `-5.2104`.
- Repo default cost model: final equity about `$3.02`, Sharpe `-5.5304`.

Conclusion for this exact hypothesis: weak/slightly negative signal plus extreme daily turnover plus punitive/default costs. Do not tune or paper trade this experiment. Future high-turnover validations must report gross-before-cost returns, explicit cost drag, borrow drag, average turnover, cost sensitivity, Rank IC, and same-day versus next-bar alignment before anyone interprets headline final equity.

See `docs/adr/0004-decompose-turnover-cost-drag-before-strategy-verdicts.md` for the general repo rule.
