# Handoff: Phase 1 Continuous Paper Ops

Updated: 2026-06-28

## Current Goal

Implement Phase 1 Continuous Paper Ops:

- Paper Ops Smoke as a non-promoting evidence sub-gate under `promotion_status=paper_ops`.
- Full immutable Paper Ops Pass gate before `paper_ops -> live_dry_run`.
- Immutable paper session artifacts, bar-cycle tracking, order lifecycle persistence, multi-cycle reconciliation, slippage aggregation, drill reports, operator reports, and manual `confirm-paper-ops-pass`.

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
- Find or create a new frozen Experiment that genuinely passes the Validation Gauntlet before running sim drills or Alpaca paper smoke.
- Exercise the continuous Alpaca paper loop against real Alpaca paper credentials for a real smoke window.
- Add stronger broker-failure drill automation for continuous sessions, not just report-level evidence.
- Add explicit reconciliation repair/blocker workflow artifacts for mismatches that are resolved versus blocked.
- Consider making slippage samples generated from order/fill reference prices instead of requiring supplied samples.
- Clean up repository-wide mypy failures if strict typing is a release requirement.

## Worktree Warning

The repo had many unrelated modified/untracked files before this handoff, including graphify cache churn, pairs work, config/model changes, and deleted `docs/handoff.md`. Keep commits scoped carefully.
