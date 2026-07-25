# BTC Confirmed Short-Squeeze Continuation v1 — Research Plan

Date saved: 2026-07-24

Status: **proposed research plan; not implemented, preregistered, validated, or approved for paper/live trading**

## Objective

Test a selective, long-only BTC spot strategy that enters only after leveraged
shorts appear trapped and their forced exit appears to have begun.

The system evaluates the market twice daily and normally returns `NO TRADE`.
It does not trade an ordinary price breakout or unconditional momentum signal.

## Material hypothesis

The proposed sequence is:

1. Derivatives traders accumulate short exposure.
2. Funding, perpetual premium, and trader positioning become unusually bearish.
3. Open interest rises, but spot price does not fall materially, suggesting that
   the additional selling is being absorbed.
4. Spot then breaks upward while open interest contracts and taker buying
   increases.
5. The combination is consistent with shorts closing or being liquidated.
6. Forced covering, stops, and hedging adjustments may continue for several
   hours, creating a tradeable continuation after confirmation.

Open interest alone cannot identify which side is closing. The inference
therefore requires prior short crowding, upward price movement, falling open
interest, and aggressive buyer flow to agree.

## Relationship to prior repository evidence

This is not the failed Binance U.S.-session momentum rule, which relied mainly
on a price pattern at fixed clocks.

It is related to, but materially different from, the failed crowded-long unwind
scout:

- the prior scout attempted to anticipate a decline from elevated funding and
  rising open interest;
- this candidate is long-only and waits until a short squeeze and leverage
  contraction are already observable;
- it trades continuation of a confirmed deleveraging transition rather than
  predicting a reversal from crowding alone.

This candidate must nevertheless be counted as a new trial in the broader
leverage-unwind family when correcting for multiple testing. It must not reuse
or tune thresholds based on the prior strategy's realized returns.

## Available repository data

Primary normalized sources:

- `data/parquet/bitcoin_5m_probability_binance_v1/bars_5m.parquet`
- `data/parquet/binance_bitcoin_derivatives_public_v1/normalized/futures_metrics_5m.parquet`
- `data/parquet/binance_bitcoin_derivatives_public_v1/normalized/futures_metrics_30m.parquet`
- `data/parquet/binance_bitcoin_derivatives_public_v1/normalized/funding_rate.parquet`
- `data/parquet/binance_bitcoin_derivatives_public_v1/normalized/premium_index_klines_30m.parquet`
- `data/parquet/binance_bitcoin_derivatives_public_v1/normalized/mark_price_klines_30m.parquet`
- `data/parquet/binance_bitcoin_derivatives_public_v1/normalized/index_price_klines_30m.parquet`
- `data/parquet/binance_bitcoin_derivatives_public_v1/normalized/perp_klines_30m.parquet`
- `data/parquet/binance_bitcoin_derivatives_public_v1/normalized/spot_klines_30m.parquet`

Available fields include spot and perpetual OHLCV, trade count, taker-buy
volume, open interest, several long/short ratios, funding, premium, mark price,
and index price. The common usable history is approximately September 2020
through December 2025.

Before implementation, audit timestamp semantics and ensure every feature is
restricted to observations fully available before the decision time.

## Decision schedule

Evaluate at:

- 00:25 UTC
- 12:25 UTC

Use only completed bars and already-settled funding observations. If a trade is
approved, enter at the next five-minute boundary. Permit at most one entry in
any rolling 24-hour period and never hold overlapping positions.

## Rolling normalization

Calculate feature percentiles and robust scales using only the preceding 180
calendar days. Do not use a full-sample scaler.

Where a z-score is needed, prefer a rolling median and median absolute
deviation over a mean and standard deviation. Missing or stale features cause
`NO TRADE`; they are not forward-filled across an unavailable decision point.

## Stage 1 — trapped-short setup

Require all of the following:

1. At least two of these three short-crowding measures are beyond their rolling
   70th crowding percentile:
   - unusually negative mean of the three latest already-settled funding rates;
   - unusually negative four-hour median perpetual premium;
   - unusually bearish trader long/short positioning.
2. Six-hour change in log open interest is above its rolling 70th percentile.
3. Six-hour spot return is greater than negative one-half of recent six-hour
   realized volatility.

The third condition means that new apparent short leverage has not produced a
commensurate price decline.

## Stage 2 — squeeze confirmation

During the most recent completed hour, require all of:

1. Spot return is above the rolling 75th percentile of positive one-hour
   returns.
2. Open-interest change is below its rolling 20th percentile, indicating a
   material contraction.
3. Taker-buy volume ratio is above its rolling 70th percentile.
4. The latest completed five-minute close is above the high of the preceding
   four hours, excluding the confirmation hour.

The intended state is:

```text
prior short crowding
+ leverage buildup without price decline
+ price rising
+ open interest falling
+ aggressive buyers dominating
= plausible forced short covering
```

## Stage 3 — abstaining analogue model

Passing the mechanical setup does not automatically authorize a trade.

Represent each twice-daily decision state with:

1. short-crowding score;
2. six-hour open-interest buildup;
3. price resistance to short pressure;
4. one-hour open-interest contraction;
5. taker-buy imbalance;
6. volatility expansion.

For each decision:

