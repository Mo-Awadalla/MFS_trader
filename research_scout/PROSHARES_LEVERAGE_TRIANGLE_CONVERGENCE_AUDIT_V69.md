# ProShares +3/−1/−3 Triangle Audit v69

## Verdict

**Rejected returns-blind before P&L.**

## Reachability

- Eligible sessions: 736 (97.742%)
- Active pair trades: 1472 (9.774/week)
- Pair trades by year: 2021=500, 2022=492, 2023=480
- UPRO/SH basis +/−: 432 / 304
- SPXU/SH basis +/−: 409 / 327

## Stability and execution evidence

- 09:31 action agreement: 54.891%
- 09:33 action agreement: 57.812%
- Independent action agreement: 99.451%
- Primary quote coverage: 100.000%
- Independent quote coverage: 99.479%

## Gates

- complete_prior_nav_coverage_at_least_95_percent: PASS
- eligible_session_coverage_at_least_95_percent: PASS
- active_pair_trades_at_least_2_per_week: PASS
- at_least_200_active_pair_trades_each_year: PASS
- each_pair_each_basis_sign_at_least_100: PASS
- neighboring_09_31_action_agreement_at_least_85_percent: FAIL
- neighboring_09_33_action_agreement_at_least_85_percent: FAIL
- independent_action_agreement_at_least_90_percent: PASS
- primary_required_quote_coverage_at_least_95_percent: PASS
- independent_required_quote_coverage_at_least_90_percent: PASS
- all_nav_source_dates_strictly_before_signal_dates: PASS
- no_basis_threshold_or_fitted_weight: PASS
- no_post_entry_return_or_recent_outcome_read: PASS

Failed gates: neighboring_09_31_action_agreement_at_least_85_percent, neighboring_09_33_action_agreement_at_least_85_percent

No post-entry return, P&L, or 2024–2025 strategy outcome was calculated.
