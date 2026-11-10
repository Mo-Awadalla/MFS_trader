# CFTC Relative-Transfer / ES Opening Acceptance Audit v65

## Verdict

**All returns-blind gates passed. Formal preregistration and the single frozen 2021–2023 P&L test are allowed; recent years remain locked.**

## Frozen state

- Slow direction: sign of Asset Manager net-position change minus Leveraged Fund net-position change in the CFTC S&P 500 Consolidated futures-only report.
- Availability: Tuesday report plus seven calendar days.
- Fast confirmation: completed ES 09:30–09:34 move in the same direction.
- Prospective entry: exact 09:36 UPRO/SPXU quote.

## Reachability

- Expected cash sessions: 753
- Eligible states: 743 (98.672%)
- Signals: 381 (2.530/week)
- UPRO / SPXU: 209 / 172
- Signals by year: 2021=137, 2022=119, 2023=125
- CFTC direction switches by year: 2021=24, 2022=29, 2023=20
- Strict Asset Manager / Leveraged Fund collision reports: 106 (67.949%)

## Robustness before returns

- four_minute: 88.291% action agreement
- six_minute: 88.425% action agreement
- Independent 2023 SPY proxy action agreement: 100.000%
- Agreement with ES-only opening momentum: 52.490%
- Agreement with COT-only direction: 51.279%
- Primary 09:36 quote coverage: 100.000%
- Independent quote coverage: 78.400%

## Gates

- source_at_least_50_reports_each_year: PASS
- source_unique_and_complete_required_fields: PASS
- eligible_coverage_at_least_90_percent: PASS
- at_least_two_signals_per_week: PASS
- at_least_90_signals_each_year: PASS
- minority_actuator_share_at_least_30_percent: PASS
- at_least_15_state_switches_each_year: PASS
- primary_entry_quote_coverage_at_least_90_percent: PASS
- four_minute_action_stability_at_least_75_percent: PASS
- six_minute_action_stability_at_least_75_percent: PASS
- independent_spy_proxy_agreement_at_least_85_percent: PASS
- es_only_control_agreement_below_80_percent: PASS
- cot_only_control_agreement_below_80_percent: PASS

Failed gates: none

No post-09:36 price, entry value, exit value, strategy return, or 2024–2025 outcome was read.
