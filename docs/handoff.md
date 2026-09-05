# Handoff: ETF SIP Paper-Evidence Campaign

Updated: 2026-09-05

## Current Goal

Produce a reproducible release and collect qualifying paper evidence for a
new frozen Alpaca SIP ETF successor only after data entitlement, parity, and
validation gates pass.

The latest-SPY SIP entitlement preflight at `2026-09-05T21:12:16.148693+00:00`
returned HTTP 403 for requested recent data. It does not block historical
acquisition: a separate read-only historical SIP probe for all seven ETFs
succeeded at `2026-09-05T21:18:56.184538+00:00` for
`2026-09-03T00:00:00Z` through `2026-09-04T00:00:00Z` with `feed=sip` and
`adjustment=all`. This limited probe is not a frozen input manifest or a full
common-history/completeness result. Do not substitute IEX; freeze and validate
only after the remaining historical-input, parity, and identity gates pass.

The authoritative historical Yahoo Experiment remains
`119131fa-0f67-48d7-ab87-f20d81c70c1f` /
`8e584c2eb4ba20a90b0af3d62a8f28c1d753a83a3e57ca79deafb869af23270e` with
promotion status `paper_ops`. Preserve it unchanged; it is not the SIP
successor and cannot be reused for different data provenance.

Perform the full read-only historical seven-symbol panel check and record feed,
as-of time, requested range, universe, and completeness. Only then create the immutable input manifest and a new
Experiment identity, run the unchanged gauntlet and session-level economic
parity reconciliation, then execute the paper gates in sequence.

## Suggested Skills

- `implement` for continued coding.
- `tdd` for adding missing coverage around broker failure drills and pass-window edge cases.
- `review` before merging the branch.
- `handoff` if context needs compacting again.

## What Is Implemented

- Immutable per-session report artifacts under `paper/sessions/{session_id}/...` in `experiments/artifacts.py`.
- Paper Ops Smoke report generation:
  - `paper_ops_smoke_report.json`
  - requires `session_kind=paper_ops_smoke`
  - requires 5 market sessions, 7 calendar days, zero unplanned interruptions, no unexplained missed cycles, and kill-switch drill evidence
  - writes `promotion_unlocked: false`
- Paper Ops Pass report generation from session + SQLite runtime evidence:
  - `operator_report.json`
  - `reconciliation_report.json`
  - `slippage_report.json`
  - `bar_cycle_report.json`
  - `kill_switch_drill_report.json`
- `confirm-paper-ops-pass` now requires `--paper-session-id` and refuses unless a full immutable `paper_ops_pass` session satisfies the 30-day/20-session/100-trade gate and all required reports pass.
- Confirmation writes immutable `paper_ops_pass_confirmation.json`.
- Continuous paper runs now:
  - record bar-cycle rows in the immutable session artifact
  - halt on unexplained missed price cycles instead of silently sleeping
  - snapshot `order_lifecycle` from `orders_live`
  - reconcile broker state on every bar cycle via `TradingEngine.reconcile_broker()`
  - record broker-sync ids in each bar-cycle record
- CLI split:
  - `paper-run --broker alpaca_paper --alpaca-paper-smoke` runs one-shot Alpaca submit/cancel smoke.
  - `paper-run --broker alpaca_paper` without `--alpaca-paper-smoke` runs the continuous paper loop, gated by `--confirm-paper-broker`.

## Important Files

- `engine/paper_session.py`
- `engine/paper_run.py`
- `engine/cli.py`
- `engine/runtime.py`
- `experiments/artifacts.py`
- `experiments/operator_confirmations.py`
- `tests/unit/test_paper_session.py`
- `tests/unit/test_paper_run.py`
- `tests/unit/test_operator_confirmations.py`
- `tests/unit/test_cli_smoke.py`

## Verification Run

Latest local audit after pulling `origin/main` and fixing event idempotency passed:

