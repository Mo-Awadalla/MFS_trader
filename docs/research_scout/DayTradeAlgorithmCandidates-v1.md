# Day-Trade Algorithm Candidates v1

Generated: 2026-07-07T00:39:24Z

Purpose: preserve source-backed intraday/day-trading candidate ideas before implementation. These are candidate hypotheses only. They are not trading approval, not paper-ops approval, and not permission to tune after seeing results.

## Selection discipline

- Use liquid ETFs or liquid large caps only.
- Prefer 30-minute regular-session bars before anything lower frequency-sensitive.
- No same-bar execution.
- Strict flat-by-close for day-trade Experiments.
- Long-only v1 unless shorting is explicitly predeclared as a separate Experiment.
- Freeze universe, windows, entry, exit, costs, and validation gates before first backtest.
- Any failed scout or Experiment is terminal for that exact frozen rule.

## Prioritized candidates

### 1. Opening Range Breakout on liquid ETFs

Source basis:

- Ulf Holmberg, Carl Lonnback, Christian Lundstrom, "Assessing the profitability of intraday opening range breakout strategies", Finance Research Letters, 2013. DOI: 10.1016/j.frl.2012.09.001
- Yi-Cheng Tsai, Mu-En Wu, Jia-Hao Syu, Chin-Laung Lei, "Assessing the Profitability of Timely Opening Range Breakout on Index Futures Markets", IEEE Access, 2019. DOI: 10.1109/access.2019.2899177

Frozen rule shape to test first:

- Universe: SPY, QQQ, IWM.
- Bars: 30-minute regular-session bars.
- Opening range: first hour / first two 30-minute bars.
- Long-only v1: if a later 30-minute bar closes above the opening-range high, enter long next bar.
- One open long per symbol per day; exit before close; no overnight exposure.
- No stop, target, range-length tuning, buffer tuning, or symbol switching after results.

Fit: strongest first implementation candidate because it is native day-trading, simple, and compatible with existing intraday validation gates.

Main risks: false breakouts, spread/slippage, parameter-shopping temptation, ETF/futures proxy mismatch.

### 2. Same-clock intraday seasonality

Source basis:

- Heston, Korajczyk, Sadka, "Intraday Patterns in the Cross-Section of Stock Returns", Journal of Finance, 2010. DOI: 10.1111/j.1540-6261.2010.01573.x

Frozen rule shape:

- Universe: liquid ETFs such as SPY, QQQ, IWM, DIA, XLK, XLF, XLE, XLV, XLY, XLP.
- For each ETF and 30-minute clock slot, compute the prior 20-session average same-slot return.
- If the same-slot prior mean is positive, hold long for that clock slot today, then exit.
- Include all regular-session slots in the frozen bundle; do not select only winning slots after results.

Fit: many observations, no news/options/order-book dependency, distinct from the failed SPY first-hour scout.

Main risks: high turnover and costs; hidden data snooping if slots are filtered after seeing results.

### 3. Overnight loser open-to-close reversal

Source basis:

- Dong Lou, Christopher Polk, Spyros Skouras, "A tug of war: Overnight versus intraday expected returns", Journal of Financial Economics, 2019. DOI: 10.1016/j.jfineco.2019.03.011
- Vincent Bogousslavsky, "The cross-section of intraday and overnight returns", Journal of Financial Economics, 2021. DOI: 10.1016/j.jfineco.2020.07.020

Frozen rule shape:

- Signal at regular-session open: today open / prior close - 1.
- Long-only v1: buy the worst overnight losers among liquid ETFs or a predeclared liquid large-cap universe.
- Exit same day at close.
- Shorts require a separate source memo and Experiment.

Fit: clean day-trade boundary, can use daily open/close plus intraday execution bars.

Main risks: overnight gaps often reflect real news; open execution is noisy; stock version needs survivorship controls.

### 4. Intraday ETF pairs mean reversion

Source basis:

- Gatev, Goetzmann, Rouwenhorst, "Pairs Trading: Performance of a Relative-Value Arbitrage Rule", Review of Financial Studies, 2006. DOI: 10.1093/rfs/hhj020
- Marco Avellaneda, Jeong-Hyun Lee, "Statistical arbitrage in the US equities market", Quantitative Finance, 2010. DOI: 10.1080/14697680903124632

Frozen rule shape:

- Predeclare economically related ETF pairs before testing, e.g. QQQ/XLK, SPY/DIA, XLF/KRE, XLE/XOP, IWM/IWN.
- Estimate spread from prior sessions only.
- Enter dollar-neutral when spread z-score breaches the frozen threshold.
- Exit on mean reversion or before close.

Fit: repo already has pairs/stat-arb concepts and alpha-sleeve validation logic.

Main risks: shorting/borrow assumptions, ETF pair efficiency, pair-selection data mining.

### 5. Sector/market lead-lag continuation

Source basis:

- Chordia, Swaminathan, "Trading Volume and Cross-Autocorrelations in Stock Returns", Journal of Finance, 2000. DOI: 10.1111/0022-1082.00231
- Hou, "Industry Information Diffusion and the Lead-lag Effect in Stock Returns", Review of Financial Studies, 2007. DOI: 10.1093/revfin/hhm003

Frozen rule shape:

- Universe: SPY plus sector ETFs XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLU, XLB.
- If SPY's prior 30-minute return is positive and a sector ETF lagged or was flat, buy that sector ETF next bar.
- Hold one 30-minute bar or until close.
- Long-only v1; sign-only rule; no threshold optimization.

Fit: medium-frequency information-diffusion test without news or low-latency data.

Main risks: may just be SPY beta; intraday ETF implementation differs from source setting.

### 6. Cross-sectional morning loser reversal

Source basis:

- Bruce Lehmann, "Fads, Martingales, and Market Efficiency", Quarterly Journal of Economics, 1990. DOI: 10.2307/2937816

Frozen rule shape:

- At 10:30 ET, rank open-to-10:30 returns.
- Long-only v1: buy the worst performers in a predeclared liquid ETF or large-cap universe.
- Exit before close.

Fit: diversified version of the failed single-ETF IBB morning-selloff scout.

Main risks: losers can be down for real news; stock implementation needs clean universe and cost controls.

### 7. Source-faithful market intraday momentum

Source basis:

- Gao, Han, Li, Zhou, "Market intraday momentum", Journal of Financial Economics, 2018. DOI: 10.1016/j.jfineco.2018.05.009
- Gao, Han, Zhou, "Intraday Momentum: The First Half-Hour Return Predicts the Last Half-Hour Return", SSRN, DOI: 10.2139/ssrn.2440866

Frozen rule shape:

- Universe: QQQ, IWM, and/or an equal-weight SPY/QQQ/IWM basket.
- If first 30-minute return is positive, buy for the final 30-minute bar; otherwise stay flat.
- Exit at close.

Fit: direct academic support and existing repo scaffolding.

Main risks: adjacent SPY scout already failed; edge is small and late-day slippage-sensitive. Treat as lower priority unless source-faithful retest is explicitly desired.

## Recommended implementation order

1. Opening Range Breakout on SPY/QQQ/IWM.
2. Same-clock intraday seasonality on liquid ETFs.
3. Overnight loser open-to-close reversal.

The first implementation target is `OpeningRangeBreakoutETF-v1`.
