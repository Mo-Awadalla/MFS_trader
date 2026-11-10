"""Multi-day conservative touch-fill adverse-selection and model-error study."""

from __future__ import annotations

import json
import math
import zipfile
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline

from research.market_making import passive_markout_bps, touch_fill_side
from research.model_breakdown import block_bootstrap_mean

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "research_scout" / "navier_stokes_liquidity_v2"
DATA = BASE / "free_data" / "binance-public" / "futures-um"
OUTPUT = BASE / "multiday_market_making_results"
TRAIN_DATES = ["2023-08-15", "2023-09-15", "2023-10-15", "2023-11-15"]
VALIDATION_DATES = ["2023-12-15", "2024-01-15"]
TEST_DATES = ["2024-02-15", "2024-03-15"]
ALL_DATES = TRAIN_DATES + VALIDATION_DATES + TEST_DATES
HORIZONS_MS = (1_000, 10_000, 60_000)
CONVENTIONAL = [
    "spread_mean",
    "depth_mean",
    "imbalance_mean",
    "realized_vol_60s",
    "trade_volume",
    "signed_trade_imbalance",
]
BREAKDOWN = [
    "spread_last",
    "depth_min",
    "depth_last",
    "imbalance_last",
    "event_rate",
    "event_linf_l2",
    "spectral_cascade_ratio",
    "inverse_interevent",
    "depth_change",
    "gross_to_net_trade",
    "opposing_trade_stress",
]


def model() -> Pipeline:
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


