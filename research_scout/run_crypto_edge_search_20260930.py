"""Cost-aware BTC screen using audited cached quotes; no imaginary passive fills.

The archive is selected, already-exposed history. Any survivor needs raw size
replay, more dates, current venue fees, and truly new confirmation observations.
"""

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

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "research_scout/btc_withdrawal_aggression_v1"
OUTPUT = ROOT / "research_scout/crypto_edge_search_20260930"
PRICE = ["prior_mid_return_30s", "prior_abs_mid_return_60s", "current_spread_bps"]
BOOK = PRICE + ["log_current_touch_depth", "current_depth_imbalance",
                "log_30s_taker_notional", "log_30s_book_update_count",
                "negative_log_touch_depth_change_30s", "spread_change_bps_30s",
                "signed_taker_notional_imbalance_30s"]


def read_days(days: list[str]) -> pd.DataFrame:
    return pd.concat([pd.read_parquet(INPUT / f"panel_{day}.parquet") for day in days], ignore_index=True)


def target(frame: pd.DataFrame) -> np.ndarray:
    entry_mid = (frame.entry_buy + frame.entry_sell) / 2
    exit_mid = (frame.exit_buy + frame.exit_sell) / 2
    return ((exit_mid / entry_mid - 1) * 1e4).to_numpy()