- `.venv/Scripts/python -m pytest tests/unit/test_paper_session.py tests/unit/test_paper_run.py tests/unit/test_operator_confirmations.py tests/unit/test_cli_smoke.py`
- `.venv/Scripts/python -m ruff check storage/event_logger.py engine/paper_session.py engine/paper_run.py engine/cli.py engine/runtime.py experiments/artifacts.py experiments/operator_confirmations.py tests/unit/test_paper_session.py tests/unit/test_paper_run.py tests/unit/test_operator_confirmations.py tests/unit/test_cli_smoke.py`

Fix note: `storage/event_logger.py` now gives automatically generated events unique idempotency keys unless a caller supplies an explicit key. This prevents legitimate heartbeats/reconciliation/bar-cycle markers from being suppressed on Windows timestamp collisions, which had made operational reports show false bar-cycle mismatches.

Earlier broad verification before the implementation commit passed:

- `.venv/bin/python -m pytest tests/unit`
- `.venv/bin/python -m pytest tests/integration`
- `.venv/bin/python -m pytest tests/contracts tests/replay tests/property`
- `.venv/bin/python -m ruff check ...` on touched files

Latest targeted audit after compaction passed:

- `.venv/bin/python -m pytest tests/unit/test_paper_session.py tests/unit/test_paper_run.py tests/unit/test_operator_confirmations.py tests/unit/test_cli_smoke.py`
  - Result: 42 passed, 1 skipped.
- `.venv/bin/python -m ruff check engine/paper_session.py engine/paper_run.py engine/cli.py engine/runtime.py experiments/artifacts.py experiments/operator_confirmations.py tests/unit/test_paper_session.py tests/unit/test_paper_run.py tests/unit/test_operator_confirmations.py tests/unit/test_cli_smoke.py`
  - Result: all checks passed.

Latest broad re-run was started but intentionally interrupted by the user:

- `.venv/bin/python -m pytest tests/unit`
- `.venv/bin/python -m pytest tests/integration`
- `.venv/bin/python -m pytest tests/contracts tests/replay tests/property`

Known not passing:

- `.venv/bin/python -m mypy experiments/artifacts.py engine/paper_session.py engine/paper_run.py experiments/operator_confirmations.py`
- Remaining mypy failures are in existing dependencies (`portfolio/sizing.py`, `risk/engine.py`, `monitoring/reports.py`, `engine/runtime.py`) plus the existing `_OperationalReportShim` typing issue in `engine/paper_session.py`.

## Commit And Push Status

- `origin/main` was pulled successfully through `b45cec6 Update paper ops handoff`.
- Fix commit `2ebd83d Fix paper ops event evidence` was pushed to `origin/main`.

## Remaining Work

