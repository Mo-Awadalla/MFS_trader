"""Preregistered multi-day test of H1/H2 local-versus-global pressure divergence."""

from __future__ import annotations

import json
import math
import zipfile
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline

from research.model_breakdown import block_bootstrap_mean

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout" / "navier_stokes_liquidity_v2"
DATA = BASE / "free_data" / "binance-public" / "futures-um"
OUTPUT = BASE / "h1_local_global_divergence_results"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TRAIN_DATES = ["2023-08-15", "2023-09-15", "2023-10-15", "2023-11-15"]
VALIDATION_DATES = ["2023-12-15", "2024-01-15"]
TEST_DATES = [
    "2024-01-31",
    "2024-02-07",
    "2024-02-21",
    "2024-03-06",
    "2024-03-20",
    "2024-03-27",
]
ALL_DATES = TRAIN_DATES + VALIDATION_DATES + TEST_DATES
BASELINE = [
    "spread_mean",
    "depth_mean_60s",
    "imbalance_mean",
    "realized_vol_60s",
    "trade_volume_60s",
    "signed_trade_imbalance_60s",
    "event_rate",
    "pressure_rms_60s",
]
AUGMENTED = BASELINE + ["pressure_max_60s", "pressure_linf_l2_60s"]
ORDINARY = [
    "pressure_rms_60s",
    "trade_volume_60s",
    "realized_vol_60s",
    "depth_mean_60s",
]


def classifier() -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            (
                "model",
                HistGradientBoostingClassifier(
                    learning_rate=0.05,
                    max_iter=150,
                    max_depth=3,
                    l2_regularization=1.0,
                    random_state=20260913,
                ),
            ),
        ]
    )


def rolling_at_decisions(values: np.ndarray, operation: str) -> np.ndarray:
    series = pd.Series(values)
    if operation == "max":
        rolled = series.rolling(60, min_periods=30).max()
    elif operation == "rms":
        rolled = series.pow(2).rolling(60, min_periods=30).mean().pow(0.5)
    elif operation == "sum":
        rolled = series.rolling(60, min_periods=30).sum()
    else:
        raise ValueError(f"unknown rolling operation: {operation}")
    return rolled.to_numpy()[9::10]


