"""Measurement-corrected executable-liquidity test on the clean free day."""

from __future__ import annotations

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

from research.executable_liquidity import executable_profile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "research_scout" / "navier_stokes_liquidity_v2" / "free_data" / "tardis" / "binance-futures"
SNAPSHOTS = DATA / "book_snapshot_25" / "2020-09-01" / "BTCUSDT.csv.gz"
TRADES = DATA / "trades" / "2020-09-01" / "BTCUSDT.csv.gz"
OUTPUT = ROOT / "research_scout" / "navier_stokes_liquidity_v2" / "executable_liquidity_results"
BIN_US = 10_000_000
HORIZON = 6

BASELINE = [
    "spread_bps",
    "total_depth",
    "imbalance",
    "realized_vol_60s",
    "event_rate",
    "trade_count",
    "trade_volume",
    "signed_trade_imbalance",
]
CORRECTED = [
    "scarcity_1bps",
    "scarcity_2bps",
    "scarcity_5bps",
    "scarcity_10bps",
    "sweep_cost_1btc_bps",
    "sweep_cost_3btc_bps",
    "sweep_cost_5btc_bps",
    "sweep_convexity_bps_per_btc",
    "depth_depletion_5bps",
    "slow_recovery_60s",
    "small_trade_amplification",
    "flow_cost_interaction",
]
ORIENTED = {
    "executable_scarcity_1bps": "scarcity_1bps",
    "executable_scarcity_5bps": "scarcity_5bps",
    "fixed_size_sweep_cost_5btc": "sweep_cost_5btc_bps",
    "impact_curve_convexity": "sweep_convexity_bps_per_btc",
    "depth_depletion": "depth_depletion_5bps",
    "slow_recovery": "slow_recovery_60s",
    "small_trade_amplification": "small_trade_amplification",
    "signed_flow_times_sweep_cost": "flow_cost_interaction",
}


def snapshot_features(raw: bytes) -> dict[str, float]:
    fields = raw.rstrip(b"\r\n").split(b",")
    if len(fields) != 104:
        raise ValueError(f"expected 104 fields, got {len(fields)}")
    asks_price = np.asarray([float(fields[4 + 4 * i]) for i in range(25)])
    asks_amount = np.asarray([float(fields[5 + 4 * i]) for i in range(25)])
    bids_price = np.asarray([float(fields[6 + 4 * i]) for i in range(25)])
    bids_amount = np.asarray([float(fields[7 + 4 * i]) for i in range(25)])
    midpoint = float((asks_price[0] + bids_price[0]) / 2.0)
    bid_depth = float(bids_amount.sum())
    ask_depth = float(asks_amount.sum())
    return {
        "midpoint": midpoint,
        "spread_bps": 10_000.0 * (asks_price[0] - bids_price[0]) / midpoint,
        "total_depth": bid_depth + ask_depth,
        "imbalance": (bid_depth - ask_depth) / max(bid_depth + ask_depth, 1e-12),
        **executable_profile(asks_price, asks_amount, bids_price, bids_amount),
    }


def extract_snapshots() -> pd.DataFrame:
    rows: list[dict[str, float | pd.Timestamp]] = []
    bin_start: int | None = None
    last_raw: bytes | None = None
    count = 0
    seen = 0

    def emit() -> None:
        if bin_start is not None and last_raw is not None:
            rows.append(
                {
                    "time": pd.to_datetime(bin_start, unit="us", utc=True),
                    **snapshot_features(last_raw),
                    "event_rate": count / 10.0,
                }
            )

    with gzip.open(SNAPSHOTS, "rb") as stream:
        header = stream.readline().rstrip(b"\r\n").split(b",")
        if len(header) != 104 or header[:4] != [b"exchange", b"symbol", b"timestamp", b"local_timestamp"]:
            raise ValueError("unexpected snapshot schema")
        for raw in stream:
            prefix = raw.split(b",", 4)
            if len(prefix) != 5:
                continue
            local_us = int(prefix[3])
            wanted = local_us - local_us % BIN_US
            if bin_start is None:
                bin_start = wanted
            if wanted != bin_start:
                emit()
                bin_start = wanted
                count = 0
            count += 1
            last_raw = raw
            seen += 1
            if seen % 1_000_000 == 0:
                print(f"processed {seen:,} snapshot rows", flush=True)
    emit()
    return pd.DataFrame(rows).set_index("time").sort_index()


