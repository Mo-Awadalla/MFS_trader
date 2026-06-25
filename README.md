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
pip install -e ".[dev,alpaca,crypto,research,monitoring,alerts]"
```

## Run

```bash
cp .env.example .env  # fill in API keys
mfs-data download --config config/research.toml
mfs-engine --config config/paper.toml
```
