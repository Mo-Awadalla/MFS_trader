# Leveraged-ETF Opening-Auction Demand Consensus — Preimplementation Critique v40

## Chronology and causal novelty

V40 follows terminal returns-blind failures in V37–V39; none had P&L opened. V40 does not modify those auction-state rules.

The defining data are synchronized official ARCX Core Opening auction quantities for UPRO, SPXU, SSO, and SDS. Earlier wrapper-flow studies used minute bars, sampled BBO geometry, or signed last sales. V40 instead measures each instrument's own opening-auction participation surprise relative to its own causal history, then asks whether the 2x and 3x long/inverse pairs agree.

This is not a claim that official auction quantity proves creations/redemptions, AP inventory, or beneficial-owner identity. It is a direct primary-listing participation measurement.

## Economic hypothesis

Directional allocators and hedgers choosing leveraged long versus inverse ETFs can express demand in the opening auctions. Raw share quantities are not comparable across products, so each product is normalized by its own trailing 20-session median Core Opening quantity, using only prior sessions.

Define `surprise(symbol) = current opening quantity / trailing-20 median opening quantity`.

- Bullish consensus: `UPRO surprise > SPXU surprise` and `SSO surprise > SDS surprise`; buy UPRO.
- Bearish consensus: `UPRO surprise < SPXU surprise` and `SSO surprise < SDS surprise`; buy SPXU.
- Pair disagreement or exact ties: cash.

The 2x pair is confirmation, not a fitted filter. No surprise-magnitude threshold is allowed.

Hypothesis: same-direction leveraged/inverse auction participation across two leverage tiers identifies directional cash demand that continues briefly into continuous repricing.

## Frozen signal construction

1. Decode ARCX `OPENING_PRICE` statistics for UPRO, SPXU, SSO, and SDS.
2. Require exactly one positive-price, positive-quantity record per symbol/session.
3. For each symbol, compute the median of its immediately preceding 20 eligible session quantities; the current session is excluded.
4. Require 20 prior observations for every symbol.
5. Apply the two strict pairwise comparisons above.
6. Require all four statistics' `ts_event` and `ts_recv` before 09:30:05 ET.
7. Exclude the union of ARCX and EQUS degraded dates from primary eligibility.

No price return, gap, imbalance side, auction indication, AUM, weekday, volatility, quantity magnitude, or spread condition forms the signal.

## Frozen execution proposal if feasibility passes

- Bullish consensus -> fixed $100 fractional long UPRO.
- Bearish consensus -> fixed $100 fractional long SPXU.
- Primary entry: first valid trade-event ask after 09:31:05 ET.
- Exit: first valid trade-event bid after 09:35:00 ET.
- One-second diagnostic: 09:31:01 entry.
- 60-second diagnostic: 09:32:00 entry.
- Maximum event wait: 60 seconds.
- Reject crossed/nonpositive quotes.
- No margin, borrowing, shorting, or overnight holding.

The signal has at least 60 seconds of publication margin before the primary entry. EQUS.MINI remains trade-event-conditioned, so event wait is measurable but standing-quote age is not.

## Institutional smell test

### Why a desk might listen

- It measures official auction participation rather than inferred last-sale aggression.
- Self-normalization avoids comparing raw share counts across structurally different ETFs.
- Agreement across independently traded 2x and 3x pairs is a direct cross-instrument coherence test.
- The rule is threshold-free and causal.
- It is unaffected by the SPY imbalance quantity-definition break.

### Adversarial objections

1. Auction share quantity is not dollar notional, AUM-normalized flow, or creation/redemption activity.
2. Split history or structural volume drift can distort trailing medians.
3. Leveraged and inverse auction quantities can reflect liquidity provision rather than directional demand.
4. The 2x confirmation may reduce cadence or merely duplicate a broad opening-risk-on state.
5. A 09:31 entry may arrive after the information is incorporated.
6. Historical outcomes and wrapper families are heavily contaminated.

These objections become feasibility, price-control, and robustness tests—not post-result parameter changes.

## Frozen returns-blind feasibility gates

All must pass before preregistration or P&L:

1. At least 2.0 feature signals per declared calendar week over 2021–2023 after rolling-history warmup.
2. At least 2.0 executable primary signals per declared week from 2023-03-28 through 2023-12-31.
3. At least 100 feature signals in each full development year 2022 and 2023; 2021 is warmup-affected and must still contain at least 80.
4. At least 20 feature signals in 2026 through 2026-07-24.
5. Minority direction at least 20% in feature development and executable 2023 development.
6. Both UPRO and SPXU executable in 2023 development.
7. Primary entry-plus-exit actuator quote coverage at least 90% over overlap signals.
8. Relevant-side 1x/2x/3x 09:31:05 quote availability at least 80% of executable signals.
9. Identical action including cash at least 70% when trailing median length is 10 sessions.
10. Identical action including cash at least 70% when trailing median length is 40 sessions.
11. Direction agreement with the sign of SPY's official close-to-open return must be below 80%.
12. Pair consensus must select between 20% and 80% of otherwise eligible four-symbol sessions.
13. Every selected official statistic must be unique and received before 09:30:05; every entry observation must follow signal receipt.
14. No symbol may have an unexplained zero/negative quantity in a selected signal.

Failure is terminal. The 20-session window, pair confirmation, strict inequalities, actuator, coverage gates, and clocks may not be changed after feasibility is read.

## Frozen alpha protocol only if feasibility passes

Preregister before reading exit bids:

- development: 2023-03-28 through 2023-12-31;
- contaminated validation: 2024–2025;
- temporal extension: 2026 through 2026-07-24;
- primary 09:31:05 entry, 09:35 exit;
- 09:31:01 and 09:32:00 fixed delay diagnostics on matched subsets;
- fixed-$100 and compounded-$100 ask-to-bid results;
- PF, win rate, cadence, drawdown, spread drag, waits, years, and directions;
- one-cent adverse entry and exit stress;
- remove ten best trades;
- matched-session passive SPY;
- controls: SPY official overnight direction, UPRO-vs-SPXU price-return comparison, raw total opening quantity, and one-session-shifted quantity consensus;
- no timing choice, sign inversion, rolling-window selection, or magnitude threshold.

## Preimplementation decision

**Pass to returns-blind feasibility only.** No P&L is authorized yet.
