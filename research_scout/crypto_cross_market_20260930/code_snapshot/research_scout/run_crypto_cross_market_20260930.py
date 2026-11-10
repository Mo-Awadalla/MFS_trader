"""Frozen BTC-to-ETH incremental information screen, with conservative costs."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from research.crypto_cross_market import FEATURES, make_panel, replay
from research.crypto_symbol_cache import build_symbol_day, digest, load_cache

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/crypto_cross_market_20260930"
TRAIN = ["2023-08-15", "2023-09-15", "2023-10-15", "2023-11-15", "2023-12-15"]
SELECT = ["2024-01-15", "2024-01-21", "2024-01-28", "2024-01-31"]
MODEL = {"max_iter": 100, "max_leaf_nodes": 7, "min_samples_leaf": 200, "learning_rate": .05,
             "l2_regularization": 10, "early_stopping": False, "random_state": 93026}
TRIALS = 42


def build_day_panel(day):
    paths, audits = {}, []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        path, audit = build_symbol_day(symbol, day)
        paths[symbol] = path
        audits.append(audit)
    eth_book, eth_trades = load_cache(paths["ETHUSDT"])
    btc_book, btc_trades = load_cache(paths["BTCUSDT"])
    panel = make_panel(day, eth_book, eth_trades, btc_book, btc_trades)
    panel.to_parquet(OUTPUT / "panels" / f"{day}.parquet", index=False)
    return day, audits, len(panel), int(panel.eligible.sum())


def summarize(ledger, daily):
    complete = bool(daily.complete.all())
    pnl = daily.closed_trade_pnl.to_numpy()
    priced = ledger.loc[ledger.status.eq("priced")] if len(ledger) else ledger
    rng = np.random.default_rng(93026)
    boot = pnl[rng.integers(0, len(pnl), (20000, len(pnl)))].mean(axis=1)
    return {"complete": complete, "closed_trade_pnl": float(pnl.sum()), "net_dollars": float(pnl.sum()) if complete else None,
                "trades": len(priced), "positive_days": int((pnl > 0).sum()) if complete else None,
                "gross_dollars": float(priced.gross_dollars.sum()) if len(priced) else 0,
                "fees": float(priced.fees.sum()) if len(priced) else 0,
                "slippage_dollars": float(priced.slippage_dollars.sum()) if len(priced) else 0,
                "daily_mean_ci95": np.quantile(boot, [.025, .975]).tolist() if complete else None,
                "adjusted_daily_mean_lower": float(np.quantile(boot, .05 / TRIALS)) if complete else None,
                "net_excluding_best_day": float(pnl.sum() - pnl.max()) if complete else None,
                "daily": daily.to_dict("records")}


def main():
    (OUTPUT / "panels").mkdir(parents=True, exist_ok=True)
    if (OUTPUT / "results.json").exists() or (OUTPUT / "specification.json").exists():
        raise FileExistsError("Frozen batch already started")
    code = [ROOT / name for name in ("research/crypto_cross_market.py", "research/crypto_symbol_cache.py",
                                     "research_scout/run_crypto_cross_market_20260930.py")]
    spec = {"created_at_utc": datetime.now(UTC).isoformat(), "train": TRAIN, "selection": SELECT,
                "hypothesis": "BTC returns and aggressive flow can add useful ETH direction/magnitude information beyond ETH price and ETH flow alone",
                "features": FEATURES, "model": MODEL, "horizons_seconds": [30, 120], "configurations": 6,
                "version_count_for_multiplicity": TRIALS,
                "clocks": "10-second decisions; 250ms feed delay, then 1s outbound latency; 3s outbound stress; all features strictly prior to feed clock",
                "costs": "5bp taker fee plus 1bp adverse execution-cost allowance EACH SIDE; displayed bid/ask crossing; doubled fees stress uses 10bp each side",
                "orders": "Max $1000 ticket on a $10000 daily account, <=10% of visible pre-decision touch size, 0.001 ETH units. IOC entry with causal 5bp price collar and actual arrival-size partial fills. Missing entry/exit or inadequate exit depth invalidates day.",
                "scheduling": "One position at a time with exit acknowledgement before reentry. No positions spanning 08:00/16:00/24:00 UTC funding boundaries.",
                "gate": "Complete and profitable under all stresses; >=100 base fills; >=3 of 4 positive selection days; 42-version-adjusted date bootstrap lower>0; profit remains excluding best day. Cross-flow also must beat own-flow matched-date control.",
                "limits": "All selected historical dates have earlier research exposure. Four selection dates cannot establish production reliability. Aggregate event timestamps plus assumed delay are not measured receipt or execution latency. Historical tape is unaffected by simulated orders.",
                "code_sha256": {str(p.relative_to(ROOT)): digest(p) for p in code}}
    (OUTPUT / "specification.json").write_text(json.dumps(spec, indent=2) + "\n")
    audits, failures = [], []
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(build_day_panel, day): day for day in TRAIN + SELECT}
        for job in as_completed(jobs):
            try:
                day, records, rows, eligible = job.result()
                audits.extend(records)
                print(f"{day}: {rows} paired clocks, {eligible} eligible ETH clocks", flush=True)
            except Exception as error:
                failures.append({"date": jobs[job], "error": str(error)})
                print(f"Admission failure {jobs[job]}: {error}", flush=True)
    (OUTPUT / "data_audit.json").write_text(json.dumps({"sources": audits, "failures": failures}, indent=2) + "\n")
    if failures:
        (OUTPUT / "results.json").write_text(json.dumps({"verdict": "DATA_ADMISSION_FAILED_BEFORE_MODELING", "failures": failures}, indent=2))
        return
    training = pd.concat([pd.read_parquet(OUTPUT / "panels" / f"{day}.parquet") for day in TRAIN], ignore_index=True)
    selection = pd.concat([pd.read_parquet(OUTPUT / "panels" / f"{day}.parquet") for day in SELECT], ignore_index=True)
    results, predictions, survivors = {}, selection[["date", "decision_ms"]].copy(), []
    for horizon in (30, 120):
        target = f"target_1000_{horizon}"
        fitting = training.loc[training.eligible & np.isfinite(training[target])]
        for family, features in FEATURES.items():
            name = f"{family}_{horizon}s"
            with threadpool_limits(limits=2):
                model = HistGradientBoostingRegressor(**MODEL).fit(fitting[features], fitting[target])
                forecast = model.predict(selection[features])
            predictions[name] = forecast
            scenarios = {}
            for scenario, arguments in {"base": {}, "double_fees": {"fee_bps": 10}, "latency_3s": {"delay_ms": 3000}}.items():
                ledger, daily = replay(selection, forecast, horizon, **arguments)
                ledger.to_parquet(OUTPUT / f"{name}_{scenario}_trades.parquet", index=False)
                daily.to_parquet(OUTPUT / f"{name}_{scenario}_daily.parquet", index=False)
                scenarios[scenario] = summarize(ledger, daily)
            b = scenarios["base"]
            passed = (all(s["complete"] and s["net_dollars"] > 0 for s in scenarios.values())
                      and b["trades"] >= 100 and b["positive_days"] >= 3
                      and b["adjusted_daily_mean_lower"] > 0 and b["net_excluding_best_day"] > 0)
            paired = None
            if family == "cross_flow":
                control = results[f"own_flow_{horizon}s"]["scenarios"]["base"]
                if b["complete"] and control["complete"]:
                    deltas = np.array([row["closed_trade_pnl"] for row in b["daily"]]) - np.array([row["closed_trade_pnl"] for row in control["daily"]])
                    paired = {"total_incremental_pnl": float(deltas.sum()), "daily_deltas": deltas.tolist()}
                    passed = passed and deltas.sum() > 0
                else:
                    passed = False
            results[name] = {"fit_rows": len(fitting), "forecast_abs_bps_quantiles": np.quantile(np.abs(forecast), [.5, .95, .99, 1]).tolist(),
                                 "scenarios": scenarios, "paired_control": paired, "passed_gate": bool(passed)}
            if passed:
                survivors.append(name)
            print(f"{name}: net={b['net_dollars']}, gross={b['gross_dollars']:.2f}, trades={b['trades']}, pass={passed}", flush=True)
    predictions.to_parquet(OUTPUT / "selection_predictions.parquet", index=False)
    assert all(digest(path) == spec["code_sha256"][str(path.relative_to(ROOT))] for path in code)
    result = {"verdict": "CANDIDATES_REQUIRE_FURTHER_STRESS" if survivors else "NO_SELECTION_SURVIVOR",
                  "survivors": survivors, "results": results, "later_history_opened": False}
    (OUTPUT / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(result["verdict"], flush=True)


if __name__ == "__main__":
    main()
