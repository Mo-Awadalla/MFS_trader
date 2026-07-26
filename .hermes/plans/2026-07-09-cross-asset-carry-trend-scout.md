# Cross-Asset Carry Trend Scout Implementation Plan

> **For Hermes:** Use subagent-driven-development review after local TDD implementation.

**Goal:** Implement and run the single frozen `CrossAssetCarryTrendScout-v1` against the pinned public pysystemtrade panel, producing reproducible gross, net, robustness, and SPY-utility evidence.

**Architecture:** A research-only module will load the ignored normalized Parquet artifacts, calculate contract-aware carry/trend features, build monthly risk-scaled targets, and simulate recursive futures point P&L with explicit execution lag, drift, rolls, and costs. A thin script will load cached SPY data and write deterministic JSON and Markdown reports. This scout will not register a strategy or enter the Validation Gauntlet.

**Tech Stack:** Python 3.12, pandas, NumPy, PyArrow, pytest, existing `research.runner.compute_metrics`.

---

### Task 1: Lock signal math with unit tests

**Objective:** Prove contract-spacing, carry direction, trend differences, missing-data behavior, monthly rebalancing, and execution lag before implementing the simulator.

**Files:**
- Create: `tests/unit/test_cross_asset_carry_trend_scout.py`
- Create: `research/cross_asset_carry_trend_scout.py`

**Steps:**
1. Write synthetic tests for earlier/later carry contracts producing the same backwardation sign.
2. Test malformed, zero-gap, and over-24-month contract identifiers.
3. Test 252-session trend and 63/42-session ex-ante point volatility.
4. Test missing carry never becomes combined trend-only exposure.
5. Test month-end targets require eight active markets and first earn P&L after the frozen execution lag.
6. Run the targeted test and confirm it fails before implementation.
7. Implement the minimum feature and target-generation code.
8. Run the targeted test to green.

### Task 2: Implement recursive futures simulation

**Objective:** Model point P&L, equity drift, scheduled rebalances, contract rolls, notional caps, and one-way costs without hidden daily rebalancing.

**Files:**
- Modify: `research/cross_asset_carry_trend_scout.py`
- Modify: `tests/unit/test_cross_asset_carry_trend_scout.py`

**Steps:**
1. Add tests for constant contract quantity between rebalances.
2. Add tests that a contract change charges close plus open turnover.
3. Add tests for 35% market and 300% gross-notional caps.
4. Add tests for zero/2/5-bps monotonic cost drag.
5. Implement the recursive state loop and result dataclasses.
6. Run targeted tests and Ruff.

### Task 3: Implement frozen diagnostics and gates

**Objective:** Produce attribution, subperiods, asset-class contributions, leave-one-class-out results, concentration, cost sensitivity, and SPY overlays exactly as frozen.

**Files:**
- Modify: `research/cross_asset_carry_trend_scout.py`
- Modify: `tests/unit/test_cross_asset_carry_trend_scout.py`

**Steps:**
1. Test every hard gate with deterministic synthetic returns and diagnostics.
2. Implement carry-only, trend-only, and combined runs using identical construction.
3. Implement pre/post-2017 and leave-one-class-out runs.
4. Implement 20% and primary 50% SPY overlays.
5. Implement monthly profit and asset-class concentration diagnostics.
6. Run targeted tests and Ruff.

### Task 4: Build and run the report command

**Objective:** Load the pinned artifacts, run exactly one frozen scout, and save deterministic evidence.

**Files:**
- Create: `scripts/run_cross_asset_carry_trend_scout.py`
- Create: `docs/reports/cross_asset_carry_trend_scout.json`
- Create: `docs/reports/cross_asset_carry_trend_scout.md`

**Steps:**
1. Add CLI defaults pinned to the source artifact and frozen dates.
2. Load cached Yahoo SPY closes without network access.
3. Refuse to run if the source commit or 15-market manifest differs from the frozen spec.
4. Write JSON first, then a human-readable Markdown rendering of the same result.
5. Run once and record the verdict without tuning.

### Task 5: Review and verification

**Objective:** Catch specification, lookahead, accounting, and reporting defects before accepting the scout result.

**Files:**
- Review all files above plus `docs/strategy_sources/CrossAssetCarryTrendScout-v1.md`.

**Steps:**
1. Dispatch a specification-compliance review.
2. Dispatch a code-quality and quant-accounting review after spec compliance.
3. Fix every critical or important issue and add regression coverage.
4. Re-run the one frozen scout only if a code defect changes results; preserve prior report evidence in the session record.
5. Run targeted pytest, Ruff, Python compilation, and `git diff --check`.
6. Report the definitive pass/fail and limitations. Do not commit unless requested.
