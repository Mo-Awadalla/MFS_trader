"""Test the next preregistered multiscale Navier-Stokes hypothesis batch."""

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

from research.multiscale_liquidity import (
    haar_energy_ratio,
    multifractal_width,
    norm_ratios,
    normalized_profile,
    power_law_fit,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout" / "navier_stokes_liquidity_v2"
SNAPSHOTS = BASE / "free_data" / "tardis" / "binance-futures" / "book_snapshot_25" / "2020-09-01" / "BTCUSDT.csv.gz"
TRADES = BASE / "free_data" / "tardis" / "binance-futures" / "trades" / "2020-09-01" / "BTCUSDT.csv.gz"
EXECUTABLE_PANEL = BASE / "executable_liquidity_results" / "feature_panel.parquet"
OUTPUT = BASE / "multiscale_batch_results"
BIN_US = 10_000_000

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
NEW_FEATURES = [
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
    "regularity_integral_60s",
]
ORIENTED = {
    "h3_higher_norm_concentration": "linf_l2",
    "h6_power_law_acceleration": "critical_score",
    "h7_profile_self_similarity": "profile_collapse_score",
    "h16_gradient_early_warning": "gradient_max",
    "h25_shortening_microbursts": "microburst_acceleration",
    "h27_fine_to_coarse_volatility": "fine_to_coarse_vol",
    "h28_wavelet_high_frequency_energy": "haar_high_low_ratio",
    "h29_multifractal_width": "multifractal_width",
    "h30_cross_scale_coupling": "cross_scale_coupling",
    "h93_regularity_integral": "regularity_integral_60s",
    "h94_estimated_critical_time": "critical_score",
}


def snapshot_multiscale(raw: bytes) -> dict[str, float]:
    fields = raw.rstrip(b"\r\n").split(b",")
    if len(fields) != 104:
        raise ValueError(f"expected 104 fields, got {len(fields)}")
    asks_price = np.asarray([float(fields[4 + 4 * i]) for i in range(25)])
    asks_amount = np.asarray([float(fields[5 + 4 * i]) for i in range(25)])
    bids_price = np.asarray([float(fields[6 + 4 * i]) for i in range(25)])
    bids_amount = np.asarray([float(fields[7 + 4 * i]) for i in range(25)])
    midpoint = float((asks_price[0] + bids_price[0]) / 2.0)
    ask_distance = (asks_price / midpoint - 1.0) * 10_000.0
    bid_distance = (1.0 - bids_price / midpoint) * 10_000.0
    ask_steps = np.diff(np.r_[0.0, ask_distance])
    bid_steps = np.diff(np.r_[0.0, bid_distance])
    susceptibility = np.r_[ask_steps / np.maximum(asks_amount, 1e-9), bid_steps / np.maximum(bids_amount, 1e-9)]
    ratios = norm_ratios(np.abs(susceptibility))
    positions = np.r_[-bid_distance[::-1], ask_distance]
    amounts = np.r_[bids_amount[::-1], asks_amount]
    density = amounts / max(float(amounts.sum()), 1e-12)
    gradient = np.gradient(density, positions)
    profile = normalized_profile(positions, amounts)
    return {
        **ratios,
        "gradient_max": float(np.max(np.abs(gradient))),
        **{f"profile_{index:02d}": float(value) for index, value in enumerate(profile)},
    }


def extract_snapshot_features() -> pd.DataFrame:
    rows: list[dict[str, float | pd.Timestamp]] = []
    bin_start: int | None = None
    last_raw: bytes | None = None
    seen = 0

    def emit() -> None:
        if bin_start is not None and last_raw is not None:
            rows.append({"time": pd.to_datetime(bin_start, unit="us", utc=True), **snapshot_multiscale(last_raw)})

    with gzip.open(SNAPSHOTS, "rb") as stream:
        header = stream.readline().rstrip(b"\r\n").split(b",")
        if len(header) != 104:
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
            last_raw = raw
            seen += 1
            if seen % 1_000_000 == 0:
                print(f"processed {seen:,} snapshot rows", flush=True)
    emit()
    return pd.DataFrame(rows).set_index("time").sort_index()


def extract_trade_features(index: pd.DatetimeIndex, trades_path: Path = TRADES) -> pd.DataFrame:
    trades = pd.read_csv(
        trades_path,
        usecols=["timestamp", "side", "price", "amount"],
        dtype={"timestamp": "int64", "side": "category", "price": "float64", "amount": "float64"},
    ).sort_values("timestamp")
    timestamps = trades["timestamp"].to_numpy(np.int64)
    signed = np.where(trades["side"].eq("buy"), trades["amount"], -trades["amount"]).astype(float)

    bucket_100ms = timestamps // 100_000
    keep = np.r_[bucket_100ms[1:] != bucket_100ms[:-1], True]
    sampled_bucket = bucket_100ms[keep]
    sampled_price = trades["price"].to_numpy(float)[keep]
    sampled_returns = np.r_[0.0, np.diff(np.log(sampled_price)) * 10_000.0]
    fine_rv = pd.Series(sampled_returns**2).groupby(sampled_bucket // 100).sum()
    last_price = pd.Series(sampled_price).groupby(sampled_bucket // 100).last()
    coarse_sq = (np.log(last_price).diff() * 10_000.0) ** 2

    start_us = int(index[0].value // 1_000)
    seconds = (timestamps - start_us) // 1_000_000
    valid = (seconds >= 0) & (seconds < 86_400)
    flow_1s = np.bincount(seconds[valid], weights=signed[valid], minlength=86_400).astype(float)
    coarse_flow = pd.Series(flow_1s).rolling(10, min_periods=2).sum().to_numpy()
    intervals = np.diff(timestamps).astype(float) / 1_000_000.0

    rows = []
    for time in index:
        bin_number = int((time.value // 1_000 - start_us) // BIN_US)
        end_second = min(bin_number * 10 + 9, 86_399)
        end_us = start_us + (bin_number + 1) * BIN_US
        trade_end = int(np.searchsorted(timestamps, end_us, side="left"))
        recent_intervals = intervals[max(0, trade_end - 50) : max(0, trade_end - 1)]
        if len(recent_intervals) >= 10:
            microburst = -float(np.polyfit(np.arange(len(recent_intervals)), np.log(np.maximum(recent_intervals, 1e-6)), 1)[0])
        else:
            microburst = 0.0
        flow64 = flow_1s[max(0, end_second - 63) : end_second + 1]
        flow300 = flow_1s[max(0, end_second - 299) : end_second + 1]
        flow60 = flow_1s[max(0, end_second - 59) : end_second + 1]
        coarse60 = coarse_flow[max(0, end_second - 59) : end_second + 1]
        if len(flow60) >= 10 and np.std(np.abs(flow60)) > 0 and np.std(np.abs(coarse60)) > 0:
            coupling = float(np.corrcoef(np.abs(flow60), np.abs(coarse60))[0, 1])
        else:
            coupling = 0.0
        key = (start_us // BIN_US) + bin_number
        fine = float(fine_rv.get(key, 0.0))
        coarse = float(coarse_sq.get(key, 0.0))
        rows.append(
            {
                "time": time,
                "microburst_acceleration": microburst,
                "fine_to_coarse_vol": float(np.log1p(fine / max(coarse, 1e-6))),
                "haar_high_low_ratio": haar_energy_ratio(flow64) if len(flow64) >= 16 else 0.0,
                "multifractal_width": multifractal_width(flow300) if len(flow300) >= 64 else 0.0,
                "cross_scale_coupling": coupling,
            }
        )
    return pd.DataFrame(rows).set_index("time")


def derive() -> pd.DataFrame:
    base = pd.read_parquet(EXECUTABLE_PANEL)
    snapshots = extract_snapshot_features()
    trades = extract_trade_features(base.index)
    frame = base.join(snapshots, how="left").join(trades, how="left")
    profile_columns = [column for column in frame if column.startswith("profile_")]
    profile_change = np.sqrt(frame[profile_columns].diff().pow(2).sum(axis=1))
    frame["profile_collapse_score"] = -profile_change.rolling(6, min_periods=2).mean()
    fits = []
    sweep = frame["sweep_cost_5btc_bps"].to_numpy(float)
    for index in range(len(frame)):
        fits.append(power_law_fit(sweep[max(0, index - 29) : index + 1]))
    frame = frame.join(pd.DataFrame(fits, index=frame.index))
    frame["regularity_integral_60s"] = frame["gradient_max"].rolling(6, min_periods=2).sum()
    mids = frame["midpoint"].to_numpy(float)
    for bins, seconds in ((1, 10), (3, 30), (6, 60)):
        outcome = np.full(len(frame), np.nan)
        for index in range(len(frame) - bins):
            outcome[index] = np.max(np.abs(np.log(mids[index + 1 : index + bins + 1] / mids[index]) * 10_000.0))
        frame[f"future_excursion_{seconds}s_bps"] = outcome
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


def split_frame(frame: pd.DataFrame, outcome: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    usable = frame.dropna(subset=[outcome])
    first, second = int(len(usable) * 0.6), int(len(usable) * 0.8)
    return usable.iloc[:first], usable.iloc[first:second], usable.iloc[second:]


def lead_time_tests(frame: pd.DataFrame) -> dict[str, object]:
    output = {}
    norm_order = ["l4_l2", "l8_l2", "l16_l2", "linf_l2"]
    for seconds in (10, 30, 60):
        outcome = f"future_excursion_{seconds}s_bps"
        train, _, test = split_frame(frame, outcome)
        threshold = float(train[outcome].quantile(0.95))
        y_train = train[outcome].ge(threshold)
        y_test = test[outcome].ge(threshold).to_numpy()
        base_model = estimator().fit(train[BASELINE], y_train)
        base_ap = float(average_precision_score(y_test, base_model.predict_proba(test[BASELINE])[:, 1]))
        increments = {}
        for feature in norm_order:
            model = estimator().fit(train[BASELINE + [feature]], y_train)
            ap = float(average_precision_score(y_test, model.predict_proba(test[BASELINE + [feature]])[:, 1]))
            increments[feature] = ap - base_ap
        gradient_model = estimator().fit(train[BASELINE + ["gradient_max"]], y_train)
        gradient_ap = float(average_precision_score(y_test, gradient_model.predict_proba(test[BASELINE + ["gradient_max"]])[:, 1]))
        output[f"{seconds}s"] = {
            "jump_threshold_bps": threshold,
            "baseline_average_precision": base_ap,
            "norm_incremental_average_precision": increments,
            "gradient_incremental_average_precision": gradient_ap - base_ap,
        }
    monotone_30 = np.all(np.diff(list(output["30s"]["norm_incremental_average_precision"].values())) >= 0)
    monotone_60 = np.all(np.diff(list(output["60s"]["norm_incremental_average_precision"].values())) >= 0)
    output["h3_gate_passed"] = bool(monotone_30 and monotone_60 and output["10s"]["norm_incremental_average_precision"]["linf_l2"] > 0)
    return output


def blocked_tests(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, object]:
    rng = np.random.default_rng(20260913)
    work = test.copy()
    work["block"] = np.arange(len(work)) // 60
    output = {}
    for label, feature in ORIENTED.items():
        low, high = float(train[feature].quantile(0.2)), float(train[feature].quantile(0.8))
        deltas = []
        for _, block in work.groupby("block"):
            lows = block.loc[block[feature].le(low), "future_excursion_60s_bps"].dropna()
            highs = block.loc[block[feature].ge(high), "future_excursion_60s_bps"].dropna()
            if len(lows) >= 2 and len(highs) >= 2:
                deltas.append(float(highs.mean() - lows.mean()))
        values = np.asarray(deltas)
        interval: list[float | None]
        delta: float | None
        if len(values):
            boot = np.asarray([rng.choice(values, len(values), replace=True).mean() for _ in range(1000)])
            interval = [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]
            delta = float(values.mean())
        else:
            interval, delta = [None, None], None
        paired = test[[feature, "future_excursion_60s_bps"]].dropna()
        rho, naive_p = spearmanr(paired[feature], paired["future_excursion_60s_bps"])
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


def safe_region_test(train: pd.DataFrame, test: pd.DataFrame, threshold: float) -> dict[str, object]:
    cutoff = float(train["regularity_integral_60s"].quantile(0.2))
    labels = test["future_excursion_60s_bps"].ge(threshold)
    safe = test["regularity_integral_60s"].le(cutoff)
    safe_n, safe_events = int(safe.sum()), int(labels[safe].sum())
    unsafe_n, unsafe_events = int((~safe).sum()), int(labels[~safe].sum())
    safe_rate = safe_events / max(safe_n, 1)
    unsafe_rate = unsafe_events / max(unsafe_n, 1)
    overall_rate = float(labels.mean())
    z = 1.959963984540054
    center = (safe_rate + z**2 / (2 * safe_n)) / (1 + z**2 / safe_n)
    radius = z * np.sqrt((safe_rate * (1 - safe_rate) + z**2 / (4 * safe_n)) / safe_n) / (1 + z**2 / safe_n)
    upper = float(center + radius)
    return {
        "training_20pct_cutoff": cutoff,
        "safe_observations": safe_n,
        "safe_jump_events": safe_events,
        "safe_jump_rate": safe_rate,
        "unsafe_jump_rate": unsafe_rate,
        "overall_test_jump_rate": overall_rate,
        "safe_rate_wilson_95pct_upper": upper,
        "h93_gate_passed": bool(safe_rate <= 0.25 * unsafe_rate and upper < overall_rate),
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    panel_path = OUTPUT / "feature_panel.parquet"
    if panel_path.exists():
        frame = pd.read_parquet(panel_path)
    else:
        frame = derive()
        frame.to_parquet(panel_path)
    train, validation, test = split_frame(frame, "future_excursion_60s_bps")
    threshold = float(train["future_excursion_60s_bps"].quantile(0.95))
    y_train = train["future_excursion_60s_bps"].ge(threshold)
    models = {}
    for name, features in (("baseline", BASELINE), ("augmented", BASELINE + NEW_FEATURES)):
        fitted = estimator().fit(train[features], y_train)
        models[name] = {}
        for split_name, split in (("validation", validation), ("test", test)):
            y = split["future_excursion_60s_bps"].ge(threshold).to_numpy()
            models[name][split_name] = scores(y, fitted.predict_proba(split[features])[:, 1])
    base, augmented = models["baseline"]["test"], models["augmented"]["test"]
    incremental = {
        "average_precision": augmented["average_precision"] - base["average_precision"],
        "roc_auc": augmented["roc_auc"] - base["roc_auc"],
        "brier_improvement": base["brier"] - augmented["brier"],
    }
    primary = incremental["average_precision"] > 0.02 and incremental["brier_improvement"] > 0
    targeted = blocked_tests(train, test)
    supported = [name for name, result in targeted.items() if result["directionally_supported"]]
    lead_times = lead_time_tests(frame)
    safe_region = safe_region_test(train, test, threshold)
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "exploratory_reuse_of_seen_clean_day_not_confirmation_or_trading_approval",
        "hypotheses": [3, 6, 7, 16, 25, 27, 28, 29, 30, 93, 94],
        "paid_requests_made": False,
        "rows": {"panel": len(frame), "train": len(train), "validation": len(validation), "test": len(test)},
        "jump_threshold_60s_bps": threshold,
        "models": models,
        "test_incremental": incremental,
        "primary_gate_passed": primary,
        "blocked_feature_tests": targeted,
        "targeted_hypotheses_supported": supported,
        "lead_time_tests": lead_times,
        "safe_region_test": safe_region,
        "verdict": "EXPLORATORY_CANDIDATES_REQUIRE_NEW_DAY" if (primary or supported or lead_times["h3_gate_passed"] or safe_region["h93_gate_passed"]) else "BATCH_IMPLEMENTATIONS_NOT_SUPPORTED",
    }
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
