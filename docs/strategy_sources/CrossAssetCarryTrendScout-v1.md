# CrossAssetCarryTrendScout-v1

Status: **FROZEN BEFORE RETURN EVALUATION**

Date frozen: 2026-07-09

## Post-run implementation audit corrections

Independent code review required the following corrections. They did not change the frozen universe, signal formulas, lookbacks, execution delay, costs, caps, thresholds, or gates:

- normalize mixed-frequency source rows with pysystemtrade's business-day convention and require carry fields to coexist on one source timestamp;
- count available zero combined signals toward the eight-market eligibility gate while retaining their zero target;
- use only pre-known business month-ends, skipping a month when that date is unavailable rather than retrospectively selecting an earlier observation;
- calculate concentration gates from equity-scaled P&L rather than sums of percentage returns;
- count rolls using the position entering a simultaneous roll/rebalance transition; and
- rebuild leave-one-class-out signal calendars from each declared subset.

All provisional reports were overwritten by a full rerun after these corrections. None of the corrections was selected based on whether it improved returns.

## Purpose and evidence boundary

Test whether a simple public institutional mechanism—futures carry plus medium-term trend—has enough gross edge and SPY-diversification value to justify acquiring raw contract data.

This is a falsification scout, not validation evidence. The public source contains curated price/carry/forward series and back-adjusted prices but not the complete raw contract chain, volume, open interest, first-notice dates, or exchange definitions. A passing result cannot authorize paper or live trading. A failing result terminates this exact hypothesis without parameter rescue.

## Frozen source

- Repository: `pst-group/pysystemtrade`
- Source commit: `883c8681cf880d83acad5c39b842403a8eac5676`
- Local manifest: `external_artifacts/pysystemtrade_futures_data/883c8681cf88/manifest.json`
- Normalized data: source-compatible business-day last observations. Carry is retained only when `PRICE`, `PRICE_CONTRACT`, `CARRY`, and `CARRY_CONTRACT` coexist on one source timestamp; no signal input is forward-filled.
- Analysis window: 2010-01-04 through 2024-03-28
- Benchmark: cached Yahoo adjusted SPY daily closes, restricted to the same dates

## Frozen universe

| Asset class | Markets |
| --- | --- |
| Equity index | SP500, NASDAQ |
| US rates | US2, US5, US10, US20 |
| FX | EUR, JPY, GBP |
| Energy | CRUDE_W, GAS_US |
| Metals | GOLD, COPPER |
| Agriculture | CORN, SOYBEAN |

No market may be added, removed, or substituted after seeing returns. A market is inactive on dates when its required inputs are unavailable.

## Frozen feature definitions

### Contract spacing

Decode `PRICE_CONTRACT` and `CARRY_CONTRACT` as `YYYYMM00`. Define signed month spacing:

`month_gap = carry_year * 12 + carry_month - (price_year * 12 + price_month)`

Rows with zero spacing, malformed identifiers, or absolute spacing above 24 months are ineligible. Contract prices and identifiers are never forward-filled.

### Carry

Define annualized carry in quoted price points:

`annualized_carry_points = (PRICE - CARRY) / (month_gap / 12)`

This convention is positive in backwardation whether the supplied carry contract is earlier or later than the price contract. The carry direction is:

`carry_signal = sign(annualized_carry_points)`

Carry magnitude is deliberately not fit or ranked. Cross-market scale is handled only through ex-ante point volatility.

### Trend

Define point P&L from the supplied back-adjusted series:

`point_change_t = ADJUSTED_t - ADJUSTED_(t-1)`

Define 12-month trend:

`trend_points_t = ADJUSTED_t - ADJUSTED_(t-252)`

`trend_signal = sign(trend_points_t)`

Differences, not percentage changes, are used because back-adjusted futures series can be zero or negative. The adjusted series is never used to infer carry.

### Ex-ante risk

For each market, estimate annualized point volatility as the 63-session rolling sample standard deviation of `point_change`, multiplied by `sqrt(252)`, with at least 42 valid observations. The estimate uses only observations available through the signal date.

### Frozen signal combination

