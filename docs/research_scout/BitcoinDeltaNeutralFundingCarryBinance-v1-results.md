# Bitcoin Delta-Neutral Funding Carry — Binance v1

Status: **DEVELOPMENT PASSED; INTERNAL VALIDATION FAILED WITH ZERO OPPORTUNITIES**

Specification: `research_scout/bitcoin_delta_neutral_funding_carry_binance_v1.json`

## Strategy

While flat, at 00:10 UTC:

- require the three latest already-settled funding rates to be strictly positive;
- require their mean to be at least 3 bps per settlement;
- require the completed spot–perpetual basis to be nonnegative;
- enter at 00:30 with the same BTC quantity long spot and short perpetual;
- hold seven calendar days without rebalancing;
- credit every actual settled funding cash flow using the contemporaneous mark-price proxy;
- exit both legs at 00:30 after seven days;
- prohibit overlapping positions.

The 3 bps threshold was frozen from economics, not observed returns: approximately half of capital earns funding, so 21 expected settlements over seven days at 3 bps project 31.5 capital bps, modestly above the 25 bps conservative entry/exit hurdle.

## Development: 2020–2022

The frozen rule passed every gate:

| Metric | Result |
|---|---:|
| Trades | 41 |
| Funding events per trade | 21 |
| Mean funding P&L | +46.9138 bps |
| Mean basis P&L | +1.2757 bps |
| Mean gross return | +48.1895 bps |
| Mean conservative return | **+23.1959 bps** |
| Bootstrap 95% conservative interval | **[+13.7976, +33.8792] bps** |

Year detail:

| Year | Trades | Gross | Conservative | Conservative accuracy |
|---|---:|---:|---:|---:|
| 2020 | 17 | +39.9487 bps | +15.0438 bps | 64.71% |
| 2021 | 24 | +54.0267 bps | +28.9703 bps | 79.17% |
| 2022 | 0 | n/a | n/a | n/a |

All 41 positions crossed exactly 21 actual funding settlements. No position overlapped another. Independent accounting checks found zero error in:

- `gross = basis P&L + funding P&L`;
- `conservative = gross - fees - slippage`.

No development trade had negative aggregate funding P&L. Conservative trade outcomes ranged from -16.4091 to +118.3109 bps.

## Internal validation: 2023

**Failed: zero qualifying trades.**

The predeclared combination of three consecutive positive settlements averaging at least 3 bps and nonnegative basis never produced a complete non-overlapping position in 2023.

This is not a negative-return failure. It is a regime-availability failure: the rich funding conditions that supported the 2020–2021 carry disappeared under the frozen rule.

The final 2024–2025 holdout remains locked and was not opened.

## Interpretation

The strategy demonstrates that multi-day carry can overcome four-execution costs when funding is exceptionally rich. Unlike the intraday convergence scout, the return source was large enough:

- about 46.9 bps from actual funding cash flows;
- about 1.3 bps from basis movement;
- about 23.2 bps left after conservative costs.

But this was a 2020–2021 leveraged-bull-market opportunity. The rule generated no trades in 2022 and none in 2023 validation. It therefore cannot be presented as a currently recurring Bitcoin sleeve.

## Relevance to the user's goals

Positive:

- market-neutral at entry;
- no latency competition;
- explicit contractual cash flow rather than directional prediction;
- public point-in-time inputs;
- only occasional entries;
- development returns survived conservative costs.

Negative:

- seven-day holding period, so not day trading;
- exchange and USDT counterparty exposure;
- perpetual margin and liquidation operations still matter despite matched BTC quantity;
- funding can reverse after entry;
- capital is tied up for a week;
- no qualifying validation trades;
- no evidence that the opportunity persists in recent regimes.

## Final verdict

**Promising historical mechanism, failed strategy validation. Do not deploy.**

The logical lesson is narrower but useful: high funding can become monetizable when held across enough settlements to amortize costs. The opportunity was regime-dependent and absent in the untouched 2023 validation period under the frozen economic hurdle.

Do not lower the 3 bps threshold, shorten the three-settlement confirmation, lengthen the holding period, permit overlapping positions, add OI filters, or open 2024–2025 to find activity. Those would be post-development/validation rescues.
