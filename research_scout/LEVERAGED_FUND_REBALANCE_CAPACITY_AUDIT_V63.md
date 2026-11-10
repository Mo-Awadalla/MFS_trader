# Leveraged-Fund Rebalance / Auction-Capacity Audit v63

## Verdict

**Rejected returns-blind before P&L.**

## Frozen construction

- Use prior-session official AUM for UPRO (+3), SPXU (-3), SSO (+2), and SDS (-2).
- Model each fund's first-order rebalance demand as `L × (L - 1) × prior AUM × SPY return`.
- SPY return ends at the completed 15:49 bar.
- Add the latest SPY closing-auction signed total imbalance strictly before 15:50.
- Trade only in the model direction when the auction imbalance does not overwhelm it; otherwise cash. No fitted magnitude threshold.

## Development reachability

- Eligible sessions: 733 (97.344%)
- Signals: 704 (4.675/week)
- UPRO / SPXU: 375 / 329
- By year: 2021=238, 2022=236, 2023=230
- Auction capacity blocked the model on 3.820% of eligible sessions.

## Stability and distinctness

- 15:49:50: 99.454% identical action including cash
- 15:50:10: 99.454% identical action including cash
- ARCX/EQUS signal agreement: 100.000%
- Agreement with pure late-day momentum: 96.180%
- Agreement with failed Closing Rebalance Torque: 55.662%
- Agreement with auction-only direction: 50.341%

## Entry evidence

- Primary 15:51 quote coverage: 100.000%
- Independent-overlap quote coverage: 100.000%

## Gates

- official_aum_source_audit_passed: PASS
- all_four_funds_have_complete_positive_prior_aum: PASS
- official_close_statistics_unique_and_positive: PASS
- eligible_coverage_at_least_95_percent: PASS
- signal_frequency_at_least_2_per_week: PASS
- at_least_100_signals_each_year: PASS
- both_sleeves_and_minority_at_least_20_percent: PASS
- selection_share_between_25_and_90_percent: FAIL
- auction_capacity_changes_at_least_10_percent_of_actions: FAIL
- adjacent_cutoff_15_49_50_stability_at_least_70_percent: PASS
- adjacent_cutoff_15_50_10_stability_at_least_70_percent: PASS
- independent_feed_overlap_at_least_150_sessions: PASS
- independent_feed_action_agreement_at_least_90_percent: PASS
- distinct_from_failed_closing_torque_below_80_percent: PASS
- distinct_from_auction_only_below_80_percent: PASS
- primary_entry_quote_coverage_at_least_95_percent: PASS
- independent_entry_quote_coverage_at_least_90_percent: PASS
- one_session_aum_delay_and_pre_entry_snapshot: PASS
- no_fitted_magnitude_threshold: PASS
- no_post_entry_return_pnl_or_recent_outcome_read: PASS

Failed gates: selection_share_between_25_and_90_percent, auction_capacity_changes_at_least_10_percent_of_actions

No price after the prospective 15:51 entry, strategy P&L, or 2024-2025 outcome was read.
