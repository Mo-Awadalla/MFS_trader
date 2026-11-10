"""Exploratory full-depth test of the Navier-Stokes liquidity hypotheses."""

from __future__ import annotations

import argparse
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from research.navier_stokes_l2 import L2Book

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "research_scout" / "navier_stokes_liquidity_v2" / "free_data" / "tardis" / "binance-futures"
DEPTH_PATH = DATA_ROOT / "incremental_book_L2" / "2020-02-01" / "BTCUSDT.csv.gz"
TRADES_PATH = DATA_ROOT / "trades" / "2020-02-01" / "BTCUSDT.csv.gz"
OUTPUT_ROOT = ROOT / "research_scout" / "navier_stokes_liquidity_v2" / "crypto_l2_results"

BASELINE = [
    "spread_bps",
    "top_depth",
    "book_imbalance",
    "realized_vol_60s",
    "trade_volume",
    "signed_trade_imbalance",
    "event_rate",
]

CONCENTRATION = [
    "liquidity_linf_l2",
    "u_linf_l2",
    "u_l4_l2",
    "core_width_bps",
    "core_width_change",
    "gradient_max",
    "gradient_energy",
    "curvature_energy",
    "gross_to_net_flow",
    "opposing_flow_stress",
    "transport_to_replenishment",
    "spectral_cascade_ratio",
    "inverse_interevent_rate",
    "price_sensitivity",
    "stress_flow_interaction",
]

ORIENTED_SIGNALS = {
    "h2_velocity_norm_concentration": "u_linf_l2",
    "h4_core_contraction": "negative_core_width",
    "h11_h13_gradient_energy": "gradient_energy",
    "h14_curvature_energy": "curvature_energy",
    "h17_h18_quadratic_opposing_flow": "opposing_flow_stress",
    "h18_gross_hidden_by_net": "gross_to_net_flow",
    "h23_spectral_migration": "spectral_cascade_ratio",
    "h24_event_acceleration": "inverse_interevent_rate",
    "h45_transport_over_replenishment": "transport_to_replenishment",
    "h51_price_displacement_per_volume": "price_sensitivity",
    "h53_core_trajectory": "negative_core_width_change",
}


