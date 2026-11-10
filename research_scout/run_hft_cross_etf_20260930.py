"""Separately frozen cross-fund information screen on existing development panels."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from research.hft_quote_edge import BOOK_FEATURES, HORIZONS, replay, summarize

ROOT = Path(__file__).resolve().parents[1]
PANELS = ROOT / "research_scout/hft_edge_search_20260930/panels"
OUTPUT = ROOT / "research_scout/hft_cross_etf_20260930"
CROSS = [f"cross_residual_{lag}" for lag in (1, 5, 30)] + [
    "cross_microprice", "cross_ofi_5", "cross_dispersion_5", "peer_count"
]


def cross_features(panel: pd.DataFrame) -> pd.DataFrame:
    frame = panel.copy()
    valid = frame.quote_age_s.le(1) & frame.eligible
    keys = [frame.date, frame.second]
    for lag in (1, 5, 30):
        underlying = (frame[f"ret_{lag}"] / frame.leverage).where(valid)
        common = underlying.groupby(keys).transform("median")
        frame[f"cross_residual_{lag}"] = common * frame.leverage - frame[f"ret_{lag}"]
        if lag == 5:
            frame["cross_dispersion_5"] = underlying.groupby(keys).transform("std")
    for field, name in [("microprice_bps", "cross_microprice"), ("ofi_5", "cross_ofi_5")]:
        # Sign inversion aligns bearish funds with the underlying; no quantity multiplier.
        aligned = (frame[field] * np.sign(frame.leverage)).where(valid)
        frame[name] = aligned.groupby(keys).transform("median") * np.sign(frame.leverage)
    frame["peer_count"] = valid.astype(int).groupby(keys).transform("sum")
    return frame


def evaluate(frame, prediction, horizon, name):
    results = {}
    for scenario, kwargs in {
        "base": {}, "double_slippage": {"slippage_bps": 2},
        "latency_1s": {"delay": 1000}, "latency_3s": {"delay": 3000},
        "wider_spread_1bp": {"spread_stress_bps": 1},
    }.items():
        ledger, daily = replay(frame, prediction, horizon, **kwargs)
        results[scenario] = summarize(ledger, daily, trials=24)
        ledger.to_parquet(OUTPUT / f"{name}_{scenario}_trades.parquet", index=False)
        daily.to_parquet(OUTPUT / f"{name}_{scenario}_daily.parquet", index=False)
    b = results["base"]
    results["selection_gate"] = bool(all(r["complete"] for r in results.values())
        and b["trades"] >= 100 and b["trade_days"] >= 60
        and b["mean_daily_pnl_familywise_lower"] > 0 and b["net_without_best_five_days"] > 0
        and results["double_slippage"]["net_dollars"] > 0
        and results["latency_1s"]["net_dollars"] > 0)
    return results


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frozen = OUTPUT / "specification.json"
    if frozen.exists():
        raise FileExistsError("This frozen batch already exists")
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "hypothesis": "Synchronized quote changes in other S&P ETFs predict return magnitude beyond a fund's own price/book state after delayed marketable costs.",
        "novelty": "Incremental feature-set screen; related cross-ETF hypotheses already failed in this repository. This is not claimed as a novel mechanism or pristine test.",
        "features": BOOK_FEATURES + CROSS, "families": ["ridge", "histboost"],
        "horizons": list(HORIZONS), "new_trials": 6, "session_trials_including_prior_batches": 24,
        "train": "2023-2024", "selection": "2025 admitted dates; previously exposed development history",
        "historical_evaluation": "No 2026 outcomes unless a candidate passes selection",
        "execution_and_gate": "Same fixed threshold, costs, whole-share size and missing-exit blockers as first batch; bootstrap correction uses 24 trials",
        "parameters": "Ridge alpha100; boosted trees 100 iterations,15 leaves,200 minimum samples/leaf,L2=10; no tuning",
        "future_data": "Only synchronous same-date/same-clock peer features, no cross-date/as-of-forward fill",
    }
    frozen.write_text(json.dumps(spec, indent=2) + "\n")
    paths = sorted(p for p in PANELS.glob("*.parquet") if p.stem < "2026-01-01")
    panel = cross_features(pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True))
    train = panel.loc[panel.date < "2025-01-01"]
    selection = panel.loc[panel.date >= "2025-01-01"]
    features = BOOK_FEATURES + CROSS
    report = {"candidates": {}, "historical_evaluation_opened": False,
              "data_dates": panel.date.nunique(),
              "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    models = {}
    with threadpool_limits(limits=2):
        for horizon in HORIZONS:
            target = f"target_250_{horizon}"
            eligible = train.eligible & np.isfinite(train[target])
            for family in spec["families"]:
                if family == "ridge":
                    model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=100))
                else:
                    model = HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=15, min_samples_leaf=200,
                                                         l2_regularization=10, early_stopping=False, random_state=93026)
                name = f"cross_{family}_{horizon}s"
                print(f"fit {name}", flush=True)
                model.fit(train.loc[eligible, features], train.loc[eligible, target])
                result = evaluate(selection, model.predict(selection[features]), horizon, name)
                report["candidates"][name] = result
                models[name] = (model, horizon)
                print(f"{name}: ${result['base']['net_dollars']:.2f}, trades={result['base']['trades']}, complete={result['base']['complete']}, pass={result['selection_gate']}", flush=True)
                (OUTPUT / "progress.json").write_text(json.dumps(report, indent=2) + "\n")
        survivors = [k for k,v in report["candidates"].items() if v["selection_gate"]]
        if survivors:
            winner = max(survivors, key=lambda k: report["candidates"][k]["base"]["net_dollars"])
            (OUTPUT / "frozen_selection.json").write_text(json.dumps({"winner": winner, "created_at_utc": datetime.now(UTC).isoformat()}, indent=2))
            from research_scout.run_hft_edge_search_20260930 import build, freeze
            later = cross_features(build(freeze(), workers=2, forward=True))
            model, horizon = models[winner]
            report["historical_evaluation_opened"] = True
            report["winner"] = winner
            report["historical_evaluation"] = evaluate(later, model.predict(later[features]), horizon, "historical_evaluation")
            report["verdict"] = "HISTORICAL_SURVIVOR_REQUIRES_FRESH_DATA" if report["historical_evaluation"]["selection_gate"] else "FAILED_LATER_HISTORY"
        else:
            report["verdict"] = "NO_CROSS_ETF_SURVIVOR"
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["verdict"], flush=True)


if __name__ == "__main__":
    main()
