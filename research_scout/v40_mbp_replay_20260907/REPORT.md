# V40 opening-auction demand consensus — September 7, 2026 UTC

**Decision: all 14 signal-only gates pass; the costed strategy fails development. No deployment or retuning.**

V40 buys UPRO when both the 3x and 2x long/inverse ETF pairs show relatively stronger opening-auction quantity surprises on the long side; it buys SPXU when both favor the inverse side. Disagreement means cash. The original trailing 20-session median and strict comparisons are unchanged.

## Feasibility repaired

All original quantity signals are identical to the prior audit. Full MBP-1 updates replace trade-triggered TBBO only for execution evidence. Primary coverage is 97.30% (433/445 overlap signals), versus 89.44% previously. Relevant-side 1x/2x/3x ladder coverage is 100%, versus 69.85%. Both delay targets exist for all 433 executable signals.

The original economic development window is March 28–December 2023. The 2021–2022 records contribute to the original signal-frequency and history checks; this does not claim a 2021–2022 execution backtest.

## Costed results

Every stage starts independently at $100. SPY is a buy-and-hold adjusted-price total-return proxy over the same full stage calendar, including strategy cash days.

| Stage | Trades | Strategy ending cash | SPY ending value | Strategy return | Daily-close drawdown |
|---|---:|---:|---:|---:|---:|
| 2023-03-28–2023-12-29 (development) | 101 | $92.94 | $121.46 | -7.06% | -7.35% |
| 2024-01-02–2025-12-31 (contaminated validation) | 270 | $82.18 | $148.00 | -17.82% | -18.47% |
| 2026-01-02–2026-06-11 (extension complete prefix) | 62 | $96.82 | $107.88 | -3.18% | -4.33% |

Development win rate is 36.63%, profit factor 0.502, daily Sharpe -3.183, and mean net return -7.214 basis points per trade. Fixed $100 per trade loses $7.29. The five-session block-bootstrap 95% interval for mean daily excess versus SPY is [-0.256%, -0.032%]. It does not support excess performance.

| Development robustness check | Ending cash |
|---|---:|
| Additional one-cent adverse entry and exit | $83.08 |
| Remove the ten best trades | $89.43 |
| Entry at 09:31:01, matched dates | $92.36 |
| Entry at 09:32:00, matched dates | $91.83 |

## Why it fails

In development, frictionless midpoint movement averages 0.879 basis points per trade, while spread plus modeled execution drag averages 8.093 basis points. The measured movement is too small to pay execution costs. Midpoints are a diagnostic, not attainable fill prices.

The development midpoint-only diagnostic ends at $100.86; crossing the observed ask/bid alone ends at $94.95, before the additional slippage and fees. Thus the rejection does not depend solely on the extra fee assumptions.

The original delay variants also lose. Both 2024 and 2025 lose separately, and the available complete 2026 prefix loses. Later periods are descriptive, contaminated history and cannot rescue the failed development test.

## Controls

Controls use the same primary signal dates; they are diagnostics, not newly optimized standalone strategies. The price control compares UPRO and SPXU official close-to-open returns; the raw participation control compares unnormalized UPRO+SSO and SPXU+SDS opening shares. Definitions were frozen before P&L.

| Development control | Ending cash |
|---|---:|
| same window SPY | $100.09 |
| overnight direction | $96.38 |
| opening price pair | $95.94 |
| raw quantity balance | $86.90 |
| prior session consensus | $97.69 |
| leverage 1x | $94.46 |
| leverage 2x | $76.19 |
| leverage 3x | $92.94 |

All control missing/cash dates and matched-session passive SPY statistics are in `economic_result.json`. No control was selected to replace the primary rule.

## Execution, coverage and verification

- Primary entry crosses the first valid observed ask after 09:31:05; exit crosses the bid after 09:35, within the original 60-second wait cap. All trades are fractional long UPRO/SPXU and flat the same day.
- Costs are observed spread plus one basis point per side, then a fixed sell-notional rate of 0.0000051 and $0.000119/share. Zero commission is assumed. These are research assumptions, not a reconstruction of historical broker fees. Fractional execution, settlement and capacity are not operationally validated.
- The full-quote dataset lacks 28 requested late-2026 sessions. Twelve original signals remain unresolved. The 2026 equity result ends June 11, before the first missing local session, rather than treating missing signals as cash. No result through July 24 is claimed.
- Benchmark data come from cached Yahoo adjusted OHLC; the downloader rescales OHLC by adjusted-close/raw-close. This is a total-return proxy, not an independently reconstructed dividend ledger. SPY benchmark friction is omitted, making this comparison slightly more demanding for the strategy.
- All 433 executable original dates are accounted for. An independent high-precision cash ledger reconstructed shares, proceeds, sell fees, fixed-dollar P&L and compounded cash, matched cached quote prices, and checked same-day flat positions. No verification errors.
- Full-period and daily-close metrics do not measure intraday drawdown. No timing, rolling length, sign, threshold or filter was changed after outcomes. No trades, purchases or external account changes occurred.

## Current position

V40 is now an economic rejection, rather than a quote-data blocker. V49 remains a signal-stability rejection. Neither supplies a validated SPY-beating intraday strategy. The useful distinction is that V40 could be measured consistently, but its price movement did not cover execution costs.

Evidence: `specification.json`, `gate_result.json`, `gate_verification.json`, `economic_scope.json`, `economic_result.json`, `trade_ledger.json`, `daily_returns.json`, `verified_cash_ledger.json`, and `verification.json`. Original historical artifacts are preserved.
