# mfs-trader

Python systematic-trading research and execution platform built around one principle: strategies are hypotheses, not assets. A hypothesis is frozen as an immutable Experiment, punished with realistic costs, validated through a statistical gauntlet, and only then allowed to move toward paper/live operational gates.

This is a portfolio/research engineering project, not trading advice and not live-trading approval.

## Why this repo exists

Most trading repos show a backtest. This repo tries to show the harder engineering loop:

1. Predeclare a source-backed hypothesis.
2. Freeze the exact Experiment snapshot: strategy, parameters, universe, data version, costs, risk profile, portfolio config, git commit, and seed.
3. Run an honest Validation Gauntlet: walk-forward analysis, Monte Carlo, Deflated Sharpe Ratio, and parameter stability.
4. Archive both passes and failures as immutable evidence.
5. Gate paper/live operation behind broker reconciliation, risk controls, caps, kill switches, and manual promotion confirmations.

## Current status

- Package: `mfs-trader`
- Primary language: Python 3.11+
- Current strongest candidate: `ETFTimeSeriesMomentumVolTarget-v1-YahooAdjustedDaily-2005-2026`
- Current promotion status: `validation_passed`
- Paper/live status: not approved; next step is paper-ops evidence, not live deployment

## Validated candidate

| Experiment | Data | Status | Sharpe | WFA OOS Sharpe | MC P(ruin) | DSR p-value | Max DD | Notes |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `ETFTimeSeriesMomentumVolTarget-v1` | Yahoo adjusted daily ETFs, 2005-2026 | `validation_passed` | 0.7954 | 0.8386 | 0.0001 | 3.48e-07 | -17.30% | Source-backed ETF absolute momentum + inverse-volatility / volatility-targeting rules |

Evidence:

- Validation report: `experiments/119131fa-0f67-48d7-ab87-f20d81c70c1f/validation/report.md`
- Frozen metadata: `experiments/119131fa-0f67-48d7-ab87-f20d81c70c1f/metadata.json`
- Source memo: `docs/strategy_sources/ETFTimeSeriesMomentumVolTarget-v1.md`
- SPY comparison: `docs/reports/etf_tsm_spy_comparison.md`
- Runtime/sim-broker replay: `docs/reports/etf_tsm_engine_replay/etf_tsm_engine_replay.md`

### ETF TSM vs SPY

Using the same cached Yahoo adjusted daily data panel:

| Metric | ETF TSM vol-target | SPY buy-and-hold |
| --- | ---: | ---: |
| Total return | 4.09x | 8.13x |
| CAGR | 7.89% | 10.86% |
| Sharpe | 0.7954 | 0.6388 |
| Sortino | 1.0009 | 0.7805 |
| Annual volatility | 10.20% | 18.96% |
| Max drawdown | -17.30% | -55.19% |
| Final equity | $50,944.37 | $91,284.71 |

![ETF TSM equity vs SPY](docs/assets/etf_tsm_equity_vs_spy.png)

![ETF TSM drawdown vs SPY](docs/assets/etf_tsm_drawdown_vs_spy.png)

Interpretation: SPY had higher absolute return over this sample, while the ETF TSM candidate had better risk-adjusted behavior and much smaller drawdowns. That is why the next question is portfolio utility and operational paper-readiness, not automatic live trading.

### ETF TSM runtime replay

The validated candidate also has a no-credential runtime replay through the engine, portfolio sizing, risk checks, OMS, SQLite order/position state, and simulated broker fills:

| Check | Result |
| --- | ---: |
| Bars/cycles | 5,405 / 5,405 |
| Orders submitted/filled/rejected/timed out | 1,072 / 1,072 / 0 / 0 |
| Operational blockers | 0 |
| Replay status | PASS |

Report: `docs/reports/etf_tsm_engine_replay/etf_tsm_engine_replay.md`.

Scope: this proves the validated ETF target weights can pass through runtime plumbing in simulation. It is still not Alpaca paper/live broker approval.

## Failed honestly, not tuned after the fact

| Experiment | Verdict | Why it matters |
| --- | --- | --- |
| `ResidualReversalStatArb-v1-LiquidLargeCapDaily-AlpacaSIP` | Failed validation | Headline collapse was decomposed into weak gross signal plus extreme turnover/cost drag; not rescued by post-result tuning. See `docs/adr/0004-decompose-turnover-cost-drag-before-strategy-verdicts.md`. |
| `ETFTacticalMomentum-v1-Daily-2010-2026` | Failed validation | Monte Carlo was healthier, but WFA/DSR missed thresholds. The adjacent `top_n=2` row was not promoted after seeing results. |
| `ResidualVolMomentum-v1-LargeCapDaily-2018-2026` | Failed validation | Failed WFA, MC, and DSR decisively; archived rather than paper-traded. |

This failure archive is intentional. The gauntlet is the strategy-selection engine.

## Architecture

