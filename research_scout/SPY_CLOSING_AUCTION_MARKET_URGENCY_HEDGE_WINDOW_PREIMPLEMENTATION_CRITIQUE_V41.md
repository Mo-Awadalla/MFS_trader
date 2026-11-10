# SPY Closing-Auction Market-Urgency Hedge Window — Preimplementation Critique v41

## Chronology and why this is not V39 repair

V39 established that `market_imbalance_qty` does not survive in the sampled pre-Core-Open state: its exact opening rule produced zero signals. V39 remains terminal and no return was opened.

V41 addresses a different auction with different protocol population and economics. The technical audit showed 1,655,339 positive `market_imbalance_qty` rows for Closing-auction messages versus 400,461 across all Core-Open messages and zero in V39's selected opening snapshots. Closing-auction market-order imbalance is therefore a directly observed closing mechanism, not a widened opening rule.

V35-R2 rejected trading *after* the close because the program requires flat-by-close execution. V41 resolves that conceptual blocker without changing V35-R2: it enters at 15:30 and exits before 16:00, trading the public hedge window leading into the closing auction rather than an overnight/post-close continuation.

## Economic hypothesis

Closing-auction market orders express deadline flow. As market-order share of the published closing imbalance rises while the unpaired side remains stable, arbitrageurs, market makers, and index/ETF hedgers may transfer that expected auction pressure into the continuous market before the 16:00 uncross.

Use the published state from 15:20:00 to 15:29:50 ET:

- stable bid-side market urgency -> buy UPRO at 15:30 and liquidate before 16:00;
- stable ask-side market urgency -> buy SPXU at 15:30 and liquidate before 16:00.

The mechanism is pre-close hedging toward a known auction deadline, not persistence after the auction.

## Frozen signal

Select the latest SPY `auction_type == "C"` message strictly before 15:20:00 and 15:29:50 ET.

A signal exists only when:

1. both snapshots exist on a nondegraded session;
2. early and late `side` are the same and in `{A, B}`;
3. early and late `total_imbalance_qty` are positive;
4. early and late `market_imbalance_qty` are nonnegative;
5. late market imbalance is positive;
6. `late_market_imbalance_qty / late_total_imbalance_qty` is strictly greater than its early value;
7. late `ts_event` and `ts_recv` are before 15:29:50.

No quantity magnitude, share-growth magnitude, price, return, gap, volatility, day, collar, or spread threshold is allowed.

## Frozen execution proposal if feasibility passes

- `B` -> fixed $100 fractional long UPRO.
- `A` -> fixed $100 fractional long SPXU.
- Primary entry: first valid trade-event ask after 15:30:05.
- One-second diagnostic: after 15:30:01.
- 60-second diagnostic: after 15:31:00.
- Exit: first valid trade-event bid after 15:59:00, required strictly before 16:00:00.
- Maximum event wait is 60 seconds for entry and only the remaining seconds before 16:00 for exit.
- Reject crossed and nonpositive quotes.
- No margin, shorting, borrowing, or overnight position.

## Institutional smell test

### Why a desk might listen

- Closing-auction pressure and pre-close hedging are established institutional microstructure objects.
- The hard market-order share is more directly tied to deadline flow than generic closing momentum.
- The rule uses only exchange-published information received before entry.
- The fixed exit is before the auction, preserving the user's flat-by-close constraint and avoiding an assumed closing-auction fill.
- The rule is threshold-free and supports both long cash actuators.

### Adversarial objections

1. Published closing imbalance may already be incorporated by 15:30.
2. Market-order flow may be offset by closing-auction liquidity and need not move the continuous market.
3. `side` is aggregate unpaired direction and may not isolate market-order direction perfectly.
4. The 2025-11-13 quantity-basis break can alter ratios.
5. A 29-minute hold can collapse to generic final-half-hour momentum.
6. The 15:59 trade-event exit may be missing or arrive after 16:00 in thin inverse ETFs.
7. Closing-auction research adds another contaminated family to an already broad program.

## Frozen returns-blind feasibility gates

All must pass before preregistration or P&L:

1. At least 2.0 feature signals per declared week over 2021–2023.
2. At least 2.0 executable primary signals per declared week over 2023-03-28 through 2023-12-31.
3. At least 100 feature signals in each development year 2021, 2022, and 2023.
4. At least 20 feature signals in 2026 through 2026-07-24.
5. Minority side at least 20% in feature and executable development.
6. Both UPRO and SPXU executable in development.
7. Primary entry-plus-pre-16:00-exit quote coverage at least 90%.
8. Relevant-side 1x/2x/3x 15:30:05 quote availability at least 80% of executable signals.
9. Identical action including cash at least 60% with a 15:29:30 late cutoff.
10. Identical action including cash at least 60% with a 15:29:59 late cutoff.
11. Signals select between 10% and 80% of eligible stable-side closing sessions.
12. At least 20 signals occur on or after the 2025-11-13 quantity-definition break.
13. Every signal `ts_event` and `ts_recv` precedes 15:29:50 and every entry follows receipt.
14. Every retained exit observation is strictly before 16:00:00 ET.

Failure is terminal. The auction type, market-share condition, side mapping, cutoffs, entry, and pre-close exit may not be changed afterward.

## P&L protocol only if feasibility passes

Freeze preregistration before reading exit bids:

- development 2023-03-28 through 2023-12-31;
- contaminated validation 2024–2025;
- temporal extension 2026;
- primary 15:30:05 ask to pre-16:00 15:59 bid;
- 15:30:01 and 15:31:00 diagnostics;
- fixed-$100 and compounded-$100 results;
- PF, win rate, cadence, drawdown, spread drag, event waits, years, sides;
- one-cent adverse entry/exit stress;
- remove ten best trades;
- matched-session passive SPY and same-window SPY execution;
- controls for final-half-hour SPY momentum, raw closing-imbalance side, closing paired-share change, and one-session-shift market-share signal;
- no rule repair, inversion, threshold search, or timing choice.

## Preimplementation decision

**Pass to returns-blind feasibility only.** No return is authorized.
