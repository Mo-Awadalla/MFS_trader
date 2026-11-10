"""Preregistered free-data screen of a joint time-and-touch-depth cascade."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from research.model_breakdown import block_bootstrap_mean
from research_scout.test_h1_local_global_divergence_v9 import (
    BASELINE,
    SYMBOLS,
    TRAIN_DATES,
    VALIDATION_DATES,
    classifier,
    extract_and_cache,
    model_scores,
)
from research_scout.test_h1_local_global_divergence_v9 import (
    OUTPUT as PRESSURE_OUTPUT,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout" / "navier_stokes_liquidity_v2"
OUTPUT = BASE / "joint_cascade_results"
TEST_DATES = [
    "2024-01-21",
    "2024-01-28",
    "2024-03-03",
    "2024-03-10",
    "2024-03-17",
    "2024-03-24",
]
ALL_DATES = TRAIN_DATES + VALIDATION_DATES + TEST_DATES
MAIN_EFFECTS = BASELINE + ["z_temporal_cascade", "z_touch_depth_contraction"]
INTERACTION = MAIN_EFFECTS + ["joint_cascade"]
OUTCOMES = [
    "future_max_excursion_bps",
    "future_max_spread_widening_bps",
    "future_max_touch_depth_depletion",
]


def add_future_outcomes(day: pd.DataFrame) -> pd.DataFrame:
    result = day.sort_index().copy()
    depth = result["depth_mean_60s"].to_numpy(float)
    spread = result["spread_mean"].to_numpy(float)
    midpoint = result["midpoint"].to_numpy(float)
    spread_widening = np.full(len(result), np.nan)
    depth_depletion = np.full(len(result), np.nan)
    signed_return = np.full(len(result), np.nan)
    for index in range(len(result) - 6):
        spread_widening[index] = np.max(spread[index + 1 : index + 7]) - spread[index]
        depth_depletion[index] = 1.0 - np.min(depth[index + 1 : index + 7]) / max(
            depth[index], 1e-12
        )
        signed_return[index] = np.log(midpoint[index + 6] / midpoint[index]) * 10_000.0
    result["future_max_spread_widening_bps"] = spread_widening
    result["future_max_touch_depth_depletion"] = depth_depletion
    result["future_signed_return_bps"] = signed_return
    result["touch_depth_contraction"] = -np.log(
        result["depth_mean_60s"] / result["depth_mean_60s"].shift(6)
    )
    result["temporal_cascade"] = result["pressure_linf_l2_60s"]
    return result.replace([np.inf, -np.inf], np.nan)


def robust_z(values: pd.Series, median: float, iqr: float) -> pd.Series:
    return (values - median) / max(iqr, 1e-12)


def evaluate_outcome(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    outcome: str,
) -> dict[str, object]:
    thresholds = {}
    combined: dict[str, dict[str, list[np.ndarray]]] = {
        split: {name: [] for name in ("target", "baseline", "main_effects", "interaction")}
        for split in ("validation", "test")
    }
    for symbol in SYMBOLS:
        symbol_train = train.loc[train["symbol"].eq(symbol)]
        symbol_splits = {
            "validation": validation.loc[validation["symbol"].eq(symbol)],
            "test": test.loc[test["symbol"].eq(symbol)],
        }
        threshold = float(symbol_train[outcome].quantile(0.95))
        thresholds[symbol] = threshold
        for name, features in (
            ("baseline", BASELINE),
            ("main_effects", MAIN_EFFECTS),
            ("interaction", INTERACTION),
        ):
            fitted = classifier().fit(
                symbol_train[features], symbol_train[outcome].ge(threshold)
            )
            for split_name, split in symbol_splits.items():
                combined[split_name][name].append(fitted.predict_proba(split[features])[:, 1])
        for split_name, split in symbol_splits.items():
            combined[split_name]["target"].append(split[outcome].ge(threshold).to_numpy())
    metrics = {}
    for split_name in ("validation", "test"):
        target = np.concatenate(combined[split_name]["target"])
        metrics[split_name] = {
            name: model_scores(target, np.concatenate(combined[split_name][name]))
            for name in ("baseline", "main_effects", "interaction")
        }
    return {"thresholds": thresholds, "metrics": metrics}


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    daily_dir = PRESSURE_OUTPUT / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    tasks = [
        (symbol, date, str(daily_dir / f"{symbol}_{date}.parquet"))
        for symbol in SYMBOLS
        for date in ALL_DATES
    ]
    with ProcessPoolExecutor(max_workers=3) as executor:
        cache_paths = list(executor.map(extract_and_cache, tasks))
    panels = [add_future_outcomes(pd.read_parquet(cache)) for cache in cache_paths]
    frame = pd.concat(panels).sort_index()
    train = frame.loc[frame["date"].isin(TRAIN_DATES)].copy()
    validation = frame.loc[frame["date"].isin(VALIDATION_DATES)].copy()
    test = frame.loc[frame["date"].isin(TEST_DATES)].copy()

    normalization = {}
    for symbol in SYMBOLS:
        symbol_train = train.loc[train["symbol"].eq(symbol)]
        temporal_median = float(symbol_train["temporal_cascade"].median())
        temporal_iqr = float(
            symbol_train["temporal_cascade"].quantile(0.75)
            - symbol_train["temporal_cascade"].quantile(0.25)
        )
        spatial_median = float(symbol_train["touch_depth_contraction"].median())
        spatial_iqr = float(
            symbol_train["touch_depth_contraction"].quantile(0.75)
            - symbol_train["touch_depth_contraction"].quantile(0.25)
        )
        normalization[symbol] = {
            "temporal_median": temporal_median,
            "temporal_iqr": temporal_iqr,
            "spatial_median": spatial_median,
            "spatial_iqr": spatial_iqr,
        }
        for split in (train, validation, test):
            mask = split["symbol"].eq(symbol)
            split.loc[mask, "z_temporal_cascade"] = robust_z(
                split.loc[mask, "temporal_cascade"], temporal_median, temporal_iqr
            )
            split.loc[mask, "z_touch_depth_contraction"] = robust_z(
                split.loc[mask, "touch_depth_contraction"], spatial_median, spatial_iqr
            )
    for split in (train, validation, test):
        split["joint_cascade"] = split["z_temporal_cascade"].clip(lower=0) * split[
            "z_touch_depth_contraction"
        ].clip(lower=0)
        split["signed_joint_cascade"] = np.sign(
            split["signed_trade_imbalance_60s"]
        ) * split["joint_cascade"]
    required = list(dict.fromkeys([*INTERACTION, *OUTCOMES, "future_signed_return_bps"]))
    train = train.dropna(subset=required)
    validation = validation.dropna(subset=required)
    test = test.dropna(subset=required)

    outcome_results = {
        outcome: evaluate_outcome(train, validation, test, outcome) for outcome in OUTCOMES
    }
    low, high = validation["joint_cascade"].quantile([0.2, 0.8])
    by_date = {}
    date_deltas = []
    for date, day in test.groupby("date"):
        low_values = day.loc[
            day["joint_cascade"].le(low), "future_max_excursion_bps"
        ]
        high_values = day.loc[
            day["joint_cascade"].ge(high), "future_max_excursion_bps"
        ]
        delta = float(high_values.mean() - low_values.mean())
        date_deltas.append(delta)
        by_date[date] = {
            "high_minus_low_excursion_bps": delta,
            "low_bins": len(low_values),
            "high_bins": len(high_values),
        }
    effect = block_bootstrap_mean(date_deltas, 20260913)
    effect["by_date"] = by_date
    signed_rho, signed_naive_p = spearmanr(
        test["signed_joint_cascade"], test["future_signed_return_bps"]
    )
    high_signed = test.loc[test["joint_cascade"].ge(high)]
    signed_hit_rate = float(
        (
            np.sign(high_signed["signed_joint_cascade"])
            == np.sign(high_signed["future_signed_return_bps"])
        ).mean()
    )

    primary_metrics = outcome_results["future_max_excursion_bps"]["metrics"]["test"]
    main_metrics = primary_metrics["main_effects"]
    interaction_metrics = primary_metrics["interaction"]
    ap_improvement = interaction_metrics["average_precision"] - main_metrics[
        "average_precision"
    ]
    brier_improvement = main_metrics["brier"] - interaction_metrics["brier"]
    interval = effect["block_bootstrap_95pct_ci"]
    primary = bool(
        ap_improvement > 0.02
        and brier_improvement > 0
        and interval[0] is not None
        and interval[0] > 0
        and len(date_deltas) == 6
        and all(delta > 0 for delta in date_deltas)
    )
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "partial_free_scientific_screen_not_live_trading_approval",
        "hypotheses": [23, 28, 30],
        "paid_requests_made": False,
        "symbols": SYMBOLS,
        "dates": {
            "training": TRAIN_DATES,
            "validation": VALIDATION_DATES,
            "holdout": TEST_DATES,
        },
        "rows": {"training": len(train), "validation": len(validation), "holdout": len(test)},
        "timestamp_rows_rejected": {
            f"{symbol}_{date}": int(
                frame.loc[
                    frame["symbol"].eq(symbol) & frame["date"].eq(date),
                    "rejected_timestamp_rows",
                ].max()
            )
            for symbol in SYMBOLS
            for date in ALL_DATES
        },
        "normalization": normalization,
        "outcome_models": outcome_results,
        "primary_interaction_over_main_effect_increment": {
            "average_precision": ap_improvement,
            "brier_improvement": brier_improvement,
            "roc_auc": interaction_metrics["roc_auc"] - main_metrics["roc_auc"],
        },
        "validation_joint_cutoffs": {"low_20pct": float(low), "high_80pct": float(high)},
        "holdout_joint_cascade_effect": effect,
        "signed_direction": {
            "spearman_rho": float(signed_rho),
            "naive_p_not_dependence_adjusted": float(signed_naive_p),
            "high_joint_state_hit_rate": signed_hit_rate,
            "high_joint_rows": len(high_signed),
        },
        "primary_gate_passed": primary,
        "verdict": "JOINT_CASCADE_REPLICATED" if primary else "JOINT_CASCADE_FAILED",
        "economic_gate_tested": False,
        "claim_limit": "BBO touch-depth proxy only; no price-level curvature, cancellations, queue, latency, failed fills, fees, or live execution claim",
    }
    (OUTPUT / "results.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
