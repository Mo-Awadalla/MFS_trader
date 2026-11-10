# SPY Late Market-Order Urgency Handoff — Preimplementation Critique v39

## Chronology and independence

V39 follows terminal returns-blind failures in V37 and V38. No V37 or V38 P&L was opened. V39 does not alter their conditions or gates.

V39 uses a different auction object: the composition of imbalance attributable to market orders. V34 used only final total-imbalance side; V35 used total unpaired pressure relative to paired quantity plus price displacement; V36 used final side/price disagreement; V37 used price-process leadership; V38 used the official uncross and continuous rejection. V39 uses no post-open price to form the signal and no indicative-price condition.

Because direction still follows the published imbalance side, V34 remains a contaminated benchmark. V39 must later beat raw final-sign continuation rather than being presented as independent proof.

## Economic hypothesis

`market_imbalance_qty` isolates the market-order component of the auction imbalance. Market-on-open interest is less price-sensitive than limit interest and expresses deadline demand. If its share of total unpaired quantity rises into the Core Open while the unpaired side remains stable, the final imbalance is increasingly composed of hard rather than price-contingent flow.

Hypothesis: this late hard-flow composition identifies opening demand likely to spill briefly into continuous hedging and wrapper repricing.

- Stable bid-side urgency: buy UPRO.
- Stable ask-side urgency: buy SPXU.

This is a hard-flow continuation hypothesis, not a claim that every final imbalance continues.

## Frozen feature rule

Use the latest SPY `auction_type == "M"` message strictly before 09:28:00 and 09:29:50 ET.

A signal exists only when:

1. both messages exist on a nondegraded session;
2. early and late `side` are equal and in `{A, B}`;
3. early and late `total_imbalance_qty` are positive;
4. early and late `market_imbalance_qty` are nonnegative;
5. late `market_imbalance_qty` is positive;
6. `late_market_imbalance_qty / late_total_imbalance_qty` is strictly greater than the corresponding early ratio;
7. late `ts_event` and `ts_recv` are strictly before 09:29:50 ET.

There is no fitted quantity, share, price, volatility, gap, collar, weekday, or spread threshold. The 2025-11-13 quantity-basis change is handled by using a within-session ratio change and by requiring temporal-extension participation; it is still a documented regime risk.

## Frozen execution proposal if feasibility passes

- `B` -> long UPRO; `A` -> long SPXU.
- Fixed $100 fractional position; no margin, shorting, or borrowing.
- Primary entry: first valid trade-event ask after 09:30:05.
- Exit: first valid trade-event bid after 09:35:00.
- Maximum wait: 60 seconds.
- One-second (09:30:01) and 60-second (09:31:00) entries are fixed robustness diagnostics on their available matched subsets, not timing choices and not required to manufacture primary coverage.
- Reject crossed and nonpositive quotes.

## Institutional smell test

### Why a desk might listen

- Market-order composition has a direct auction-urgency interpretation.
- The rule is ordinal and threshold-free.
- Signal publication and receipt precede the order.
- It is unaffected by standing-quote-age assumptions at signal time.
- The hard-flow condition is falsifiable separately from raw final-sign continuation.

### Adversarial objections

1. Market-on-open flow is completed at the auction and may be exhausted rather than persistent.
2. The aggregate side may not identify the side of every market-order component cleanly.
3. The quantity-basis break can change ratio behavior despite within-session normalization.
4. Direction inherits V34's already-failed final-sign direction and is therefore highly contaminated.
5. EQUS.MINI can miss prompt executable observations even when the auction signal exists.
6. A positive result could be a few large opening-gap days rather than hard-flow persistence.

These are mandatory controls and rejection gates, not invitations to invert the rule later.

## Frozen returns-blind feasibility gates

All must pass:

1. At least 2.0 feature signals per declared week over 2021–2023.
2. At least 2.0 executable primary signals per declared week over 2023-03-28 through 2023-12-31.
3. At least 100 feature signals in each development year 2021, 2022, and 2023.
4. At least 20 feature signals in 2026 through 2026-07-24.
5. Minority side at least 20% in feature development and executable development.
6. Both UPRO and SPXU executable in development.
7. Primary entry-plus-exit actuator quote coverage at least 90% over overlap signals.
8. Relevant-side 1x/2x/3x 09:30:05 quote availability at least 80% of executable signals.
9. Identical action including cash at least 60% with a 09:29:30 late cutoff.
10. Identical action including cash at least 60% with a 09:29:59 late cutoff.
11. Signals must represent between 10% and 80% of otherwise eligible stable-side sessions, proving the market-order condition is neither vanishing nor a relabeling of almost every final-side day.
12. At least 20 signals must occur on or after the 2025-11-13 quantity-definition break.
13. Every signal `ts_event` and `ts_recv` must precede 09:29:50 and the 09:30:05 primary order target.

Failure is terminal. The rule may not be widened to market quantity merely being positive, side flips, lower share growth, another cutoff, or the opposite direction.

## P&L protocol only if feasibility passes

Freeze preregistration before reading exit bids:

- development 2023-03-28 through 2023-12-31;
- contaminated historical validation 2024–2025;
- temporal extension 2026;
- primary 09:30:05 ask-to-09:35 bid execution;
- fixed 09:30:01 and 09:31:00 delay diagnostics on matched subsets;
- fixed-$100 and compounded-$100 results;
- PF, win rate, cadence, drawdown, spread drag, event waits, years, sides;
- one-cent adverse entry and exit stress;
- remove ten best trades;
- matched passive SPY;
- raw final-sign V34 control, gap-sign control, recent-reference-momentum control, and one-session-shift market-share placebo;
- no repair, threshold search, sign inversion, or timing selection.

## Preimplementation decision

**Pass to returns-blind feasibility only.** No return calculation is authorized.
