# SPY Opening-Auction Absorption-Failure Handoff — Preimplementation Critique v35

## Institutional-interest question

**Would a senior Jane Street or Goldman Sachs ETF trading desk listen to this hypothesis and be genuinely intrigued?**

**Yes, for one bounded falsification—not because it is complex, but because the defining state is exchange-published auction absorption dynamics that ordinary OHLCV cannot observe.** It is not deployment-ready and may be too public or too fast for a retail cash account.

## Exact economic hypothesis

At two fixed, pre-open observations—latest NYSE Arca SPY `auction_type M` messages strictly before 09:28:00 and 09:29:50 New York time—measure:

1. imbalance side;
2. unpaired pressure share, `total_imbalance_qty / (paired_qty + total_imbalance_qty)`;
3. side-signed indicative displacement, `side_sign × (ind_match_price / ref_price - 1)`, where bid is +1 and ask is −1.

An **absorption failure** exists only when:

- both snapshots have the same non-neutral side;
- all prices and quantities required above are positive;
- unpaired pressure share increases;
- side-signed indicative displacement increases and is positive at 09:29:50.

The claim is not that a large final imbalance predicts price. The claim is that, while the deadline approaches, paired auction liquidity is losing relative ground and the indicative clearing state is moving in the pressure direction. The opening uncross may transfer residual inventory demand into the continuous market before the leveraged ETF ladder fully settles.

Bid-side failure maps to a long $100 UPRO position. Ask-side failure maps to a long $100 SPXU position. No ETF is shorted.

## Concrete institutional mechanism

Deadline-bound benchmark, market-on-open, and risk-transfer orders demand immediacy. Opposing liquidity suppliers and arbitrageurs can absorb them by adding paired quantity or improving the indicative match. A falling absorption ratio in the final two minutes says the opposite side is not keeping pace. A contemporaneous side-consistent indicative displacement says price, not only quantity, is conceding.

At the handoff, auction participants may receive inventory they hedge in SPY, futures, baskets, or correlated ETFs; the strategy itself trades only cash ETFs. Leveraged wrappers mechanically reprice to the underlying, but their displayed trade-event BBOs may absorb public pressure through spread and depth before the midprice completes its short adjustment.

The proposed edge must survive public observability because it is conditional on **deteriorating absorption**, not mere publication of a final imbalance. If informed market makers fully pre-hedge or the uncross clears all pressure, the effect disappears.

## Why the new data is defining

Ordinary bars cannot distinguish:

- imbalance growth from successful pairing;
- price movement caused by auction-only interest from ordinary premarket trades;
- a stable final side from worsening absorption;
- the message publication path from the realized opening print.

ARCX.PILLAR directly supplies reference, indicative, paired, and imbalance fields with event timestamps. EQUS.MINI supplies marketable pre-trade BBO evidence across the leverage ladder, subject to its trade-event and non-SIP limitations.

## Falsifiable predictions frozen before P&L

1. Signals occur at least twice per calendar week over usable overlap and both sides exceed 20%.
2. The feature is not mostly a relabeling of the opening gap or recent reference-price momentum.
3. Adjacent late snapshots at 09:29:30 and 09:29:59 produce materially consistent actions without changing the rule.
4. UPRO and SPXU both have sufficient valid first-event asks after 1, 5, and 60 seconds and bids at 09:35.
5. The actual trajectory beats final-snapshot, gap-only, momentum-only, paired-quantity-only, previous-session, shifted-session, sign-reversed, time-permuted, volatility/spread-matched, and randomized-session controls.
6. Consistent leverage-scaled response should be visible across SPY/SSO/UPRO or SH/SDS/SPXU. If only one thin wrapper appears profitable, the institutional story fails.
7. Profit should decay coherently with latency, not appear only at the causal timestamp or only after a longer delay.
8. The effect should weaken or vanish when absorption share does not deteriorate.

## Strongest skeptical desk response

### Is this merely opening momentum or gap continuation?

Possibly. Side-signed indicative displacement and a rising unpaired share can covary with the overnight gap and pre-open return. Gap-only and recent-momentum controls are mandatory. If they explain the result, reject the auction story.

### Is auction imbalance already incorporated into SPY?

It should be rapidly incorporated by professional liquidity providers. The hypothesis survives only if the *trajectory of absorption failure* conveys marginal inventory information that the final published level does not. Same-timestamp profitability is insufficient.

### Is ETF response simultaneous rather than tradably delayed?

This is the leading risk. Entries are tested after 1, 5, and 60 seconds using the first eligible marketable ask. Failure at 60 seconds, or only same-event success, is terminal for this account.

### Is the apparent edge just spread variation?

Executable ask-to-bid P&L, midpoint P&L, spread drag, quote-event wait, and one-cent-per-share adverse stress are separated. Spread-matched controls and cross-leverage response comparisons are required.

### Is the leveraged ETF mechanically tracking NAV with no exploitable lag?

Very likely. A statistically meaningful SPY handoff can still be unmonetizable after 3x-wrapper spreads. The test rejects that case rather than calling it alpha.

### Does the signal depend on crisis sessions?

Best-trade deletion, year partitions, extension/freeze-session exclusion diagnostics, and concentration reporting are mandatory.

### Is this a timestamp-alignment artifact?

Features use `ts_event` strictly before 09:29:50. Orders occur after 09:30:00 plus latency. `auction_time`, final opening price, final match state, and post-auction messages are not signal inputs. `ts_recv` is audited but cannot move information backward.

### Is it economically meaningful but impossible to execute?

Yes, that is plausible because EQUS.MINI TBBO is trade-event-conditioned and true standing-quote age is absent. Orders with no valid event within the frozen maximum wait are unfilled; no midpoint or forward-filled quote is allowed.

### Would an informed market maker already eliminate it?

Probably unless inventory risk, capital, or cross-product hedging frictions delay complete transfer. Survival through 60 seconds and one-cent stress is the minimum evidence against immediate elimination.

### Is the test secretly selecting auction time, side, leverage, threshold, or holding period from outcomes?

No V35 return has been viewed. The clocks are fixed at 09:28 and 09:29:50, conditions are ordinal rather than magnitude-fitted, side maps symmetrically to UPRO/SPXU, and liquidation is fixed at 09:35. Adjacent cutoffs are stability checks, not alternatives eligible for selection.

## Frozen implementation boundary

- Signal observations: latest `M` messages strictly before 09:28:00 and 09:29:50 ET.
- Entry target: 09:30:00 plus 1, 5, or 60 seconds.
- Fill: first valid trade-event ask within 60 seconds of target.
- Exit target: 09:35:00 ET; first valid trade-event bid within 60 seconds.
- Position: fixed $100 fractional long UPRO or SPXU; no compounding, shorting, overlap, or overnight hold.
- Stop: none.
- Primary exclusions: union of ARCX.PILLAR and EQUS.MINI degraded dates, invalid quotes, and abnormal status sessions under a rule fixed before returns.
- Costs: explicit zero commission assumption, observed spread, and an additional adverse one cent per share at entry and exit.

## Decision

**Pass one returns-blind feasibility audit.** If frequency, side balance, quote coverage, timing, stability, or control-distinctness fails, do not calculate V35 P&L and do not repair the rule. If feasibility passes, hash and freeze a preregistration before opening returns.