def finite_or_none(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def extract_book(path: Path, *, bin_seconds: int, levels: int, max_rows: int | None = None) -> pd.DataFrame:
    book = L2Book()
    rows: list[dict[str, float | int]] = []
    interval_us = bin_seconds * 1_000_000
    bin_start_us: int | None = None
    seen = 0

    def emit(start_us: int) -> None:
        try:
            feature = book.features(levels=levels, bin_seconds=bin_seconds)
        except ValueError:
            book.reset_window()
            return
        rows.append({"bin_start_us": start_us, **feature})
        book.reset_window()

    with gzip.open(path, "rb") as stream:
        header = stream.readline().rstrip(b"\r\n").split(b",")
        expected = [b"exchange", b"symbol", b"timestamp", b"local_timestamp", b"is_snapshot", b"side", b"price", b"amount"]
        if header != expected:
            raise ValueError(f"unexpected depth schema: {header!r}")
        for raw in stream:
            parts = raw.rstrip(b"\r\n").split(b",")
            if len(parts) != 8:
                continue
            timestamp_us = int(parts[2])
            if bin_start_us is None:
                bin_start_us = timestamp_us - timestamp_us % interval_us
            while timestamp_us >= bin_start_us + interval_us:
                emit(bin_start_us)
                bin_start_us += interval_us
            book.apply(
                side=parts[5].decode("ascii"),
                price=float(parts[6]),
                amount=float(parts[7]),
                is_snapshot=parts[4] == b"true",
                timestamp_us=timestamp_us,
                bin_start_us=bin_start_us,
                bin_seconds=bin_seconds,
            )
            seen += 1
            if seen % 5_000_000 == 0:
                print(f"processed {seen:,} depth rows", flush=True)
            if max_rows is not None and seen >= max_rows:
                break
    if bin_start_us is not None:
        emit(bin_start_us)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("no valid book intervals extracted")
    frame["time"] = pd.to_datetime(frame["bin_start_us"], unit="us", utc=True)
    return frame.sort_values("time").drop_duplicates("time", keep="last").set_index("time")


def load_trades(path: Path, *, bin_seconds: int, origin_us: int) -> pd.DataFrame:
    trades = pd.read_csv(path, compression="gzip")
    trades["timestamp"] = pd.to_numeric(trades["timestamp"], errors="coerce")
    trades["amount"] = pd.to_numeric(trades["amount"], errors="coerce").fillna(0.0)
    interval_us = bin_seconds * 1_000_000
    trades["bin_start_us"] = origin_us + ((trades["timestamp"] - origin_us) // interval_us) * interval_us
    trades["buy"] = np.where(trades["side"].eq("buy"), trades["amount"], 0.0)
    trades["sell"] = np.where(trades["side"].eq("sell"), trades["amount"], 0.0)
    grouped = trades.groupby("bin_start_us", sort=True).agg(
        buy_volume=("buy", "sum"),
        sell_volume=("sell", "sum"),
        trade_count=("amount", "size"),
        median_trade_size=("amount", "median"),
    )
    grouped.index = pd.to_datetime(grouped.index, unit="us", utc=True)
    return grouped


def add_derived_features(book: pd.DataFrame, trades: pd.DataFrame, *, horizon: int) -> pd.DataFrame:
    frame = book.join(trades, how="left")
    for column in ["buy_volume", "sell_volume", "trade_count", "median_trade_size"]:
        frame[column] = frame[column].fillna(0.0)
    frame["trade_volume"] = frame["buy_volume"] + frame["sell_volume"]
    frame["signed_trade_imbalance"] = (
        (frame["buy_volume"] - frame["sell_volume"]) / frame["trade_volume"].replace(0.0, np.nan)
    ).fillna(0.0)
    log_mid = np.log(frame["midpoint"])
    frame["mid_return_bps"] = 10_000.0 * log_mid.diff()
    frame["realized_vol_60s"] = frame["mid_return_bps"].rolling(horizon, min_periods=2).std()
    frame["core_width_change"] = frame["core_width_bps"].diff()
    frame["negative_core_width"] = -frame["core_width_bps"]
    frame["negative_core_width_change"] = -frame["core_width_change"]
    frame["inverse_interevent_rate"] = 1.0 / frame["mean_interevent_ms"].clip(lower=1e-6)
    frame["price_sensitivity"] = frame["mid_return_bps"].abs() / frame["trade_volume"].replace(0.0, np.nan)
    frame["stress_flow_interaction"] = frame["gradient_energy"] * frame["signed_trade_imbalance"].abs()

    midpoint = frame["midpoint"].to_numpy(float)
    future_excursion = np.full(len(frame), np.nan)
    future_return = np.full(len(frame), np.nan)
    for index in range(len(frame) - horizon):
        path = 10_000.0 * np.log(midpoint[index + 1 : index + horizon + 1] / midpoint[index])
        future_excursion[index] = float(np.max(np.abs(path)))
        future_return[index] = float(path[-1])
    frame["future_max_excursion_bps"] = future_excursion
    frame["future_return_bps"] = future_return
    return frame.replace([np.inf, -np.inf], np.nan)


def model() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", RobustScaler(quantile_range=(10.0, 90.0))),
        ("model", LogisticRegression(C=0.25, class_weight="balanced", max_iter=2_000)),
    ])


