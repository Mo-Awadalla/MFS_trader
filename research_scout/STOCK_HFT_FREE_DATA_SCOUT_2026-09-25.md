# Free-data stock HFT scout — 2026-09-25

## Scope

US listed individual stocks, seconds-scale decisions, no paid market-data
subscription, and no broker orders. Neither an ETF strategy nor a crypto strategy
is used here. AAPL is a fixed feasibility symbol, not a validated universe.

## Available data and execution boundary

- Alpaca Basic supplies real-time IEX trades and quotes, but IEX is one venue.
  It does not provide a live consolidated NBBO in this workspace.
- Alpaca historical SIP trades and quotes are accessible after a 15-minute
  delay. A read-only one-second AAPL request returned HTTP 200 and 494 SIP
  quotes; the frozen five-minute development downloads subsequently completed.
- IEX HIST publishes free next-day exchange feed files, but a live real-time
  IEX DEEP feed is paid. The free live IEX Level 1 feed remains useful for
  plumbing and narrow venue research, not for assuming consolidated execution.
- Tradier documents real-time consolidated stock data for Brokerage account
  holders. No Tradier token or other live consolidated feed is configured here.

Sources: [Alpaca market data](https://docs.alpaca.markets/us/docs/market-data-faq),
[IEX HIST](https://iextrading.com/trading/market-data/index.html),
[IEX fee schedule](https://www.iex.io/resources/trading/fee-schedule),
[Tradier market data](https://docs.tradier.com/docs/market-data).

## Frozen tests and result

The first [IEX rule](iex_stock_hft_v1.json) required a same-price 50% offer-size
drop, stable bid size, a spread no wider than three cents, and a one-second
entry delay. The existing 2026-07-08 AAPL opening sample produced zero signals.
Only 6 of 26,913 IEX quotes in the 09:31–09:34:30 signal window had spreads
within three cents, and none also met the offer-size condition. This is a
feasibility check, not a performance estimate. The rule was left unchanged.

The independently frozen [historical SIP rule](sip_stock_hft_v1.json) applied
the same economic mechanism to consolidated quotes at 11:00–11:05 ET on twelve
preselected 2025 sessions. All sessions were downloaded and hash-verified. The
immutable [development report](sip_stock_hft_v1/development_report.json) found:

| Measure | Result |
| --- | ---: |
| Frozen sessions | 12 of 12 present |
| Signals | 17, all in November and December |
| Signals with fresh entry and exit quotes | 5 across 2 sessions |
| Mean gross crossing return | +0.17 bps |
| Mean after commission and 1 bp friction | -1.55 bps |
| Day-block 95% interval on net mean | -3.41 to -0.30 bps |
| Progression gates passed | 1 of 7 (coverage only) |

The numerical report passed an independent recomputation of all five
executable-proxy returns from its stored entry asks, exit bids, commission rule,
and friction rule (maximum difference 0). The report has a [text-label erratum](sip_stock_hft_v1/ERRATUM.md):
its data source is historical SIP, and complete development **failed**.

## Decision

Close both exact offer-depletion rules. Do not loosen the spread, size, freshness,
clock, or holding-period conditions using these observed dates. The SIP result
does not support after-cost stock alpha, and its 15-minute delay prevents live
use in this workspace. The IEX result establishes only that the frozen opening
rule was infeasible in its one-day plumbing sample.

The next executable stock HFT experiment requires a free **real-time consolidated**
stock feed linked to a brokerage account, plus timestamped order acknowledgments,
fills, and cancellations. A fresh hypothesis would be frozen before examining
new data. Historical SIP remains useful for falsification, but cannot alone
demonstrate queue priority or achievable passive fills.
