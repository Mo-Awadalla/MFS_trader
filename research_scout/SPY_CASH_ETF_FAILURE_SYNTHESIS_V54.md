# SPY Cash-ETF Failure Synthesis v54

## Decision

Historical hypothesis generation from the current auction snapshots and trade-event TBBO is paused.

This is not a claim that SPY day-trading alpha does not exist. It is a learned research boundary:

> The remaining easy-to-form hypotheses are mostly transformations, conjunctions, or clock variants of causal objects already consumed in V34–V53. Continuing to backtest them would increase multiple-testing risk faster than it increases independent evidence.

V54 was rejected before feasibility because it substituted official-statistic timing into V40's already-consumed pair-consensus topology. No V48–V54 P&L was opened.

## What the failures actually teach

### 1. Mechanistic specificity repeatedly destroys cadence

| Candidate | Mechanism | Development cadence |
|---|---|---:|
| V48 | Official-open 3× basis lag | 1.982/week |
| V51 | Prior Closing hard flow aligned with next Opening displacement | 0.633/week |
| V53 | Same-sign widening reserve-liquidity wedge | 1.342/week |

These are not invitations to delete conditions. They show that the directly measurable institutional states occur too infrequently under the fixed construction.

### 2. Trade-event TBBO is the recurring execution bottleneck

- V49 produced zero synchronized 2023 development signals under a five-second six-fund requirement.
- V50 achieved 87.387% complete 1/5/60-second-plus-exit evidence.
- V53 achieved 86.364%.
- Earlier V37/V40 results clustered around the same high-80% boundary.

The missing observations are not losing trades and cannot be safely forward-filled. Opening P&L only on observed sessions would select on data availability after a failed gate.

### 3. The most frequent new state was definition-sensitive

V52 was genuinely interesting:

- 579 development signals;
- 3.701/week;
- balanced directions;
- 90.649% complete execution evidence;
- controls distinct from gap, prefreeze movement, and final imbalance side.

But action including cash was only 36.675% when the start point moved from the last nonfrozen message to the first frozen message. The final result depended on whether the transition message belonged to the signal. That is a protocol-endpoint artifact risk, not a small robustness blemish.

Adding a tick threshold, choosing the penultimate endpoint, or using the favorable definition would be outcome-driven repair.

### 4. Real field differences need not create stable states

V53 used a genuine semantic distinction: `ind_match_price` versus auction-interest-only clearing price. It was independent of gap and final imbalance side, but its action changed drastically under neighboring clocks and its cadence decayed from 111 signals in 2021 to 29 in 2023.

The correct lesson is not to search more wedge windows.

### 5. A new column is not necessarily a new hypothesis

V54 proposed cross-leverage completion-latency consensus. Program-level review rejected it before measurement:

- the pair-comparison structure was V40's;
- official statistic ordering may reflect serialization;
- the same execution bottleneck was already known.

Rejecting V54 is the procedural improvement prompted by the accumulated failures.

## New acceptance standard

No further historical implementation should proceed unless its defining causal evidence is outside the consumed set.

Disallowed as “new”:

- another sign, level, slope, acceleration, flip, percentile, or conjunction of the current opening-auction fields;
- another neighboring opening or closing cutoff;
- another 1×/2×/3× comparison using trade-event-conditioned quotes;
- another long-versus-inverse pair consensus with a substituted field;
- a covered-session-only return after a quote-coverage failure.

Potentially independent:

1. Complete quote-update or official consolidated BBO history with true quote-age reconstruction.
2. Intraday iNAV/NAV, shares outstanding, creations/redemptions, baskets, and AP hedge evidence.
3. Prospectively frozen untouched auction and execution data collected after the rule is written.

No additional paid data should be acquired without explicit permission.

## Current strategy status

- No V48–V54 strategy is authorized for paper trading or production.
- V52's return remains unopened despite being the most feasible new state.
- V54 has no audit JSON because it was rejected before feasibility.
- The multiple-testing count remains cumulative.

## Reproducibility

- V51 audit: `python research_scout/audit_spy_cross_auction_inventory_persistence_v51.py`
- V52 audit: `python research_scout/audit_spy_core_open_freeze_transfer_v52.py`
- V53 audit: `python research_scout/audit_spy_auction_reserve_liquidity_wedge_v53.py`
- Registry: `research_scout/CASH_ETF_HYPOTHESIS_REGISTRY_V34.md`
- Machine synthesis: `research_scout/cash_etf_failure_synthesis_v54.json`
