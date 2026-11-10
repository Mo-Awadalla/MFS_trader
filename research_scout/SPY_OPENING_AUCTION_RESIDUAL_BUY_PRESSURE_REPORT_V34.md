# SPY Opening-Auction Residual Buy Pressure v34

## Verdict

**Rejected in development. The 2024–2026 return partitions remain locked.**

Specification SHA-256: `11da19921addc95fc9133462082ab863047599061623a30d12640350c49e54f7`

## Development: 2021–2023

- Trades/week: 2.26
- Ending cash: $83.19
- Price-only SPY: $126.66
- Profit factor: 0.914
- Fixed-$100 P&L: $-15.40
- P&L without ten best sessions: $-44.15
- Bootstrap lower mean return: -0.001769

Failed development gates:

- profit_factor_strictly_above_1_1, each_development_year_positive, ending_cash_at_least_110_percent_of_spy, positive_after_one_extra_cent_each_fill, positive_after_five_minute_entry_delay, positive_after_removing_ten_best_sessions, bootstrap_lower_mean_above_zero, positive_on_nonnegative_reference_gaps, positive_on_negative_reference_gaps, outperform_sell_side_placebo, outperform_previous_session_placebo

No result-driven threshold, sign, clock, stop, actuator, or sleeve change was made.

Preimplementation critique: `research_scout/SPY_OPENING_AUCTION_RESIDUAL_BUY_PRESSURE_PREIMPLEMENTATION_CRITIQUE_V34.md`.
