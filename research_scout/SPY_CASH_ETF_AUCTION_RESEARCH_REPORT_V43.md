# Institutional Cash-ETF and Auction Research Report v43

## Decision

**V43 failed its frozen returns-blind feasibility gates. No V43 return or P&L was calculated.**

The final SPY 04:00 Early Opening imbalance side was frequent, directionally balanced, stable to neighboring snapshot cutoffs, and only weakly related to the later Core Opening side. The available EQUS.MINI TBBO package could not reconstruct a remotely adequate UPRO/SPXU premarket execution panel at the frozen clocks, and the SPY Early Opening feature disappeared from the supplied 2026 imbalance history.

V43 is terminal. Its 04:00 auction cutoff, side mapping, 07:01 entry, 09:20 exit, spread limits, and evidence gates may not be widened or repaired.

## Frozen mechanism

- Use only SPY NYSE Arca Early Opening (`auction_type = O`) messages for the projected 04:00 auction.
- Select the latest state strictly before 03:59:50 ET.
- Require a nonneutral side, positive indicative match price, and positive total imbalance quantity.
- Map bid imbalance to long UPRO and ask imbalance to long SPXU.
- Primary entry: first valid trade-event pre-trade ask at or after 07:01, within 60 seconds.
- Exit: first valid trade-event pre-trade bid at or after 09:20, within 60 seconds and strictly before 09:30.
- Remain flat overnight and through the Core Open.

The mechanism asked whether thin-liquidity 04:00 residual demand survives into the later premarket. It did not use any Core Opening field as a signal.

## Returns-blind result

| Measurement | Result |
|---|---:|
| Development features, 2021–2023 | 725 |
| Development features per declared week | 4.635 |
| Development sides | 329 bid / 396 ask |
| Executable 2023 development signals | 1 |
| Executable development cadence | 0.025/week |
| All-overlap feature signals | 612 |
| All-overlap primary executable signals | 24 |
| Primary 07:01 entry-plus-exit coverage | 3.92% |
| 07:00:01 diagnostic coverage | 6.05% |
| 07:05 diagnostic coverage | 5.72% |
| Primary median entry spread | 4.42 bps |
| Primary entry spread p95 | 44.94 bps |
| 07:00:01 entry spread p95 | 329.31 bps |
| 03:59:30 identical action including cash | 94.05% |
| 03:59:59 identical action including cash | 91.84% |
| Agreement with later Core Opening side | 50.98% |
| 2026 features | 0 |
| Post-2025-11-13 features | 0 |

## Gates that passed

- At least two development features per week.
- At least 100 features in each full development year.
- Adequate development side balance.
- More than 80% identical action at both neighboring snapshot cutoffs.
- Less than 80% direction agreement with the later Core Opening side.
- Every signal was received before the earliest proposed order.
- Every retained entry followed signal receipt and every retained exit preceded 09:30.
- Frozen degraded dates were excluded.

## Terminal gate failures

1. Executable development cadence was 0.025/week rather than at least 2/week.
2. The executable development minority side had zero observations rather than at least 20.
3. Primary entry-plus-exit quote coverage was 3.92% rather than at least 90%.
4. Both diagnostic timing-coverage gates failed by a wide margin.
5. The 07:00:01 entry spread p95 was 329.31 bps rather than at most 50 bps.
6. No 2026 or post-quantity-break Early Opening features were present.

## Interpretation

The causal feature itself was not the problem in the historical 2021–2025 panel: it appeared almost daily, remained stable across nearby final-snapshot clocks, and was not a delayed copy of the Core Opening side. The blocker was executability and temporal continuity.

EQUS.MINI TBBO is trade-event-conditioned. A missing premarket event does not prove that no standing quote existed, but it also does not authorize forward-filling an unobserved quote. Only 24 of 612 overlap features had both the frozen 07:01 entry and 09:20 exit evidence. That is too incomplete to estimate a historical strategy honestly.

The absence of 2026 Early Opening features is a second independent failure. It prevents treating the rule as a recurring current mechanism even if a future complete quote feed solved the execution reconstruction problem.

## Outcome-control policy

No V43 post-entry return, compounded equity, profit factor, SPY comparison, best-trade deletion, cost stress, or placebo was opened. Do not move the entry later, replace UPRO/SPXU with SPY/SH, use a midpoint, forward-fill premarket quotes, alter the Early Opening cutoff, or switch to the later Core Open using this result.

## Reproducibility

- Preimplementation critique: `research_scout/SPY_EARLY_OPENING_AUCTION_TO_PREMARKET_HANDOFF_PREIMPLEMENTATION_CRITIQUE_V43.md`
- Snapshot and quote extraction: `python research_scout/extract_spy_early_opening_premarket_v43.py`
- Returns-blind feasibility: `python research_scout/audit_spy_early_opening_to_premarket_v43.py`
- Machine result: `research_scout/spy_early_opening_to_premarket_returns_blind_audit_v43.json`
- Registry: `research_scout/CASH_ETF_HYPOTHESIS_REGISTRY_V34.md`

No paid API call was made during this continuation.
