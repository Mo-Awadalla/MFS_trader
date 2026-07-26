# ES Extreme Creativity Pass v2

Saved: 2026-07-26

## Research budget

Three orthogonal hypotheses were frozen before testing. Each required at least two trades per week, positive development P&L in 2021, 2022, and 2023, positive long and short P&L, and aggregate profit factor above one. No failed rule accessed 2024-2025.

## 1. Aggressor Causality Switch

Construction: use every ES transaction from 15:00-15:30 to estimate whether size-weighted aggressors correctly anticipate the next transaction-price change. Follow net flow when aggression is locally predictive and fade it when locally wrong.

Result:

- 747 trades; 4.788 per week.
- -$2,056.28; profit factor 0.874.
- Negative in every development year.
- Long: -$2,052.67; short: -$3.61.

Decision: rejected without holdout access.

## 2. Aggressor Clock Compression

Construction: model buyer and seller aggression as separate point processes. Compare the coefficients of variation of their exchange-event interarrival times and fade the more burst-clustered side.

Result:

- 749 trades; 4.801 per week.
- -$3,911.26; profit factor 0.774.
- Negative in every development year and both directions.

Decision: rejected without holdout access.

## 3. Auction Entropy Phase Transition

Construction: encode opening minute bodies as binary states. Follow second-half directional magnetization when entropy falls and fade it when entropy rises.

Result:

- 601 trades; 3.853 per week.
- +$1,962.26; profit factor 1.091.
- 2021: -$434.17.
- 2022: +$3,543.19.
- 2023: -$1,146.76.
- Long: -$42.11; short: +$2,004.37.
- Ordered transitions: +$3,024.59.
- Disordered transitions: -$1,062.33.

Decision: rejected without holdout access. Ordered-only, short-only, or 2022-style selection is prohibited because those favorable subsets were observed only after the full rule was tested.

## Lessons

1. Transaction-level complexity is not automatically persistent information.
2. Next-trade causal response and point-process burstiness were not useful directional summaries.
3. Entropy decline may identify occasional coordination, but the tested state machine was a 2022 and short-side artifact.
4. Frequency remained easy; year-and-side stability remained the binding constraint.
5. The unchanged three-engine paper portfolio remains the benchmark.

## Next untouched direction

The next family should measure **impact recovery**, not flow direction:

- identify an endogenous transaction-impact event before 15:30;
- measure how much of its immediate price displacement is retained versus recovered before entry;
- define direction from the retained/recovered state without selecting flow side, year, or magnitude after results;
- use recorded MES entry and exit spreads.

No event definition, recovery horizon, or direction has been chosen. They must be preregistered before any calculation.