- Latest trading attempt: downloaded Alpaca IEX AAPL daily bars and froze `BB-AAPL-1D-v2-Alpaca-IEX-2020-2026` as Experiment `68127d37-d4d3-4516-be61-ccf8148161e1`. Validation failed, so it is not eligible for `paper_ops` and no paper broker session should be run for it. Evidence is under `experiments/68127d37-d4d3-4516-be61-ccf8148161e1/validation/`.
- Latest broader strategy attempt: tested a frozen residual volatility-managed cross-sectional momentum hypothesis as `ResidualVolMomentum-v1-LargeCapDaily-2018-2026` / Experiment `5b8514cc-5f1b-4c63-b815-6f90a26c5aba` on a bounded 75-stock large-cap universe plus SPY/QQQ/IWM daily bars. It failed validation decisively: research Sharpe `-0.6302`, research total return `-0.4219`, WFA OOS Sharpe `-0.65 < 0.8`, WFA OOS Sortino `-1.17 < 1.0`, negative fold fraction `0.73 > 0.5`, MC ruin probability `0.908 >= 0.05`, MC 5th percentile CAGR `-0.139 <= 0`, MC 95th percentile max drawdown `-0.449 < -0.3`, and DSR had no positive Sharpe to deflate. Do not paper trade it. Only the immutable failed Experiment evidence was retained; the failed strategy implementation should not be kept active in the registry.
- Latest low-API ETF strategy attempt: tested a frozen long-only ETF tactical momentum hypothesis as `ETFTacticalMomentum-v1-Daily-2010-2026` / Experiment `017c9b19-14ee-4b0b-92f7-7e5d8886ba2c` on SPY, QQQ, IWM, IEF, GLD, SHY, and DBC daily bars. It failed validation: research Sharpe `0.4628`, research total return `0.3214`, WFA OOS Sharpe `0.52 < 0.8`, WFA OOS Sortino `0.83 < 1.0`, DSR p-value `0.0605 >= 0.05`, and DSR collapsed under raw trial count with `p = 0.5590 >= 0.10`. Monte Carlo did not fail (`P(ruin)=0.0026`, 5th percentile CAGR `0.00105`, 95th percentile max drawdown `-0.143`), so this was healthier than the previous failed attempts but still not eligible for `paper_ops`. Do not paper trade it or switch to the better adjacent `top_n=2` row after seeing results; that would be tuning.
- Latest residual reversal attempt: `ResidualReversalStatArb-v1-LiquidLargeCapDaily-AlpacaSIP` / Experiment `886f5819-9b51-4ff8-b025-11fbdd8dd06a` failed validation and is not paper-trade eligible. The `$10,000` to `$3.02` headline was mostly cost/turnover compounding, not pure anti-alpha: average daily turnover was `3.4216x` equity, average gross signal return was only `-0.9079` bps/day, and repo default average daily cost drag was `36.3887` bps/day. Cost sensitivity: true gross/no explicit cost ended around `$7,295.81` with Sharpe `-0.1351`, while repo default ended around `$3.02` with Sharpe `-5.5304`. Future high-turnover strategy reviews must decompose gross return, trading-cost drag, borrow drag, turnover, cost sensitivity, Rank IC, and execution alignment before interpreting headline final equity. See `docs/adr/0004-decompose-turnover-cost-drag-before-strategy-verdicts.md`.
- Latest validation-passed strategy/data-version: reran the unchanged frozen `ETFTimeSeriesMomentumVolTarget-v1` rules as a new long-history Yahoo adjusted daily data-version Experiment `119131fa-0f67-48d7-ab87-f20d81c70c1f` / `ETFTimeSeriesMomentumVolTarget-v1-YahooAdjustedDaily-2005-2026`. Data source is `yahoo_chart_static_etf_tsm_v1_adjusted_cached`, using adjusted OHLC from Yahoo Chart API for SPY, QQQ, IWM, IEF, GLD, SHY, and DBC. Panel date range is `2005-01-03` to `2026-06-29`; DBC starts `2006-02-06`. Validation passed: research Sharpe `0.7954`, total return `4.0944`, WFA OOS Sharpe `0.8386`, negative fold fraction `0.2692`, Monte Carlo `P(loss)=0.0`, `P(ruin)=0.0001`, 5th percentile CAGR `0.05923`, 95th percentile max drawdown `-0.1648`, DSR p-value `3.48e-07`, and stability passed. Promotion status is `validation_passed`. This is the first current candidate eligible for the next paper-ops gate, but no Alpaca paper broker session has been started yet.
- Next: run paper-ops/sim drills only for validation-passed Experiment `119131fa-0f67-48d7-ab87-f20d81c70c1f`; do not use any validation-failed Experiment.
- Exercise the continuous Alpaca paper loop against real Alpaca paper credentials for a real smoke window.
- Add stronger broker-failure drill automation for continuous sessions, not just report-level evidence.
- Add explicit reconciliation repair/blocker workflow artifacts for mismatches that are resolved versus blocked.
- Consider making slippage samples generated from order/fill reference prices instead of requiring supplied samples.
- Clean up repository-wide mypy failures if strict typing is a release requirement.

## Worktree Warning

The repo had many unrelated modified/untracked files before this handoff, including graphify cache churn, pairs work, config/model changes, and deleted `docs/handoff.md`. Keep commits scoped carefully.
