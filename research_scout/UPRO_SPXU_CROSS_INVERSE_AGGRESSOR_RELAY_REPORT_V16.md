# UPRO/SPXU Cross-Inverse Aggressor Relay v16

## Verdict

**Rejected in development. The 2024–2025 return holdout remains locked.**

## Development: 2021–2023

| Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY |
|---:|---:|---:|---:|---:|
| 4.46 | $154.41 | $60.32 | 1.116 | $126.66 |

Development stress and identification:

- One extra cent per share at both fills: $3.65.
- Five-minute entry delay: $45.31.
- Sign-flipped placebo: $-126.01.
- Unconfirmed event-sign placebo: $24.89.
- Result without ten best sessions: $-5.69.

Development gate failures:

- both upro and spxu positive, positive after removing ten best sessions

The returns-blind signal audit passed, but cross-feed score correlation was only 0.251 and remains an identification warning.

No threshold, clock, sign, stop, or direction was repaired after outcomes.

Preimplementation critique: `research_scout/UPRO_SPXU_CROSS_INVERSE_AGGRESSOR_RELAY_PREIMPLEMENTATION_CRITIQUE_V16.md`.

Machine-readable results: `research_scout/upro_spxu_cross_inverse_aggressor_relay_results_v16.json`.
