# SPY Auction Price/Quantity Disagreement Handoff — Preimplementation Critique v36

## Institutional-interest question

**Would a senior Jane Street or Goldman Sachs ETF trading desk listen to this hypothesis and be genuinely intrigued?**

**Yes, for a bounded falsification.** The idea compares two distinct exchange-published auction objects—unpaired quantity side and indicative price displacement—rather than treating either as a generic bullish/bearish label.

## Exact hypothesis

Use the latest SPY ARCX.PILLAR `auction_type M` message with `ts_event` strictly before 09:29:50 New York time. Require positive `ref_price`, `ind_match_price`, `paired_qty`, and `total_imbalance_qty`, with side `A` or `B`.

Define indicative displacement as `ind_match_price / ref_price - 1`.

A price/quantity disagreement occurs when:

- the published imbalance side is bid (`B`) but indicative displacement is negative; or
- the published imbalance side is ask (`A`) but indicative displacement is positive.

The direction is the **price-setting direction**, opposite the unpaired quantity side:

- ask imbalance with positive displacement → long $100 UPRO;
- bid imbalance with negative displacement → long $100 SPXU.

No magnitude threshold is allowed.

## Mechanism

`total_imbalance_qty` identifies shares unpaired at the reference price. `ind_match_price` identifies the collar-constrained price that maximizes matched shares. When their directions disagree, the visible residual side is not the side controlling the price concession. The opposing limit-order curve has enough depth or urgency to move the match price against the imbalance label.

That disagreement can reveal which side actually owns the marginal clearing price. Auction participants receiving inventory at the uncross may continue hedging in SPY, baskets, or related products during the first minutes of continuous trading. The strategy trades only long cash ETFs.

This differs from V34, which traded unconditional final imbalance-side continuation, and from V35, which required a two-snapshot deterioration in paired absorption. V36 makes no claim that either final imbalance side or pressure growth is directional by itself.

## Why the new data is defining

OHLCV cannot identify a bid imbalance that clears below reference or an ask imbalance that clears above it. The exchange message directly separates quantity pressure from the indicative price-setting result. The 1x/2x/3x TBBO ladder can then test whether the price-setting direction is transmitted and executable after latency.

## Strongest skeptical desk response

### Is this merely opening momentum or the overnight gap?

Possibly. Indicative displacement can track the pre-open price path. Gap-only and recent-reference-momentum controls are mandatory. If they explain the result, reject the auction mechanism.

### Is disagreement a semantic artifact?

Possibly. `ref_price` is the price at which imbalance is calculated, not necessarily the immediately prevailing continuous-market midpoint. The rule must beat final-snapshot, gap, momentum, and paired-only controls and remain coherent across adjacent cutoffs.

### Is all information incorporated at the uncross?

That is the base case. Entry occurs only after 09:30:00 plus 1, 5, or 60 seconds. A same-timestamp-only effect fails.

### Is the ETF reaction simultaneous?

Likely. Survival at 60 seconds and in both UPRO and SPXU is mandatory. A result isolated to one thin inverse wrapper fails the institutional story.

### Is apparent performance just spread variation?

Observed ask-to-bid P&L, midpoint P&L, spread drag, event wait, cross-leverage scaling, and one-cent-per-share adverse stress are separate outputs. No passive or midpoint fill may be promoted.

### Would an informed market maker eliminate it?

Probably, unless the uncross transfers inventory faster than all wrappers and hedges normalize. The five-minute horizon is intentionally short; failure is expected and informative.

### Is this a repair of failed V34 by flipping its sign?

No unconditional inversion is permitted. V36 trades only sessions where quantity side and indicative price direction conflict, based on a pre-P&L claim that price-setting dominance is more informative than residual-side labeling. The unconditional sign flip remains prohibited and is a mandatory placebo.

### Is time, side, leverage, threshold, or holding period selected from outcomes?

No V36 return has been viewed. The cutoff is 09:29:50, disagreement is sign-only, direction is mechanically determined, entries are frozen at 1/5/60 seconds after 09:30, and exit is 09:35. Adjacent cutoffs are stability diagnostics, not selectable alternatives.

## Falsifiable predictions

1. Usable signals exceed two per week and each side exceeds 20%.
2. At least 100 feature signals occur in each full 2021–2023 development year.
3. UPRO and SPXU entry/exit coverage is sufficient at all delays.
4. Actions remain reasonably stable at preregistered adjacent 09:29:30 and 09:29:59 cutoffs.
5. The rule is not at least 80% directionally identical to opening-gap or recent-reference-momentum controls.
6. Actual price/quantity disagreement beats reversed sign, previous-session imbalance, one-session shift, time permutation, paired-only, gap-only, momentum-only, volatility/spread matching, final-snapshot continuation, and randomized session matching.
7. Leverage-scaled response is coherent across SPY/SSO/UPRO and SH/SDS/SPXU.
8. Both directional regimes and every major calendar partition contribute positively after executable spread.

## Frozen execution boundary

- Signal: latest eligible `M` message strictly before 09:29:50 ET.
- Entry: first valid trade-event ask after 09:30:00 plus 1, 5, or 60 seconds, within 60 seconds.
- Exit: first valid trade-event bid after 09:35:00, within 60 seconds.
- Position: fixed $100 fractional long UPRO or SPXU; no compounding, overlap, shorting, margin, or overnight hold.
- Stop: none.
- Primary exclusions: union of ARCX.PILLAR and EQUS.MINI degraded dates, abnormal status sessions, crossed/nonpositive quotes, and missing fills.
- Costs: zero commission explicitly assumed, observed spread separated, plus one cent per share adverse stress at entry and exit.

## Decision

**Pass one returns-blind feasibility audit.** If it fails, calculate no V36 P&L and do not add a displacement magnitude, quantity threshold, different cutoff, or alternate exit.