def scores(labels: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    return {
        "average_precision": float(average_precision_score(labels, probability)),
        "roc_auc": float(roc_auc_score(labels, probability)),
        "brier": float(brier_score_loss(labels, probability)),
    }


def evaluate_models(frame: pd.DataFrame) -> dict[str, object]:
    usable = frame.dropna(subset=["future_max_excursion_bps"]).copy()
    train_end = int(len(usable) * 0.60)
    validation_end = int(len(usable) * 0.80)
    train = usable.iloc[:train_end]
    validation = usable.iloc[train_end:validation_end]
    test = usable.iloc[validation_end:]
    threshold = float(train["future_max_excursion_bps"].quantile(0.95))
    result: dict[str, object] = {
        "rows": {"train": len(train), "validation": len(validation), "test": len(test)},
        "boundaries": {"train_end": str(train.index[-1]), "validation_end": str(validation.index[-1])},
        "jump_threshold_bps_training_only": threshold,
        "models": {},
    }
    fitted: dict[str, Pipeline] = {}
    for name, features in (("baseline", BASELINE), ("augmented", BASELINE + CONCENTRATION)):
        estimator = model()
        estimator.fit(train[features], (train["future_max_excursion_bps"] >= threshold).astype(int))
        fitted[name] = estimator
        result["models"][name] = {}  # type: ignore[index]
        for split_name, split in (("validation", validation), ("test", test)):
            labels = (split["future_max_excursion_bps"] >= threshold).astype(int).to_numpy()
            probability = estimator.predict_proba(split[features])[:, 1]
            result["models"][name][split_name] = scores(labels, probability)  # type: ignore[index]
    base_test = result["models"]["baseline"]["test"]  # type: ignore[index]
    aug_test = result["models"]["augmented"]["test"]  # type: ignore[index]
    result["test_incremental"] = {
        "average_precision": aug_test["average_precision"] - base_test["average_precision"],
        "roc_auc": aug_test["roc_auc"] - base_test["roc_auc"],
        "brier_improvement": base_test["brier"] - aug_test["brier"],
    }
    return result


def block_feature_tests(frame: pd.DataFrame, *, seed: int = 20260913) -> dict[str, object]:
    usable = frame.dropna(subset=["future_max_excursion_bps"]).copy()
    train_end = int(len(usable) * 0.60)
    test_start = int(len(usable) * 0.80)
    train, test = usable.iloc[:train_end], usable.iloc[test_start:].copy()
    test["block"] = np.arange(len(test)) // 60
    rng = np.random.default_rng(seed)
    output: dict[str, object] = {}
    for label, feature in ORIENTED_SIGNALS.items():
        low = float(train[feature].quantile(0.20))
        high = float(train[feature].quantile(0.80))
        block_deltas = []
        for _, block in test.groupby("block"):
            low_values = block.loc[block[feature] <= low, "future_max_excursion_bps"]
            high_values = block.loc[block[feature] >= high, "future_max_excursion_bps"]
            if len(low_values) >= 2 and len(high_values) >= 2:
                block_deltas.append(float(high_values.mean() - low_values.mean()))
        rho, rho_p = spearmanr(test[feature], test["future_max_excursion_bps"], nan_policy="omit")
        if block_deltas:
            values = np.asarray(block_deltas)
            boot = np.asarray([rng.choice(values, size=len(values), replace=True).mean() for _ in range(1_000)])
            ci = [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]
            delta = float(values.mean())
        else:
            ci, delta = [float("nan"), float("nan")], float("nan")
        output[label] = {
            "feature": feature,
            "spearman_rho_test": finite_or_none(float(rho)),
            "spearman_p_naive_not_independence_adjusted": finite_or_none(float(rho_p)),
            "high_minus_low_future_excursion_bps": finite_or_none(delta),
            "block_bootstrap_95pct_ci": [finite_or_none(value) for value in ci],
            "eligible_test_blocks": len(block_deltas),
            "directionally_supported": bool(np.isfinite(ci[0]) and ci[0] > 0.0 and rho > 0.0),
        }
    return output


def conditional_tests(frame: pd.DataFrame, *, seed: int = 20260913) -> dict[str, object]:
    usable = frame.dropna(subset=["future_max_excursion_bps", "future_return_bps"]).copy()
    train, test = usable.iloc[: int(len(usable) * 0.60)], usable.iloc[int(len(usable) * 0.80) :]
    stress_cut = float(train["gradient_energy"].quantile(0.80))
    calm_cut = float(train["gradient_energy"].quantile(0.20))
    small_cut = float(train.loc[train["trade_volume"] > 0, "trade_volume"].median())
    small = test.loc[(test["trade_volume"] > 0) & (test["trade_volume"] <= small_cut)].copy()
    small["impact_per_volume"] = small["future_max_excursion_bps"] / small["trade_volume"]
    high_impact = float(small.loc[small["gradient_energy"] >= stress_cut, "impact_per_volume"].mean())
    low_impact = float(small.loc[small["gradient_energy"] <= calm_cut, "impact_per_volume"].mean())

    tiny_cut = float(train["book_imbalance"].abs().median())
    tiny = test.loc[test["book_imbalance"].abs() <= tiny_cut]
    slopes: dict[str, float] = {}
    for name, subset in (
        ("high_stress", tiny.loc[tiny["gradient_energy"] >= stress_cut]),
        ("low_stress", tiny.loc[tiny["gradient_energy"] <= calm_cut]),
    ):
        if len(subset) >= 10 and float(subset["book_imbalance"].var()) > 0:
            slopes[name] = float(np.polyfit(subset["book_imbalance"], subset["future_return_bps"], 1)[0])
        else:
            slopes[name] = float("nan")
    rng = np.random.default_rng(seed)
    blocks = test.index.floor("10min").unique()
    impact_differences: list[float] = []
    slope_differences: list[float] = []
    for _ in range(1_000):
        selected = rng.choice(blocks, size=len(blocks), replace=True)
        sampled = pd.concat([test.loc[test.index.floor("10min") == block] for block in selected])
        sampled_small = sampled.loc[
            (sampled["trade_volume"] > 0) & (sampled["trade_volume"] <= small_cut)
        ].copy()
        sampled_small["impact_per_volume"] = (
            sampled_small["future_max_excursion_bps"] / sampled_small["trade_volume"]
        )
        high = sampled_small.loc[
            sampled_small["gradient_energy"] >= stress_cut, "impact_per_volume"
        ]
        low = sampled_small.loc[
            sampled_small["gradient_energy"] <= calm_cut, "impact_per_volume"
        ]
        if len(high) >= 5 and len(low) >= 5:
            impact_differences.append(float(high.mean() - low.mean()))
        sampled_tiny = sampled.loc[sampled["book_imbalance"].abs() <= tiny_cut]
        high_state = sampled_tiny.loc[sampled_tiny["gradient_energy"] >= stress_cut]
        low_state = sampled_tiny.loc[sampled_tiny["gradient_energy"] <= calm_cut]
        if len(high_state) >= 10 and len(low_state) >= 10:
            high_slope = float(np.polyfit(high_state["book_imbalance"], high_state["future_return_bps"], 1)[0])
            low_slope = float(np.polyfit(low_state["book_imbalance"], low_state["future_return_bps"], 1)[0])
            slope_differences.append(abs(high_slope) - abs(low_slope))
    impact_ci = (
        [float(np.quantile(impact_differences, 0.025)), float(np.quantile(impact_differences, 0.975))]
        if impact_differences
        else [float("nan"), float("nan")]
    )
    slope_ci = (
        [float(np.quantile(slope_differences, 0.025)), float(np.quantile(slope_differences, 0.975))]
        if slope_differences
        else [float("nan"), float("nan")]
    )
    return {
        "h21_h39_small_trade_amplification": {
            "small_trade_bin_cutoff": small_cut,
            "high_stress_impact_per_volume": finite_or_none(high_impact),
            "low_stress_impact_per_volume": finite_or_none(low_impact),
            "ratio": finite_or_none(high_impact / low_impact) if low_impact > 0 else None,
            "high_minus_low_block_bootstrap_95pct_ci": [finite_or_none(value) for value in impact_ci],
            "directionally_supported": bool(np.isfinite(impact_ci[0]) and impact_ci[0] > 0.0),
        },
        "h52_tiny_imbalance_stress_amplification": {
            "tiny_absolute_imbalance_cutoff": tiny_cut,
            "future_return_slope_by_state": {
                name: finite_or_none(value) for name, value in slopes.items()
            },
            "absolute_slope_difference_block_bootstrap_95pct_ci": [
                finite_or_none(value) for value in slope_ci
            ],
            "directionally_supported": bool(np.isfinite(slope_ci[0]) and slope_ci[0] > 0.0),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bin-seconds", type=int, default=10)
    parser.add_argument("--levels", type=int, default=25)
    parser.add_argument("--max-rows", type=int)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    if args.bin_seconds <= 0 or args.levels < 2:
        raise ValueError("invalid bin or level configuration")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    panel_path = OUTPUT_ROOT / "feature_panel.parquet"
    if panel_path.exists() and not args.rebuild and args.max_rows is None:
        frame = pd.read_parquet(panel_path)
        frame.index = pd.to_datetime(frame.index, utc=True)
    else:
        book = extract_book(DEPTH_PATH, bin_seconds=args.bin_seconds, levels=args.levels, max_rows=args.max_rows)
        origin_us = int(book["bin_start_us"].iloc[0])
        trades = load_trades(TRADES_PATH, bin_seconds=args.bin_seconds, origin_us=origin_us)
        frame = add_derived_features(book, trades, horizon=max(1, 60 // args.bin_seconds))
        target = panel_path if args.max_rows is None else OUTPUT_ROOT / "pilot_feature_panel.parquet"
        frame.to_parquet(target)

    evaluation = evaluate_models(frame)
    feature_tests = block_feature_tests(frame)
    conditional = conditional_tests(frame)
    incremental = evaluation["test_incremental"]
    primary_gate = bool(
        incremental["average_precision"] > 0.02 and incremental["brier_improvement"] > 0.0  # type: ignore[index]
    )
    supported = [name for name, result in feature_tests.items() if result["directionally_supported"]]
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "exploratory_single_day_not_trading_approval",
        "source": str(DEPTH_PATH.relative_to(ROOT)).replace("\\", "/"),
        "known_data_warning": "Tardis flags collection issues before 2020-05-14; this 2020-02-01 sample requires post-cutoff replication.",
        "configuration": {"bin_seconds": args.bin_seconds, "levels_per_side": args.levels, "outcome_seconds": 60},
        "panel_rows": len(frame),
        "evaluation": evaluation,
        "targeted_feature_tests": feature_tests,
        "conditional_tests": conditional,
        "directionally_supported_feature_tests": supported,
        "primary_gate_passed": primary_gate,
        "verdict": "PROVISIONAL_SIGNAL_REQUIRES_CLEAN_DATA_REPLICATION" if primary_gate else "NO_INCREMENTAL_SIGNAL_IN_EXPLORATORY_DAY",
    }
    output = OUTPUT_ROOT / ("results.json" if args.max_rows is None else "pilot_results.json")
    output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
