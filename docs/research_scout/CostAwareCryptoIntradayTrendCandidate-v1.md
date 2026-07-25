# Cost-Aware Crypto Intraday Trend Candidate v1

Date: 2026-07-20

Status: candidate-selection memo only. This is not a frozen Experiment, validated Strategy, paper candidate, live-trading authorization, or investment advice.

## Candidate conclusion

The most suitable several-trades-per-day crypto candidate for this repository is a cost-aware, volatility-scaled intraday trend/breakout strategy across a small universe of highly liquid Binance spot pairs.

The candidate deliberately avoids market making, latency arbitrage, unconstrained five-minute prediction, and multi-leg spot/perpetual execution. Those approaches either conflict with the repository's current data and execution capabilities or have already produced unfavorable local evidence.

## Intended behavior

- Initial research universe: BTC/USDT, ETH/USDT, SOL/USDT, and LTC/USDT, matching the current crypto configuration. A later point-in-time liquidity universe would be a separate specification.
- Raw data: one-minute Binance spot bars, resampled into synchronized 30-minute decision bars.
- Activity objective: approximately 2-8 portfolio-level executions or round-trip events per day across the universe; no activity quota may override the signal or cost hurdle.
- Position direction: long or flat for the first implementation because the current CCXT Binance adapter is spot-only.
- Expected holding period: approximately 2-8 hours, with no forced overnight boundary in the continuously traded crypto market.

## Proposed signal family

At each completed 30-minute bar:

1. Compute short- and medium-horizon time-series momentum, initially represented by 3-hour and 12-hour returns.
2. Normalize each momentum measure by lagged realized volatility, using information available before the decision.
3. Require both momentum horizons to be positive.
4. Require a breakout above a lagged 6-12-hour price range to avoid trading weak drift.
5. Admit an entry only when a development-period mapping from signal strength to subsequent return clears a predeclared all-in cost hurdle with a safety margin.

The exact horizons, breakout definition, estimator, cost multiplier, and decision timing must be frozen before development returns are inspected. The values above define the family, not permission to search every adjacent combination.

## Turnover controls

- Use a stronger threshold to enter than to remain invested.
- Enforce a minimum holding period and a cooldown after exits.
- Do not continuously rebalance small target changes.
- Require a minimum notional change before producing an order.
- Model taker execution as the conservative baseline even if paper execution later attempts maker/post-only limits.
- Treat unfilled maker orders and adverse selection as costs, not free execution.

## Portfolio and risk construction

- Scale positions inversely to lagged volatility.
- Apply a portfolio volatility target rather than equal nominal weights.
- Cap per-asset risk and total gross exposure.
- Treat the crypto universe as a correlated cluster and cap aggregate cluster exposure.
- Add stale-data, abnormal-spread, exchange-disconnect, and daily-loss entry blocks.
- No leverage in the first research implementation.

## Required comparisons

The candidate must be compared against:

- BTC buy-and-hold with matched starting capital;
- an equal-weight buy-and-hold basket over the same point-in-time universe;
- a simpler single-horizon trend rule;
- cash, including the effect of inactive capital;
- gross, maker-cost, taker-cost, and stressed-cost cases.

## Minimum evidence gates

Before paper consideration, the frozen Experiment should require:

- positive net expectancy under the conservative taker-plus-slippage model;
- sufficient independent trading days, not merely many correlated bars;
- positive net performance in multiple chronological regimes;
- walk-forward out-of-sample performance and parameter stability;
- day-level or week-level block-bootstrap uncertainty bounds;
- acceptable turnover, drawdown, tail loss, and profit concentration;
- performance that is not dominated by one coin or one market regime;
- explicit delisting, missing-bar, timestamp, and survivorship checks;
- a successful multi-asset scheduled engine replay with realistic order lifecycle behavior.

The activity target is descriptive, not a validation gate. A rule must not be loosened merely to manufacture several trades per day.

## Repository work required if research passes

1. Add a frozen strategy specification and immutable Experiment snapshot.
2. Build a synchronized multi-asset Binance research panel with point-in-time availability rules.
3. Implement conservative cost-aware backtesting and intraday validation units.
4. Add scheduled multi-asset intraday engine replay.
5. Strengthen the CCXT adapter's symbol-aware order-status cache, reconciliation, maker/post-only behavior, and partial-fill handling.
6. Demonstrate paper operations before any live-capital discussion.

## Evidence boundary

Repository results already reject the tested BTC U.S.-session close momentum rule, ordinary-account intraday spot/perpetual convergence, the frozen crowded-long unwind rule, and the frozen funding-carry implementation as deployable candidates. The existing five-minute BTC probability model also produced too little predictive improvement to establish executable alpha.

This proposal is therefore a new candidate family: multi-asset, cost-gated, volatility-scaled breakout/trend behavior. It must not reuse consumed samples to tune nearby variants of the rejected strategies.
