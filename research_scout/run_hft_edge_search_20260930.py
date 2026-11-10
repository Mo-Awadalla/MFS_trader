"""Fixed nine-model development screen; later history opens only after a survivor."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from research.hft_quote_edge import (
    BOOK_FEATURES,
    HORIZONS,
    PRICE_FEATURES,
    SYMBOLS,
    replay,
    summarize,
    symbol_panel,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "external_artifacts/databento_cash_etf_mbp1_open_v55"
OUTPUT = ROOT / "research_scout/hft_edge_search_20260930"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract(path_text: str) -> dict:
    path = Path(path_text)
    day = path.name.removesuffix(".dbn.zst")
    target = OUTPUT / "panels" / f"{day}.parquet"
    audit_path = target.with_suffix(".json")
    extractor_sha256 = sha256(ROOT / "research/hft_quote_edge.py")
    if target.exists() and audit_path.exists():
        audit = json.loads(audit_path.read_text())
        if audit["source_sha256"] != sha256(path):
            raise ValueError(f"changed input {path}")
        if audit.get("extractor_sha256") == extractor_sha256:
            return audit
    frame = db.read_dbn(path).to_df(map_symbols=True, tz="UTC").reset_index()
    if not frame.ts_recv.is_monotonic_increasing:
        raise ValueError(f"nonmonotonic input {day}")
    panels = [symbol_panel(frame, day, symbol) for symbol in SYMBOLS]
    panel = pd.concat(panels, ignore_index=True)
    audit = {"date": day, "source_sha256": sha256(path), "extractor_sha256": extractor_sha256, "source_rows": len(frame),
             "decision_rows": len(panel), "eligible": int(panel.eligible.sum()),
             "symbols": sorted(panel.symbol.unique().tolist())}
    target.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(target, index=False)
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")
    return audit


def freeze() -> dict:
    path = OUTPUT / "specification.json"
    if path.exists():
        return json.loads(path.read_text())
    validation = json.loads((DATA / "validation_report.json").read_text())
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "objective": "Raw profit after costs on equal $10,000 starting capital; reliability gates before ranking.",
        "status": "Exploratory research on previously exposed history, not competition or live approval.",
        "competition": "Name, eligible instruments, benchmark, scoring period and execution rules unresolved.",
        "train": "2023-03-28 through 2024-12-31",
        "selection": "2025-01-01 through 2025-12-31",
        "historical_evaluation": "2026 files only after selection gate; not pristine confirmation",
        "untouched_confirmation": "Required, not yet available",
        "families": ["price_ridge", "book_ridge", "book_histboost"],
        "horizons_seconds": list(HORIZONS), "trials": 9,
        "ridge_alpha": 100.0, "boost": {"iterations": 100, "leaf_nodes": 15, "min_samples_leaf": 200, "l2": 10},
        "feature_clock": "Completed F_LAST messages with ts_recv strictly before decision; exclude bad receive timestamps",
        "decisions": "Every 5 seconds, 09:30:30 to 09:37:30 ET; max exit 09:39:33",
        "latency_ms": [250, 1000, 3000], "max_quote_age_seconds": 1,
        "execution": "Marketable long positions, one at a time, no leverage, buy ask/sell bid, integer shares",
        "sizing": "$10,000 start; maximum available cash and 10% of decision/arrival ask size; exit cannot exceed displayed bid size",
        "costs": "1 bp adverse slippage each side + $0.005/share each side + 0.0000051 sell notional + $0.000119/share sell; assumptions, not verified competition fees",
        "action": "Largest predicted crossing return minus current estimated costs exceeds 1 bp; fixed threshold",
        "selection_gate": "Complete; >=100 trades and >=60 trade days; 9-trial adjusted 5-day-block bootstrap lower mean daily P&L >0; positive under extra 1bp/side and 1s latency; positive excluding best 5 days",
        "known_degraded_dates": validation["known_degraded_dates_equs_mini"],
        "degraded_policy": "Prespecified historical data-quality exclusions; results conditional on these exclusions, not deployable calendar returns",
        "feed_limit": "EQUS.MINI anonymized aggregated component-venue BBO; not full NBBO, no venue routing, no queue or actual fill guarantee",
        "trial_accounting": "Nine new candidates; prior repository searches remain unquantified dependent selection exposure; correction does not erase them",
        "source": "https://databento.com/docs/venues-and-datasets/equs-mini",
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    return spec


def build(spec: dict, workers: int, *, forward: bool = False, limit: int | None = None):
    files = sorted((DATA / "EQUS.MINI/mbp-1").glob("*.dbn.zst"))
    files = [p for p in files if (p.name[:4] == "2026") == forward
             and p.name.removesuffix(".dbn.zst") not in spec["known_degraded_dates"]]
    if limit:
        files = files[:limit]
    audits = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = [pool.submit(extract, str(path)) for path in files]
        for count, job in enumerate(as_completed(jobs), 1):
            audits.append(job.result())
            if count % 40 == 0 or count == len(files):
                print(f"decoded {count}/{len(files)} sessions", flush=True)
    name = "forward" if forward else "development"
    (OUTPUT / f"{name}_data_audit.json").write_text(json.dumps(sorted(audits, key=lambda x: x['date']), indent=2) + "\n")
    return pd.concat([pd.read_parquet(OUTPUT / "panels" / (p.name.removesuffix(".dbn.zst") + ".parquet")) for p in files], ignore_index=True)


def fit_model(family: str, train: pd.DataFrame, horizon: int):
    features = PRICE_FEATURES if family == "price_ridge" else BOOK_FEATURES
    target = f"target_250_{horizon}"
    good = train.eligible & np.isfinite(train[target])
    if family.endswith("ridge"):
        estimator = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=100.0))
    else:
        estimator = HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=15,
                                                 min_samples_leaf=200, l2_regularization=10,
                                                 early_stopping=False, random_state=93026)
    estimator.fit(train.loc[good, features], train.loc[good, target])
    return estimator, features


def evaluate_candidate(panel: pd.DataFrame, prediction: np.ndarray, horizon: int, prefix: str):
    results = {}
    settings = {
        "base": {}, "double_slippage": {"slippage_bps": 2.0},
        "latency_1s": {"delay": 1000}, "latency_3s": {"delay": 3000},
        "wider_spread_1bp": {"spread_stress_bps": 1.0},
    }
    for name, kwargs in settings.items():
        ledger, daily = replay(panel, prediction, horizon, **kwargs)
        results[name] = summarize(ledger, daily)
        ledger.to_parquet(OUTPUT / f"{prefix}_{name}_trades.parquet", index=False)
        daily.to_parquet(OUTPUT / f"{prefix}_{name}_daily.parquet", index=False)
    base = results["base"]
    results["selection_gate"] = bool(
        all(r["complete"] for r in results.values())
        and base["trades"] >= 100 and base["trade_days"] >= 60
        and base["mean_daily_pnl_familywise_lower"] > 0
        and base["net_without_best_five_days"] > 0
        and results["double_slippage"]["net_dollars"] > 0
        and results["latency_1s"]["net_dollars"] > 0
    )
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--max-files", type=int)
    args = parser.parse_args()
    spec = freeze()
    panel = build(spec, args.workers, limit=args.max_files)
    print(f"panel: {len(panel)} rows, {panel.date.nunique()} dates", flush=True)
    if args.build_only or args.max_files:
        return
    train = panel.loc[panel.date < "2025-01-01"]
    selection = panel.loc[panel.date >= "2025-01-01"].copy()
    report = {"created_at_utc": datetime.now(UTC).isoformat(),
              "specification_sha256": sha256(OUTPUT / "specification.json"),
              "code_sha256": sha256(ROOT / "research/hft_quote_edge.py"),
              "train_dates": train.date.nunique(), "selection_dates": selection.date.nunique(),
              "candidates": {}, "historical_evaluation_opened": False}
    models = {}
    with threadpool_limits(limits=2):
        for horizon in HORIZONS:
            for family in spec["families"]:
                name = f"{family}_{horizon}s"
                print(f"fit {name}", flush=True)
                estimator, features = fit_model(family, train, horizon)
                prediction = estimator.predict(selection[features])
                result = evaluate_candidate(selection, prediction, horizon, name)
                report["candidates"][name] = result
                models[name] = (estimator, features, horizon)
                print(f"{name}: base=${result['base']['net_dollars']:.2f}, trades={result['base']['trades']}, gate={result['selection_gate']}", flush=True)
                (OUTPUT / "development_results.json").write_text(json.dumps(report, indent=2) + "\n")
        survivors = [name for name, result in report["candidates"].items() if result["selection_gate"]]
        if survivors:
            winner = max(survivors, key=lambda name: report["candidates"][name]["base"]["net_dollars"])
            report["frozen_winner"] = winner
            (OUTPUT / "selected_candidate.json").write_text(json.dumps({"winner": winner, "created_at_utc": datetime.now(UTC).isoformat()}, indent=2) + "\n")
            forward = build(spec, args.workers, forward=True)
            estimator, features, horizon = models[winner]
            report["historical_evaluation_opened"] = True
            report["historical_evaluation"] = evaluate_candidate(forward, estimator.predict(forward[features]), horizon, "historical_evaluation")
            report["verdict"] = "HISTORICAL_SURVIVOR_REQUIRES_FRESH_CONFIRMATION" if report["historical_evaluation"]["selection_gate"] else "FAILED_LATER_HISTORY"
        else:
            report["verdict"] = "NO_SELECTION_SURVIVOR_LATER_HISTORY_UNOPENED"
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["verdict"], flush=True)


if __name__ == "__main__":
    main()
