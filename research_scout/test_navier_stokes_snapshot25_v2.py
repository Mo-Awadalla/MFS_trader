"""Post-cutoff spatial replication using Tardis 25-level snapshots."""

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

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research_scout" / "navier_stokes_liquidity_v2" / "free_data" / "tardis" / "binance-futures" / "book_snapshot_25" / "2020-09-01" / "BTCUSDT.csv.gz"
OUTPUT = ROOT / "research_scout" / "navier_stokes_liquidity_v2" / "snapshot25_results"
BIN_US = 10_000_000
SUBBINS = 100
HORIZON = 6

BASELINE = ["spread_bps", "total_depth", "imbalance", "realized_vol_60s", "event_rate"]
AUGMENTED = ["liquidity_linf_l2", "core_width_bps", "core_width_change", "gradient_max", "gradient_energy", "curvature_energy", "event_linf_l2", "spectral_cascade_ratio"]
ORIENTED = {
    "h2_h3_liquidity_norm_concentration": "liquidity_linf_l2",
    "h4_core_contraction": "negative_core_width",
    "h11_gradient_max": "gradient_max",
    "h13_gradient_energy": "gradient_energy",
    "h14_curvature_energy": "curvature_energy",
    "h15_event_localization": "event_linf_l2",
    "h53_core_trajectory": "negative_core_width_change",
}


def snapshot_features(raw: bytes) -> dict[str, float]:
    fields = raw.rstrip(b"\r\n").split(b",")
    if len(fields) != 104:
        raise ValueError(f"expected 104 fields, got {len(fields)}")
    asks_price = np.asarray([float(fields[4 + 4 * i]) for i in range(25)])
    asks_amount = np.asarray([float(fields[5 + 4 * i]) for i in range(25)])
    bids_price = np.asarray([float(fields[6 + 4 * i]) for i in range(25)])
    bids_amount = np.asarray([float(fields[7 + 4 * i]) for i in range(25)])
    midpoint = (asks_price[0] + bids_price[0]) / 2.0
    prices = np.concatenate((bids_price[::-1], asks_price))
    amounts = np.concatenate((bids_amount[::-1], asks_amount))
    positions = 10_000.0 * (prices - midpoint) / midpoint
    normalized = amounts / max(float(amounts.sum()), 1e-12)
    l2 = float(np.sqrt(np.mean(normalized**2)))
    order = np.argsort(np.abs(positions))
    cumulative = np.cumsum(normalized[order])
    half = min(int(np.searchsorted(cumulative, 0.5)), len(order) - 1)
    core_width = float(np.max(np.abs(positions[order[: half + 1]])))
    gradient = np.gradient(normalized, positions)
    curvature = np.gradient(gradient, positions)
    bid_depth, ask_depth = float(bids_amount.sum()), float(asks_amount.sum())
    return {
        "midpoint": midpoint,
        "spread_bps": 10_000.0 * (asks_price[0] - bids_price[0]) / midpoint,
        "total_depth": bid_depth + ask_depth,
        "imbalance": (bid_depth - ask_depth) / max(bid_depth + ask_depth, 1e-12),
        "liquidity_linf_l2": float(normalized.max() / max(l2, 1e-12)),
        "core_width_bps": core_width,
        "gradient_max": float(np.max(np.abs(gradient))),
        "gradient_energy": float(np.mean(gradient**2)),
        "curvature_energy": float(np.mean(curvature**2)),
    }


