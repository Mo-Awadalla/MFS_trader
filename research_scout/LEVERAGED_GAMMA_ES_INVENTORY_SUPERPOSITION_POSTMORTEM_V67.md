# Leveraged-Fund Gamma / ES Inventory Superposition Postmortem v67

## Decision

Reject v67 unchanged. Recent years remain locked.

## What was credible

The rule combined scheduled leveraged-fund exposure adjustment and completed ES
aggressor inventory in common S&P-dollar units. Its returns-blind state was
dense, balanced, stable at a neighboring clock, distinct from both components,
and exactly executable on the available primary and independent quote views.

## What the frozen test showed

- 733 trades, or 4.867 per declared week.
- Fixed-$100 P&L: -$22.86; compounded cash: $77.89 versus adjusted SPY
  $132.40.
- Profit factor: 0.890.
- 2021 / 2022 / 2023: -$11.79 / -$1.88 / -$9.18.
- UPRO / SPXU: -$20.21 / -$2.65.
- One-extra-cent stress: -$88.24.
- Five-minute-delay stress: -$40.38.
- Delete ten best sessions: -$51.95.
- Five-session bootstrap lower mean: -0.000801.
- Independent 2023 overlap: -$15.25, profit factor 0.612.

The combined rule lost less than fund-only, ES-only, fixed-coefficient, and
shifted-ES controls, but it still had negative expectancy. Relative
less-badness is not a tradable edge.

## Mechanistic lesson

Signed ES aggressor volume does not identify residual dealer inventory.
Passive counterparties can be informed, naturally offsetting, or already
cross-hedged. Adding that completed transfer to a public first-order rebalance
estimate did not forecast the remaining closing pressure.

The result also strengthens the warning from the earlier MES close-flow study:
late ES flow states can be economically interpretable without producing a
stable post-15:30 premium.

## Prohibited repairs

Do not invert the net-pressure sign, select component-agreement or opposition
days, rescale either term, add a magnitude threshold, drop UPRO, choose 2022,
or move the entry/exit clocks. Those are now outcome-derived variants of a
consumed construction.