- Carry-only attribution: `carry_signal`
- Trend-only attribution: `trend_signal`
- Primary combined signal: `0.5 * carry_signal + 0.5 * trend_signal`

The primary combined signal requires both component signals. Disagreement produces a zero target. Missing carry produces a zero combined target; it is not replaced with trend-only exposure.

## Frozen portfolio construction

- Rebalance only when the pre-known final business day of the month is present on the common market calendar. If it is absent, skip that month's rebalance rather than retrospectively selecting an earlier observation.
- Require at least 8 active markets at a rebalance; otherwise target zero exposure.
- Annual portfolio volatility target: 10%.
- For signal `s_i` and annualized point volatility `v_i`, preliminary point exposure per dollar of equity is:

  `q_i = 0.10 * s_i / (v_i * sqrt(sum_j(s_j^2)))`

- Cap each market's absolute notional exposure `abs(q_i * PRICE_i)` at 35% of equity.
- Cap aggregate gross notional exposure at 300% of equity by proportional scaling.
- Signals formed from settlement data at date T become executable only after one full intervening session. They first earn close-to-close P&L on T+2.
- Between scheduled rebalances, contract quantity is held constant relative to portfolio equity except when the source price contract changes, which is treated as a close-and-open roll.
- No volatility, correlation, or performance-based portfolio multiplier is fitted.

## Frozen return and cost model

Daily gross excess return is the sum of held point exposure times current point change. Portfolio equity and point exposure drift are updated recursively; skipped rebalances do not imply daily re-targeting.

Transaction costs are charged on absolute notional turnover:

- Default: 2 basis points per one-way notional traded.
- Sensitivity: 0, 1, 2, and 5 basis points.
- A contract roll charges both closing and opening notional.
- No borrow cost applies.
- Standalone futures results are excess returns with zero collateral yield.
- SPY overlays add the futures excess return to SPY; collateral interest is not double-counted.

## Frozen reports

Report, without selecting among alternatives:

1. carry-only gross and default-net performance;
2. trend-only gross and default-net performance;
3. primary combined gross and default-net performance;
4. default-net performance for 2010-01-04–2016-12-31 and 2017-01-01–2024-03-28;
5. gross and net contribution by the six frozen asset classes;
6. combined net performance after leaving out each asset class separately;
7. turnover, contract-roll count, active-market count, leverage, and cost drag;
8. combined cost sensitivity at 0/1/2/5 bps;
9. SPY, SPY plus a 20%-scaled combined net overlay, and the primary SPY plus 50%-scaled combined net overlay;
10. monthly profit concentration and daily correlation to SPY.

Standard metrics are total return, CAGR, annualized arithmetic return, annualized volatility, Sharpe, Sortino, maximum drawdown, and final equity. No risk-free-rate subtraction is used.

## Frozen hard gates

The scout passes only if every gate passes:

1. combined gross total return is positive;
2. combined gross Sharpe is at least 0.40;
3. combined default-net total return is positive;
4. combined default-net Sharpe is at least 0.35;
5. carry-only and trend-only gross total returns are each positive;
6. both frozen subperiods have positive combined default-net total return and Sharpe;
7. every leave-one-asset-class-out combined default-net Sharpe is positive;
8. no single asset class exceeds 60% of the sum of absolute gross asset-class P&L;
9. the best 12 months contribute no more than 50% of total positive combined net monthly P&L;
10. combined net remains profitable at 5 bps one-way cost;
11. primary SPY plus 50%-scaled overlay Sharpe is not below SPY Sharpe;
12. primary overlay maximum drawdown is no worse than SPY by more than 1 percentage point;
13. primary overlay CAGR is not below SPY CAGR by more than 1 percentage point.

## Predeclared interpretation

- **Fail:** Reject this exact carry/trend construction. Do not change lookbacks, weights, universe, cost, rebalance schedule, or gates on this sample.
- **Pass:** The result only justifies a five-market raw-contract replication using ES, ZN, CL, GC, and ZC from Databento or another auditable source. Promotion still requires raw settlements, volume/open interest, contract definitions, notice/expiry handling, and a previous-session-only roll rule.
