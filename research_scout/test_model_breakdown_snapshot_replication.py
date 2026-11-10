"""Cross-representation replication of the operational model-breakdown test."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from research.model_breakdown import regression_metrics
from research_scout.test_model_breakdown_v6 import (
    disagreement_blocks,
    lagged_residual_test,
    nonlinear_model,
    predict_level,
    ridge_model,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout" / "navier_stokes_liquidity_v2"
IMPACT_PANEL = BASE / "impact_regime_results" / "feature_panel.parquet"
MULTISCALE_PANEL = BASE / "multiscale_batch_results" / "feature_panel.parquet"
OUTPUT = BASE / "model_breakdown_snapshot_replication_results"
CONVENTIONAL = [
    "spread_mean",
    "depth_mean",
    "imbalance_mean",
    "realized_vol_60s",
    "trade_volume",
    "signed_trade_imbalance",
    "sqrt_normalized_signed_flow",
]
BREAKDOWN = [
    "total_depth",
    "near_qty_1bps_min",
    "near_qty_2bps_min",
    "near_qty_5bps_min",
    "near_qty_10bps_min",
    "sweep_cost_1btc_bps",
    "sweep_cost_3btc_bps",
    "sweep_cost_5btc_bps",
    "sweep_convexity_bps_per_btc",
    "event_rate",
    "l4_l2",
    "l8_l2",
    "l16_l2",
    "linf_l2",
    "gradient_max",
    "critical_score",
    "profile_collapse_score",
    "microburst_acceleration",
    "fine_to_coarse_vol",
    "haar_high_low_ratio",
    "multifractal_width",
    "cross_scale_coupling",
    "rolling_impact_exponent",
    "rolling_impact_convexity",
    "impact_exponent_change_60s",
    "known_permanence_5m",
]


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(IMPACT_PANEL)
    multiscale = pd.read_parquet(MULTISCALE_PANEL)[
        [column for column in BREAKDOWN if column not in frame.columns]
    ]
    frame = frame.join(multiscale, how="left")
    frame["spread_mean"] = frame["spread_bps"]
    frame["depth_mean"] = frame["near_qty_1bps_total"]
    frame["imbalance_mean"] = frame["imbalance"]
    scale = frame["trade_volume"].rolling(30, min_periods=10).median().clip(lower=1e-6)
    frame["sqrt_normalized_signed_flow"] = np.sqrt(frame["signed_trade_volume"].abs() / scale)
    frame = frame.replace([np.inf, -np.inf], np.nan)
    usable = frame.dropna(subset=["future_max_excursion_bps"])
    first, second = int(len(usable) * 0.6), int(len(usable) * 0.8)
    train, validation, test = usable.iloc[:first], usable.iloc[first:second], usable.iloc[second:]
    y_train = np.log1p(train["future_max_excursion_bps"].to_numpy(float))
    parametric = ridge_model().fit(train[CONVENTIONAL], y_train)
    regular = nonlinear_model().fit(train[CONVENTIONAL], y_train)
    breakdown = nonlinear_model().fit(train[CONVENTIONAL + BREAKDOWN], y_train)
    predictions = {}
    for split_name, split in (("validation", validation), ("test", test)):
        predictions[split_name] = {
            "parametric": predict_level(parametric, split, CONVENTIONAL),
            "nonlinear_regular": predict_level(regular, split, CONVENTIONAL),
            "breakdown": predict_level(breakdown, split, CONVENTIONAL + BREAKDOWN),
        }
    metrics = {}
    for split_name, split in (("validation", validation), ("test", test)):
        actual = split["future_max_excursion_bps"].to_numpy(float)
        metrics[split_name] = {
            name: regression_metrics(actual, prediction)
            for name, prediction in predictions[split_name].items()
        }
    validation_disagreement = np.abs(predictions["validation"]["breakdown"] - predictions["validation"]["nonlinear_regular"])
    test_disagreement = np.abs(predictions["test"]["breakdown"] - predictions["test"]["nonlinear_regular"])
    blocks = disagreement_blocks(
        validation,
        test,
        validation_disagreement,
        test_disagreement,
        predictions["test"]["nonlinear_regular"],
        predictions["test"]["breakdown"],
    )
    h47 = lagged_residual_test(
        validation,
        test,
        predictions["validation"]["nonlinear_regular"],
        predictions["test"]["nonlinear_regular"],
    )
    validation_underprediction = validation["future_max_excursion_bps"].to_numpy(float) - predictions["validation"]["nonlinear_regular"]
    catastrophe_threshold = float(np.quantile(validation_underprediction, 0.95))
    catastrophe = test["future_max_excursion_bps"].to_numpy(float) - predictions["test"]["nonlinear_regular"] >= catastrophe_threshold
    disagreement_ap = float(average_precision_score(catastrophe, test_disagreement))
    regular_mae = metrics["test"]["nonlinear_regular"]["mae"]
    breakdown_mae = metrics["test"]["breakdown"]["mae"]
    mae_improvement = (regular_mae - breakdown_mae) / regular_mae
    error_ci = blocks["h46_h50_conventional_error_high_minus_low"]["block_bootstrap_95pct_ci"]
    advantage_ci = blocks["h48_breakdown_advantage_high_minus_low"]["block_bootstrap_95pct_ci"]
    primary = bool(mae_improvement >= 0.05 and error_ci[0] is not None and error_ci[0] > 0 and advantage_ci[0] is not None and advantage_ci[0] > 0)
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "cross_representation_replication_on_seen_clean_day",
        "hypotheses_tested": [46, 47, 48, 50],
        "paid_requests_made": False,
        "rows": {"train": len(train), "validation": len(validation), "test": len(test)},
        "metrics": metrics,
        "breakdown_relative_mae_improvement_vs_nonlinear_regular": mae_improvement,
        "disagreement_tests": blocks,
        "h47_lagged_residual_test": h47,
        "validation_95pct_catastrophic_underprediction_bps": catastrophe_threshold,
        "disagreement_average_precision_for_test_catastrophic_underprediction": disagreement_ap,
        "primary_gate_passed": primary,
        "verdict": "MODEL_BREAKDOWN_REPLICATED_REQUIRES_PRISTINE_DATA" if primary else "MODEL_BREAKDOWN_FAILED_CROSS_REPRESENTATION",
    }
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
