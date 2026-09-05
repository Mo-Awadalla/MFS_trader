# FTRE v1 validation postmortem

## Verdict

FTRE v1 is `validation_failed`. Archive it without changing the frozen experiment.

## Evidence

- Effective validation window: 2021-12-21 through 2026-06-30, bounded by Binance OI/taker metrics plus the frozen 20-day warmup.
- Scheduled observations: 4,959 per symbol; 14,877 total.
- Gap-overlap exclusions: BTCUSDT 25 (0.504%), ETHUSDT 25 (0.504%), SOLUSDT 44 (0.887%). No series was interpolated.
- Events with funding strictly above 20 bps: zero.
- Maximum funding: BTCUSDT 8.81 bps, ETHUSDT 10.17 bps, SOLUSDT 11.93 bps.

With no observations surviving the first frozen trigger condition, WFA cannot form folds, Monte
Carlo has no OOS event returns, DSR has no positive Sharpe to deflate, and parameter stability has
no sweep surface. Execution-adapter and paper-ops work remain gated off.

## Decision

Do not lower the funding threshold in place. Any revised threshold, venue, funding normalization,
or use of off-cycle settlements is a new hypothesis and must be frozen as a new Experiment with
the v1 trial included in DSR accounting.
