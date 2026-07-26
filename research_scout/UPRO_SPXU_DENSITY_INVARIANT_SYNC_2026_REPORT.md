# Density-Invariant Synchronization Shock — 2026 Prospective Test

## Research protocol

The rule was frozen before acquiring or inspecting any 2026 outcome:

- 2021–2025 was used only for hypothesis formation.
- 2026-01-02 through 2026-07-24 was the prospective sample.
- One hypothesis and one parameterization were tested.
- No inversion, threshold repair, clock adjustment, direction selection, or
  alternative was permitted after the result.

## Data acquisition

Databento ARCX.PILLAR data acquired:

- SPY, UPRO, and SPXU OHLCV-1m.
- UPRO and SPXU BBO-1m.

Estimated incremental cost: **$0.269912**.

Estimated cumulative Databento spend: **$3.615379** of the original $50
authorization, leaving approximately **$46.384621**.

Validation found 140 RTH sessions and exact 11:01 and 15:30 BBO observations for
both ETFs on all sessions. The officially degraded 2026-06-24 and 2026-07-14
sessions were excluded, leaving 138 eligible sessions.

## Frozen hypothesis

The 09:30–10:59 morning was divided into six 15-minute blocks. Each ETF was
represented by a binary trade-activity mask.

For each block:

- Synchronization was the Jaccard similarity between UPRO and SPXU activity.
- Directional share was UPRO active minutes divided by combined UPRO and SPXU
  active minutes.

The rule required:

1. Median synchronization in the final three blocks to exceed the first three.
2. Buy UPRO if relative UPRO activity share accelerated.
3. Buy SPXU if it decelerated.
4. Enter at the observed 11:01 ask and exit at the 15:30 bid.

## Prospective result

**Zero trades.**

The rule failed the minimum-frequency criterion and produced no P&L. Over the
same period, price-only SPY grew from $100 to **$107.76**.

This is a valid prospective rejection rather than a neutral result: the claimed
phase transition did not occur in the frozen direction.

## Why no trades occurred

Across 138 eligible sessions:

- Positive synchronization shocks: 0.
- Zero synchronization shocks: 119.
- Negative synchronization shocks: 19.
- Nonzero positive directional acceleration: 5.
- Zero directional acceleration: 122.
- Nonzero negative directional acceleration: 11.
- Sessions satisfying both frozen signal conditions: 0.

Mean Jaccard synchronization by 15-minute block:

1. 09:30–09:44: 0.9990
2. 09:45–09:59: 0.9947
3. 10:00–10:14: 0.9971
4. 10:15–10:29: 0.9894
5. 10:30–10:44: 0.9821
6. 10:45–10:59: 0.9763

The pair was already almost perfectly synchronized immediately after the open.
Synchronization then stayed equal or weakened. The hypothesized transition
from lower to higher synchronization was structurally absent.

## Decision

Reject the hypothesis unchanged. Do not invert it or weaken the positive-shock
condition using this sample.

The experiment was useful because it exposed a data invariant that historical
search had obscured: with 2026 ARCA activity density, a rising-synchronization
morning state is nearly impossible under the frozen binary definition.

