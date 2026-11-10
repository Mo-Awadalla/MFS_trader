# SPY Early-Opening Auction to Premarket Handoff — Preimplementation Critique v43

## Why continue here

The current package contains a distinct auction protocol that V34–V42 did not use as a trading sensor: NYSE Arca's 04:00 Early Opening auction (`auction_type = O`, projected `auction_time = 04:00:00`). V34–V40 used the Core Opening auction, and V41–V42 used the Closing auction. V43 asks whether early-auction residual pressure persists into the later premarket, with the position closed before the Core Open.

This is not permission to modify V34's failed Core-Opening sign continuation. No Core Opening field participates in the signal, and the position is closed before 09:30.

## Economic hypothesis

The 04:00 Early Opening auction clears overnight interest when liquidity is thin and fragmented. A nonneutral residual side at the final public pre-cross state may identify overnight demand that is too large to be fully satisfied at that facility. As more participants and venues become active, the residual pressure may continue through the premarket.

This is a public-flow persistence hypothesis, not an AP/dealer attribution claim. The data cannot identify who submitted the interest.

## Frozen signal

For each New York session date:

1. Use only SPY `auction_type = O` messages whose projected exchange-local `auction_time` is exactly `04:00:00`.
2. Select the latest `ts_event` strictly before 03:59:50 ET.
3. Exclude ARCX degraded dates.
4. Require `side` in `{B, A}`, positive `ind_match_price`, and positive `total_imbalance_qty`.
5. `B` maps to long UPRO; `A` maps to long SPXU.
6. No magnitude, price-return, gap, Core-auction, weekday, volatility, spread, or status condition enters the signal.

The quantity requirement is a validity check only. No quantity level or change is compared across the 2025-11-13 semantic break.

## Frozen execution proposal if feasibility passes

- Fixed $100 fractional long position; otherwise cash.
- Primary entry: first valid trade-event pre-trade ask at or after 07:01:00 ET, no later than 60 seconds after the target.
- Timing diagnostics: the same rule at 07:00:01 and 07:05:00.
- Exit: first valid trade-event pre-trade bid at or after 09:20:00, no later than 60 seconds after the target and strictly before 09:30.
- UPRO for `B`; SPXU for `A`.
- Reject nonpositive and crossed quotes.
- Do not forward-fill a missing trade-event BBO.
- No shorting, margin, stop, target, overnight position, passive fill, or same-auction fill.

The long signal-to-entry delay is deliberate: it asks whether an Early Opening state survives until a liquid-enough premarket clock rather than pretending the available feed supports a 04:00 retail latency race.

## Contamination and novelty audit

- V34 tested final Core-Opening side after 09:30. V43 uses only the Early Opening protocol and exits before Core Opening.
- V31 tested prior-close/current-open accepted-value memory, not an official 04:00 auction residual.
- V16/V25 used signed continuous last-sale flow, not exchange-published Early Opening imbalance.
- No V1–V42 result determines V43's side, clocks, or exit.
- Agreement with the later 09:29:50 Core side is a returns-blind novelty control, not a signal condition.

V43 is still part of the same broad auction research program and counts against familywise multiplicity.

## Mandatory returns-blind feasibility gates

All gates are frozen before extraction of the 04:00 snapshots or new quote targets:

1. At least 2.0 eligible development features per declared week during 2021–2023.
2. At least 100 features in each full development year 2021, 2022, and 2023.
3. At least 20 features on the minority side during development.
4. At least 2.0 executable development-overlap signals per declared week from 2023-03-28 through 2023-12-31.
5. At least 20 executable development-overlap signals on the minority side.
6. At least 90% complete primary entry-plus-exit quote coverage on nondegraded overlap signals.
7. At least 85% complete coverage at each diagnostic entry target plus the same exit.
8. Median proportional quoted spread at each actuator's primary entry is at most 15 basis points; the 95th percentile is at most 50 basis points.
9. At least 80% identical action including cash when the Early Opening snapshot cutoff moves to 03:59:30 and to 03:59:59.
10. At least 20 signals in 2026 and at least 20 after 2025-11-13.
11. Direction agreement with the later Core-Opening side is below 80% on days where both are observed; otherwise V43 is treated as a delayed copy of the consumed V34 sensor.
12. Every selected Early Opening message is received before the 07:00:01 diagnostic order target.
13. Every entry quote is received after the selected signal message, and every exit event occurs strictly before 09:30.
14. Excluding degraded dates is fixed independently of outcomes.

If any gate fails, V43 terminates without P&L. Do not change the Early Opening clock, quantity validity checks, actuator mapping, entry clocks, exit, or coverage thresholds.

## Smell test

### Strong aspects

- Uses a genuinely unused exchange protocol and time interval.
- Signal is known hours before execution.
- Position is flat before the Core Open.
- Frequent Early Opening messages exist across the full feature history.
- The rule is ordinal and simple.

### Weak aspects

- Residual side is public and may be fully cleared at 04:00.
- Three hours between signal and primary entry may eliminate the mechanism.
- Premarket leveraged-ETF spreads may be too wide.
- A final pre-cross state does not prove the same pressure remains after the uncross.
- EQUS.MINI remains trade-event-conditioned and cannot prove standing quote age.

## Decision before field inspection

Proceed to one returns-blind feasibility audit. Do not calculate a return unless every gate passes.
