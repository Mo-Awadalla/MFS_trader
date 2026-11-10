"""Clean-date official Binance replication of frozen cross-scale coupling H30."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research_scout.test_multiscale_candidates_legacy_replication import blocked_test
from research_scout.test_multiscale_liquidity_v4 import estimator, scores

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout" / "navier_stokes_liquidity_v2"
PANEL = BASE / "bbo_replication_results" / "feature_panel.parquet"
TRADES = BASE / "free_data" / "binance-public" / "futures-um" / "BTCUSDT" / "2024-01-15" / "BTCUSDT-aggTrades-2024-01-15.zip"
OUTPUT = BASE / "h30_binance_clean_replication_results"
FEATURE = "cross_scale_coupling"
BASELINE = [
    "spread_mean",
    "spread_last",
    "depth_mean",
    "depth_min",
    "imbalance_mean",
    "imbalance_last",
    "realized_vol_60s",
    "trade_volume",
    "signed_trade_imbalance",
    "event_rate",
]


def cross_scale_feature(index: pd.DatetimeIndex) -> pd.Series:
    trades = pd.read_csv(
        TRADES,
        compression="zip",
        usecols=["quantity", "transact_time", "is_buyer_maker"],
    )
    signed = np.where(trades["is_buyer_maker"].astype(bool), -trades["quantity"], trades["quantity"])
    start_ms = int(index[0].value // 1_000_000)
    seconds = (trades["transact_time"].to_numpy(np.int64) - start_ms) // 1_000
    valid = (seconds >= 0) & (seconds < 86_400)
    flow = np.bincount(seconds[valid], weights=signed[valid], minlength=86_400).astype(float)
    coarse = pd.Series(flow).rolling(10, min_periods=2).sum().to_numpy()
    values = []
    for bin_number in range(8_640):
        end = bin_number * 10 + 9
        fine_window = flow[max(0, end - 59) : end + 1]
        coarse_window = coarse[max(0, end - 59) : end + 1]
        if len(fine_window) >= 10 and np.std(np.abs(fine_window)) > 0 and np.std(np.abs(coarse_window)) > 0:
            values.append(float(np.corrcoef(np.abs(fine_window), np.abs(coarse_window))[0, 1]))
        else:
            values.append(0.0)
    return pd.Series(values, index=index[:8_640], name=FEATURE)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base = pd.read_parquet(PANEL).iloc[:8_640].copy()
    frame = base.join(cross_scale_feature(base.index), how="left").replace([np.inf, -np.inf], np.nan)
    usable = frame.dropna(subset=["future_max_excursion_bps"])
    first, second = int(len(usable) * 0.6), int(len(usable) * 0.8)
    train, validation, test = usable.iloc[:first], usable.iloc[first:second], usable.iloc[second:]
    threshold = float(train["future_max_excursion_bps"].quantile(0.95))
    y_train = train["future_max_excursion_bps"].ge(threshold)
    model_results = {}
    for name, features in (("baseline", BASELINE), ("augmented", BASELINE + [FEATURE])):
        fitted = estimator().fit(train[features], y_train)
        model_results[name] = {}
        for split_name, split in (("validation", validation), ("test", test)):
            y = split["future_max_excursion_bps"].ge(threshold).to_numpy()
            model_results[name][split_name] = scores(y, fitted.predict_proba(split[features])[:, 1])
    base_test, augmented_test = model_results["baseline"]["test"], model_results["augmented"]["test"]
    incremental = {
        "average_precision": augmented_test["average_precision"] - base_test["average_precision"],
        "roc_auc": augmented_test["roc_auc"] - base_test["roc_auc"],
        "brier_improvement": base_test["brier"] - augmented_test["brier"],
    }
    targeted = blocked_test(train, test, FEATURE)
    model_gate = incremental["average_precision"] > 0.02 and incremental["brier_improvement"] > 0
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "clean_independent_date_replication_but_not_pristine_dataset_blindness",
        "hypothesis": 30,
        "paid_requests_made": False,
        "rows": {"panel": len(frame), "train": len(train), "validation": len(validation), "test": len(test)},
        "jump_threshold_bps": threshold,
        "models": model_results,
        "test_incremental": incremental,
        "incremental_model_gate_passed": model_gate,
        "targeted_test": targeted,
        "h30_clean_date_replicated": targeted["replicated"],
        "verdict": "H30_CLEAN_DATE_SURVIVOR_REQUIRES_PRISTINE_DAY" if targeted["replicated"] else "H30_REJECTED",
    }
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
