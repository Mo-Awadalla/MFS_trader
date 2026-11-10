# Leveraged-Fund Rebalance Absorption Audit v64

## Verdict

**Rejected returns-blind before P&L.**

## Frozen construction

- Use the v63 four-fund prior-AUM rebalance model at 15:50.
- Require the published SPY closing-auction imbalance to be strictly opposite modelled rebalance direction.
- Trade only when absolute model-equivalent SPY shares strictly exceed that opposing auction quantity.
- Enter no earlier than 15:51. Same-side auctions and capacity overruns by the auction are cash.

## Development reachability

- Eligible sessions: 733
- Opposing-auction sessions: 363
- Signals: 335 (2.224/week)
- UPRO / SPXU: 175 / 160
- By year: 2021=73, 2022=129, 2023=133
- Model-size filter rejected 7.713% of opposing-auction sessions.

## Stability and independence

- 15:49:50: 80.082% exact action
- 15:50:10: 77.490% exact action
- ARCX/EQUS overlap action agreement: 100.000%
- Agreement with rejected broad v63: 49.659%
- Agreement with failed Closing Rebalance Torque: 44.884%

## Entry evidence

- Primary exact 15:51 quote coverage: 100.000%
- Independent exact 15:51 quote coverage: 100.000%

## Gates

- all_four_funds_have_complete_positive_prior_aum: PASS
- official_close_statistics_unique_and_positive: PASS
- eligible_coverage_at_least_95_percent: PASS
- signal_frequency_at_least_2_per_week: PASS
- at_least_90_signals_each_year: FAIL
- both_sleeves_and_minority_at_least_20_percent: PASS
- selection_share_between_25_and_65_percent: PASS
- aum_capacity_filter_rejects_5_to_40_percent_of_opposing_sessions: PASS
- adjacent_cutoff_15_49_50_stability_at_least_70_percent: PASS
- adjacent_cutoff_15_50_10_stability_at_least_70_percent: PASS
- independent_feed_overlap_at_least_150_sessions: PASS
- independent_feed_action_agreement_at_least_90_percent: PASS
- distinct_from_v63_broad_capacity_below_80_percent: PASS
- distinct_from_failed_closing_torque_below_80_percent: PASS
- primary_entry_quote_coverage_at_least_95_percent: PASS
- independent_entry_quote_coverage_at_least_90_percent: PASS
- one_session_aum_delay_and_pre_entry_snapshot: PASS
- no_fitted_magnitude_threshold: PASS
- no_post_entry_return_pnl_or_recent_outcome_read: PASS

Failed gates: at_least_90_signals_each_year

No post-15:51 price, strategy P&L, or 2024-2025 outcome was read.
