"""Cross-symbol ETHUSDT replication of lagged conventional-model error H47."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sklearn.metrics import mean_absolute_error

from research_scout.test_multiday_market_making_v7 import (
    ALL_DATES,
    CONVENTIONAL,
    TEST_DATES,
    TRAIN_DATES,
    VALIDATION_DATES,
    clustered_effect,
    extract_day,
    model,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout" / "navier_stokes_liquidity_v2"
OUTPUT = BASE / "h47_eth_replication_results"
CONTROL_FEATURES = CONVENTIONAL + ["event_rate", "lagged_abs_markout_60s"]
AUGMENTED_FEATURES = CONTROL_FEATURES + ["lagged_model_error_60s", "excess_model_error_60s"]
ERROR_EXPECTATION_FEATURES = [
    "lagged_abs_markout_60s",
    "realized_vol_60s",
    "spread_mean",
    "depth_mean",
    "imbalance_mean",
    "event_rate",
    "trade_volume",
    "signed_trade_imbalance",
]


def add_lagged_signals(frame: pd.DataFrame, prediction: pd.Series) -> pd.DataFrame:
    result = frame.copy()
    absolute_error = (result["mean_markout_10s"] - prediction).abs()
    result["lagged_model_error_60s"] = absolute_error.groupby(result["date"]).transform(
        lambda values: values.shift(1).rolling(6, min_periods=3).mean()
    )
    result["lagged_abs_markout_60s"] = result["mean_markout_10s"].abs().groupby(
        result["date"]
    ).transform(lambda values: values.shift(1).rolling(6, min_periods=3).mean())
    return result


def main() -> int:
    daily_dir = OUTPUT / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    panels = []
    for date in ALL_DATES:
        cache = daily_dir / f"ETHUSDT_{date}.parquet"
        if cache.exists():
            panel = pd.read_parquet(cache)
        else:
            panel = extract_day(date, symbol="ETHUSDT")
            panel.to_parquet(cache)
        panels.append(panel)
    frame = pd.concat(panels).sort_index().dropna(subset=["mean_markout_10s"])
    train = frame.loc[frame["date"].isin(TRAIN_DATES)].copy()
    validation = frame.loc[frame["date"].isin(VALIDATION_DATES)].copy()
    test = frame.loc[frame["date"].isin(TEST_DATES)].copy()

    crossfit_prediction = pd.Series(index=train.index, dtype=float)
    for held_date in TRAIN_DATES:
        fit_rows = train.loc[train["date"].ne(held_date)]
        held_rows = train.loc[train["date"].eq(held_date)]
        fitted = model().fit(fit_rows[CONVENTIONAL], fit_rows["mean_markout_10s"])
        crossfit_prediction.loc[held_rows.index] = fitted.predict(held_rows[CONVENTIONAL])
    conventional = model().fit(train[CONVENTIONAL], train["mean_markout_10s"])
    validation_prediction = pd.Series(
        conventional.predict(validation[CONVENTIONAL]), index=validation.index
    )
    test_prediction = pd.Series(conventional.predict(test[CONVENTIONAL]), index=test.index)

    train = add_lagged_signals(train, crossfit_prediction)
    validation = add_lagged_signals(validation, validation_prediction)
    test = add_lagged_signals(test, test_prediction)
    signal_train = train.dropna(subset=["lagged_model_error_60s", *ERROR_EXPECTATION_FEATURES])
    expectation = model().fit(
        signal_train[ERROR_EXPECTATION_FEATURES], signal_train["lagged_model_error_60s"]
    )
    for split in (train, validation, test):
        split["excess_model_error_60s"] = split["lagged_model_error_60s"] - expectation.predict(
            split[ERROR_EXPECTATION_FEATURES]
        )

    fit_train = train.dropna(subset=AUGMENTED_FEATURES)
    control_model = model().fit(fit_train[CONTROL_FEATURES], fit_train["mean_markout_10s"])
    augmented_model = model().fit(
        fit_train[AUGMENTED_FEATURES], fit_train["mean_markout_10s"]
    )
    metrics = {}
    predictions = {}
    for name, split in (("validation", validation), ("test", test)):
        eligible = split.dropna(subset=AUGMENTED_FEATURES)
        control_prediction = control_model.predict(eligible[CONTROL_FEATURES])
        augmented_prediction = augmented_model.predict(eligible[AUGMENTED_FEATURES])
        predictions[name] = (eligible, control_prediction, augmented_prediction)
        metrics[name] = {
            "control_mae": float(
                mean_absolute_error(eligible["mean_markout_10s"], control_prediction)
            ),
            "augmented_mae": float(
                mean_absolute_error(eligible["mean_markout_10s"], augmented_prediction)
            ),
        }

    validation_eligible = predictions["validation"][0]
    test_eligible = predictions["test"][0]
    excess_low, excess_high = validation_eligible["excess_model_error_60s"].quantile([0.2, 0.8])
    excess_scored = test_eligible.copy()
    excess_scored["critical_score"] = excess_scored["excess_model_error_60s"]
    excess_effect = clustered_effect(excess_scored, float(excess_low), float(excess_high))
    raw_low, raw_high = validation_eligible["lagged_model_error_60s"].quantile([0.2, 0.8])
    raw_scored = test_eligible.copy()
    raw_scored["critical_score"] = raw_scored["lagged_model_error_60s"]
    raw_effect = clustered_effect(raw_scored, float(raw_low), float(raw_high))
    control_mae = metrics["test"]["control_mae"]
    augmented_mae = metrics["test"]["augmented_mae"]
    improvement = (control_mae - augmented_mae) / control_mae
    date_deltas = [
        entry["high_minus_low_markout_bps"] for entry in excess_effect["by_date"].values()
    ]
    interval = excess_effect["block_bootstrap_95pct_ci"]
    primary = bool(
        interval[1] is not None
        and interval[1] < 0
        and all(delta < 0 for delta in date_deltas)
        and improvement >= 0.02
    )
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "cross_symbol_replication_of_h47_not_live_execution_approval",
        "hypothesis": 47,
        "symbol": "ETHUSDT",
        "paid_requests_made": False,
        "dates": {
            "training": TRAIN_DATES,
            "validation": VALIDATION_DATES,
            "holdout": TEST_DATES,
        },
        "rows": {
            "all_fill_bins": len(frame),
            "training": len(train),
            "validation": len(validation),
            "holdout": len(test),
        },
        "timestamp_rows_rejected_by_date": {
            date: int(frame.loc[frame["date"].eq(date), "rejected_timestamp_rows"].max())
            for date in ALL_DATES
        },
        "metrics": metrics,
        "holdout_mae_improvement_from_error_signals": improvement,
        "validation_excess_error_cutoffs": {
            "low_20pct": float(excess_low),
            "high_80pct": float(excess_high),
        },
        "controlled_excess_error_holdout_effect": excess_effect,
        "uncontrolled_raw_error_holdout_effect": raw_effect,
        "primary_gate_passed": primary,
        "verdict": "H47_CROSS_SYMBOL_REPLICATED" if primary else "H47_CROSS_SYMBOL_FAILED",
        "claim_limit": "touch-qualified hypothetical fills only; no queue, fees, rebates, latency or actual fill probability",
    }
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
