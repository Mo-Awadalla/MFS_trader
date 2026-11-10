# UPRO/SPXU Variance-State Research v9

## Verdict

**No candidate passed both the frozen development and secondary-holdout gates. None is suitable for paper or live trading.**

The rules were saved in `research_scout/upro_spxu_variance_state_prereg_v9.json` before outcomes were calculated. Results use observed asks for buys and observed bids for sells, fractional shares, a $100 starting account, full reinvestment, no overnight position, and no parameter search.

## Development: 2021-2023

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash | Gate |
|---|---:|---:|---:|---:|---:|---|
| Quiet-Variance Carry | 2.45 | $110.47 | $20.42 | 1.067 | $126.66 | Fail |
| Downside-Variance Handoff | 4.74 | $53.56 | $-36.05 | 0.951 | $126.66 | Fail |
| Paired Variance Harvest | 4.73 | $67.41 | $-39.39 | 0.140 | $126.66 | Fail |

## Secondary holdout: 2024-2025

| Candidate | Trades/week | Ending cash | Fixed-$100 P&L | PF | SPY ending cash | Holdout gate |
|---|---:|---:|---:|---:|---:|---|
| Quiet-Variance Carry | 2.48 | $101.96 | $5.32 | 1.035 | $144.41 | Fail |
| Downside-Variance Handoff | 4.77 | $43.05 | $-67.22 | 0.842 | $144.41 | Fail |
| Paired Variance Harvest | 4.75 | $81.87 | $-19.98 | 0.189 | $144.41 | Fail |

## Full retrospective span: 2021-2026 YTD

| Candidate | Sessions | Ending cash | Fixed-$100 P&L | PF | Max drawdown | SPY ending cash |
|---|---:|---:|---:|---:|---:|---:|
| Quiet-Variance Carry | 695 | $120.58 | $33.85 | 1.066 | $-36.48 | $196.88 |
| Downside-Variance Handoff | 1351 | $24.86 | $-93.09 | 0.926 | $-99.43 | $196.88 |
| Paired Variance Harvest | 1348 | $52.74 | $-63.90 | 0.155 | $-47.26 | $196.88 |

## Consolidated execution audit: 2023-03-28 through 2025-12-31

| Candidate | ARCA BBO P&L | Consolidated BBO P&L |
|---|---:|---:|
| Quiet-Variance Carry | $11.00 | $4.83 |
| Downside-Variance Handoff | $-92.66 | $-99.46 |
| Paired Variance Harvest | $-30.55 | $-32.15 |

## Frozen-rule explanations

### Quiet-Variance Carry

Buy UPRO for the next cash session only when the prior session's realized one-minute variance is no greater than the median of the prior 20 completed sessions. The claim is a volatility-drag gate on the positive equity risk premium, not a price-trend signal.

### Downside-Variance Handoff

Buy SPXU only after an above-median-variance session in which negative minute returns contributed more than half of realized variance; buy UPRO otherwise. The claim is persistence of deleveraging pressure, measured from semivariance rather than return direction.

### Paired Variance Harvest

Buy $50 each of UPRO and SPXU, rebalance their liquidation values to 50/50 at 12:31 by crossing the observed quotes, and liquidate at 15:55. The claim is constant-mix harvesting of oscillation without forecasting SPY direction.

## Robustness and interpretation

- **Quiet-Variance Carry:** development +1-cent stress $6.35; five-minute delay $13.46; full-period P&L without ten best sessions $-27.68. Failed development gates: each development year positive, ending cash above spy, positive after removing ten best sessions.
- **Downside-Variance Handoff:** development +1-cent stress $-81.95; five-minute delay $-61.14; full-period P&L without ten best sessions $-169.90. Failed development gates: profit factor at least one, each development year positive, ending cash above spy, positive after one extra cent each fill, positive after five minute entry delay, positive after removing ten best sessions.
- **Paired Variance Harvest:** development +1-cent stress $-101.35; five-minute delay $-38.02; full-period P&L without ten best sessions $-69.76. Failed development gates: profit factor at least one, each development year positive, ending cash above spy, positive after one extra cent each fill, positive after five minute entry delay, positive after removing ten best sessions.

A backtest cannot establish that an outcome was “not luck.” The pre-registration, untouched rule application, year splits, cost stress, delayed execution, winner deletion, and SPY hurdle reduce the chance of fooling ourselves; they do not eliminate it.

The simulation also assumes the full account can be redeployed each eligible session. A literal US cash account can be constrained by settlement and good-faith-violation rules, so operational feasibility is separate from signal performance.

Machine-readable results: `research_scout/upro_spxu_variance_state_results_v9.json`.
