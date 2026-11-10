"""Test whether conventional-feature forecasts fail in model-disagreement states."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from research.model_breakdown import block_bootstrap_mean, regression_metrics
from research_scout.test_h30_binance_clean_replication import cross_scale_feature

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout" / "navier_stokes_liquidity_v2"
PANEL = BASE / "h36_binance_clean_replication_results" / "feature_panel.parquet"
OUTPUT = BASE / "model_breakdown_results"
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
    "spread_last",
    "depth_min",
    "imbalance_last",
    "event_rate",
    "return_linf_l2",
    "event_linf_l2",
    "spectral_cascade_ratio",
    "inverse_interevent",
    "gross_to_net_trade",
    "opposing_trade_stress",
    "price_sensitivity",
    "depth_change",
    "rolling_impact_exponent",
    "rolling_impact_convexity",
    "impact_exponent_change_60s",
    "known_permanence_5m",
    "cross_scale_coupling",
]


def ridge_model() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", RobustScaler(quantile_range=(10, 90))),
            ("model", Ridge(alpha=10.0)),
        ]
    )


def nonlinear_model() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            (
                "model",
                HistGradientBoostingRegressor(
                    learning_rate=0.05,
                    max_iter=150,
                    max_depth=3,
                    l2_regularization=1.0,
                    random_state=20260913,
                ),
            ),
        ]
    )


def predict_level(model: Pipeline, frame: pd.DataFrame, columns: list[str]) -> np.ndarray:
    return np.maximum(np.expm1(model.predict(frame[columns])), 0.0)


def disagreement_blocks(
    validation: pd.DataFrame,
    test: pd.DataFrame,
    validation_disagreement: np.ndarray,
    test_disagreement: np.ndarray,
    regular_prediction: np.ndarray,
    breakdown_prediction: np.ndarray,
) -> dict[str, object]:
    low, high = float(np.quantile(validation_disagreement, 0.2)), float(np.quantile(validation_disagreement, 0.8))
    work = pd.DataFrame(
        {
            "actual": test["future_max_excursion_bps"].to_numpy(float),
            "disagreement": test_disagreement,
            "regular_error": np.abs(test["future_max_excursion_bps"].to_numpy(float) - regular_prediction),
            "breakdown_error": np.abs(test["future_max_excursion_bps"].to_numpy(float) - breakdown_prediction),
            "block": np.arange(len(test)) // 60,
        },
        index=test.index,
    )
    error_deltas = []
    advantage_deltas = []
    for _, block in work.groupby("block"):
        lows = block.loc[block["disagreement"].le(low)]
        highs = block.loc[block["disagreement"].ge(high)]
        if len(lows) >= 2 and len(highs) >= 2:
            error_deltas.append(float(highs["regular_error"].mean() - lows["regular_error"].mean()))
            low_advantage = (lows["regular_error"] - lows["breakdown_error"]).mean()
            high_advantage = (highs["regular_error"] - highs["breakdown_error"]).mean()
            advantage_deltas.append(float(high_advantage - low_advantage))
    error_result = block_bootstrap_mean(error_deltas, 20260913)
    advantage_result = block_bootstrap_mean(advantage_deltas, 20260914)
    rho, naive_p = spearmanr(work["disagreement"], work["regular_error"])
    error_result["spearman_disagreement_vs_regular_error"] = float(rho)
    error_result["naive_p_not_independence_adjusted"] = float(naive_p)
    return {
        "validation_low_cutoff": low,
        "validation_high_cutoff": high,
        "h46_h50_conventional_error_high_minus_low": error_result,
        "h48_breakdown_advantage_high_minus_low": advantage_result,
    }


def lagged_residual_test(
    validation: pd.DataFrame,
    test: pd.DataFrame,
    validation_prediction: np.ndarray,
    test_prediction: np.ndarray,
) -> dict[str, object]:
    combined = pd.concat([validation, test])
    predictions = np.r_[validation_prediction, test_prediction]
    residual = pd.Series(
        np.abs(combined["future_max_excursion_bps"].to_numpy(float) - predictions),
        index=combined.index,
    )
    past_observable = residual.shift(6).rolling(6, min_periods=3).mean()
    validation_signal = past_observable.iloc[: len(validation)].dropna()
    test_signal = past_observable.iloc[len(validation) :]
    low, high = float(validation_signal.quantile(0.2)), float(validation_signal.quantile(0.8))
    work = test[["future_max_excursion_bps"]].copy()
    work["past_residual"] = test_signal
    work["block"] = np.arange(len(work)) // 60
    deltas = []
    for _, block in work.groupby("block"):
        lows = block.loc[block["past_residual"].le(low), "future_max_excursion_bps"].dropna()
        highs = block.loc[block["past_residual"].ge(high), "future_max_excursion_bps"].dropna()
        if len(lows) >= 2 and len(highs) >= 2:
            deltas.append(float(highs.mean() - lows.mean()))
    result = block_bootstrap_mean(deltas, 20260915)
    paired = work.dropna()
    rho, naive_p = spearmanr(paired["past_residual"], paired["future_max_excursion_bps"])
    result.update(
        {
            "validation_low_cutoff": low,
            "validation_high_cutoff": high,
            "spearman_rho_test": float(rho),
            "naive_p_not_independence_adjusted": float(naive_p),
            "supported": bool(rho > 0 and result["block_bootstrap_95pct_ci"][0] is not None and result["block_bootstrap_95pct_ci"][0] > 0),
        }
    )
    return result


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frame = pd.read_parquet(PANEL).iloc[:8_640].copy()
    volume_scale = frame["trade_volume"].rolling(30, min_periods=10).median().clip(lower=1e-6)
    frame["sqrt_normalized_signed_flow"] = np.sqrt(frame["signed_trade_volume"].abs() / volume_scale)
    frame = frame.join(cross_scale_feature(frame.index), how="left").replace([np.inf, -np.inf], np.nan)
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
    test_catastrophe = test["future_max_excursion_bps"].to_numpy(float) - predictions["test"]["nonlinear_regular"] >= catastrophe_threshold
    disagreement_ap = float(average_precision_score(test_catastrophe, test_disagreement))
    regular_mae = metrics["test"]["nonlinear_regular"]["mae"]
    breakdown_mae = metrics["test"]["breakdown"]["mae"]
    mae_improvement = (regular_mae - breakdown_mae) / regular_mae
    error_ci = blocks["h46_h50_conventional_error_high_minus_low"]["block_bootstrap_95pct_ci"]
    advantage_ci = blocks["h48_breakdown_advantage_high_minus_low"]["block_bootstrap_95pct_ci"]
    primary = bool(mae_improvement >= 0.05 and error_ci[0] is not None and error_ci[0] > 0 and advantage_ci[0] is not None and advantage_ci[0] > 0)
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "exploratory_test_of_operational_model_error_not_evidence_of_market_beliefs",
        "hypotheses_tested": [46, 47, 48, 50],
        "hypothesis_49": "not_testable_with_free_aggregate_data",
        "paid_requests_made": False,
        "rows": {"train": len(train), "validation": len(validation), "test": len(test)},
        "metrics": metrics,
        "breakdown_relative_mae_improvement_vs_nonlinear_regular": mae_improvement,
        "disagreement_tests": blocks,
        "h47_lagged_residual_test": h47,
        "validation_95pct_catastrophic_underprediction_bps": catastrophe_threshold,
        "disagreement_average_precision_for_test_catastrophic_underprediction": disagreement_ap,
        "primary_gate_passed": primary,
        "verdict": "MODEL_BREAKDOWN_CANDIDATE_REQUIRES_NEW_DATA" if primary else "OPERATIONAL_WRONG_ASSUMPTION_TEST_FAILED",
    }
    frame.to_parquet(OUTPUT / "feature_panel.parquet")
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