def extract_trades() -> pd.DataFrame:
    trades = pd.read_csv(
        TRADES,
        usecols=["timestamp", "side", "amount"],
        dtype={"timestamp": "int64", "side": "category", "amount": "float64"},
    )
    trades["time"] = pd.to_datetime(trades["timestamp"], unit="us", utc=True).dt.floor("10s")
    trades["signed_amount"] = np.where(trades["side"].eq("buy"), trades["amount"], -trades["amount"])
    trades["small_amount"] = trades["amount"].where(trades["amount"].le(0.1), 0.0)
    grouped = trades.groupby("time", observed=True).agg(
        trade_count=("amount", "size"),
        trade_volume=("amount", "sum"),
        signed_trade_volume=("signed_amount", "sum"),
        small_trade_volume=("small_amount", "sum"),
    )
    grouped["signed_trade_imbalance"] = grouped["signed_trade_volume"] / grouped["trade_volume"].clip(lower=1e-12)
    return grouped


def derive(snapshots: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    frame = snapshots.join(trades, how="left")
    trade_columns = [
        "trade_count",
        "trade_volume",
        "signed_trade_volume",
        "small_trade_volume",
        "signed_trade_imbalance",
    ]
    frame[trade_columns] = frame[trade_columns].fillna(0.0)
    frame["mid_return_bps"] = np.log(frame["midpoint"]).diff() * 10_000.0
    frame["realized_vol_60s"] = frame["mid_return_bps"].rolling(HORIZON, min_periods=2).std()
    for band in (1, 2, 5, 10):
        frame[f"scarcity_{band}bps"] = -frame[f"near_qty_{band}bps_min"]
    depth = frame["near_qty_5bps_min"]
    frame["depth_depletion_5bps"] = -depth.pct_change().clip(-5.0, 5.0)
    recovery = depth / depth.rolling(HORIZON, min_periods=2).min() - 1.0
    frame["slow_recovery_60s"] = -recovery
    frame["small_trade_amplification"] = frame["small_trade_volume"] / depth.clip(lower=1e-6)
    frame["flow_cost_interaction"] = frame["signed_trade_volume"].abs() * frame["sweep_cost_5btc_bps"]
    mids = frame["midpoint"].to_numpy(float)
    excursion = np.full(len(frame), np.nan)
    for i in range(len(frame) - HORIZON):
        excursion[i] = np.max(np.abs(np.log(mids[i + 1 : i + HORIZON + 1] / mids[i]) * 10_000.0))
    frame["future_max_excursion_bps"] = excursion
    return frame.replace([np.inf, -np.inf], np.nan)


def estimator() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", RobustScaler(quantile_range=(10, 90))),
            ("model", LogisticRegression(C=0.25, class_weight="balanced", max_iter=2000)),
        ]
    )


