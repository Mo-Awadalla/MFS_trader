# Fundamental-Event Smart Reversal Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Implement and honestly evaluate a frozen daily smart short-term reversal strategy that vetoes entries and exits holdings around point-in-time SEC material filings, then compare its after-cost utility with SPY.

**Architecture:** Cache SEC submissions data under ignored `data/parquet/`, normalize filing acceptance timestamps into conservative next-session event flags, append those flags to the existing multi-symbol OHLCV panel, and generate stateful quintile target weights with median-cross exits. Reuse the shared cross-sectional backtester for research, add explicit gross/cost/turnover/rank-IC/SPY diagnostics, and do not promote through the known-flawed gauntlet.

**Tech Stack:** Python 3.12, pandas, requests, Parquet, pytest, existing strategy/Experiment contracts.

---

### Task 1: Freeze the hypothesis

**Files:**
- Create: `docs/strategy_sources/FundamentalEventSmartReversal-v1.md`

Document the exact universe, signal chronology, SEC forms, availability policy, six-session veto, quintile entries, median-cross exits, sizing, costs, diagnostics, and no-tuning rule before downloading event data or running results.

### Task 2: Add SEC filing-event ingestion

**Files:**
- Create: `data/sec_filings.py`
- Create: `scripts/download_sec_filing_events.py`
- Test: `tests/unit/test_sec_filings.py`

Implement ticker-to-CIK mapping with frozen overrides for renamed symbols, SEC fair-access headers/rate limiting, recent and archived submissions parsing, exact acceptance timestamps, deterministic deduplication, Parquet caching, and conservative first-session-after-acceptance event flags.

Verification: `python -m pytest tests/unit/test_sec_filings.py -q`.

### Task 3: Implement the stateful strategy

**Files:**
- Create: `strategies/fundamental_event_smart_reversal/__init__.py`
- Create: `strategies/fundamental_event_smart_reversal/signal.py`
- Create: `strategies/fundamental_event_smart_reversal/strategy.py`
- Modify: `strategies/registry.py`
- Modify additively: `tests/contracts/helpers.py`
- Create: `tests/unit/test_fundamental_event_smart_reversal_signal.py`

Implement daily five-session ranking, one-session execution skip through the shared lag, symmetric material-event veto, event/eligibility forced exits, bottom/top quintile entries, median-cross retention, deterministic ties, and equal-weight dollar-neutral targets.

Verification: targeted signal tests and strategy contract suite.

### Task 4: Add research and SPY diagnostics

**Files:**
- Create: `research/fundamental_event_smart_reversal_pipeline.py`
- Create: `scripts/run_fundamental_event_smart_reversal_scout.py`
- Test: `tests/unit/test_fundamental_event_smart_reversal_pipeline.py`

Report gross/no-cost performance, default costs, borrow, turnover, cost sensitivity, rank IC, event-veto counts, beta/alpha/correlation to SPY, direct SPY metrics, and a predeclared 100% SPY plus 20% gross strategy overlay. Label results as survivorship-biased scout evidence and block promotion until validator defects and point-in-time universe coverage are fixed.

### Task 5: Acquire data and run once

Use cached Alpaca SIP daily bars, download SEC submissions with a compliant user agent, run the frozen scout exactly once, and save a deterministic JSON/Markdown report under `docs/reports/`.

Do not modify parameters after seeing results. If gross/no-cost performance is nonpositive, archive the hypothesis.

### Task 6: Verify and review

Run targeted tests, Ruff on changed Python files, the full pytest suite, `git diff --check`, and an integration/code-quality review. Separate pre-existing suite failures from changes introduced here. Do not commit or push.
