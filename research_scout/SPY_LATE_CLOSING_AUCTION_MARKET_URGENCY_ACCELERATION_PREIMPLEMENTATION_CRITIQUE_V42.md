# SPY Late Closing-Auction Market-Urgency Acceleration — Preimplementation Critique v42

## Chronology and independence

A delegated returns-blind mechanism search was dispatched before V41 feasibility was read. Its rank-one recommendation, completed independently, specified this late-closing construction: 15:50/15:55 Closing-auction market-imbalance growth, SPY/SH cash actuators, delayed pre-close execution. The result was delivered only after V41 had terminated.

V42 is therefore not selected from a P&L result—no V37–V41 return exists—and its defining clocks, field, and actuators were independently proposed before V41 evidence was available. It is still counted as the same broad closing-auction research family for multiplicity. V41 remains locked; V42 does not repair V41's 15:20/15:29:50 market-share rule, UPRO/SPXU actuator, or 15:30 entry.

## Economic hypothesis

`market_imbalance_qty` is the exchange-published deadline-bound component of the closing-auction imbalance. If the same nonneutral side persists and its market-order quantity increases from 15:50 to 15:55, expected auction counterparties may hedge anticipated inventory in continuous trading before 16:00.

The claim is anticipatory pre-close inventory hedging, not continuation after the closing auction.

## Frozen signal

Select the latest SPY `auction_type == "C"` message strictly before 15:50:00 and 15:55:00 America/New_York.

Require:

1. projected `auction_time` is the regular 16:00 closing auction at both snapshots;
2. the same `side` in `{A, B}` at both snapshots;
3. positive `market_imbalance_qty` at both snapshots;
4. late `market_imbalance_qty` is strictly greater than early quantity;
5. both `ts_event` and `ts_recv` precede their decision clocks;
6. the session is outside the frozen ARCX/EQUS degraded-date union.

Direction and actuator:

- `B` -> fixed-$100 fractional long SPY;
- `A` -> fixed-$100 fractional long SH;
- ties, neutral sides, missing observations, nonpositive quantities, early closes, or non-growing quantities -> cash.

No total-imbalance ratio, price, momentum, calendar, quantity-magnitude threshold, rank, collar, auction status, spread, volatility, or prior outcome enters the signal.

## Frozen execution proposal if feasibility passes

- 1-second diagnostic: first valid trade-event ask after 15:55:01.
- 5-second diagnostic: first valid trade-event ask after 15:55:05.
- Primary 60-second delay: first valid trade-event ask after 15:56:00.
- Exit: first valid trade-event bid after 15:59:00 with both `ts_event` and `ts_recv` strictly before 16:00:00.
- Maximum event wait: 60 seconds, further capped by 16:00 for the exit.
- Reject crossed and nonpositive quotes.
- Fixed $100 fractional exposure; no shorting, margin, leverage, stop, overnight position, or assumed closing-auction fill.

EQUS.MINI is trade-event-conditioned rather than official SIP NBBO. Event wait is observable; standing-quote age is not.

## Institutional/adversarial smell test

### Why a desk might listen

- Closing-auction pre-hedging is an institutionally recognizable mechanism.
- The market-order component is more directly connected to deadline flow than total imbalance alone.
- The rule acts before the uncross and preserves flat-by-close execution.
- SPY/SH remove leverage-ladder dependence and use cash long-only actuators.
- The signal is ordinal and threshold-free.

### Why it may fail

1. Public closing imbalance information may be incorporated within seconds.
2. Market-order growth may be met inside the auction rather than hedged continuously.
3. The shared `side` does not separately sign the market-order component.
4. Closing flow can be concentrated in month-end, expiry, or rebalance sessions.
5. A 60-second delay can remove the effect.
6. SH trade-event observations may be incomplete even if a standing quote existed.
7. The 2025-11-13 quantity-basis change can alter participation.
8. The broad closing-auction family is now historically contaminated even though V42 P&L is untouched.

## Frozen returns-blind feasibility gates

All must pass before preregistration or P&L:

1. At least 2.0 feature signals per declared calendar week over 2021–2023 and at least 2.0 in each full development year.
2. At least 2.0 executable primary signals per declared week from 2023-03-28 through 2023-12-31.
3. At least 100 feature signals in each of 2021, 2022, and 2023.
4. At least 20 feature signals in 2026 through 2026-07-24.
5. Minority side at least 20% in feature and executable development; SPY and SH must both be executable.
6. At least 90% complete SPY/SH quote coverage at all three entry delays plus the strictly pre-16:00 exit over overlap signals.
7. Identical action including cash at least 60% for the predeclared shifted window 15:49:50/15:54:50.
8. Identical action including cash at least 60% for the predeclared shifted window 15:50:10/15:55:10.
9. At least 20 signals after the 2025-11-13 quantity-basis break, with both directions present.
10. Causal pre-signal SPY midpoint movement from the first valid event after 15:50:00 to the first valid event after 15:54:50 must be available before 15:55 on at least 80% of signals, and direction agreement must be below 80%.
11. Direction agreement below 80% with final total-imbalance side on sessions where that side is observable independently of the signal definition. Because V42 requires the shared published side, this comparison is expected to be mechanically high and is reported as a contamination warning rather than claimed as independence; the gate is satisfied only if the late market-quantity-growth condition selects no more than 80% of otherwise eligible same-side sessions.
12. Signals select between 10% and 80% of otherwise eligible regular-close same-side positive-market-quantity sessions.
13. No more than 25% of signals occur on last-trading-day-of-month or third-Friday sessions combined.
14. Every signal is received before 15:55:00, every entry follows signal receipt, and every retained exit is strictly before 16:00.
15. Prefix/tail TBBO deduplication is enforced at 2024-10-02/2024-10-03 and degraded dates are fixed before results.

Failure is terminal. The clocks, growth condition, side mapping, SPY/SH actuators, primary delay, exit, and gates may not be changed after feasibility is read.

## Frozen alpha protocol only if feasibility passes

Preregister before opening any exit bid:

- development: 2023-03-28 through 2023-12-31;
- contaminated validation: 2024–2025;
- temporal extension: 2026 through 2026-07-24;
- primary 15:56 ask to strictly pre-16:00 15:59 bid;
- 1/5/60-second delay sensitivity on fixed definitions;
- fixed-$100 and compounded-$100 P&L;
- PF, win rate, cadence, maximum drawdown, event waits, spread drag, years, and sides;
- one-cent adverse entry and exit stress;
- remove ten best trades;
- matched-session passive SPY and same-window SPY execution;
- controls for pre-signal SPY momentum, total closing-imbalance side, previous-session and one-session-shifted signals, month-end/third-Friday removal, and same-clock spread matching;
- no inversion, threshold search, timing selection, or actuator switch.

## Preimplementation decision

**Pass to returns-blind feasibility only. No post-entry return is authorized.**
