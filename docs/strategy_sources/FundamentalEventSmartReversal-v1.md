# FundamentalEventSmartReversal-v1 — SEC Material-Filing Veto

Status: frozen before event-data download and before any strategy result was observed.

## Objective

Test whether a cost-aware smart short-term reversal portfolio has positive post-cost, low-beta alpha-sleeve utility when recent moves associated with public fundamental filings are excluded. This is not a direct SPY replacement and is not authorized for paper or live trading.

## Source hypothesis

Short-horizon relative losers may rebound against relative winners when their moves reflect temporary liquidity pressure or sentiment rather than durable cash-flow news. Chan (2003) reports drift after public-news moves and reversal after no-news moves. Da, Liu, and Schaumburg (2014) report stronger reversal in returns unexplained by cash-flow news. De Groot, Huij, and Zhou (2012) report that rank-buffer exits can reduce reversal turnover.

Sources:

- Chan, “Stock Price Reaction to News and No-news,” JFE 2003, DOI `10.1016/S0304-405X(03)00146-6`.
- Da, Liu, and Schaumburg, “A Closer Look at the Short-Term Return Reversal,” Management Science 2014, DOI `10.1287/mnsc.2013.1766`.
- de Groot, Huij, and Zhou, “Another Look at Trading Costs and Short-Term Reversal Profits,” JBF 2012, DOI `10.1016/j.jbankfin.2011.07.015`.

## Important limitation of the fundamental check

This v1 does not claim to measure fundamental-news direction or sentiment. Free point-in-time analyst-estimate and historical-news data are unavailable in the repository. It uses a deliberately blunt, reproducible public-information proxy: a recent accepted SEC material filing veto. This can remove both justified moves and genuine overreactions.

## Frozen universe and data

- Static 133-stock liquid large-cap universe from `research/universes/residual_reversal_v1.py`.
- SPY is included only as the benchmark and is never traded by the strategy.
- Alpaca SIP split/dividend-adjusted daily OHLCV, cached locally, beginning 2018-01-01.
- SEC submissions data downloaded from official SEC endpoints.
- Historical symbol-to-CIK overrides are frozen for `MMC -> 0000062709`, `FI -> 0000798354`, `BK -> 0001390777`, and `XOM -> 0000034088` because the current SEC ticker file uses renamed/legacy or newly reorganized issuers.
- The static current-active stock panel has survivorship bias. Results are scout evidence only, never promotion evidence.

## Point-in-time SEC event definition

Material forms are fixed to:

`8-K`, `8-K/A`, `10-Q`, `10-Q/A`, `10-K`, `10-K/A`, `6-K`, `6-K/A`.

For each filing:

- Use SEC `acceptanceDateTime` when present; otherwise use the filing date conservatively.
- The filing becomes usable only on the first panel trading session strictly after its acceptance calendar date.
- Deduplicate by CIK and accession number.
- If requested symbols share a CIK, propagate the one deduplicated issuer filing to every requested share class.
- At a signal timestamp, only event flags from completed prior sessions are visible.

A symbol is blocked from new entry if at least one material filing became available during the previous six completed trading sessions. A held symbol with such an event is exited at the next executable strategy bar.

## Frozen signal chronology

For target timestamp `t`:

1. Use data strictly before `t`; the latest visible close is `t-1`.
2. Compute the raw five-session return ending at `t-1`.
3. Rank eligible, non-event-vetoed stocks ascending by return, breaking ties by symbol.
4. The shared backtester shifts target weights one bar, creating the source-motivated skipped session before returns are credited.
5. No same-bar return is allowed.

## Eligibility

- At least 60 prior daily bars.
- Latest visible price at least $5.
- Twenty-session median dollar volume at least $20 million.
- At least 100 eligible, non-benchmark stocks before constructing a portfolio.
- A valid five-session score.

## Entry and retention

- Entry tails: bottom 20% long and top 20% short using `floor(eligible_count / 5)` names per side.
- Long gross: 1.0. Short gross: 1.0.
- Equal weight within each side; maximum absolute symbol weight 5%.
- A held long remains until its current rank crosses into the winner half (`percentile > 0.50`).
- A held short remains until its current rank crosses into the loser half (`percentile <= 0.50`).
- Event-veto or eligibility failure forces an exit regardless of rank.
- Vacancies are filled from the current extreme quintile. A rank-based side flip is allowed.

## No tuning

This Experiment has one configuration. Do not change after observing results:

- Five-session lookback.
- Six-session filing-event veto.
- Material-form list.
- 20% entry tails.
- Median-cross exits.
- Liquidity, price, history, or universe thresholds.
- Gross exposure or maximum symbol weight.
- Long/short symmetry.

The no-event version may be reported only as a mechanism diagnostic, not selected for promotion.

## Costs and diagnostics

Report before any gauntlet:

- Rank IC versus next-bar return; reversal expects a negative sign.
- Gross/no-explicit-cost return and Sharpe.
- Explicit trading-cost drag and borrow drag.
- Average and percentile daily turnover.
- Cost sensitivity at 0, 0.5, 1, 2, 5, and 10 bps per dollar traded plus repository default costs.
- Filing counts, event-vetoed candidate counts, and event-forced exits.
- SPY same-period return, CAGR, Sharpe, Sortino, and max drawdown.
- Strategy beta, annualized alpha, and correlation to SPY.
- A predeclared 100% SPY plus 20% gross strategy overlay, with leverage stated explicitly.

## Scout verdict gates

Archive without a full gauntlet if any condition holds:

- Gross/no-explicit-cost total return is not positive.
- Gross/no-explicit-cost Sharpe is not positive.
- Mean Rank IC is not negative.
- Default-cost total return is not positive.
- Average daily gross turnover exceeds 1.0x equity.

A future promotion would additionally require positive post-cost alpha, low SPY beta, improved SPY-overlay utility, the corrected Validation Gauntlet, point-in-time historical universe/delisting coverage, broker/data reconciliation, and short-borrow evidence.