```text
config/          TOML config and typed schema
storage/         SQLite event/order state and Parquet market data helpers
data/            Alpaca/Yahoo/CCXT-style download, validation, resampling
strategies/      Pure signal/target-weight strategy templates
research/        Vectorized research, sweeps, source-backed pipelines
validation/      WFA, Monte Carlo, DSR, and parameter-stability gauntlet
experiments/     Immutable Experiment registry, hashes, promotion status, artifacts
portfolio/       Target-position and sizing logic
risk/            Exposure, drawdown, sector/correlation, and kill-switch checks
execution/       Broker adapters, simulated broker, OMS, order state machine
engine/          Runtime loop, replay, shakedown, paper/live gate commands
monitoring/      Operational report and alert plumbing
tests/           Unit, integration, replay, and contract tests
```

Core design docs:

- System plan: `docs/PLAN.md`
- Domain vocabulary and promotion rules: `CONTEXT.md`
- Artifact manager ADR: `docs/adr/0001-artifact-manager-owns-canonical-experiment-artifacts.md`
- Paper broker authority ADR: `docs/adr/0003-alpaca-paper-runs-are-one-shot-gated-broker-sessions.md`

## Validation Gauntlet

A frozen Experiment must pass all four checks before it can be considered for paper ops:

1. Walk-forward analysis: OOS Sharpe/Sortino and fold stability.
2. Monte Carlo: block-bootstrap path stress, P(loss), P(ruin), CAGR, drawdown distribution.
3. Deflated Sharpe Ratio: adjusts for multiple trials / effective trial count.
4. Parameter stability: rejects isolated parameter peaks.

The implementation lives in `validation/gauntlet.py` with sub-engines under `validation/wfa`, `validation/mc`, `validation/dsr`, and `validation/stability`.

## Operational safety spine

The repo includes paper/live plumbing, but broker authority is intentionally gated:

- deterministic client order IDs
- 12-state order lifecycle plus separate reconciliation status
- simulated broker failure modes
- risk engine with exposure/drawdown/sector/correlation checks
- Experiment-scoped kill switches
- immutable paper-session evidence
- manual confirmations for paper/live promotion
- live mode gated by `config/live.toml` and explicit authorization flags

Paper ops proves implementation behavior, not alpha. Live deployment still requires manual approval and capped capital.

## Quickstart

### Reproducible dev setup

```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pip install -e . --no-deps
```

For all optional broker/research/monitoring extras instead of the locked minimal dev set:

```bash
pip install -e ".[dev,alpaca,crypto,research,monitoring,alerts]"
```

### No-credential local smoke

These commands do not require broker credentials:

```bash
mfs-data --config config/research.toml status
mfs-engine --config config/paper.toml preflight
mfs-engine shakedown-ma --out-dir runs/ma_shakedown
mfs-engine report --db runs/ma_shakedown/baseline.sqlite --allow-blockers
```

Expected result for the shakedown is `MA shakedown status: PASS`. It exercises synthetic data quality, research backtest, engine replay, sim-broker fills, rejection, timeout, partial-fill scenarios, and operational reports.

### Regenerate the SPY comparison artifacts

```bash
python scripts/build_etf_tsm_spy_report.py
```

Outputs:

- `docs/reports/etf_tsm_spy_comparison.md`
- `docs/assets/etf_tsm_equity_vs_spy.png`
- `docs/assets/etf_tsm_drawdown_vs_spy.png`

### Run the ETF TSM runtime replay

```bash
python -m engine.cli --config config/research.toml replay-etf-tsm --out-dir runs/etf_tsm_engine_replay
```

Expected result is `ETF TSM engine replay status: PASS`. The command requires cached Yahoo ETF bars under `data/parquet/equity/yahoo_chart`; it does not require broker credentials and writes runtime/operational artifacts under the chosen output directory.

## Quality gates

Local checks:

```bash
python -m ruff check .
python -m pytest tests/unit tests/contracts tests/integration/test_ma_shakedown.py
```

GitHub Actions workflow: `.github/workflows/ci.yml`.

Live broker tests are skipped unless explicitly enabled with `RUN_LIVE_BROKER_TESTS=1`. Test collection does not load `.env` by default; set `MFS_TEST_LOAD_DOTENV=1` only for explicit live-broker runs.

## Credentials and live mode

Copy `.env.example` to `.env` only for local broker/data credentials. Never commit `.env`.

```bash
cp .env.example .env
```

Live mode is intentionally gated by `config/live.toml`; it refuses to start unless `live_deployment.authorized = true` and live credentials/caps are configured.

## Known limitations / next serious work

- The current public repo should be renamed from the old `untitled_project` remote before resume use.
- ETF TSM has passed simulated runtime replay, but continuous Alpaca paper ops has not yet been run for the validation-passed candidate.
- The runtime replay uses a target-weight adapter and simulated broker; real paper broker authority remains a separate evidence gate.

## License / reuse

`pyproject.toml` currently marks this as proprietary. Treat this as a source-visible portfolio project unless a formal open-source license is added.
