# Candidate C12 — DispersionGated TSMOM

## Hypothesis

C5 (Bayesian DMA) falsified the "speed up the signal" hypothesis: dynamic
lookback selection degraded performance. C12 tests the complementary
hypothesis: the weekly 12-week TSMOM base signal is fine, but it should not
trade through high cross-sectional dispersion regimes, where asset-selection
lag is worst. Keep the base signal untouched; gate exposure when dispersion
is elevated.

## Specification

- **Base signal**: existing weekly 12-week TSMOM (63-day momentum, long-only,
  inverse 20-day vol sizing, 50% per-asset cap, gross ≤ 1.0, SHY cash proxy,
  W-FRI rebalance, next-session-open execution). Unchanged from prior work.
- **Universe**: existing 10 risk ETFs (SPY, QQQ, IWM, IEF, GLD, DBC, EFA,
  EEM, VNQ, TLT) + SHY.
- **Gate signal**:
  1. Weekly returns per ETF from closes strictly before each weekly label
     (same no-lookahead convention as the base signal).
  2. Cross-sectional dispersion = std of same-week returns across the 10
     risk ETFs.
  3. Smooth with a rolling mean over N weeks.
  4. Threshold = 0.80 quantile of smoothed dispersion over the **first 52
     weekly observations only** (training window). Frozen; never re-estimated.
  5. Gate is inactive inside the training window (pure baseline there), so
     the threshold is never applied to the data that produced it.
  6. If smoothed dispersion > threshold at a rebalance date: apply the gate
     action. Otherwise run the normal base signal.

### Pre-declared variants (no parameter search)

| Variant | Smoothing window | Threshold quantile | Gate action |
|---|---|---|---|
| `C12_v1_hard_cash` | 4 weeks | 0.80 | 100% cash proxy |
| `C12_v2_soft_shrink` | 4 weeks | 0.80 | 50% exposure, remainder to cash |
| `C12_v3_8w_hard_cash` | 8 weeks | 0.80 | 100% cash proxy |

No further variants without an explicit new declaration. The threshold is
not re-tuned after seeing out-of-sample results.

## How to run

```bash
python3 -m research.candidate_runner list
python3 -m research.candidate_runner run C12_v1_hard_cash
python3 -m research.candidate_runner run --family C12_DispersionGated_TSMOM
```

Artifacts land in `research/artifacts/c12/<variant>/`:
`report.json` (standardized metrics, WFA/MC/DSR, stress windows, gate
diagnostics), plus `returns.parquet`, `gross_returns.parquet`,
`weights.parquet`, `gate_diagnostics.parquet`.

## Verdict criteria (declared before evaluation)

A variant is verdict `prioritize_c12_gate_for_review` only if, versus its
own gate-disabled baseline on identical data and costs:

1. rolling 12-week negative-Sharpe fraction improves (stability), **and**
2. max drawdown improves, **and**
3. Sharpe within 0.10 of baseline.

One of the three → `partial_improvement_not_priority`. None →
`reject_c12_variant`. Promotion beyond review still requires the house
gauntlet (strict WFA, MC 5th-pct Sharpe > 0.10, DSR p < 0.05, strict
stability); a `prioritize` verdict is a research signal, not a promotion.

## Results (2021-06-30 → 2026-06, net of costs)

| | Sharpe | CAGR | MaxDD | Calmar | Stab. score | Gate-on % | WFA | MC | DSR p |
|---|---|---|---|---|---|---|---|---|---|
| Baseline (gate off) | 0.328 | — | -0.333 | — | 0.711 | — | — | — | — |
| C12_v1_hard_cash | 0.167 | 0.013 | -0.349 | 0.037 | 0.683 | 8.6% | fail | fail | 0.355 |
| C12_v2_soft_shrink | 0.252 | 0.024 | -0.341 | 0.070 | 0.703 | 8.6% | fail | fail | 0.287 |
| C12_v3_8w_hard_cash | 0.347 | 0.036 | -0.311 | 0.114 | 0.712 | 6.2% | pass | fail | 0.220 |

Verdicts: v1 reject, v2 reject, v3 `prioritize_c12_gate_for_review`.

Interpretation:

- 4-week smoothing (v1/v2) gates the wrong weeks: baseline Sharpe **during**
  v1/v2 gate-on periods was +1.96 — the gate removed good exposure. Both
  variants underperform baseline on every axis. Hypothesis falsified at
  4-week smoothing.
- 8-week smoothing (v3) gates weeks where baseline Sharpe was -0.45; it
  improved 2022 (-19.3% vs -21.9%), max drawdown, and Sharpe, with 2023/2025
  untouched (gate never fired). Directionally consistent with the
  hypothesis, but the stability improvement is marginal (negative fraction
  0.288 vs 0.289) and MC/DSR still fail.
- **Overall**: C12 does not fix the stability failure class that killed
  C2/C3/C5. v3 earns review priority under the declared criteria but is not
  promotable. Any follow-up (e.g. different smoothing) would be a new
  declared candidate, not a tweak to these.

Stress-window and gate-overlap detail is in each variant's `report.json`
(`stress_windows`, `gate_diagnostics`).

## Relationship to `dispersion_gate_v1`

`research/etf_tsmom_dispersion_gate.py` (CrossSectionalDispersionGateWeeklyETF-v1)
is an earlier, different formulation: daily-return dispersion, 21-day
smoothing, rolling 252-day quantile threshold. It is preserved untouched,
along with its artifacts. C12 supersedes it conceptually with weekly
dispersion and a frozen in-sample threshold.
