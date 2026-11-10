# Institutional SPY Cash-ETF Research Report v50

## Decision

Three new cash-only mechanisms were frozen before measurement. None authorized P&L.

V50 is the strongest new non-survivor: it met cadence, annual participation, directional balance, timing, control-distinctness, and event-wait gates. It failed the frozen adjacent-window stability gate by 0.123 percentage point and the execution-coverage gate by 2.613 percentage points. Those misses are binding.

No threshold, clock, actuator, synchronization cap, or gate was changed after inspection. No paid data or API call was made.

## Candidate results

| Version | Economic hypothesis | Returns-blind evidence | Terminal result |
|---|---|---|---|
| V48 | A 3× official opening price lagging its lower-leverage consensus catches up after the open | 310 development signals; balanced 169 UPRO / 141 SPXU; 83.7% action stability under both 10/40 baselines | 1.982/week, 95 signals in 2023, and some six-statistic publication times after 09:30:01; no P&L |
| V49 | A synchronized lower-leverage fair-value simplex identifies one underpriced 3× wrapper | Only 20 synchronized warm sessions and 13 signals over the entire overlap | Zero development signals because strict five-second synchronization was unavailable; no P&L |
| V50 | Accelerating late indicative-price revision intensity carries auction price discovery into continuous trading | 365 development signals, 2.333/week; 115/116/134 signals in 2021/22/23; 73 in 2026; balanced 161 UPRO / 204 SPXU | Left-window identical action 59.877% < 60%; execution coverage 87.387% < 90%; no P&L |

## Economic hypothesis versus data evidence

V48's cross-leverage official-price basis was economically coherent and stable to trailing-window length. The data rejected its frozen cadence and publication boundary before an exact execution study was justified.

V49 directly tested whether the new TBBO feed could support a desk-style six-fund lead/lag residual. It could not. The problem was not a losing backtest: the defining synchronized state was almost never observable. A trade-conditioned record cannot be silently promoted into a complete standing quote.

V50 isolated a genuinely new auction observable. Revision-rate acceleration selected 54.6% of sessions with nonzero late indicative moves. Its direction agreed only 45.0% with the opening gap, 70.0% with the early-window move, and 54.4% with final imbalance side. Thus it was not merely a renamed gap or final-sign rule. It nevertheless failed the preregistered stability and execution-evidence gates.

## Executable result

There is no executable return result because no candidate cleared returns-blind feasibility.

For V50, 103 executable 2023 development signals would have supplied 2.584 trades/week with balanced directions, and the primary event-wait p95 was 24.77 seconds. Across the full TBBO overlap, however, only 388 of 444 feature signals had complete 1/5/60-second entry and exit evidence, or 87.387%. Opening the covered subset's P&L would condition the result on a failed availability gate.

## Robustness result

No alpha robustness was authorized. The applicable robustness findings are pre-return:

- V48 was stable to 10/40-session basis windows but missed cadence and publication timing.
- V49 failed synchronization and adjacent-clock stability decisively.
- V50 passed the right-shifted window at 65.385% identical action including cash but failed the left shift at 59.877%. Selecting the passing shift would be timing optimization.
- V50 passed all frozen simpler-direction controls but failed execution coverage.

## Contamination risk

The fields are new relative to V1–V33, but the historical price outcomes are not pristine. V48–V50 add three more attempted families to an already large multiple-testing registry. Even a later historical survivor would require prospective forward paper trading; no historical result from this repository alone can establish production readiness.

## What remains unknown

1. Whether V50's event-intensity state has positive expectancy. Its return remains deliberately unopened.
2. Whether V49's simplex exists in complete quote-update data; trade-event TBBO cannot answer.
3. True standing quote age and quote-only repricing.
4. Whether any auction effect survives a prospectively frozen 1/5/60-second shadow-execution test.
5. ETF iNAV/NAV, baskets, creations/redemptions, AP inventory, and hedge flow.

## Required forward evidence

The highest-value next step is not a V50 clock or gate repair. It is either:

- a complete quote-update or official consolidated BBO feed with observable quote age, collected without changing the economic rule; or
- a new prospective SPY auction-message collection with a separately frozen causal mechanism and at least 100 nonoverlapping paper trades across both directions.

Any forward paper test must execute fixed $100 long-only cash ETF orders, record asks/bids and 1/5/60-second delays, remain flat overnight, and preserve failed historical rules unchanged.

## Reproducibility

- V48 critique: `research_scout/LEVERAGED_ETF_OFFICIAL_OPEN_BASIS_CATCHUP_PREIMPLEMENTATION_CRITIQUE_V48.md`
- V48 audit: `python research_scout/audit_leveraged_etf_official_open_basis_v48.py`
- V49 critique: `research_scout/LEVERAGED_ETF_POST_OPEN_FAIR_VALUE_SIMPLEX_PREIMPLEMENTATION_CRITIQUE_V49.md`
- V49 audit: `python research_scout/audit_leveraged_etf_post_open_simplex_v49.py`
- V50 critique: `research_scout/SPY_AUCTION_REVISION_INTENSITY_ACCELERATION_PREIMPLEMENTATION_CRITIQUE_V50.md`
- V50 audit: `python research_scout/audit_spy_auction_revision_acceleration_v50.py`
- Machine summary: `research_scout/cash_etf_auction_research_results_v50.json`
- Registry: `research_scout/CASH_ETF_HYPOTHESIS_REGISTRY_V34.md`