1. Normalize the state using trailing information only.
2. Find the 60 nearest prior decision states.
3. Exclude observations within the preceding 24 hours so overlapping outcomes
   are not treated as independent evidence.
4. Estimate the next six-hour gross spot-return distribution.
5. Bootstrap whole decision events, not individual five-minute bars.

Trade only if:

- at least 60 valid historical analogues exist;
- estimated mean gross return exceeds 60 basis points;
- the 80% bootstrap lower bound for mean gross return exceeds 40 basis points;
- estimated probability of finishing above the frozen 30-basis-point
  round-trip cost exceeds 60%;
- the five largest analogue outcomes do not dominate the estimate.

These are economic abstention hurdles. They must not be optimized for the
highest historical Sharpe. If they result in no trades, the candidate fails its
recurrence requirement.

## Instrument and execution

- Traded instrument: BTCUSDT spot.
- Direction: long only.
- Leverage: none.
- Entry: next five-minute boundary after the decision.
- Backtest entry price: next five-minute open plus the specified adverse
  execution cost.
- Maximum notional: 50% of account equity.
- Maximum risk per trade: 0.35% of account equity.
- Initial stop distance: 1.25 times trailing one-hour ATR.
- If risk-based sizing requires more than 50% notional, cap at 50%.
- No profit target.
- Time exit: six hours after entry.
- A touched stop is modeled conservatively using five-minute OHLC.
- No averaging down, re-entry, or simultaneous position.

The live version must also reject a trade when quoted spread or available depth
violates a separately frozen execution limit. Historical results must not claim
to test that gate unless suitable historical quote/depth data exists.

## Cost assumptions

- Ordinary round-trip cost: 30 basis points.
- Stress round-trip cost: 50 basis points.
- Report gross returns separately from fees and slippage.
- Do not substitute maker fees without historical fill evidence.
- Do not lower costs after observing a failed result.

## Proposed partitions

- Development: 2020-09-01 through 2022-12-31
- Internal validation: 2023-01-01 through 2023-12-31
- Final holdout: 2024-01-01 through 2025-12-31

The data has been used by other repository hypotheses, so this is not a
repository-wide pristine holdout. The new rule and its outcomes have not yet
been evaluated. Register the trial and account for all related prior attempts
when applying DSR or another multiple-testing correction.

Do not open a later partition unless every gate in the preceding partition
passes.

## Development gates

All gates are conjunctive:

- at least 50 completed trades;
- positive mean return after the 30-basis-point cost;
- positive net expectancy in both chronological halves;
- event-bootstrap lower confidence bound above zero;
- net profit factor above 1.20;
- largest 5% of profitable trades contribute no more than 40% of total profit;
- positive mean return after the 50-basis-point stress cost;
- no timestamp leakage or same-bar signal execution;
- no year or single short interval accounts for the entire result.

## Internal-validation gates

In addition to repeating the applicable development gates:

- at least 15 completed trades in 2023;
- no threshold changes, refitting choices, feature additions, or clock changes;
- positive net expectancy under both ordinary and stress costs;
- acceptable calibration of the analogue probability estimate;
- no material degradation caused by a small number of extreme trades.

Zero or insufficient validation opportunities is a recurrence failure, not a
pass.

## Required diagnostics

Report:

- candidate counts after each stage;
- gross and net expectancy per trade;
- compounded equity and maximum drawdown;
- hit rate, payoff ratio, and profit factor;
- maximum adverse and favorable excursion;
- results by year, decision clock, and chronological half;
- turnover and cost decomposition;
- analogue distances and effective sample size;
- bootstrap intervals;
- top-outcome concentration and trimmed results;
- sensitivity to 20, 30, and 50 basis points of round-trip cost;
- feature availability and timestamp-alignment audit;
- comparison against unconditional six-hour BTC returns at the same clocks.

Sensitivity rows are diagnostics only. They do not authorize selecting a better
threshold after seeing results.

## Frozen stopping rules

If development fails, do not rescue the consumed sample by:

- changing percentile thresholds;
- adding RSI, MACD, Bollinger, volume, weekday, or session filters;
- changing the two decision clocks;
- changing the six-hour horizon;
- adding a short side;
- using leverage;
- lowering costs;
- changing nearest-neighbour count or distance metric;
- removing losing years or adverse tail observations;
- opening validation or holdout data.

If the candidate fails, a successor must introduce a materially new mechanism
or information source and be registered as a new trial.

## Implementation checklist

1. Audit schemas, timestamp meanings, missingness, and common history.
2. Write a machine-readable preregistration and hash it.
3. Implement point-in-time feature construction with unit tests.
4. Implement event alignment, analogue selection, embargo, and bootstrap tests.
5. Add explicit cost, stop, sizing, and next-bar execution tests.
6. Run only non-return feasibility checks needed to confirm event count and data
   availability.
7. Freeze the final specification before computing development outcomes.
8. Run development once and emit immutable machine and human reports.
9. Enforce progression locks for validation and holdout.

## Research interpretation

This plan is a hypothesis, not a profitability claim. Its appeal is that it
combines technical confirmation with a potential forced-flow mechanism and a
formal abstention rule. Its principal risks are rare-event overfitting,
venue-specific positioning data, regime dependence, execution cost, and an
incorrect inference about which side is closing when open interest falls.