def extract_day(symbol: str, date: str) -> pd.DataFrame:
    day = DATA / symbol / date
    book_path = day / f"{symbol}-bookTicker-{date}.zip"
    trade_path = day / f"{symbol}-aggTrades-{date}.zip"
    trades = pd.read_csv(
        trade_path,
        compression="zip",
        usecols=["quantity", "transact_time", "is_buyer_maker"],
    ).sort_values("transact_time")
    trade_time = trades["transact_time"].to_numpy(np.int64)
    trade_quantity = trades["quantity"].to_numpy(float)
    buyer_maker = trades["is_buyer_maker"].astype(bool).to_numpy()
    start_ms = int(pd.Timestamp(date, tz="UTC").value // 1_000_000)

    quote_count = np.zeros(8_640, dtype=np.int64)
    spread_sum = np.zeros(8_640)
    depth_sum = np.zeros(8_640)
    imbalance_sum = np.zeros(8_640)
    midpoint_last = np.full(8_640, np.nan)
    pressure_1s = np.zeros(86_400)
    volume_1s = np.zeros(86_400)
    signed_volume_1s = np.zeros(86_400)
    trade_pointer = 0
    last_event = -1
    last_bid_qty = math.nan
    last_ask_qty = math.nan
    rejected_timestamp_rows = 0

    def consume_trades(before_ms: int) -> None:
        nonlocal trade_pointer
        while trade_pointer < len(trades) and trade_time[trade_pointer] < before_ms:
            second = (int(trade_time[trade_pointer]) - start_ms) // 1_000
            if 0 <= second < 86_400 and np.isfinite(last_bid_qty + last_ask_qty):
                quantity = trade_quantity[trade_pointer]
                is_sell = buyer_maker[trade_pointer]
                touch_quantity = last_bid_qty if is_sell else last_ask_qty
                pressure_1s[second] += quantity / max(touch_quantity, 1e-12)
                volume_1s[second] += quantity
                signed_volume_1s[second] += -quantity if is_sell else quantity
            trade_pointer += 1

    rows_seen = 0
    with zipfile.ZipFile(book_path) as archive, archive.open(archive.namelist()[0]) as stream:
        header = stream.readline().rstrip(b"\r\n")
        expected = b"update_id,best_bid_price,best_bid_qty,best_ask_price,best_ask_qty,transaction_time,event_time"
        if header != expected:
            raise ValueError(f"unexpected BBO schema for {symbol} {date}: {header!r}")
        for raw in stream:
            fields = raw.rstrip(b"\r\n").split(b",")
            if len(fields) != 7:
                continue
            event_ms = int(fields[6])
            if last_event >= 0 and (event_ms < last_event or event_ms > last_event + 60_000):
                rejected_timestamp_rows += 1
                continue
            if last_event >= 0 and event_ms > last_event:
                consume_trades(event_ms)
            bid = float(fields[1])
            bid_qty = float(fields[2])
            ask = float(fields[3])
            ask_qty = float(fields[4])
            midpoint = (bid + ask) / 2.0
            bin_number = (event_ms - start_ms) // 10_000
            if 0 <= bin_number < 8_640:
                depth = bid_qty + ask_qty
                quote_count[bin_number] += 1
                spread_sum[bin_number] += 10_000.0 * (ask - bid) / midpoint
                depth_sum[bin_number] += depth
                imbalance_sum[bin_number] += (bid_qty - ask_qty) / max(depth, 1e-12)
                midpoint_last[bin_number] = midpoint
            last_event = event_ms
            last_bid_qty = bid_qty
            last_ask_qty = ask_qty
            rows_seen += 1
            if rows_seen % 10_000_000 == 0:
                print(f"{symbol} {date}: processed {rows_seen:,} BBO rows", flush=True)
    consume_trades(start_ms + 86_400_000)

    valid = quote_count > 0
    index = pd.date_range(date, periods=8_640, freq="10s", tz="UTC")
    frame = pd.DataFrame(index=index)
    frame["symbol"] = symbol
    frame["date"] = date
    frame["rejected_timestamp_rows"] = rejected_timestamp_rows
    frame["midpoint"] = pd.Series(midpoint_last, index=index).ffill().bfill()
    frame["spread_mean"] = np.divide(
        spread_sum, quote_count, out=np.full(8_640, np.nan), where=valid
    )
    depth_mean = np.divide(
        depth_sum, quote_count, out=np.full(8_640, np.nan), where=valid
    )
    frame["depth_mean_60s"] = pd.Series(depth_mean, index=index).rolling(
        6, min_periods=3
    ).mean()
    frame["imbalance_mean"] = np.divide(
        imbalance_sum, quote_count, out=np.full(8_640, np.nan), where=valid
    )
    frame["event_rate"] = quote_count / 10.0
    frame["pressure_max_60s"] = rolling_at_decisions(pressure_1s, "max")
    frame["pressure_rms_60s"] = rolling_at_decisions(pressure_1s, "rms")
    frame["pressure_linf_l2_60s"] = frame["pressure_max_60s"] / frame[
        "pressure_rms_60s"
    ].clip(lower=1e-12)
    frame["trade_volume_60s"] = rolling_at_decisions(volume_1s, "sum")
    signed_60s = rolling_at_decisions(signed_volume_1s, "sum")
    frame["signed_trade_imbalance_60s"] = signed_60s / frame[
        "trade_volume_60s"
    ].clip(lower=1e-12)
    returns = np.log(frame["midpoint"]).diff() * 10_000.0
    frame["realized_vol_60s"] = returns.rolling(6, min_periods=3).std()
    mids = frame["midpoint"].to_numpy(float)
    excursion = np.full(len(frame), np.nan)
    for index_number in range(len(frame) - 6):
        excursion[index_number] = np.max(
            np.abs(np.log(mids[index_number + 1 : index_number + 7] / mids[index_number]))
            * 10_000.0
        )
    frame["future_max_excursion_bps"] = excursion
    print(
        f"{symbol} {date}: {rows_seen:,} accepted BBO rows, {len(trades):,} trades, "
        f"{rejected_timestamp_rows:,} timestamp rows rejected",
        flush=True,
    )
    return frame.replace([np.inf, -np.inf], np.nan)


def model_scores(target: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    return {
        "average_precision": float(average_precision_score(target, probability)),
        "roc_auc": float(roc_auc_score(target, probability)),
        "brier": float(brier_score_loss(target, probability)),
    }


def extract_and_cache(task: tuple[str, str, str]) -> str:
    symbol, date, cache_text = task
    cache = Path(cache_text)
    if not cache.exists():
        panel = extract_day(symbol, date)
        panel.to_parquet(cache)
    return cache_text


def main() -> int:
    daily_dir = OUTPUT / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    tasks = [
        (symbol, date, str(daily_dir / f"{symbol}_{date}.parquet"))
        for symbol in SYMBOLS
        for date in ALL_DATES
    ]
    with ProcessPoolExecutor(max_workers=3) as executor:
        cache_paths = list(executor.map(extract_and_cache, tasks))
    panels = [pd.read_parquet(cache) for cache in cache_paths]
    frame = pd.concat(panels).sort_index().dropna(
        subset=["future_max_excursion_bps", *AUGMENTED]
    )
    train = frame.loc[frame["date"].isin(TRAIN_DATES)].copy()
    validation = frame.loc[frame["date"].isin(VALIDATION_DATES)].copy()
    test = frame.loc[frame["date"].isin(TEST_DATES)].copy()

    ordinary_bounds: dict[str, dict[str, list[float]]] = {}
    thresholds: dict[str, float] = {}
    predictions: dict[str, dict[str, np.ndarray]] = {"baseline": {}, "augmented": {}}
    for symbol in SYMBOLS:
        symbol_train = train.loc[train["symbol"].eq(symbol)]
        symbol_validation = validation.loc[validation["symbol"].eq(symbol)]
        symbol_test = test.loc[test["symbol"].eq(symbol)]
        thresholds[symbol] = float(symbol_train["future_max_excursion_bps"].quantile(0.95))
        ordinary_bounds[symbol] = {
            feature: [
                float(symbol_train[feature].quantile(0.2)),
                float(symbol_train[feature].quantile(0.8)),
            ]
            for feature in ORDINARY
        }
        for name, features in (("baseline", BASELINE), ("augmented", AUGMENTED)):
            fitted = classifier().fit(
                symbol_train[features],
                symbol_train["future_max_excursion_bps"].ge(thresholds[symbol]),
            )
            predictions[name][f"validation_{symbol}"] = fitted.predict_proba(
                symbol_validation[features]
            )[:, 1]
            predictions[name][f"test_{symbol}"] = fitted.predict_proba(symbol_test[features])[
                :, 1
            ]

    metrics: dict[str, dict[str, dict[str, float]]] = {}
    for split_name, split in (("validation", validation), ("test", test)):
        target = np.concatenate(
            [
                split.loc[split["symbol"].eq(symbol), "future_max_excursion_bps"].ge(
                    thresholds[symbol]
                )
                for symbol in SYMBOLS
            ]
        )
        metrics[split_name] = {}
        for name in ("baseline", "augmented"):
            probability = np.concatenate(
                [predictions[name][f"{split_name}_{symbol}"] for symbol in SYMBOLS]
            )
            metrics[split_name][name] = model_scores(target, probability)

    validation_ordinary = []
    test_ordinary = []
    for symbol in SYMBOLS:
        bounds = ordinary_bounds[symbol]
        for source, destination in (
            (validation, validation_ordinary),
            (test, test_ordinary),
        ):
            selected = source.loc[source["symbol"].eq(symbol)].copy()
            mask = np.ones(len(selected), dtype=bool)
            for feature, (low, high) in bounds.items():
                mask &= selected[feature].between(low, high).to_numpy()
            destination.append(selected.loc[mask])
    validation_ordinary_frame = pd.concat(validation_ordinary)
    test_ordinary_frame = pd.concat(test_ordinary)
    low, high = validation_ordinary_frame["pressure_linf_l2_60s"].quantile([0.2, 0.8])

    by_date = {}
    date_deltas = []
    for date, day in test_ordinary_frame.groupby("date"):
        low_values = day.loc[
            day["pressure_linf_l2_60s"].le(low), "future_max_excursion_bps"
        ]
        high_values = day.loc[
            day["pressure_linf_l2_60s"].ge(high), "future_max_excursion_bps"
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
    invalid_holdout_dates = sorted(
        date
        for date in TEST_DATES
        if frame.loc[
            frame["date"].eq(date), "rejected_timestamp_rows"
        ].max()
        > 0
    )
    clean_sensitivity_by_date = {}
    clean_sensitivity_deltas = []
    for date, day in test_ordinary_frame.loc[
        ~test_ordinary_frame["date"].isin(invalid_holdout_dates)
    ].groupby("date"):
        low_values = day.loc[
            day["pressure_linf_l2_60s"].le(low), "future_max_excursion_bps"
        ]
        high_values = day.loc[
            day["pressure_linf_l2_60s"].ge(high), "future_max_excursion_bps"
        ]
        eligible = len(low_values) >= 20 and len(high_values) >= 20
        delta = float(high_values.mean() - low_values.mean())
        if eligible:
            clean_sensitivity_deltas.append(delta)
        clean_sensitivity_by_date[date] = {
            "high_minus_low_excursion_bps": delta,
            "low_bins": len(low_values),
            "high_bins": len(high_values),
            "minimum_cell_count_met": eligible,
        }
    clean_sensitivity = block_bootstrap_mean(clean_sensitivity_deltas, 20260913)
    clean_sensitivity["by_date"] = clean_sensitivity_by_date
    clean_sensitivity["inference_usable"] = len(clean_sensitivity_deltas) >= 3
    if not clean_sensitivity["inference_usable"]:
        clean_sensitivity["block_bootstrap_95pct_ci"] = [None, None]
    test_baseline = metrics["test"]["baseline"]
    test_augmented = metrics["test"]["augmented"]
    ap_improvement = test_augmented["average_precision"] - test_baseline["average_precision"]
    brier_improvement = test_baseline["brier"] - test_augmented["brier"]
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
        "status": "free_experiment_not_live_trading_approval",
        "hypotheses": [1, 2],
        "paid_requests_made": False,
        "symbols": SYMBOLS,
        "dates": {
            "training": TRAIN_DATES,
            "validation": VALIDATION_DATES,
            "holdout": TEST_DATES,
        },
        "rows": {
            "training": len(train),
            "validation": len(validation),
            "holdout": len(test),
            "validation_ordinary": len(validation_ordinary_frame),
            "holdout_ordinary": len(test_ordinary_frame),
        },
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
        "symbol_jump_threshold_bps": thresholds,
        "ordinary_state_training_bounds": ordinary_bounds,
        "validation_signal_cutoffs": {"low_20pct": float(low), "high_80pct": float(high)},
        "metrics": metrics,
        "test_incremental": {
            "average_precision": ap_improvement,
            "brier_improvement": brier_improvement,
            "roc_auc": test_augmented["roc_auc"] - test_baseline["roc_auc"],
        },
        "ordinary_state_concentration_effect": effect,
        "data_quality": {
            "invalid_holdout_dates": invalid_holdout_dates,
            "confirmatory_interpretation_valid": not invalid_holdout_dates,
            "reason": "one or more symbols had timestamp rows rejected by the frozen monotonicity guard",
        },
        "posthoc_clean_minimum_cell_sensitivity": clean_sensitivity,
        "primary_gate_passed": primary,
        "verdict": "H1_H2_REPLICATED" if primary else "H1_H2_FAILED",
        "claim_limit": "BBO and aggregate trades only; no L2/L3 cancellation, queue, latency, fees, or live execution claim",
    }
    (OUTPUT / "results.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
