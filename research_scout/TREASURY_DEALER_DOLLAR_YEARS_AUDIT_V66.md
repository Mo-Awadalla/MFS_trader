# Treasury Dealer Dollar-Years Audit v66

## Verdict

**All returns-blind gates passed. Formal preregistration and a single frozen development P&L test are allowed.**

## Reachability

- Valid mapped event sessions: 572
- Signals: 572 (3.798/week)
- UPRO / SPXU: 304 / 268
- Signals by year: 2021=197, 2022=183, 2023=192
- Valid auction-date mapping coverage: 100.000%

## Feature diagnostics

- Largest bucket absolute contribution: 11.742% (Note|7-Year|FRN=No|TIPS=No)
- Bill absolute contribution: 18.267%
- Notional-only agreement: 82.517%
- Coupon-only conditional agreement: 97.445%
- Prior-SPY agreement: 48.252%
- Rejected-v58 agreement: 47.727%
- Primary 09:33 quote coverage: 100.000%
- Independent 09:33 quote coverage: 78.646%

## Gates

- required_source_fields_valid_at_least_95_percent: PASS
- auction_date_mapping_coverage_at_least_90_percent: PASS
- at_least_two_signals_per_week: PASS
- at_least_90_signals_each_year: PASS
- minority_actuator_share_at_least_35_percent: PASS
- at_least_20_direction_switches_each_year: PASS
- largest_bucket_below_50_percent_absolute_shock: PASS
- notional_only_action_agreement_at_least_70_percent: PASS
- coupon_only_conditional_agreement_at_least_70_percent: PASS
- primary_entry_quote_coverage_at_least_90_percent: PASS
- prior_spy_action_agreement_below_80_percent: PASS
- v58_action_agreement_below_80_percent: PASS

Failed gates: none

No post-09:33 price, strategy P&L, or 2024–2025 outcome was read.
