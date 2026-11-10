# Primary-Flow / Opening-Auction Handoff Audit v61

## Verdict

**Returns-blind construction gates passed. A formal critique and preregistration may be written; P&L remains unopened.**

## Frozen construction

- State 1: prior-session split-adjusted UPRO minus SPXU creation flow.
- State 2: latest eligible SPY Arca opening-auction message strictly before 09:29 ET.
- Candidate: act only when the two directions agree; use no magnitude threshold.

## Development reachability

- Joint eligible sessions: 732
- Aligned candidate sessions: 373 (2.477/week)
- UPRO / SPXU actions: 166 / 207
- Signals by year: 2021=140, 2022=126, 2023=107

## Distinctness

- Exact-action agreement including cash with flow-only: 50.956%
- Exact-action agreement including cash with auction-only: 50.956%
- Exact-action agreement including cash with failed v34 buy-only: 46.858%

## Gates

- underlying_flow_audit_passed: PASS
- auction_source_has_clean_eof_and_hash: PASS
- joint_coverage_at_least_95_percent: PASS
- candidate_frequency_at_least_2_per_week: PASS
- at_least_90_signals_each_year: PASS
- both_sleeves_and_minority_at_least_25_percent: PASS
- selection_share_between_35_and_65_percent: PASS
- distinct_from_flow_only_below_80_percent_action_agreement: PASS
- distinct_from_auction_only_below_80_percent_action_agreement: PASS
- distinct_from_failed_v34_below_80_percent_action_agreement: PASS
- flow_delayed_and_auction_timestamp_strictly_before_09_29: PASS
- no_returns_pnl_or_recent_year_outcomes_read: PASS

Failed gates: none

No target return, strategy P&L, or 2024-2025 outcome was read.
