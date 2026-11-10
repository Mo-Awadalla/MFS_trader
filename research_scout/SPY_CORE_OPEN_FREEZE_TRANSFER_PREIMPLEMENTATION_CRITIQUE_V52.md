# SPY Core-Open Freeze Transfer — Preimplementation Critique v52

## Corrected field premise

Earlier screening grouped freeze, extension, and collar events together as exceptional. The decoded SPY history shows a different fact:

- 09:29:50 snapshot: 0 of 1,395 sessions frozen;
- 09:29:59 snapshot: 1,395 of 1,395 sessions frozen.

The Core-Open freeze is a routine final auction phase, not a rare-event strategy. Extensions remain absent and are not part of V52.

## Hypothesis

For each Core Opening:

1. Identify the last nonfrozen (`freeze_status = 0`) message before the first frozen message.
2. Identify the final frozen (`freeze_status = 1`) message received before 09:30:00.
3. Compute the change in `ind_match_price` across that exact phase transition.
4. Positive change maps to long UPRO; negative change maps to long SPXU; zero change maps to cash.

The freeze phase constrains participants' ability to withdraw or reprice committed auction liquidity. A directional indicative-price change across the transition should therefore isolate deadline flow that auction suppliers had little time to offset. The predicted result is brief continuation after the uncross.

No imbalance sign, quantity, magnitude threshold, collar distance, reference-price return, message-count threshold, opening gap, or bar momentum enters the rule.

## Why a desk might listen

- The feature is defined by an exchange state transition rather than an arbitrary clock.
- It measures price discovery after liquidity commitments become constrained.
- It is distinct from V50, whose windows ended before the frozen phase and whose defining variable was revision-rate acceleration.
- It is frequent by construction if prices actually revise during the universal freeze phase.
- The effect is falsifiable at 1/5/60-second delays.

## Strongest skeptical response

- `freeze_status` marks exchange protocol state, but the supplied schema does not identify which participant actions were constrained.
- The final indication may already be incorporated into continuous/pre-open SPY prices.
- A one-tick change may be pure auction noise and below leveraged-ETF spread.
- The sign may duplicate the final imbalance side, gap, or prefreeze price move.
- Endpoint choice within a handful of messages may be unstable.
- Trade-event TBBO may understate execution availability.
- A market maker should eliminate any post-uncross continuation quickly.

These objections are returns-blind gates and mandatory controls, not reasons to optimize thresholds.

## Frozen stability variants

- Transition-only variant: first frozen indication to final frozen indication.
- Endpoint variant: last nonfrozen indication to penultimate frozen indication.

The primary last-nonfrozen-to-final-frozen action must match each variant, including cash, on at least 60% of union sessions. No variant may replace the primary after inspection.

## Returns-blind gates

1. At least two feature signals per week in 2021–2023.
2. At least 100 signals per development year and 20 in 2026.
3. Both UPRO/SPXU with minority side at least 20%.
4. At least two executable 2023-overlap trades per week, both actuators, and 20% minority side.
5. At least 90% complete 1/5/60-second entry-plus-exit evidence.
6. Primary entry wait p95 no more than 30 seconds and every wait no more than 60 seconds.
7. Both frozen stability variants at least 60% identical action including cash.
8. Direction agreement below 80% with the opening gap, final imbalance side, and the preceding nonfrozen price move.
9. Nonzero transition selects between 20% and 80% of valid freeze sessions.
10. Every feature has a 0→1 freeze transition, all messages arrive before 09:30, and every entry follows the final feature message.

## Frozen execution if feasible

- Fixed signal boundary: 09:30:00.
- Entry asks after 09:30:01, 09:30:05, and 09:31:00.
- Primary entry: 09:30:05.
- Exit bid after 09:35:00.
- Fixed $100 fractional long UPRO or SPXU; no margin, shorting, overlap, or overnight.

## Decision

**Pass V52 to one returns-blind full-message audit.** Failure locks the transition definition, endpoints, actuators, and gates.