def extract() -> pd.DataFrame:
    rows: list[dict[str, float | pd.Timestamp]] = []
    bin_start: int | None = None
    last_raw: bytes | None = None
    counts = np.zeros(SUBBINS, dtype=np.int64)
    seen = 0

    def emit() -> None:
        if bin_start is None or last_raw is None:
            return
        feature = snapshot_features(last_raw)
        values = counts.astype(float)
        event_l2 = float(np.sqrt(np.mean(values**2)))
        centered = values - values.mean()
        power = np.abs(np.fft.rfft(centered)) ** 2
        frequency = np.fft.rfftfreq(SUBBINS, d=0.1)
        high = float(power[(frequency >= 1.0) & (frequency <= 5.0)].sum())
        low = float(power[(frequency >= 0.1) & (frequency < 1.0)].sum())
        rows.append({
            "time": pd.to_datetime(bin_start, unit="us", utc=True),
            **feature,
            "event_rate": float(values.sum() / 10.0),
            "event_linf_l2": float(values.max() / max(event_l2, 1e-12)),
            "spectral_cascade_ratio": high / max(low, 1e-12),
        })

    with gzip.open(SOURCE, "rb") as stream:
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
                counts.fill(0)
            sub = min(SUBBINS - 1, (local_us % BIN_US) * SUBBINS // BIN_US)
            counts[sub] += 1
            last_raw = raw
            seen += 1
            if seen % 1_000_000 == 0:
                print(f"processed {seen:,} snapshot rows", flush=True)
    emit()
    return pd.DataFrame(rows).set_index("time").sort_index()


def derive(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["mid_return_bps"] = np.log(frame["midpoint"]).diff() * 10_000.0
    frame["realized_vol_60s"] = frame["mid_return_bps"].rolling(HORIZON, min_periods=2).std()
    frame["core_width_change"] = frame["core_width_bps"].diff()
    frame["negative_core_width"] = -frame["core_width_bps"]
    frame["negative_core_width_change"] = -frame["core_width_change"]
    mids = frame["midpoint"].to_numpy(float)
    excursion = np.full(len(frame), np.nan)
    for i in range(len(frame) - HORIZON):
        excursion[i] = np.max(np.abs(np.log(mids[i + 1 : i + HORIZON + 1] / mids[i]) * 10_000.0))
    frame["future_max_excursion_bps"] = excursion
    return frame.replace([np.inf, -np.inf], np.nan)


def estimator() -> Pipeline:
    return Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", RobustScaler(quantile_range=(10, 90))), ("model", LogisticRegression(C=0.25, class_weight="balanced", max_iter=2000))])


def scores(y: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    return {"average_precision": float(average_precision_score(y, probability)), "roc_auc": float(roc_auc_score(y, probability)), "brier": float(brier_score_loss(y, probability))}


def blocked_tests(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, object]:
    rng = np.random.default_rng(20260913)
    work = test.copy()
    work["block"] = np.arange(len(work)) // 60
    output = {}
    for label, feature in ORIENTED.items():
        low, high = float(train[feature].quantile(0.2)), float(train[feature].quantile(0.8))
        deltas = []
        for _, block in work.groupby("block"):
            lows = block.loc[block[feature] <= low, "future_max_excursion_bps"]
            highs = block.loc[block[feature] >= high, "future_max_excursion_bps"]
            if len(lows) >= 2 and len(highs) >= 2:
                deltas.append(float(highs.mean() - lows.mean()))
        values = np.asarray(deltas)
        if len(values):
            boot = np.asarray([rng.choice(values, len(values), replace=True).mean() for _ in range(1000)])
            interval = [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]
            delta = float(values.mean())
        else:
            interval, delta = [None, None], None
        rho, naive_p = spearmanr(test[feature], test["future_max_excursion_bps"], nan_policy="omit")
        output[label] = {"feature": feature, "spearman_rho_test": float(rho), "naive_p_not_independence_adjusted": float(naive_p), "high_minus_low_excursion_bps": delta, "block_bootstrap_95pct_ci": interval, "eligible_blocks": len(values), "directionally_supported": bool(interval[0] is not None and interval[0] > 0 and rho > 0)}
    return output


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    panel_path = OUTPUT / "feature_panel.parquet"
    if panel_path.exists():
        frame = pd.read_parquet(panel_path)
    else:
        frame = derive(extract())
        frame.to_parquet(panel_path)
    usable = frame.dropna(subset=["future_max_excursion_bps"])
    a, b = int(len(usable) * 0.6), int(len(usable) * 0.8)
    train, validation, test = usable.iloc[:a], usable.iloc[a:b], usable.iloc[b:]
    threshold = float(train["future_max_excursion_bps"].quantile(0.95))
    model_results = {}
    for name, features in (("baseline", BASELINE), ("augmented", BASELINE + AUGMENTED)):
        fitted = estimator().fit(train[features], train["future_max_excursion_bps"].ge(threshold))
        model_results[name] = {}
        for split_name, split in (("validation", validation), ("test", test)):
            y = split["future_max_excursion_bps"].ge(threshold).to_numpy()
            model_results[name][split_name] = scores(y, fitted.predict_proba(split[features])[:, 1])
    base, aug = model_results["baseline"]["test"], model_results["augmented"]["test"]
    incremental = {"average_precision": aug["average_precision"] - base["average_precision"], "roc_auc": aug["roc_auc"] - base["roc_auc"], "brier_improvement": base["brier"] - aug["brier"]}
    block_results = blocked_tests(train, test)
    primary = incremental["average_precision"] > 0.02 and incremental["brier_improvement"] > 0
    payload = {"created_at_utc": datetime.now(UTC).isoformat(), "status": "post_cutoff_spatial_replication_not_trading_approval", "source": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "rows": {"panel": len(frame), "train": len(train), "validation": len(validation), "test": len(test)}, "jump_threshold_bps": threshold, "models": model_results, "test_incremental": incremental, "blocked_feature_tests": block_results, "primary_gate_passed": primary, "verdict": "POST_CUTOFF_SPATIAL_PASS_REQUIRES_MORE_DAYS" if primary else "POST_CUTOFF_SPATIAL_FAIL"}
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
