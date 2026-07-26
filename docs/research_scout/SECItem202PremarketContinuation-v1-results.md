# SEC Item 2.02 Premarket Continuation v1 — Development Result

Status: **TERMINAL DEVELOPMENT FAIL**

Evaluated: 2026-07-24

This is a bounded static-universe Alpaca IEX scout. It is not a registered
Strategy, an Experiment, or authorization for paper/live trading.

Frozen specification:
`research_scout/sec_item_202_premarket_continuation_v1.json`

Specification SHA-256:
`68b4e2fa9cda02f0f4c9362806f7c7933c36a0feeb98754c6ba4ebd07691ecbb`

Local machine report:
`data/parquet/sec_item_202_premarket_continuation_v1/development/report.json`

## Data audit

The first attempted download established before any return panel was built that
the configured Alpaca IEX account returned no bars before 2020-07-28. The
development start was corrected to that observed feed boundary without changing
the event, signal, clocks, costs, or gates.

- Eligible premarket Item 2.02 events: 806
- Symbols: 94
- Event sessions: 256
- Complete event windows: 787 (97.64%)
- Normalized event-session bars: 81,268
- Development interval: 2020-07-28 through 2022-12-31

The 98% completeness gate narrowly failed. This did not determine the verdict;
the economic and stability gates also failed.

## Result

| Metric | Development result |
| --- | ---: |
| Selected events | 411 |
| Active sessions | 191 |
| Mean stock gross | 5.2419 bps |
| Mean stock after 10 bps round trip | -4.7581 bps |
| Mean stock-minus-SPY gross | 9.0972 bps |
| Mean stock-minus-SPY after 10 bps round trip | -0.9028 bps |
| Mean stock-minus-SPY after 20 bps stress cost | -10.9028 bps |
| Residual directional accuracy | 52.55% |
| Residual net profit factor | 0.9855 |
| Session-bootstrap 95% residual-net interval | [-26.7257, 15.6758] bps |
| First / second chronological-half residual net | -25.0804 / 14.1444 bps |
| Top-5%-trimmed residual net | 2.2874 bps |

## Interpretation

The positive gross residual was smaller than the frozen ordinary retail
round-trip cost. Actual stock P&L was negative after cost, the first
chronological half was materially negative, the session-bootstrap interval
crossed zero, profit factor was below one, and the 20-bps stress result was
negative.

The later 2022 result was positive, but the frozen rule does not permit selecting
that regime after observing development. The internal-validation and final
holdout partitions remain untouched and locked.

This exact branch is terminated. Do not rescue it with:

- a residual-return or gap threshold;
- an earnings surprise, volume, sentiment, sector, or market-regime filter;
- a different signal, entry, or exit clock;
- stops, targets, re-entry, or an inverted short side;
- deletion of 2020–2021 or post-result symbol selection.

Any future earnings research must introduce a genuinely different information
source or mechanism and receive a new preregistered specification.