def simulate(frame: pd.DataFrame, prediction: np.ndarray, margin: float, fee_side: float = 5.0,
             slippage_side: float = 1.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Signal threshold is always fixed at BASE costs. Stress never changes selection.
    work = frame.copy()
    work["prediction"] = prediction
    signal = np.abs(prediction) > (12.0 + work.current_spread_bps.to_numpy() + margin)
    # Avoid crossing known scheduled funding boundaries; no unmodeled funding cash flow.
    entry_s = work.second.to_numpy() + 1
    exit_s = entry_s + 60
    crosses = np.zeros(len(work), dtype=bool)
    for boundary in (28800, 57600, 86400):
        crosses |= (entry_s <= boundary) & (exit_s >= boundary)
    work["signal"] = signal & ~crosses
    cash = 10000.0
    ledger, daily = [], []
    for day, rows in work.groupby("date", sort=True):
        start = cash
        free_at = -1
        for row in rows.loc[rows.signal].sort_values("second").to_dict("records"):
            if row["second"] <= free_at:
                continue
            direction = 1 if row["prediction"] > 0 else -1
            entry = row["entry_buy"] if direction > 0 else row["entry_sell"]
            exit_price = row["exit_buy"] if direction > 0 else row["exit_sell"]
            gross_bps = direction * (exit_price / entry - 1) * 1e4
            # Correct cash fees on both entry and exit notionals; adverse fills both sides.
            fill_entry = entry * (1 + direction * slippage_side / 1e4)
            fill_exit = exit_price * (1 - direction * slippage_side / 1e4)
            qty = cash / (fill_entry * (1 + fee_side / 1e4))
            fees = qty * (fill_entry + fill_exit) * fee_side / 1e4
            pnl = direction * qty * (fill_exit - fill_entry) - fees
            cash += pnl
            free_at = row["second"] + 61
            ledger.append({"date": day, "second": row["second"], "direction": direction,
                           "entry": entry, "exit": exit_price, "quantity": qty,
                           "prediction": row["prediction"], "gross_bps": gross_bps,
                           "net_bps": pnl / (qty * fill_entry) * 1e4, "pnl": pnl,
                           "fees": fees, "cash": cash})
        daily.append({"date": day, "pnl": cash - start, "cash": cash,
                      "return": cash / start - 1})
    return pd.DataFrame(ledger), pd.DataFrame(daily)


def summary(ledger: pd.DataFrame, daily: pd.DataFrame) -> dict:
    v = daily.pnl.to_numpy()
    rng = np.random.default_rng(93026)
    boot = v[rng.integers(0, len(v), (20000, len(v)))].mean(axis=1)
    curve = np.r_[10000, daily.cash.to_numpy()]
    return {"days": len(v), "trades": len(ledger), "net_dollars": float(v.sum()),
            "positive_days": int((v > 0).sum()),
            "trade_days": int((v != 0).sum()),
            "mean_gross_bps": float(ledger.gross_bps.mean()) if len(ledger) else None,
            "mean_net_bps": float(ledger.net_bps.mean()) if len(ledger) else None,
            "net_without_best_day": float(v.sum() - v.max()),
            "daily_mean_ci95": np.quantile(boot, [0.025, 0.975]).tolist(),
            "nine_trial_adjusted_daily_mean_lower": float(np.quantile(boot, 0.05 / 9)),
            "max_drawdown_pct": float(np.min(curve / np.maximum.accumulate(curve) - 1) * 100),
            "by_date": {r["date"]: r["pnl"] for r in daily.to_dict("records")}}


def evaluate(frame, prediction, margin, name):
    results = {}
    for scenario, fee, slip in [("base", 5, 1), ("double_fees", 10, 1),
                                ("double_slippage", 5, 2), ("zero_fee_diagnostic", 0, 0)]:
        ledger, daily = simulate(frame, prediction, margin, fee, slip)
        results[scenario] = summary(ledger, daily)
        ledger.to_parquet(OUTPUT / f"{name}_{scenario}_trades.parquet", index=False)
        daily.to_parquet(OUTPUT / f"{name}_{scenario}_daily.parquet", index=False)
    b = results["base"]
    results["screen_pass"] = bool(b["trades"] >= 100 and b["trade_days"] >= 3
                                  and b["positive_days"] >= 3
                                  and b["nine_trial_adjusted_daily_mean_lower"] > 0
                                  and b["net_without_best_day"] > 0
                                  and results["double_fees"]["net_dollars"] > 0
                                  and results["double_slippage"]["net_dollars"] > 0)
    return results


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    original = json.loads((ROOT / "research_scout/btc_withdrawal_aggression_prereg_20260925.json").read_text())
    splits = original["splits"]
    spec = {
        "created_at_utc": datetime.now(UTC).isoformat(), "splits": splits,
        "hypothesis": "Direct conditional return magnitude can isolate events that exceed execution costs even where unconditional classification is uneconomic.",
        "families": ["price_ridge", "book_ridge", "book_boost"], "margin_bps": [0, 5, 10],
        "trials": 9, "ridge_alpha": 100,
        "boost": {"iterations": 100, "leaf_nodes": 7, "min_samples_leaf": 100, "l2": 10},
        "target": "60s delayed entry-to-exit midpoint arithmetic return; direct regression, no accuracy objective",
        "execution": "BTCUSDT perpetual, hypothetical one position, at most 1x capital, 1s delay, 60s hold, observed bid/ask; 5bps fee and 1bp slippage EACH side",
        "selection": "Fixed net-cost thresholds, largest expected sign; never relax threshold after seeing validation",
        "funding": "No entries crossing 00:00/08:00/16:00 UTC; no estimated funding profit",
        "capacity": "Size at entry/exit missing in cache: this is an optimistic small-order feasibility screen, cannot establish deployable capacity",
        "freshness": "Inherited <=1s at both execution quotes; original extraction filtered unavailable future quotes, so admission is conditional and cannot be a complete forward trading path",
        "confirmation": "All dates previously exposed; even a screen pass is provisional and needs fresh dates and raw replay",
        "screen_gate": ">=100 trades, >=3 positive selection days, 9-trial adjusted date-bootstrap lower>0, profit excluding best day, positive doubled fees/slippage",
        "paid_requests": False,
    }
    frozen = OUTPUT / "specification.json"
    if frozen.exists():
        raise FileExistsError("Preserve the existing frozen batch; use a separately versioned run for changes")
    frozen.write_text(json.dumps(spec, indent=2) + "\n")
    train = read_days(splits["train"])
    val = read_days(splits["validation_diagnostics_only"])
    report = {"created_at_utc": datetime.now(UTC).isoformat(), "candidates": {},
              "historical_test_opened": False, "input_sha256": {}}
    for day in splits["train"] + splits["validation_diagnostics_only"]:
        p = INPUT / f"panel_{day}.parquet"
        report["input_sha256"][day] = hashlib.sha256(p.read_bytes()).hexdigest()
    models = {}
    with threadpool_limits(limits=2):
        for family in spec["families"]:
            features = PRICE if family == "price_ridge" else BOOK
            if family.endswith("ridge"):
                model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=100))
            else:
                model = HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=7, min_samples_leaf=100,
                                                     l2_regularization=10, early_stopping=False, random_state=93026)
            model.fit(train[features], target(train))
            prediction = model.predict(val[features])
            for margin in spec["margin_bps"]:
                name = f"{family}_margin{margin}"
                result = evaluate(val, prediction, margin, name)
                models[name] = (model, features, margin)
                report["candidates"][name] = result
                print(f"{name}: ${result['base']['net_dollars']:.2f}, {result['base']['trades']} trades, pass={result['screen_pass']}", flush=True)
        survivors = [k for k,v in report["candidates"].items() if v["screen_pass"]]
        if survivors:
            winner = max(survivors, key=lambda k: report["candidates"][k]["base"]["net_dollars"])
            (OUTPUT / "frozen_selection.json").write_text(json.dumps({"winner": winner, "created_at_utc": datetime.now(UTC).isoformat()}, indent=2))
            test = read_days(splits["historical_test"])
            model, features, margin = models[winner]
            report["winner"] = winner
            report["historical_test_opened"] = True
            report["historical_test"] = evaluate(test, model.predict(test[features]), margin, "historical_test")
            report["verdict"] = "PROVISIONAL_SURVIVOR_REQUIRES_RAW_REPLAY" if report["historical_test"]["screen_pass"] else "FAILED_LATER_DATES"
        else:
            report["verdict"] = "NO_COST_AWARE_CRYPTO_SURVIVOR"
    report["code_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(report["verdict"], flush=True)


if __name__ == "__main__":
    main()
