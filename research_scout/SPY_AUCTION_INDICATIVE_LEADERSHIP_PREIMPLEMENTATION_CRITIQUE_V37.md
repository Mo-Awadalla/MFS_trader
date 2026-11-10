# SPY Auction Indicative-Leadership Handoff — Preimplementation Critique v37

## Chronology and contamination

V37 is a new numbered attempt. It does not invert, widen, or delete conditions from V34–V36:

- V34 consumed final opening-imbalance-sign continuation after negative development P&L.
- V35 consumed paired-absorption trajectory at its frozen cadence and stability gates without opening P&L.
- V36 consumed final price/quantity disagreement at its frozen adjacent-cutoff and all-six-evidence gates without opening P&L.
- V37 does not use imbalance side, paired quantity, total imbalance quantity, or market imbalance quantity to trigger or direct a trade. The 2025-11-13 quantity-definition break therefore cannot generate the signal.

Historical outcomes remain multiply exposed. Passing this critique or a returns-blind gate would not make later historical P&L pristine.

## Economic hypothesis

The ARCX Core Open carries two contemporaneous price processes:

1. `ref_price`, the exchange reference at which imbalance shares are calculated; and
2. `ind_match_price`, the price that maximizes matched auction shares subject to collars and including reserve quantity.

Between 09:28:00 and 09:29:50 ET, calculate the return of each process. Define **indicative leadership** as:

`indicative return - reference return`.

A signal exists only when the indicative return is nonzero and has the same sign as indicative leadership. This means the auction's executable clearing-price discovery moved farther in that direction than the reference process, or continued in that direction while the reference moved against it. It is not merely a final imbalance sign or a final indicative/reference level disagreement.

Hypothesized mechanism: late auction participants and reserve liquidity have moved the executable match price beyond the contemporaneous reference revision. The uncross transfers that incremental auction information into continuous ETF prices over the first few seconds after 09:30.

- Positive indicative leadership: buy UPRO.
- Negative indicative leadership: buy SPXU.

This is a short handoff, not a claim that a 3x ETF is intrinsically mispriced.

## Frozen returns-blind feature rule

Primary snapshots are the latest `auction_type == "M"` messages strictly before:

- early: 09:28:00 ET;
- late: 09:29:50 ET.

Eligibility:

1. Both snapshots exist on a nondegraded ARCX/EQUS session.
2. `ref_price` and `ind_match_price` are strictly positive at both snapshots.
3. `indicative_return = late_ind_match / early_ind_match - 1` is nonzero.
4. `leadership = indicative_return - (late_ref / early_ref - 1)` is nonzero.
5. `indicative_return * leadership > 0`.
6. The late message has both `ts_event` and `ts_recv` strictly before 09:29:50 ET.

No magnitude threshold, volatility normalization, side requirement, quantity filter, collar filter, day-of-week filter, gap filter, or outcome-conditioned exception is permitted.

## Frozen actuator and execution proposal if feasibility passes

- Positive leadership: long UPRO.
- Negative leadership: long SPXU.
- Fixed $100 fractional long position; no shorting, leverage borrowing, or margin.
- Marketable entry observations: first valid trade-event ask after 09:30:01, 09:30:05, and 09:31:00 ET.
- Exit observation: first valid trade-event bid after 09:35:00 ET.
- Maximum wait from every target to the first valid event: 60 seconds.
- Reject nonpositive and crossed quotes.
- Primary timing, if activated: 5-second entry. One- and 60-second entries are execution-delay robustness variants, not choices.

EQUS.MINI is trade-event-conditioned rather than an official complete quote feed. Event wait is observable; standing-quote age is not. That limitation must remain explicit.

## Institutional smell test

### Why a serious desk might listen

- The state variable has a venue-specific microstructure interpretation: auction executable-price discovery versus the exchange reference process.
- It uses only information published and received before the order.
- It avoids fitted thresholds and survives the 2025 quantity-definition break by not using quantity fields.
- It makes a directional statement that can be falsified separately from execution quality.
- The same-side 1x/2x/3x wrapper ladder can diagnose whether the actuator observation exists without requiring all six products on every signal.

### Adversarial objections

1. `ref_price` is not a live SIP midpoint. Leadership may be an exchange-protocol artifact rather than transferable information.
2. The rule may collapse to generic recent indicative momentum or the final indicative/reference displacement already implicated in V36.
3. Exact snapshot timing can make action membership unstable in the final seconds.
4. UPRO/SPXU may have no prompt trade-event quote even if the auction signal is valid.
5. A positive historical result could be concentrated in a few opening gaps or event-wait artifacts.
6. Historical outcomes and nearby auction families are already heavily contaminated.

These objections are gates, not parameters to tune after inspection.

## Frozen returns-blind feasibility gates

All must pass before a preregistration or P&L script may be created:

1. At least 2.0 feature signals per calendar week over 2021–2023.
2. At least 2.0 executable signals per calendar week over 2023-03-28 through 2023-12-31.
3. At least 100 feature signals in each of 2021, 2022, and 2023.
4. At least 20 feature signals in the 2026 temporal-extension window through 2026-07-24.
5. Minority direction share at least 20% in both feature development and executable development overlap.
6. Both UPRO and SPXU present in executable development.
7. Required actuator quote coverage at least 90% over the event-level overlap.
8. Relevant-side 1x/2x/3x five-second quote availability at least 80% of executable signals: SPY/SSO/UPRO for positive signals; SH/SDS/SPXU for negative signals. This is the economic ladder needed for the chosen direction; requiring the opposite ladder would add unrelated missingness.
9. Identical action including cash at least 60% when the late cutoff is changed to 09:29:30.
10. Identical action including cash at least 60% when the late cutoff is changed to 09:29:59.
11. Direction on fewer than 80% of signals may be explained by the sign of recent reference return.
12. Direction on fewer than 80% of signals may be explained by final indicative/reference displacement.
13. Direction on fewer than 80% of signals may be explained by the final published imbalance side.
14. Every signal's `ts_event` and `ts_recv` must precede 09:29:50 ET and the earliest 09:30:01 order.

A failure is terminal for this exact construction. No cutoff, condition, threshold, actuator, or gate may be relaxed after reading feasibility output.

## P&L and robustness protocol only if every feasibility gate passes

The preregistration must freeze before reading post-entry bids:

- development: 2023-03-28 through 2023-12-31;
- historical validation: 2024-01-01 through 2025-12-31, explicitly contaminated;
- temporal extension: 2026-01-01 through 2026-07-24;
- primary entry: 5 seconds; 1/60 seconds fixed delay diagnostics;
- fixed-$100 ask-to-bid P&L and compounded $100 equity;
- profit factor, win rate, trade cadence, maximum drawdown, spread drag, and event waits;
- both years and both directions positive in development where available;
- delete ten best trades;
- add one cent per share adverse entry and exit stress;
- compare to matched-session passive SPY;
- compare against gap sign, recent reference momentum, final indicative/reference displacement, raw imbalance side, and a one-session-shift placebo;
- no holdout repair, sign inversion, threshold search, or timing selection.

## Preimplementation decision

**Pass to returns-blind feasibility only.** The mechanism is coherent enough to count and audit, but no claim of alpha is made and no post-signal return is authorized yet.
