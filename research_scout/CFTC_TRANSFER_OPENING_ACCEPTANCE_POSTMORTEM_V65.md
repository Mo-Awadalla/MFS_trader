# CFTC Relative-Transfer / ES Opening Acceptance Postmortem v65

## Decision

**Rejected in 2021–2023. Recent years remain locked.**

The candidate passed every returns-blind construction gate but failed the
economic, benchmark, cost, side, concentration, and inference gates after the
single frozen P&L test.

## Frozen result

- 381 feature signals; 372 executable nondegraded trades.
- 2.470 executed trades per declared week.
- Fixed-$100 P&L: +$14.28.
- Compounded ending cash: $101.47 versus adjusted SPY at $132.40.
- Profit factor: 1.041.
- Annual P&L: 2021 -$19.84, 2022 +$26.28, 2023 +$7.84.
- UPRO +$25.83; SPXU -$11.55.
- One-extra-cent-each-fill stress: -$15.14.
- Five-minute entry delay: +$6.47, but still negative compounded growth.
- Delete five best CFTC source-report clusters: -$43.65.
- Source-report moving-block bootstrap 2.5th percentile: -0.004211.
- Source-report direction-permutation p-value: 0.2006.

## Mechanism falsification

The slow/fast interaction did not add identified information:

- Actual mean trade P&L: +$0.0384.
- COT-only relative-transfer mean: +$0.0424.
- One-report-shifted transfer mean: +$0.0568.
- Asset-Manager-only confirmation mean: +$0.0706.

The actual state was weaker than both preregistered causal controls. The
five-minute ES agreement condition therefore did not isolate a persistent
participant-transfer handoff.

The independent 2023 quote overlap was positive (+$18.34, PF 1.309), but it
cannot override the negative 2021 result, inverse-sleeve loss, negative cost
stress, cluster concentration, and failed permutation inference. It is
consistent with a favorable 2023 subperiod.

## Failure lesson

A weekly category state can be dense, balanced, causal, and stable while still
having too little directional resolution for intraday trading. Reusing the
same report across several sessions inflates the apparent trade count; the
source-report analysis exposed that most gross profit came from a small number
of weeks.

The broader lesson is that a slow state needs a payoff mechanism tied to a
specific inventory liquidation or information-release clock. Generic opening
acceptance is not enough.

## Prohibited repairs

- No strict-collision-only subset.
- No Asset-Manager-only substitution.
- No one-report-shifted substitution.
- No UPRO-only rule or SPXU deletion.
- No removal of 2021.
- No magnitude threshold, normalization, shorter report lag, or alternate
  opening clock.
- No promotion of the independent 2023 overlap.

The next candidate must use a new causal event and inventory mechanism rather
than another slow-state filter on opening momentum.

