# SPY Core-Open Uncross Overshoot Rejection — Preimplementation Critique v38

## Chronology

V38 begins only after V37 failed its frozen returns-blind actuator-coverage gate at 88.37% versus 90%. V37 remains terminal and no V37 return was opened. V38 does not alter V37's coverage threshold, quote targets, or indicative-leadership condition.

V38 is a different causal clock. V34–V37 used only pre-open auction state to choose direction. V38 waits for the realized ARCX Core Opening auction statistic and a post-open SPY trade-event BBO before it can signal. It therefore cannot be used for a pre-open order.

## Economic hypothesis

The latest pre-open `ind_match_price` is an exchange estimate of the price maximizing matched auction shares. The ARCX `OPENING_PRICE` statistic is the realized Core Opening auction outcome. A last-second order shock can push the realized uncross beyond the final published indication.

The first continuous SPY trade-event midpoint after 09:30:01 provides a causal acceptance test:

- If the realized opening price lies beyond the final indicative match price and the first continuous midpoint has moved strictly back inside the interval between them, continuous liquidity is rejecting the auction overshoot.
- The hypothesized short-horizon destination is the final published indication, not the raw imbalance side.

Direction follows the rejected overshoot:

- final indicative price above realized open and midpoint between them: buy UPRO;
- final indicative price below realized open and midpoint between them: buy SPXU.

This is a bounded auction-to-continuous mean-reversion mechanism. It is not final-sign continuation, price/quantity disagreement, indicative leadership, generic wrapper lag, or an inversion of a failed P&L result.

## Frozen primary signal

For each nondegraded session in the EQUS overlap:

1. Select the latest `auction_type == "M"` SPY imbalance message strictly before 09:29:59 ET.
2. Select the SPY ARCX `OPENING_PRICE` statistic for that session and require positive price and quantity.
3. Select the first valid SPY trade-event BBO at or after 09:30:01 ET from the bounded target cache.
4. Require that SPY event's wait from 09:30:01 is no more than 4 seconds, making the continuous observation available by 09:30:05.
5. Require both statistic `ts_event`/`ts_recv` and SPY BBO `ts_event`/`ts_recv` before 09:30:05 ET.
6. Let `I` be final `ind_match_price`, `O` official Core Open price, and `M` the SPY BBO midpoint.
7. Require `I != O` and `M` strictly between `I` and `O`.
8. If `I > O`, direction is positive and actuator is UPRO. If `I < O`, direction is negative and actuator is SPXU.

No minimum overshoot, midpoint-rejection fraction, quantity, imbalance-side, gap, volatility, weekday, collar, or spread threshold is allowed.

## Frozen execution proposal if feasibility passes

The signal is not known until after the official uncross and continuous acceptance observation. To preserve a clear availability margin:

- one-second timing diagnostic: first valid actuator ask after 09:31:01;
- primary five-second timing: first valid actuator ask after 09:31:05;
- 60-second timing diagnostic: first valid actuator ask after 09:32:00;
- exit: first valid actuator bid after 09:35:00;
- maximum event wait: 60 seconds at each target;
- fixed $100 fractional long position, no margin, borrowing, or shorting;
- reject nonpositive and crossed quotes.

EQUS.MINI is trade-event-conditioned and not official SIP NBBO. Standing-quote age remains unknown and must be reported.

## Institutional smell test

### Why a serious desk might listen

- It separates estimated auction clearing from the realized uncross and then asks whether continuous liquidity accepts or rejects the difference.
- The official statistic is post-cross information, but the order is explicitly delayed until after publication and a continuous SPY observation.
- The direction does not depend on a fitted magnitude or imbalance sign.
- It uses SPY to measure the mechanism and UPRO/SPXU only as long cash actuators.
- It has a natural placebo: one-session-shifted final indication cannot explain same-session uncross rejection.

### Adversarial objections

1. The first available TBBO record is conditioned on a trade and may not represent the quote path between trades.
2. A midpoint inside the interval may simply be ordinary spread/noise around the open.
3. The final indication and official open can differ by a trivial amount; no threshold is permitted, so costs may dominate.
4. A 09:31 entry may be too late for a genuine uncross rejection.
5. The rule could collapse to ordinary first-minute momentum or final-indicative displacement.
6. Historical outcome contamination remains severe.

These objections must be tested as frozen feasibility, control, and stress gates rather than repaired after results.

## Frozen returns-blind feasibility gates

All must pass before preregistration or P&L:

1. At least 2.0 primary signals per declared calendar week from 2023-03-28 through 2023-12-31.
2. At least 80 primary signals in the 2023 development overlap.
3. At least 100 primary signals in each full historical year 2024 and 2025.
4. At least 20 primary signals in 2026 through 2026-07-24.
5. Minority direction at least 20% in 2023 development and in all overlap.
6. Both UPRO and SPXU have executable 2023 development signals.
7. Required actuator quote coverage for 09:31:01, 09:31:05, 09:32:00, and 09:35:00 at least 90%.
8. Relevant-side 1x/2x/3x quote availability at 09:31:05 at least 80%: SPY/SSO/UPRO for positive; SH/SDS/SPXU for negative.
9. Identical action including cash at least 60% when the pre-open indication cutoff is changed from 09:29:59 to 09:29:50.
10. Identical action including cash at least 60% when the continuous acceptance observation changes from the first event after 09:30:01 (available by 09:30:05) to the first event after 09:30:05 (available by 09:30:10).
11. Signal direction agreement with the sign of first-continuous midpoint versus final pre-open reference must be below 80%.
12. Signal direction agreement with final published imbalance side must be below 80%.
13. Signal direction agreement with final indicative/reference displacement must be below 80%.
14. Every official opening statistic and primary SPY event must be received before 09:30:05 and every actuator entry observation must occur after signal availability.
15. Exactly one valid SPY Core Opening statistic must be selected per eligible session; duplicate or ambiguous outcome records fail closed.

Failure is terminal. No magnitude threshold, wider acceptance interval, later signal window, relaxed coverage, or alternative exit may be introduced after feasibility is read.

## P&L protocol only if every feasibility gate passes

Freeze a preregistration before reading actuator exit bids:

- development: 2023-03-28 through 2023-12-31;
- contaminated historical validation: 2024–2025;
- temporal extension: 2026 through 2026-07-24;
- primary 09:31:05 entry plus fixed 09:31:01/09:32:00 diagnostics;
- fixed-$100 ask-to-bid P&L and compounded $100 equity;
- profit factor, win rate, cadence, drawdown, spread drag, event waits, years, and directions;
- one-cent-per-share adverse entry and exit stress;
- delete ten best trades;
- matched-session passive SPY comparison;
- controls for first-minute momentum, raw imbalance side, final indicative displacement, and opening gap;
- one-session-shifted final-indication placebo;
- no rule repair or timing selection.

## Preimplementation decision

**Pass to returns-blind feasibility only.** The economic object is distinct and causally ordered, but no return calculation is authorized.
