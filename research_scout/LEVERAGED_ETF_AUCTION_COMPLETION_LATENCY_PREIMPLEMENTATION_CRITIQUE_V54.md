# Leveraged-ETF Auction Completion-Latency Consensus — Preimplementation Critique v54

## Final screening decision

**Reject before feasibility. Do not run the prototype or inspect returns.**

Program-level review found that V54 violates the learned stopping boundary:

1. It reuses V40's exact 2×/3× long-versus-inverse pair-consensus structure and substitutes event timing for quantity.
2. The subsecond statistic order may be publisher serialization rather than economic auction difficulty.
3. V40, V48, V50, V51, and V53 already demonstrate the same 87–89% leveraged-actuator execution-evidence ceiling at nearby clocks.
4. Testing another field through the same comparison topology would increase multiplicity without creating a sufficiently independent causal object.

The remainder below records the proposed rule so it cannot be rediscovered under a new name. It is a rejection record, not an authorization.

## Hypothesis

Official Core Opening statistics carry event timestamps for UPRO, SPXU, SSO, and SDS. Products whose opening auctions are harder to clear may complete or publish later within the opening second. Raw symbol latency can contain deterministic sequencing, so each product is centered by its own trailing 20 eligible sessions.

For each symbol:

`latency_surprise = current OPENING_PRICE event time after 09:30:00 - trailing-20 median latency`

- Bullish consensus: UPRO surprise > SPXU surprise and SSO surprise > SDS surprise; buy UPRO.
- Bearish consensus: UPRO surprise < SPXU surprise and SSO surprise < SDS surprise; buy SPXU.
- Disagreement or ties: cash.

No price, quantity, imbalance, gap, spread, or return enters the signal.

## Institutional mechanism

A same-direction delay across two leverage tiers can indicate that one side of the leveraged/inverse complex required more time to source offsetting auction liquidity. Dealers supplying those auctions may hedge in the underlying after completion, while continuous-market quoting in the 3× wrapper catches up. Cross-tier agreement distinguishes a directional liquidity state from a single-symbol processing delay.

The effect should disappear when ordering is deterministic by symbol, when timing surprises are below timestamp noise, or when hedging finishes before the one-minute signal boundary.

## Strongest skeptical response

- ARCX may serialize statistics in a stable instrument/channel order unrelated to auction difficulty.
- Subsecond timestamps can reflect processing rather than economic completion.
- The signal may be another version of V40's quantity consensus with a different field.
- Auction completion may occur simultaneously even if statistics are received sequentially.
- Public information should be incorporated well before 09:31.
- UPRO/SPXU execution coverage may remain insufficient.

V54 explicitly tests these objections. It is rejected if one direction dominates, if the latency margin is not materially above one millisecond, if action is unstable to trailing-window length, or if it duplicates V40 quantity consensus.

## Why this is new

V40 measured self-normalized official auction quantities. V54 measures event timing only. V48 measured opening prices. V49 measured continuous quote synchronization. No earlier candidate used official cross-product auction-completion timing as the causal field.

## Frozen returns-blind gates

1. At least two feature signals per week in 2021–2023.
2. At least 100 signals per development year and 20 in 2026.
3. Both directions with minority at least 20%.
4. At least two executable 2023-overlap trades per week, both actuators, and 20% minority.
5. At least 90% complete 1/5/60-second entry-plus-exit evidence.
6. Primary entry wait p95 no more than 30 seconds and every wait no more than 60.
7. Ten- and 40-session baselines each at least 70% identical action including cash.
8. Direction agreement below 80% with V40 quantity consensus and the SPY official opening gap.
9. Consensus selects between 20% and 80% of warm eligible sessions.
10. Median minimum pair-comparison timing margin on selected sessions exceeds one millisecond.
11. Every required statistic is received before 09:31:00 and every entry follows that boundary.

## Frozen execution if feasible

- Signal boundary: 09:31:00 ET.
- Entry asks after 09:31:01, 09:31:05, and 09:32:00.
- Primary entry: 09:31:05.
- Exit bid after 09:35:00.
- Fixed $100 fractional long UPRO or SPXU; no margin, shorting, overlap, or overnight.

## Decision

**Rejected before feasibility.** No V54 audit JSON, preregistration, or P&L is authorized. Reopening requires evidence that official statistic timing represents economic completion rather than deterministic publication order, plus execution data that resolves the known coverage ceiling.
