# ProShares Inventory History Audit v59

## Verdict

**Rejected returns-blind. No strategy P&L may be opened from this inventory path.**

No Databento endpoint and no strategy return was used.

## 2021-2023 daily NAV/AUM

- Expected SPY sessions: 753
- UPRO: 753 sessions, 100.000% coverage
- UPRO AUM identity maximum relative error: 0.00000000
- SPXU: 753 sessions, 100.000% coverage
- SPXU AUM identity maximum relative error: 0.00000343

## Daily holdings archive

- Public 2021-2023 captures found: 3
- Distinct holdings as-of dates recovered: 3
- Session coverage: 0.398%

## SEC validation

- UPRO: 12 public N-PORT filings filed during 2021-2023
- SPXU: 12 public N-PORT filings filed during 2021-2023

Failed admission gates: daily_holdings_coverage_at_least_98_percent, historical_holdings_publication_timing_known

## Boundary

Daily NAV, AUM, shares outstanding, and split history are excellent, but they do not replace dated daily derivative holdings. The frozen 98% holdings and causal-publication gates are not relaxed. AUM-only rebalance testing would be a post-audit proxy substitution.
