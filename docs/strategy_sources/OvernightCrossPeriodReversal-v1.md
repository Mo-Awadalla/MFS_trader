# OvernightCrossPeriodReversal-v1

Status: predeclared hypothesis; not implemented, backtested, validated, or approved for paper operations.

## Research basis

- Dong Lou, Christopher Polk, Spyros Skouras, "A tug of war: Overnight versus intraday expected returns," Journal of Financial Economics, 2019. DOI: https://doi.org/10.1016/j.jfineco.2019.03.011
- Vincent Bogousslavsky, "The cross-section of intraday and overnight returns," Journal of Financial Economics, 2021. DOI: https://doi.org/10.1016/j.jfineco.2020.07.020

The source family studies the decomposition of stock returns into overnight and intraday components. Lou, Polk, and Skouras report firm-level continuation within the overnight and intraday components together with an offsetting cross-period reversal. Bogousslavsky studies the cross-section of the same components. These papers support testing the relationship; they do not prove that this exact portfolio will be profitable after current costs.

## Job

Active day-trading alpha sleeve.

This is not the repository's standalone SPY challenger. It is a flat-by-close, long-only day-trading candidate evaluated by after-cost expectancy, risk-adjusted return, capacity, and concentration. A day-trading sleeve is not expected to beat SPY's raw CAGR without an explicit capital-utilization or leverage comparison.

## Frozen hypothesis

Among liquid U.S. stocks, the stocks with the most negative overnight returns tend to earn positive same-session intraday returns relative to the stocks with less-negative or positive overnight returns. A long-only portfolio of the worst overnight losers, entered after the opening bar and exited before the close, can produce positive after-cost daily expectancy.

## Frozen universe

- Point-in-time historical S&P 500 constituents.
- Common stocks only.
- Historical identifiers and delisted securities must be retained.
- Prior-close price must be at least $5.
- Prior-20-session median dollar volume must be at least $20,000,000, calculated only from data available before the current session.
- A stock with a missing official open, missing execution bar, or incomplete session is ineligible for that session.
- No current-survivor-only universe.
- No post-result constituent substitutions.

The S&P 500 membership choice is a capacity and data constraint, not a claim that the cited papers used this exact index universe.

## Frozen signal and portfolio rules

- Overnight return for stock `i` on session `t`:

  `overnight_return[i,t] = official_open[i,t] / prior_regular_close[i,t] - 1`

- At the official regular-session open, rank eligible stocks by overnight return.
- Buy the bottom cross-sectional quintile, meaning the stocks with the most negative overnight returns.
- Equal-weight all eligible stocks in that bottom quintile.
- Maximum gross exposure is 1.0.
- No short positions.
- No market, sector, news, earnings, gap-size, relative-volume, VWAP, stop-loss, profit-target, or volatility filter in v1.
- No position is re-entered after its same-session exit.
- If the eligible universe or bottom quintile is empty, remain flat.

## Frozen execution rules

- Bar frequency: 5-minute regular-session OHLCV bars.
- The overnight signal uses the official opening price and is known only after the session opens.
- Entry: open of the next 5-minute bar after the opening bar; no same-bar execution.
- Exit: open of the final regular-session 5-minute bar, so the strategy is flat during the final bar and carries no overnight exposure.
- All target weights and trades must be shifted so that a signal cannot execute on the signal bar.
- No opening-auction fill assumption.
- No discretionary order handling.

## Frozen cost and accounting requirements

- Use the repository's conservative intraday spread/slippage model, with costs applied to every entry and exit.
- Report gross and net returns separately.
- Report round-trip cost drag, turnover, per-name ADV participation, daily trade count, and profit concentration by session.
- Do not reduce costs after observing results.
- The strategy must be evaluated with session-aware annualization and flat-by-close checks.

## Cheap falsification gates

Before the full validation gauntlet, the frozen mechanism must show:

1. Positive gross mean same-session return in the selected bottom quintile.
2. Positive gross spread versus the rest of the eligible universe.
3. Positive gross result in both chronological halves.
4. Positive net mean trade after the predeclared cost model.
5. No single stock, sector, session, or small group of sessions explains the result.
6. Sufficient eligible sessions and trades for the intraday validation gates.
7. No hidden overnight exposure or same-bar fills.

Failure of any gross expected-sign gate is terminal for this hypothesis. Do not rescue it with a different quintile, gap threshold, holding window, market filter, news filter, entry delay, or short side.

## Full validation gates

A cheap scout pass is not promotion. A full run must also pass the repository's WFA, Monte Carlo, DSR, stability, intraday annualization, session-aware split, profit-factor, trade-count, turnover, day-level concentration, and cost-stress gates.

The result must be reported against:

- zero-return cash for the flat-by-close sleeve;
- SPY buy-and-hold over identical dates for context;
- a risk-matched SPY comparison if the sleeve is evaluated as a portfolio component.

## Research priority after the repository audit

`StockOpeningDrive-v1` would combine overnight gap direction, first-window continuation, opening-range breakout, relative volume, and possibly market/sector confirmation. That is intuitive but has more discretionary degrees of freedom and is not a single source-faithful rule.

The repository already tested a simpler ETF opening-range breakout in `docs/strategy_sources/OpeningRangeBreakoutETF-v1.md` and its Experiment failed economically. A stock-level opening-drive version would therefore need to be justified as a materially different, separately predeclared hypothesis rather than a rescue of that result.

This candidate is cleaner to falsify than StockOpeningDrive, but it is still part of the reversal family. The repository's CSMR, residual-reversal, fundamental-event-reversal, and IBB recovery tests provide negative nearby evidence. The cited papers do not by themselves justify treating this as the next experiment.

Current priority: keep this specification archived as a candidate, but do not implement it as the immediate next day-trading run. Only reopen it after a bounded data audit demonstrates a materially different point-in-time stock universe, reliable official opens, and a cheap gross event study that is explicitly separated from the prior reversal results.

The only narrowly justified near-term rerun in the existing day-trading family is a source-faithful market-intraday-momentum replication using full-market SIP-quality bars, and only as a data-source question distinct from the failed Alpaca IEX Experiment. If that data distinction cannot be demonstrated, do not run another nearby intraday pattern.

## Explicit exclusions

- No ETF rotation.
- No overnight holding.
- No same-session news or earnings filter.
- No minute-level entry optimization.
- No parameter sweep.
- No shorting in v1.
- No claim that the cited papers validate this exact implementation.
