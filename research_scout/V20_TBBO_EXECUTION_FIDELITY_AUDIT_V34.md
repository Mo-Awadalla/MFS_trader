# V20 Event-Level TBBO Execution-Fidelity Audit v34

## Status

V20 remains rejected because its unchanged original development test failed winner-concentration. This audit is execution reconstruction, not a new strategy, a repair, or pristine validation.

The frozen V20 economic rule remains: prior ES volume scar; current 09:30–09:59 ES center/terminal confirmation; long UPRO for positive state or long SPXU for negative state; enter after the causal 10:01 boundary; liquidate on the minute after structural ES invalidation or at 15:30.

## Event-level execution model

- Entry: first valid EQUS.MINI trade-event pre-trade ask after 10:01 plus 1, 5, or 60 seconds.
- Exit: first valid trade-event pre-trade bid after the unchanged V20 target.
- Quotes with nonpositive prices or ask below bid are rejected.
- If no valid event appears within 60 seconds, the order is unfilled and excluded; no forward fill is allowed.
- EQUS.MINI is derived and anonymized, not official SIP NBBO.
- True standing quote age is not present in TBBO; event wait and capture latency are the measurable substitutes.
- Spread drag is midpoint-return P&L minus executable ask-to-bid P&L. One-cent-per-share adverse execution is reported separately.

## Results

| Partition | Delay | Trades | Fixed-$100 P&L | PF | Spread drag | +1 cent/share P&L | UPRO | SPXU |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| development_overlap_2023 | 1s | 79 | $9.06 | 1.395 | $3.76 | $1.55 | $14.16 | $-5.10 |
| development_overlap_2023 | 5s | 79 | $9.50 | 1.425 | $3.77 | $1.99 | $14.09 | $-4.59 |
| development_overlap_2023 | 60s | 69 | $8.65 | 1.368 | $3.38 | $1.83 | $14.75 | $-6.10 |
| historical_validation_2024_2025 | 1s | 162 | $9.15 | 1.157 | $5.04 | $0.11 | $4.33 | $4.81 |
| historical_validation_2024_2025 | 5s | 165 | $10.85 | 1.184 | $5.11 | $1.68 | $5.56 | $5.29 |
| historical_validation_2024_2025 | 60s | 146 | $7.18 | 1.126 | $4.50 | $-1.00 | $4.00 | $3.18 |
| temporal_extension_2026 | 1s | 0 | n/a | n/a | n/a | n/a | n/a | n/a |
| temporal_extension_2026 | 5s | 0 | n/a | n/a | n/a | n/a | n/a | n/a |
| temporal_extension_2026 | 60s | 0 | n/a | n/a | n/a | n/a | n/a | n/a |

## Interpretation boundary

The overlap begins on 2023-03-28, so this feed cannot reconstruct V20's 2021–2022 executions. Results after 2023 are historically contaminated because the rule and much of the price history were previously examined. Any improved fill fidelity cannot undo V20's failed original concentration gate, and no rule component may be modified from these outcomes.

The frozen V20 ES source ends at 2025-12-31. The zero-trade 2026 rows therefore mean no V20 states were available, not that a 2026 execution sample failed.

Machine-readable evidence: `research_scout/v20_tbbo_execution_fidelity_audit_v34.json`.

