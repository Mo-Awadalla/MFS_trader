# Creation-Conditioned Wrapper Discount Audit v62

## Verdict

**Returns-blind construction gates passed. Formal critique and preregistration are allowed; entry/exit P&L remains unopened.**

## Frozen measurement

- Only a fund with a positive prior-session creation estimate is eligible.
- SPY return: prior official close to the 09:31 one-minute bar close.
- Wrapper return: point-in-time split-normalized prior official NAV to the 09:32 BBO midpoint.
- UPRO residual = UPRO return / 3 - SPY return.
- SPXU residual = SPXU return / 3 + SPY return.
- Buy eligibility requires a strictly negative residual. If both funds qualify, select the more negative underlying-unit residual.
- The 09:31 bar is timestamped at interval start and is not complete before 09:32. A future implementation may not enter before 09:33.

## Reachability

- Eligible sessions: 736 (97.742% coverage)
- Signals: 315 (2.092/week)
- UPRO / SPXU: 151 / 164
- By year: 2021=116, 2022=107, 2023=92

## Measurement stability and distinctness

- one_minute_earlier: 92.527% identical action including cash
- one_minute_later_diagnostic_only: 92.527% identical action including cash
- ARCX/EQUS overlap: 182 sessions; 96.154% identical action
- Action agreement with failed V19: 25.498%
- Action agreement with failed V48: 45.551%

## Gates

- official_flow_audit_passed: PASS
- statistics_unique_and_positive: PASS
- primary_source_coverage_at_least_95_percent: PASS
- signal_frequency_at_least_2_per_week: PASS
- at_least_90_signals_each_year: PASS
- both_sleeves_and_minority_at_least_20_percent: PASS
- selection_share_between_25_and_75_percent: PASS
- earlier_clock_action_stability_at_least_65_percent: PASS
- later_clock_diagnostic_stability_at_least_65_percent: PASS
- independent_feed_overlap_at_least_150_sessions: PASS
- independent_feed_action_agreement_at_least_75_percent: PASS
- distinct_from_failed_v19_below_80_percent_agreement: PASS
- distinct_from_failed_v48_below_80_percent_agreement: PASS
- one_session_flow_delay_and_entry_after_signal: PASS
- no_magnitude_threshold: PASS
- no_post_entry_return_pnl_or_recent_outcome_read: PASS

Failed gates: none

No price after the prospective 09:33 entry, strategy P&L, or 2024-2025 result was read.
