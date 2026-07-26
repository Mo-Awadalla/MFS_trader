# UPRO/SPXU Activity-Topology Research

## Concept

This batch ignored price direction. Each morning minute was represented only as:

- one when the ETF printed an ARCA trade bar; or
- zero when it was silent.

The hypotheses measured synchronization transitions, silence repayment,
activity lead–lag, longest-run recency, silence entropy, binary event clocks,
and post-silence persistence.

## Development screen: 2021–2023

The price-only SPY hurdle was $126.66 from a $100 starting position.

| Candidate | Trades/week | Ending cash | Net P&L | PF | Result |
|---|---:|---:|---:|---:|---|
| Synchronization Transition Charge | 3.53 | $129.03 | +$30.17 | 1.096 | Failed robustness |
| Silence Debt Release | 3.53 | $38.47 | -$87.43 | 0.765 | Failed |
| Activity Lead–Lag Braid | 2.24 | $48.30 | -$69.59 | 0.653 | Failed |
| Longest Run Recency | 3.52 | **$152.25** | +$52.39 | 1.176 | Failed 2022 |
| Silence Entropy Order | 2.87 | **$135.65** | +$36.87 | 1.173 | **Passed development** |
| Binary Event Clock Braid | 3.52 | $73.52 | -$26.68 | 0.921 | Failed |
| Onset Persistence Asymmetry | 0.78 | $110.66 | +$11.19 | 1.227 | Failed frequency and SPY |

## Development survivor: Silence Entropy Order

For each ETF, the rule extracted every run of consecutive silent ARCA minutes
between 09:30 and 10:59. It converted the silence-run lengths into a probability
distribution and calculated normalized Shannon entropy.

- Lower UPRO silence entropy than SPXU: buy UPRO.
- Lower SPXU silence entropy than UPRO: buy SPXU.
- Enter at 11:01 and exit at 15:30.

The hypothesis was that a lower-entropy pattern of liquidity withdrawal
represents a more coherent participation schedule than chaotic silence.

Development results:

- 447 trades, or 2.87 per week.
- $100 to $135.65 versus $126.66 for SPY.
- +$36.87 fixed-notional P&L.
- Profit factor 1.173.
- 2021: +$2.95.
- 2022: +$9.25.
- 2023: +$24.68.
- Bearish trades: +$4.43.
- Bullish trades: +$32.44.
- One extra cent per share at both fills: +$16.56.
- Five-minute delayed entry: +$30.97.
- Removing five best trades: +$10.64.

This was the first candidate to pass every frozen development gate under the
SPY-relative protocol.

## Secondary holdout: 2024–2025

The unchanged rule failed:

- 312 trades, or 3.00 per week.
- Fixed-$100 P&L: -$19.09.
- Fresh simulated account: $100 to $81.36.
- Profit factor: 0.874.
- 2024: +$8.10.
- 2025: -$27.20.
- Bearish trades: -$10.42.
- Bullish trades: -$8.67.
- Midpoint diagnostic: -$11.84.
- Consolidated-BBO P&L: -$22.20.
- One-minute delayed entry: -$19.25.
- Five-minute delayed entry: -$16.38.

The five-session bootstrap assigned a 76.2% probability to nonpositive total
holdout P&L. Its 95% interval was -$61.99 to +$30.20.

Across 2021–2025, the strategy account ended at $116.56 while price-only SPY
ended at $181.68. It fails the user's economic usefulness criterion.

## Other clues

### Longest Run Recency

The side with the longest active-minute run ending latest produced a strong
aggregate development result:

- $100 to $152.25.
- Positive after added cost, five-minute delay, and deletion of five winners.
- 2021: +$35.94.
- 2022: **-$4.59**.
- 2023: +$21.04.

It failed the frozen 2022 requirement and did not unlock later years. This is
exactly why the bear-regime gate is valuable: aggregate performance would have
made the candidate look substantially better than it was.

### Synchronization Transition Charge

This was positive in every development year and beat price-only SPY, but
bearish signals lost $17.74, one-cent execution stress lost $25.08, and deleting
the five best trades changed the result to -$4.42.

## Lessons

1. Activity topology contains more information than raw volume timing; two
   candidates beat SPY during development.
2. Silence entropy was regime-dependent. It survived 2022 but broke completely
   in 2025.
3. Longest-run structure was strong in ordinary years but failed the 2022 bear
   regime.
4. Lead–lag and silence-debt stories were strongly wrong, not merely
   cost-damaged.
5. The next search should focus on invariants that remain meaningful when the
   market's overall activity density changes. Historical entropy levels or run
   lengths must not be fitted to exclude 2025.

## Decision

No activity-topology candidate is suitable for deployment. Silence Entropy
Order was a legitimate development survivor, but its later-year failure and
five-year SPY underperformance reject it.

