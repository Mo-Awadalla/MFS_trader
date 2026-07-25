# BTC Confirmed Short-Squeeze Continuation v1 — Feasibility Result

Date run: 2026-07-25

Status: **FAILED NON-RETURN RECURRENCE CHECK; DEVELOPMENT RETURNS NOT OPENED**

## Frozen specification

- Specification: `research_scout/bitcoin_confirmed_short_squeeze_continuation_v1.json`
- SHA-256: `acc2b10d97e80c7a5af1036b608622b8f843ec17e88bef1fc4c57c808fe103e4`
- Feasibility report:
  `data/parquet/bitcoin_confirmed_short_squeeze_continuation_v1/feasibility/report.json`

The specification was hashed before this check. The feasibility runner did not
construct or inspect forward returns.

## Point-in-time data audit

All four required inputs had unique timestamps and the implemented availability
checks passed:

- 561,024 BTCUSDT spot five-minute bars;
- 560,389 futures-metrics observations;
- 6,576 settled funding observations;
- 104,877 premium-index half-hour bars.

The common point-in-time construction produced 3,869 complete twice-daily
decisions. Of those, 3,689 had the required strict-prior rolling history.

## Candidate funnel

- Rolling-normalization-ready decisions: 3,689
- Stage-1 trapped-short setups: 249
- Stage-2 squeeze confirmations: 3

The analogue model can only reject Stage-2 events; it cannot create additional
events. The complete six-year sample therefore contains at most three trades,
before the analogue abstention rule and rolling 24-hour entry throttle.

## Verdict

The frozen development gate requires at least 50 completed trades. Since the
entire dataset contains only three mechanical Stage-2 candidates, that gate is
impossible to satisfy.

This is a recurrence failure. In accordance with the preregistered stopping
rules, development returns were not evaluated, validation and holdout remain
locked, and thresholds were not relaxed.

Any successor must be registered as a new trial with a materially different
mechanism or information source. This result does not support paper or live
trading.
