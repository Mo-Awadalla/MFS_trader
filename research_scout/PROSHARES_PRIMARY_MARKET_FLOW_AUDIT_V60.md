# ProShares Primary-Market Flow Audit v60

## Verdict

**Data and cadence gates passed for preimplementation critique. No return has been opened.**

The source is the free official ProShares historical NAV/shares file. Every observation is delayed by one U.S. trading session.

## Coverage and activity

- Expected 2021-2023 SPY sessions: 753
- UPRO: 100.000% coverage
- UPRO: 686 active sessions (4.555/week)
- SPXU: 100.000% coverage
- SPXU: 711 active sessions (4.721/week)

## Paired directional exposure-flow state

- Nonzero next-session states: 748 (4.967/week)
- Bullish / bearish: 351 / 397
- Top-ten absolute-flow concentration: 22.379%

## Admission gates

- official_source_audit_rejects_no_nav_or_split_field: PASS
- both_symbols_at_least_98_percent_coverage: PASS
- split_dates_explicitly_normalized: PASS
- one_session_publication_delay_enforced: PASS
- paired_state_cadence_at_least_2_per_week: PASS
- both_directions_at_least_15_percent_of_states: PASS
- no_target_return_or_strategy_pnl_read: PASS

Failed gates: none

## Boundary

This audit establishes availability and cadence only. Share changes estimate creations/redemptions; they do not identify end investors, AP inventory, or the timing of the fund's hedge. A strategy may not be tested until a separate institutional critique and preregistration freeze the direction, timing, controls, and execution gates.
