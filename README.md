# mfs-trader

Medium-frequency trading system for US equities and crypto on daily/hourly bars.

## Philosophy

The edge comes from honest validation and execution discipline, not clever math. Most strategies die in the gauntlet. The 1-2 that survive have a real chance.

## Build order

- Phase 1: Minimal end-to-end skeleton (config, storage, data, MA baseline, research runner)
- Phase 2: Validation engine (WFA, Monte Carlo, DSR, parameter stability)
- Phase 3: Execution skeleton (portfolio, risk, execution, engine, monitoring)
- Phase 4: Real strategies (BB, pairs, CSMR)

See `docs/PLAN.md` for the full design.

## Install

```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash
pip install -e ".[dev,alpaca,crypto,research,monitoring,alerts]"
```

## Local smoke checks

These commands do not require broker credentials:

```bash
mfs-data --config config/research.toml status
mfs-engine --config config/paper.toml preflight
mfs-engine shakedown-ma --out-dir runs/ma_shakedown
mfs-engine report --db runs/ma_shakedown/baseline.sqlite --allow-blockers
```

## Run with real broker/data credentials

```bash
cp .env.example .env  # fill in API keys
mfs-data --config config/research.toml download
mfs-engine --config config/paper.toml preflight
```

Live mode is intentionally gated by `config/live.toml`; it refuses to start unless `live_deployment.authorized = true` and live credentials/caps are configured.