def extract_day(date: str, symbol: str = "BTCUSDT") -> pd.DataFrame:
    day = DATA / symbol / date
    book_path = day / f"{symbol}-bookTicker-{date}.zip"
    trade_path = day / f"{symbol}-aggTrades-{date}.zip"
    trades = pd.read_csv(
        trade_path,
        compression="zip",
        usecols=["price", "quantity", "transact_time", "is_buyer_maker"],
    ).sort_values("transact_time")
    trade_time = trades["transact_time"].to_numpy(np.int64)
    trade_price = trades["price"].to_numpy(float)
    trade_quantity = trades["quantity"].to_numpy(float)
    buyer_maker = trades["is_buyer_maker"].astype(bool).to_numpy()
    start_ms = int(pd.Timestamp(date, tz="UTC").value // 1_000_000)

    count = np.zeros(8_640, dtype=np.int64)
    spread_sum = np.zeros(8_640)
    depth_sum = np.zeros(8_640)
    imbalance_sum = np.zeros(8_640)
    depth_min = np.full(8_640, np.inf)
    spread_last = np.full(8_640, np.nan)
    depth_last = np.full(8_640, np.nan)
    imbalance_last = np.full(8_640, np.nan)
    midpoint_last = np.full(8_640, np.nan)
    subcounts = np.zeros((8_640, 100), dtype=np.int32)

    fill_time: list[int] = []
    fill_side: list[int] = []
    fill_price: list[float] = []
    markouts: dict[int, list[float]] = {horizon: [] for horizon in HORIZONS_MS}
    pending: dict[int, deque[tuple[int, int]]] = {horizon: deque() for horizon in HORIZONS_MS}
    trade_pointer = 0
    last_event = -1
    last_bid = math.nan
    last_ask = math.nan
    rejected_timestamp_rows = 0

    def qualify_until(before_ms: int) -> None:
        nonlocal trade_pointer
        while trade_pointer < len(trades) and trade_time[trade_pointer] < before_ms:
            side = touch_fill_side(
                trade_price[trade_pointer],
                bool(buyer_maker[trade_pointer]),
                last_bid,
                last_ask,
            )
            if side:
                index = len(fill_time)
                fill_time.append(int(trade_time[trade_pointer]))
                fill_side.append(side)
                fill_price.append(last_bid if side == 1 else last_ask)
                for horizon in HORIZONS_MS:
                    markouts[horizon].append(math.nan)
                    pending[horizon].append((int(trade_time[trade_pointer] + horizon), index))
            trade_pointer += 1

    rows_seen = 0
    with zipfile.ZipFile(book_path) as archive, archive.open(archive.namelist()[0]) as stream:
        header = stream.readline().rstrip(b"\r\n")
        expected = b"update_id,best_bid_price,best_bid_qty,best_ask_price,best_ask_qty,transaction_time,event_time"
        if header != expected:
            raise ValueError(f"unexpected BBO schema for {date}: {header!r}")
        for raw in stream:
            fields = raw.rstrip(b"\r\n").split(b",")
            if len(fields) != 7:
                continue
            event_ms = int(fields[6])
            bid, bid_qty = float(fields[1]), float(fields[2])
            ask, ask_qty = float(fields[3]), float(fields[4])
            midpoint = (bid + ask) / 2.0
            if last_event >= 0 and (event_ms < last_event or event_ms > last_event + 60_000):
                rejected_timestamp_rows += 1
                continue
            if last_event >= 0 and event_ms > last_event:
                qualify_until(event_ms)
            for horizon in HORIZONS_MS:
                queue = pending[horizon]
                while queue and queue[0][0] <= event_ms:
                    _, fill_index = queue.popleft()
                    markouts[horizon][fill_index] = passive_markout_bps(
                        fill_price[fill_index], midpoint, fill_side[fill_index]
                    )
            bin_number = (event_ms - start_ms) // 10_000
            if 0 <= bin_number < 8_640:
                spread = 10_000.0 * (ask - bid) / midpoint
                depth = bid_qty + ask_qty
                imbalance = (bid_qty - ask_qty) / max(depth, 1e-12)
                count[bin_number] += 1
                spread_sum[bin_number] += spread
                depth_sum[bin_number] += depth
                imbalance_sum[bin_number] += imbalance
                depth_min[bin_number] = min(depth_min[bin_number], depth)
                spread_last[bin_number] = spread
                depth_last[bin_number] = depth
                imbalance_last[bin_number] = imbalance
                midpoint_last[bin_number] = midpoint
                sub = min(99, (event_ms % 10_000) // 100)
                subcounts[bin_number, sub] += 1
            last_event, last_bid, last_ask = event_ms, bid, ask
            rows_seen += 1
            if rows_seen % 10_000_000 == 0:
                print(f"{date}: processed {rows_seen:,} BBO rows", flush=True)

    valid_bins = count > 0
    index = pd.date_range(date, periods=8_640, freq="10s", tz="UTC")
    panel = pd.DataFrame(index=index)
    panel["date"] = date
    panel["rejected_timestamp_rows"] = rejected_timestamp_rows
    panel["midpoint"] = pd.Series(midpoint_last, index=index).ffill().bfill()
    panel["spread_mean"] = np.divide(spread_sum, count, out=np.full(8_640, np.nan), where=valid_bins)
    panel["depth_mean"] = np.divide(depth_sum, count, out=np.full(8_640, np.nan), where=valid_bins)
    panel["imbalance_mean"] = np.divide(imbalance_sum, count, out=np.full(8_640, np.nan), where=valid_bins)
    panel["spread_last"] = spread_last
    panel["depth_min"] = np.where(valid_bins, depth_min, np.nan)
    panel["depth_last"] = depth_last
    panel["imbalance_last"] = imbalance_last
    panel["event_rate"] = count / 10.0
    event_l2 = np.sqrt(np.mean(subcounts.astype(float) ** 2, axis=1))
    panel["event_linf_l2"] = np.divide(
        subcounts.max(axis=1), event_l2, out=np.zeros(8_640), where=event_l2 > 0
    )
    centered = subcounts - subcounts.mean(axis=1, keepdims=True)
    power = np.abs(np.fft.rfft(centered, axis=1)) ** 2
    frequency = np.fft.rfftfreq(100, d=0.1)
    high_power = power[:, (frequency >= 1.0) & (frequency <= 5.0)].sum(axis=1)
    low_power = power[:, (frequency >= 0.1) & (frequency < 1.0)].sum(axis=1)
    panel["spectral_cascade_ratio"] = high_power / np.maximum(low_power, 1e-12)
    panel["inverse_interevent"] = count / 10_000.0
    panel["mid_return_bps"] = np.log(panel["midpoint"]).diff() * 10_000.0
    panel["realized_vol_60s"] = panel["mid_return_bps"].rolling(6, min_periods=2).std()
    panel["depth_change"] = panel["depth_last"].pct_change()

    trade_bins = ((trade_time - start_ms) // 10_000).astype(int)
    valid_trade = (trade_bins >= 0) & (trade_bins < 8_640)
    signed_trade = np.where(buyer_maker, -trade_quantity, trade_quantity)
    gross = np.bincount(trade_bins[valid_trade], weights=trade_quantity[valid_trade], minlength=8_640)
    signed = np.bincount(trade_bins[valid_trade], weights=signed_trade[valid_trade], minlength=8_640)
    buys = np.bincount(
        trade_bins[valid_trade],
        weights=np.where(~buyer_maker[valid_trade], trade_quantity[valid_trade], 0.0),
        minlength=8_640,
    )
    sells = gross - buys
    panel["trade_volume"] = gross
    panel["signed_trade_imbalance"] = signed / np.maximum(gross, 1e-12)
    panel["gross_to_net_trade"] = gross / (np.abs(signed) + 1.0)
    panel["opposing_trade_stress"] = np.sqrt(buys * sells) / np.maximum(panel["depth_last"], 1e-12)

    fills = pd.DataFrame(
        {
            "bin": ((np.asarray(fill_time, dtype=np.int64) - start_ms) // 10_000).astype(int),
            "markout_1s": markouts[1_000],
            "markout_10s": markouts[10_000],
            "markout_60s": markouts[60_000],
        }
    )
    fills = fills.loc[fills["bin"].between(0, 8_639)].dropna(subset=["markout_10s"])
    fill_bins = fills.groupby("bin").agg(
        hypothetical_fill_count=("markout_10s", "size"),
        mean_markout_1s=("markout_1s", "mean"),
        mean_markout_10s=("markout_10s", "mean"),
        mean_markout_60s=("markout_60s", "mean"),
        negative_markout_rate_10s=("markout_10s", lambda values: float(values.lt(0).mean())),
    )
    fill_bins.index = index[fill_bins.index.to_numpy(int)]
    panel = panel.join(fill_bins, how="left")
    print(
        f"{date}: {rows_seen:,} BBO rows, {len(trades):,} aggregate trades, "
        f"{len(fills):,} touch-qualified observations, "
        f"{rejected_timestamp_rows:,} timestamp rows rejected",
        flush=True,
    )
    return panel.replace([np.inf, -np.inf], np.nan)


def clustered_effect(frame: pd.DataFrame, low: float, high: float) -> dict[str, object]:
    deltas = []
    by_date = {}
    for date, day in frame.groupby("date"):
        low_values = day.loc[day["critical_score"].le(low), "mean_markout_10s"]
        high_values = day.loc[day["critical_score"].ge(high), "mean_markout_10s"]
        delta = float(high_values.mean() - low_values.mean())
        deltas.append(delta)
        by_date[date] = {
            "high_minus_low_markout_bps": delta,
            "low_bins": len(low_values),
            "high_bins": len(high_values),
        }
    result = block_bootstrap_mean(deltas, 20260913)
    result["by_date"] = by_date
    return result


def lagged_residual_effect(
    validation: pd.DataFrame,
    test: pd.DataFrame,
    validation_prediction: np.ndarray,
    test_prediction: np.ndarray,
) -> dict[str, object]:
    combined = pd.concat([validation, test])
    residual = pd.Series(
        np.abs(
            combined["mean_markout_10s"].to_numpy(float)
            - np.r_[validation_prediction, test_prediction]
        ),
        index=combined.index,
    )
    past_observable = residual.groupby(combined["date"]).transform(
        lambda values: values.shift(1).rolling(6, min_periods=3).mean()
    )
    validation_signal = past_observable.iloc[: len(validation)].dropna()
    low, high = float(validation_signal.quantile(0.2)), float(validation_signal.quantile(0.8))
    scored = test.copy()
    scored["critical_score"] = past_observable.iloc[len(validation) :]
    result = clustered_effect(scored.dropna(subset=["critical_score"]), low, high)
    result["validation_low_cutoff"] = low
    result["validation_high_cutoff"] = high
    result["supported"] = bool(
        result["block_bootstrap_95pct_ci"][1] is not None
        and result["block_bootstrap_95pct_ci"][1] < 0
    )
    return result


def main() -> int:
    daily_dir = OUTPUT / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    panels = []
    for date in ALL_DATES:
        cache_name = f"{date}_timestamp_guard.parquet" if date == "2024-02-15" else f"{date}.parquet"
        cache = daily_dir / cache_name
        if cache.exists():
            panel = pd.read_parquet(cache)
            if "rejected_timestamp_rows" not in panel:
                panel["rejected_timestamp_rows"] = 0
        else:
            panel = extract_day(date)
            panel.to_parquet(cache)
        panels.append(panel)
    frame = pd.concat(panels).sort_index()
    usable = frame.dropna(subset=["mean_markout_10s"])
    train = usable.loc[usable["date"].isin(TRAIN_DATES)]
    validation = usable.loc[usable["date"].isin(VALIDATION_DATES)]
    test = usable.loc[usable["date"].isin(TEST_DATES)]
    conventional = model().fit(train[CONVENTIONAL], train["mean_markout_10s"])
    breakdown = model().fit(train[CONVENTIONAL + BREAKDOWN], train["mean_markout_10s"])
    predictions = {}
    metrics = {}
    for name, split in (("validation", validation), ("test", test)):
        regular_prediction = conventional.predict(split[CONVENTIONAL])
        breakdown_prediction = breakdown.predict(split[CONVENTIONAL + BREAKDOWN])
        critical_score = regular_prediction - breakdown_prediction
        predictions[name] = (regular_prediction, breakdown_prediction, critical_score)
        metrics[name] = {
            "conventional_mae": float(mean_absolute_error(split["mean_markout_10s"], regular_prediction)),
            "breakdown_mae": float(mean_absolute_error(split["mean_markout_10s"], breakdown_prediction)),
            "actual_mean_markout_bps": float(split["mean_markout_10s"].mean()),
            "actual_negative_markout_rate": float(split["mean_markout_10s"].lt(0).mean()),
        }
    low, high = np.quantile(predictions["validation"][2], [0.2, 0.8])
    scored_test = test.copy()
    scored_test["critical_score"] = predictions["test"][2]
    primary_effect = clustered_effect(scored_test, float(low), float(high))
    regular_error = np.abs(test["mean_markout_10s"].to_numpy() - predictions["test"][0])
    error_frame = scored_test.copy()
    error_frame["mean_markout_10s"] = regular_error
    error_effect = clustered_effect(error_frame, float(low), float(high))
    h47_effect = lagged_residual_effect(
        validation,
        test,
        predictions["validation"][0],
        predictions["test"][0],
    )
    regular_mae = metrics["test"]["conventional_mae"]
    breakdown_mae = metrics["test"]["breakdown_mae"]
    mae_improvement = (regular_mae - breakdown_mae) / regular_mae
    date_deltas = [entry["high_minus_low_markout_bps"] for entry in primary_effect["by_date"].values()]
    interval = primary_effect["block_bootstrap_95pct_ci"]
    primary = bool(
        interval[1] is not None
        and interval[1] < 0
        and mae_improvement >= 0.05
        and all(delta < 0 for delta in date_deltas)
    )
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "exploratory_touch_fill_adverse_selection_not_live_execution_approval",
        "hypotheses": [46, 47, 50, 76],
        "paid_requests_made": False,
        "dates": {"training": TRAIN_DATES, "validation": VALIDATION_DATES, "holdout": TEST_DATES},
        "rows": {"all_fill_bins": len(usable), "training": len(train), "validation": len(validation), "holdout": len(test)},
        "timestamp_rows_rejected_by_date": {
            date: int(frame.loc[frame["date"].eq(date), "rejected_timestamp_rows"].max())
            for date in ALL_DATES
        },
        "metrics": metrics,
        "breakdown_relative_mae_improvement": mae_improvement,
        "validation_critical_score_cutoffs": {"low_20pct": float(low), "high_80pct": float(high)},
        "holdout_high_minus_low_markout": primary_effect,
        "holdout_high_minus_low_conventional_absolute_error": error_effect,
        "h47_lagged_observable_residual_markout_test": h47_effect,
        "primary_gate_passed": primary,
        "verdict": "MULTIDAY_ADVERSE_SELECTION_CANDIDATE_REQUIRES_EXECUTION_DATA" if primary else "MULTIDAY_TOUCH_FILL_HYPOTHESIS_FAILED",
        "claim_limit": "touch-qualified hypothetical fills only; queue position, fill probability, fees, rebates and latency are not modeled",
    }
    (OUTPUT / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
