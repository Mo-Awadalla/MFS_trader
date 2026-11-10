"""Run the preregistered MBP-1 liquidity-concentration feasibility pilot."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import databento as db
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from research.navier_stokes_liquidity import (
    BASELINE_FEATURES,
    CONCENTRATION_FEATURES,
    concentration_features,
    future_jump_outcomes,
    second_snapshots,
)

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "external_artifacts" / "databento_cash_etf_mbp1_open_v55"
FILES_ROOT = DATA_ROOT / "EQUS.MINI" / "mbp-1"
OUTPUT_ROOT = ROOT / "research_scout" / "navier_stokes_liquidity_v1"
NY = ZoneInfo("America/New_York")
UTC_ZONE = ZoneInfo("UTC")
SIGNAL_START = time(9, 25)
SIGNAL_END = time(9, 30)
OUTCOME_END = time(9, 35)
SYMBOLS = ["SPY", "SSO", "UPRO", "SH", "SDS", "SPXU"]


def _stamp(day: date, clock: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, clock, tzinfo=NY).astimezone(UTC_ZONE))


def extract_file(path_text: str) -> list[dict[str, object]]:
    path = Path(path_text)
    day = date.fromisoformat(path.name.removesuffix(".dbn.zst"))
    frame = db.read_dbn(path).to_df(map_symbols=True, tz="UTC").reset_index()
    frame["ts_recv"] = pd.to_datetime(frame["ts_recv"], utc=True)
    signal_start = _stamp(day, SIGNAL_START)
    signal_end = _stamp(day, SIGNAL_END)
    outcome_end = _stamp(day, OUTCOME_END)
    rows: list[dict[str, object]] = []
    for symbol in SYMBOLS:
        symbol_frame = frame.loc[frame["symbol"].astype(str) == symbol]
        if symbol_frame.empty:
            continue
        try:
            signal = second_snapshots(symbol_frame, start=signal_start, end=signal_end)
            outcome = second_snapshots(symbol_frame, start=signal_end, end=outcome_end)
            trades = symbol_frame.loc[
                (symbol_frame["action"].astype(str) == "T")
                & (symbol_frame["ts_recv"] >= signal_start)
                & (symbol_frame["ts_recv"] < signal_end),
                ["ts_recv", "side", "size"],
            ]
            event_count = int(
                ((symbol_frame["ts_recv"] >= signal_start) & (symbol_frame["ts_recv"] < signal_end)).sum()
            )
            features = concentration_features(
                signal,
                trades,
                event_count=event_count,
                duration_seconds=300,
            )
            outcomes = future_jump_outcomes(outcome)
        except (ValueError, KeyError, TypeError):
            continue
        rows.append({"session_date": day.isoformat(), "symbol": symbol, **features, **outcomes})
    return rows


def _model(feature_names: list[str]) -> Pipeline:
    numeric = Pipeline(
        [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
    )
    transform = ColumnTransformer(
        [("numeric", numeric, feature_names), ("symbol", OneHotEncoder(handle_unknown="ignore"), ["symbol"])],
        remainder="drop",
    )
    return Pipeline(
        [("transform", transform), ("model", LogisticRegression(C=0.25, max_iter=2_000, class_weight="balanced"))]
    )


def _score(y: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    return {
        "average_precision": float(average_precision_score(y, probability)),
        "roc_auc": float(roc_auc_score(y, probability)),
        "brier": float(brier_score_loss(y, probability)),
    }


def temporal_evaluation(panel: pd.DataFrame) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    panel = panel.copy()
    panel["year"] = pd.to_datetime(panel["session_date"]).dt.year
    for train_end, test_year in ((2024, 2025), (2025, 2026)):
        train = panel.loc[panel["year"] <= train_end].copy()
        test = panel.loc[panel["year"] == test_year].copy()
        if len(train) < 100 or len(test) < 30:
            continue
        threshold = float(train["future_max_excursion_bps"].quantile(0.90))
        y_train = (train["future_max_excursion_bps"] >= threshold).astype(int).to_numpy()
        y_test = (test["future_max_excursion_bps"] >= threshold).astype(int).to_numpy()
        if np.unique(y_train).size < 2 or np.unique(y_test).size < 2:
            continue
        fold: dict[str, object] = {
            "train_through": train_end,
            "test_year": test_year,
            "train_rows": len(train),
            "test_rows": len(test),
            "jump_threshold_bps_from_training_only": threshold,
            "test_event_rate": float(y_test.mean()),
            "models": {},
        }
        for name, features in (
            ("baseline", BASELINE_FEATURES),
            ("baseline_plus_concentration", BASELINE_FEATURES + CONCENTRATION_FEATURES),
        ):
            estimator = _model(features)
            estimator.fit(train[["symbol", *features]], y_train)
            probability = estimator.predict_proba(test[["symbol", *features]])[:, 1]
            fold["models"][name] = _score(y_test, probability)  # type: ignore[index]
        baseline = fold["models"]["baseline"]  # type: ignore[index]
        augmented = fold["models"]["baseline_plus_concentration"]  # type: ignore[index]
        fold["incremental"] = {
            "average_precision": augmented["average_precision"] - baseline["average_precision"],
            "roc_auc": augmented["roc_auc"] - baseline["roc_auc"],
            "brier_improvement": baseline["brier"] - augmented["brier"],
        }
        results.append(fold)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        raise ValueError("--workers must be between 1 and 8")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    panel_path = OUTPUT_ROOT / "feature_panel.parquet"
    files = sorted(FILES_ROOT.glob("*.dbn.zst"))
    if args.max_files is not None:
        files = files[: args.max_files]
    if not files:
        raise RuntimeError(f"No MBP-1 files found under {FILES_ROOT}")

    if panel_path.exists() and not args.rebuild and args.max_files is None:
        panel = pd.read_parquet(panel_path)
    else:
        rows: list[dict[str, object]] = []
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(extract_file, str(path)): path for path in files}
            for index, future in enumerate(as_completed(futures), start=1):
                rows.extend(future.result())
                if index % 50 == 0 or index == len(files):
                    print(f"decoded {index}/{len(files)} sessions", flush=True)
        panel = pd.DataFrame(rows).sort_values(["session_date", "symbol"]).reset_index(drop=True)
        target = panel_path if args.max_files is None else OUTPUT_ROOT / "pilot_feature_panel.parquet"
        panel.to_parquet(target, index=False)

    folds = temporal_evaluation(panel)
    ap_increments = [
        float(fold["incremental"]["average_precision"])  # type: ignore[index]
        for fold in folds
    ]
    test_weights = [int(fold["test_rows"]) for fold in folds]
    weighted_ap_increment = (
        float(np.average(ap_increments, weights=test_weights)) if ap_increments else None
    )
    primary_gate_passed = bool(
        len(folds) == 2
        and all(value > 0.0 for value in ap_increments)
        and weighted_ap_increment is not None
        and weighted_ap_increment >= 0.02
    )
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "feasibility_only_not_trading_approval",
        "source": str(FILES_ROOT.relative_to(ROOT)).replace("\\", "/"),
        "files_requested": len(files),
        "panel_rows": len(panel),
        "sessions": int(panel["session_date"].nunique()) if not panel.empty else 0,
        "symbols": sorted(panel["symbol"].unique().tolist()) if not panel.empty else [],
        "rows_by_symbol": {
            str(symbol): int(count)
            for symbol, count in panel["symbol"].value_counts().sort_index().items()
        }
        if not panel.empty
        else {},
        "signal_window_et": "09:25:00-09:29:59",
        "outcome_window_et": "09:30:00-09:34:59",
        "baseline_features": BASELINE_FEATURES,
        "concentration_proxy_features": CONCENTRATION_FEATURES,
        "important_scope_limit": "MBP-1 is top-of-book; price-space gradients and full-depth core width are not tested.",
        "temporal_folds": folds,
        "weighted_average_precision_increment": weighted_ap_increment,
        "primary_gate_passed": primary_gate_passed,
        "verdict": (
            "PASS_STAGE_1_REQUIRES_FULL_DEPTH_CONFIRMATION"
            if primary_gate_passed
            else "FAIL_STAGE_1_NO_INCREMENTAL_JUMP_RANKING_VALUE"
        ),
    }
    output = OUTPUT_ROOT / ("results.json" if args.max_files is None else "pilot_results.json")
    output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