def scores(y: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    return {
        "average_precision": float(average_precision_score(y, probability)),
        "roc_auc": float(roc_auc_score(y, probability)),
        "brier": float(brier_score_loss(y, probability)),
    }


def blocked_tests(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, object]:
    rng = np.random.default_rng(20260913)
    work = test.copy()
    work["block"] = np.arange(len(work)) // 60
    output: dict[str, object] = {}
    for label, feature in ORIENTED.items():
        low = float(train[feature].quantile(0.2))
        high = float(train[feature].quantile(0.8))
        deltas = []
        for _, block in work.groupby("block"):
            lows = block.loc[block[feature].le(low), "future_max_excursion_bps"].dropna()
            highs = block.loc[block[feature].ge(high), "future_max_excursion_bps"].dropna()
            if len(lows) >= 2 and len(highs) >= 2:
                deltas.append(float(highs.mean() - lows.mean()))
        values = np.asarray(deltas)
        if len(values):
            boot = np.asarray([rng.choice(values, len(values), replace=True).mean() for _ in range(1000)])
            interval: list[float | None] = [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]
            delta: float | None = float(values.mean())
        else:
            interval, delta = [None, None], None
        paired = test[[feature, "future_max_excursion_bps"]].dropna()
        rho, naive_p = spearmanr(paired[feature], paired["future_max_excursion_bps"])
        output[label] = {
            "feature": feature,
            "spearman_rho_test": float(rho),
            "naive_p_not_independence_adjusted": float(naive_p),
            "high_minus_low_excursion_bps": delta,
            "block_bootstrap_95pct_ci": interval,
            "eligible_blocks": len(values),
            "directionally_supported": bool(interval[0] is not None and interval[0] > 0 and rho > 0),
        }
    return output


def recovery_events(frame: pd.DataFrame) -> dict[str, object]:
    depth = frame["near_qty_5bps_min"].to_numpy(float)
    excursion = frame["future_max_excursion_bps"].to_numpy(float)
    drops = np.flatnonzero(depth[1:] / np.maximum(depth[:-1], 1e-12) <= 0.8) + 1
    times = []
    event_excursions = []
    for index in drops:
        target = 0.9 * depth[index - 1]
        future = np.flatnonzero(depth[index + 1 : index + 31] >= target)
        times.append(float((future[0] + 1) * 10) if len(future) else 300.0)
        if np.isfinite(excursion[index]):
            event_excursions.append(float(excursion[index]))
    return {
        "depletion_events": len(drops),
        "median_seconds_to_90pct_recovery_censored_at_300": float(np.median(times)) if times else None,
        "mean_60s_excursion_after_depletion_bps": float(np.mean(event_excursions)) if event_excursions else None,
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    panel_path = OUTPUT / "feature_panel.parquet"
    if panel_path.exists():
        frame = pd.read_parquet(panel_path)
    else:
        frame = derive(extract_snapshots(), extract_trades())
        frame.to_parquet(panel_path)
    usable = frame.dropna(subset=["future_max_excursion_bps"])
    first = int(len(usable) * 0.6)
    second = int(len(usable) * 0.8)
    train, validation, test = usable.iloc[:first], usable.iloc[first:second], usable.iloc[second:]
    threshold = float(train["future_max_excursion_bps"].quantile(0.95))
    model_results: dict[str, object] = {}
    for name, features in (("baseline", BASELINE), ("corrected", BASELINE + CORRECTED)):
        fitted = estimator().fit(train[features], train["future_max_excursion_bps"].ge(threshold))
        split_scores = {}
        for split_name, split in (("validation", validation), ("test", test)):
            y = split["future_max_excursion_bps"].ge(threshold).to_numpy()
            split_scores[split_name] = scores(y, fitted.predict_proba(split[features])[:, 1])
        model_results[name] = split_scores
    base = model_results["baseline"]["test"]
    corrected = model_results["corrected"]["test"]
    incremental = {
        "average_precision": corrected["average_precision"] - base["average_precision"],
        "roc_auc": corrected["roc_auc"] - base["roc_auc"],
        "brier_improvement": base["brier"] - corrected["brier"],
    }
    primary = incremental["average_precision"] > 0.02 and incremental["brier_improvement"] > 0
    block_results = blocked_tests(train, test)
    targeted_supported = [name for name, result in block_results.items() if result["directionally_supported"]]
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "exploratory_single_clean_day_not_trading_approval",
        "sources": [str(SNAPSHOTS.relative_to(ROOT)).replace("\\", "/"), str(TRADES.relative_to(ROOT)).replace("\\", "/")],
        "paid_requests_made": False,
        "rows": {"panel": len(frame), "train": len(train), "validation": len(validation), "test": len(test)},
        "jump_threshold_bps": threshold,
        "models": model_results,
        "test_incremental": incremental,
        "blocked_feature_tests": block_results,
        "recovery_event_study_full_day": recovery_events(usable),
        "primary_gate_passed": primary,
        "targeted_hypotheses_supported": targeted_supported,
        "verdict": "CORRECTED_PASS_REQUIRES_NEW_WHOLE_DAY" if primary else "CORRECTED_PRIMARY_FAIL_CLOSE_BRANCH",
    }
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
