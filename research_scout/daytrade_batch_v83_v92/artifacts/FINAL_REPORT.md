# Day-trading backtest results

Four profitability tests completed; none passed the SPY hurdle. One additional candidate failed its pre-return screen; five lacked the data needed for a defensible test. All 591 simulated trades closed the same day. No market data was purchased.

## After-cost development results

| Strategy | Period | Trades | Ending $100 | Matched SPY $100 | Sharpe | Max daily drawdown |
|---|---|---:|---:|---:|---:|---:|
| Month-end allocation pressure (v83) | Jan 4, 2021â€“Dec 29, 2023 | 107 | $116.56 | $132.37 | 0.91 | -7.2% |
| Opening liquidity replenishment (v84) | Mar 28â€“Dec 29, 2023 | 105 | $85.03 | $121.43 | -3.97 | -15.0% |
| Earnings-network propagation (v85) | Jan 4, 2021â€“Dec 29, 2023 | 335 | $104.26 | $132.37 | 0.18 | -44.8% |
| BTC funding-payment unwind (v86) | Jan 4, 2021â€“Dec 29, 2023 | 44 | $88.02 | $132.37 | -1.24 | -12.2% |

The opening-liquidity test has a shorter period because the complete quote-update data starts in March 2023. Its SPY comparator uses that same period. All other rows use 2021â€“2023. SPY includes overnight returns and reinvested distributions; the strategies hold cash outside their frozen windows.

## Interpretation

- **Month-end pressure:** +16.56%, profitable in each development year and robust to the specified cost/delay checks. However, SPY gained 32.37%, and the confidence interval for excess daily return included negative values. Most of the strategy's profit came in 2022. This is a failed SPY challenger, with a potentially interesting but unvalidated defensive profile.
- **Opening replenishment:** its signal passed the availability, stability and simple-momentum distinctness gates, but lost 14.97%. Better quote data established that the rule could be measured; it did not establish an economic edge.
- **Earnings network:** only +4.26% compounded and a 44.77% daily drawdown. 2021 lost 36.17%; a 2022 rebound did not rescue the strategy. Its graph controls were weaker, but the actual rule still failed costs/robustness and SPY.
- **BTC funding unwind:** lost 11.98% after 30 bps round-trip modeled friction. This is a bar-based economic screen, not observed-quote execution validation.

## Stress tests

| Strategy | Extra-cost ending $100 | Delayed-entry ending $100 | Remove five best days |
|---|---:|---:|---:|
| Month-end allocation pressure | $104.72 | $114.92 | $101.76 |
| Opening liquidity replenishment | $75.59 | $85.11 | $82.09 |
| Earnings-network propagation | $76.80 | $113.60 | $74.44 |
| BTC funding-payment unwind | $80.61 | $88.83 | $81.82 |

ETF extra-cost stress adds one cent per share at each fill; delay is five minutes. BTC cost stress is 50 bps round trip and delay is 30 minutes because five-minute prices are unavailable. No stress variant is promoted as a replacement strategy.

## Remaining candidates

| Candidate | Decision |
|---|---|
| Crowded futures positions (v87) | Stopped before P&L: 327 bullish versus 37 bearish signals; 95.6% agreement with plain net-position control. |
| Treasury bid dispersion (v88) | historical Treasury result-publication timestamp unverified |
| Collateral borrowing fees (v89) | NYFed historical first-publication/revision timing unverified |
| Futures roll dislocation (v90) | simultaneous front/next executable quotes absent |
| Buyback-window reopening (v91) | issuer buyback authorizations/policies and execution history absent |
| Polymarket complete-set pricing (v92) | simultaneous binary outcome asks/depth absent |

## Verification and limits

Eight synthetic tests passed for accounting, episode recovery/timeout, same-day exits and calendar/DST handling. An independent cash-ledger reconciliation reproduced all 591 trade returns and final balances. Input SHA-256 hashes, frozen JSON specification, per-trade ledgers, gate decisions and inference results are saved alongside this report.

No candidate passed development, so 2024â€“2025 confirmation was not evaluated. A stronger historical Sharpe alone does not pass the frozen SPY-outperformance objective. Holm-adjusted excess-return p-values across the ten-candidate screen were 1.0 for all four tested rules. Earlier repository work already exposed these histories; no historical result is pristine forward evidence.

Drawdown is measured on daily closing equity, not intraday marked positions. ETF simulations cross observed minute BBO plus slippage and fixed research fee assumptions. Actual fractional fills, venue access, settlement and intraday margin/risk behavior remain unvalidated. CFTC 2023 outage dates were excluded before its signal screen. No inference of identifiable dealer inventory or guaranteed quote fills is made.

Independent EQUS.MINI overlap metrics in machine reports are diagnostic and retain the full development calendar with cash outside available dates; do not interpret those Sharpe/CAGR figures as matched-overlap comparisons. They did not determine a promotion.

Descriptive exposure and beta are in `exposure_attribution.json`; detailed inputs/results are in the adjacent JSON files.
