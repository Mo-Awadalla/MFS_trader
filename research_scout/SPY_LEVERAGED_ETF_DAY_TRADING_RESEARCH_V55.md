# SPY / Leveraged-ETF Day-Trading Research v55

## Outcome

No strategy from this cycle qualifies for paper or live trading.

One previously frozen hypothesis, VX forward-stress persistence v47, passed
every 2021-2023 development gate and therefore legitimately unlocked
2024-2025. It then failed decisively. A new fresh-position hypothesis v55 was
rejected returns-blind for inadequate cadence before any target return was
read.

This is a useful result: the development protocol successfully admitted a
plausible, apparently robust historical edge, and the untouched later years
showed that it was not stable.

## Evidence reviewed before proposing a strategy

The repo's accumulated archive covers more than fifty numbered or terminally
screened SPY/UPRO/SPXU families. The recurring failure modes are:

1. **2022 concentration.** Many signals make nearly all development profit in
   the 2022 volatility regime.
2. **Winner concentration.** Deleting five or ten sessions often changes the
   sign of the result.
3. **Actuator asymmetry.** UPRO can be profitable while SPXU loses after its
   wider spread and inverse-wrapper drag.
4. **Gross edge below friction.** Midpoint profit frequently becomes a loss at
   observed ask-to-bid execution or after one additional cent per fill.
5. **Later-year reversal.** Opening-center, activity-topology, cross-market,
   ES-anchor, macro, BTC, and wrapper-state survivors repeatedly fail in
   2024-2025.
6. **Mechanistic sparsity.** Stronger auction, hard-flow, and position-state
   definitions often fall below two trades per week.
7. **Data identification.** Trade-event TBBO cannot reconstruct quote age;
   one-minute BBO cannot justify queue or passive-fill assumptions; unsigned
   ETF volume cannot identify AP or dealer hedge direction.
8. **Multiple testing.** A new transform, clock, sign, or conjunction of an
   exposed causal object is not independent evidence.

Primary local syntheses:

- `research_scout/SPY_CASH_ETF_FAILURE_SYNTHESIS_V54.md`
- `research_scout/CASH_ETF_HYPOTHESIS_REGISTRY_V34.md`
- `research_scout/NEW_DATA_TECHNICAL_AUDIT_V34.md`
- `research_scout/SPY_DAY_TRADING_HYPOTHESIS_SCREEN_V44.md`
- `research_scout/UPRO_SPXU_CREATIVE_HYPOTHESES_REPORT_V1.md`
- `research_scout/UPRO_SPXU_ACTIVITY_TOPOLOGY_REPORT_V5.md`

## Frozen evaluation protocol

- Development: 2021-01-01 through 2023-12-31.
- Later-year holdout: 2024-01-01 through 2025-12-31.
- Holdout returns remain unread unless every development gate passes.
- Cash-only fractional UPRO/SPXU; one long ETF position at a time.
- Entry at observed ask and exit at observed bid.
- Flat by 15:30.
- Minimum two executable trades per calendar week.
- Positive every development year and in both ETF sleeves.
- Compounded ending cash above split/dividend-adjusted SPY.
- Profit factor at least 1.05.
- Positive after one extra cent at each fill and a five-minute entry delay.
- Positive after deleting the ten best development trades.
- Positive on the independent EQUS overlap.
- Better mean trade P&L than all preregistered controls.
- No sign, threshold, clock, contract, stop, or regime repair after outcomes.

## Candidate 1 — VX forward-stress persistence v47

### Hypothesis and institutional critique

The normalized front/second standard-monthly VX settlement slope captures the
location of forward-volatility stress. A daily move toward relief was mapped
to next-session UPRO; a move toward near-term stress was mapped to SPXU.

The mechanism is institutionally relevant because it uses actual VX contracts
and an overnight observability buffer. Its weaknesses were equally explicit:
settlements are not executable quotes, volatility direction need not imply
equity direction, the overnight market may absorb the information, roll
mechanics matter, and a 2022 stress episode could dominate.

The full critique and preregistration predate return inspection:

- `research_scout/SPY_VX_FORWARD_STRESS_PERSISTENCE_PREIMPLEMENTATION_CRITIQUE_V47.md`
- `research_scout/spy_vx_forward_stress_persistence_prereg_v47.json`

### Returns-blind admission

