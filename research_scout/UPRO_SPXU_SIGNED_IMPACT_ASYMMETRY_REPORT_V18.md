# UPRO/SPXU Cross-Inverse Signed-Impact Asymmetry v18

## Verdict

**Rejected in development; 2024–2026 returns remain locked.**

| Period | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY |
|---|---:|---:|---:|---:|---:|
| Development 2021–2023 | 4.74 | $79.52 | $-5.08 | 0.991 | $126.66 |

## Development stress

- Extra cent at both fills: $-67.67
- Five-minute delay: $10.21
- Without ten best sessions: $-74.77
- Sign-flipped placebo: $-65.84
- Raw aggressor-count placebo: $24.89

Development failures: profit factor strictly above one, each development year positive, both upro and spxu positive, ending cash above spy, positive after one extra cent each fill, positive after removing ten best sessions, outperform unconfirmed event sign placebo.

No outcome-driven repair was made.

Machine-readable results: `research_scout/upro_spxu_signed_impact_asymmetry_results_v18.json`.