- 727 executable development trades.
- 4.652 trades per calendar week in the frozen feasibility calculation.
- 248 / 243 / 236 trades in 2021 / 2022 / 2023.
- Minority direction: 40.85%.
- Primary execution coverage: 98.78%.
- Independent execution coverage: 98.90%.
- Early-roll action agreement: 91.86%.

Every returns-blind gate passed.

### Development result: 2021-2023

| Metric | V47 | Dividend-adjusted SPY |
|---|---:|---:|
| Ending cash from $100 | $408.90 | $132.40 |
| Fixed-$100 P&L | $164.41 | n/a |
| Profit factor | 1.273 | n/a |
| Trades/week | 4.682 | n/a |
| P&L after deleting ten best trades | $86.56 | n/a |
| P&L with one extra cent each fill | $108.48 | n/a |
| P&L with five-minute delayed entry | $148.77 | n/a |

Annual fixed-notional P&L was +$2.56, +$111.90, and +$49.96. Both UPRO
(+$125.00) and SPXU (+$39.42) were positive. The independent 2023 overlap made
+$28.66. All preregistered controls had lower mean trade P&L.

All development gates passed. This is why opening the later partition was
procedurally valid despite the clear warning that 68% of fixed-notional profit
came from 2022.

### Later-year result: 2024-2025

| Metric | V47 | Dividend-adjusted SPY |
|---|---:|---:|
| Ending cash from $100 | $30.60 | $148.00 |
| Fixed-$100 P&L | -$102.60 | n/a |
| Profit factor | 0.766 | n/a |
| Trades/week | 4.743 | n/a |
| P&L after deleting five best trades | -$145.53 | n/a |
| P&L with one extra cent each fill | -$134.37 | n/a |

2024 lost $2.80 and 2025 lost $99.79. UPRO lost $35.52 and SPXU lost
$67.08. The frozen sign-flipped control made $63.77, demonstrating a state
reversal, but promoting that flip would be direct holdout overfitting.

**Decision: reject.** Do not add a regime filter, flip the sign, select 2022,
or change the hold window.

Machine-readable result:
`research_scout/spy_vx_forward_stress_persistence_results_v47.json`.

## Candidate 2 — VX fresh-position risk transfer v55

### Hypothesis and internal critique

Use same-contract front VX settlement direction only when the next
start-of-day open-interest observation confirms that positions expanded:

- settlement up and open interest up: buy SPXU;
- settlement down and open interest up: buy UPRO;
- otherwise cash.

This is more directly tied to S&P 500 volatility positioning than the failed
BTC open-interest transfer. It is still imperfect because open interest
identifies contract creation, not informed ownership, and historical
publication timestamps are not present in each row.

The rule was preregistered before target returns:

- `research_scout/SPY_VX_FRESH_POSITION_RISK_TRANSFER_PREIMPLEMENTATION_CRITIQUE_V55.md`
- `research_scout/spy_vx_fresh_position_risk_transfer_prereg_v55.json`

### Returns-blind result

- 28 executable development signals.
- 0.179 trades per week.
- 8 / 7 / 13 trades in 2021 / 2022 / 2023.
- Direction split: 24 UPRO, 4 SPXU.
- Primary and independent execution coverage: 100%.

The candidate failed cadence, per-year sample size, and direction-balance
gates. No entry-to-exit return or strategy P&L was calculated.

**Decision: reject before returns.** Do not weaken the open-interest condition
or add a magnitude threshold.

## New MBP-1 data boundary

The complete six-symbol MBP-1 package is valuable: it can reconstruct true
quote updates and subsecond quote age around 09:20-09:40. It contains 806 valid
sessions and all six symbols in each decoded file.

Its history begins on 2023-03-28. Therefore it cannot honestly satisfy a
2021-2023 development mandate for a signal defined by quote age, replenishment,
or full order-book updates. Using it to discover a 2023 rule and backfilling
that rule with one-minute ARCA snapshots would change the measured causal
object. No such backfill was performed.

## Final decision

There is no newly qualified SPY/UPRO/SPXU day-trading strategy in the supplied
history.

V47 is the strongest development result in this cycle, but the later-year
collapse is decisive evidence against deployment. V55 lacked enough events to
test. The honest next research path is prospective:

1. freeze one genuinely MBP-1-native quote-age/replenishment hypothesis;
2. use 2023-2025 only for mechanism falsification, not pristine validation;
3. collect untouched future sessions before promotion;
4. require marketable execution, both sleeves, cost stress, and winner
   deletion;
5. do not deploy or paper-promote a historical survivor without new forward
   evidence.

