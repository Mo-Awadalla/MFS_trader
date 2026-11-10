"""Frozen exploratory BBO withdrawal and aggressive-flow test."""

from __future__ import annotations

import argparse
import json
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research_scout.audit_btc_microstructure_admission import ARCHIVES, ROOT


SPEC_PATH = ROOT / "research_scout" / "btc_withdrawal_aggression_prereg_20260925.json"
ADMISSION_PATH = ROOT / "research_scout" / "btc_microstructure_admission_20260925.json"
OUTPUT = ROOT / "research_scout" / "btc_withdrawal_aggression_v1"
BASELINE = [
    "prior_mid_return_30s",
    "prior_abs_mid_return_60s",
    "current_spread_bps",
    "log_current_touch_depth",
    "current_depth_imbalance",
    "log_30s_taker_notional",
    "log_30s_book_update_count",
]
WITHDRAWAL = ["negative_log_touch_depth_change_30s", "spread_change_bps_30s"]
AGGRESSION = ["signed_taker_notional_imbalance_30s"]
SECONDS = 86_400


def zip_stream(path: Path):
    archive = zipfile.ZipFile(path)
    name = archive.namelist()[0]
    return archive, archive.open(name)


def book_seconds(day: str) -> dict[str, np.ndarray]:
    path = ARCHIVES / day / f"BTCUSDT-bookTicker-{day}.zip"
    start = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)
    columns = {name: np.full(SECONDS, np.nan, dtype=np.float64) for name in ("bid", "ask", "bid_qty", "ask_qty")}
    event_ms = np.full(SECONDS, -1, dtype=np.int64)
    count = np.zeros(SECONDS, dtype=np.int64)
    archive, stream = zip_stream(path)
    with archive, stream:
        expected = b"update_id,best_bid_price,best_bid_qty,best_ask_price,best_ask_qty,transaction_time,event_time"
        if stream.readline().rstrip(b"\r\n") != expected:
            raise ValueError(f"unexpected BBO schema on {day}")
        for raw in stream:
            fields = raw.rstrip(b"\r\n").split(b",")
            timestamp = int(fields[6])
            second = (timestamp - start) // 1000
            if 0 <= second < SECONDS:
                columns["bid"][second] = float(fields[1])
                columns["bid_qty"][second] = float(fields[2])
                columns["ask"][second] = float(fields[3])
                columns["ask_qty"][second] = float(fields[4])
                event_ms[second] = timestamp
                count[second] += 1
    latest = np.maximum.accumulate(np.where(event_ms >= 0, np.arange(SECONDS), -1))
    valid = latest >= 0
    for name, values in columns.items():
        expanded = np.full(SECONDS, np.nan)
        expanded[valid] = values[latest[valid]]
        columns[name] = expanded
    expanded_event = np.full(SECONDS, -1, dtype=np.int64)
    expanded_event[valid] = event_ms[latest[valid]]
    columns["event_ms"] = expanded_event
    columns["count"] = count
    return columns


def trade_seconds(day: str) -> dict[str, np.ndarray]:
    path = ARCHIVES / day / f"BTCUSDT-aggTrades-{day}.zip"
    frame = pd.read_csv(path, compression="zip")
    start = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)
    second = ((frame["transact_time"].to_numpy(np.int64) - start) // 1000).astype(np.int64)
    valid = (second >= 0) & (second < SECONDS)
    second = second[valid]
    notional = frame["price"].to_numpy(float)[valid] * frame["quantity"].to_numpy(float)[valid]
    buyer_maker = frame["is_buyer_maker"].to_numpy(bool)[valid]
    signed = np.where(buyer_maker, -notional, notional)
    return {
        "notional": np.bincount(second, weights=notional, minlength=SECONDS),
        "signed": np.bincount(second, weights=signed, minlength=SECONDS),
    }


def window_sums(values: np.ndarray, end: np.ndarray, length: int) -> np.ndarray:
    cumulative = np.concatenate(([0.0], np.cumsum(values, dtype=np.float64)))
    return cumulative[end] - cumulative[end - length]


def build_day(day: str) -> tuple[str, int]:
    book = book_seconds(day)
    trade = trade_seconds(day)
    t = np.arange(120, 86_340, 60, dtype=np.int64)  # 00:02 through 23:58 inclusive

    def quote(second: np.ndarray) -> tuple[np.ndarray, ...]:
        idx = second - 1  # state strictly before the integer-second decision
        bid, ask = book["bid"][idx], book["ask"][idx]
        bid_qty, ask_qty = book["bid_qty"][idx], book["ask_qty"][idx]
        age = (second * 1000 + int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000) - book["event_ms"][idx]) / 1000
        return bid, ask, bid_qty, ask_qty, age

    b, a, bq, aq, age = quote(t)
    b30, a30, bq30, aq30, age30 = quote(t - 30)
    b60, a60, _, _, age60 = quote(t - 60)
    bf, af, _, _, agef = quote(t + 60)
    be, ae, _, _, agee = quote(t + 1)
    bx, ax, _, _, agex = quote(t + 61)
    mid, mid30, mid60, midf = (b + a) / 2, (b30 + a30) / 2, (b60 + a60) / 2, (bf + af) / 2
    depth, depth30 = bq + aq, bq30 + aq30
    spread = (a - b) / mid * 10_000
    spread30 = (a30 - b30) / mid30 * 10_000
    volume = window_sums(trade["notional"], t, 30)
    signed = window_sums(trade["signed"], t, 30)
    quote_count = window_sums(book["count"], t, 30)
    with np.errstate(divide="ignore", invalid="ignore"):
        panel = pd.DataFrame({
            "date": day,
            "second": t,
            "prior_mid_return_30s": np.log(mid / mid30) * 10_000,
            "prior_abs_mid_return_60s": np.abs(np.log(mid / mid60)) * 10_000,
            "current_spread_bps": spread,
            "log_current_touch_depth": np.log(depth),
            "current_depth_imbalance": (bq - aq) / depth,
            "log_30s_taker_notional": np.log1p(volume),
            "log_30s_book_update_count": np.log1p(quote_count),
            "negative_log_touch_depth_change_30s": -np.log(depth / depth30),
            "spread_change_bps_30s": spread - spread30,
            "signed_taker_notional_imbalance_30s": np.divide(signed, volume, out=np.zeros_like(signed), where=volume > 0),
            "future_return_bps": np.log(midf / mid) * 10_000,
            "future_abs_return_bps": np.abs(np.log(midf / mid)) * 10_000,
            "entry_buy": ae,
            "entry_sell": be,
            "exit_buy": bx,
            "exit_sell": ax,
            "quote_age_decision_s": age,
            "quote_age_entry_s": agee,
            "quote_age_exit_s": agex,
        })
    fresh = np.maximum.reduce([age, age30, age60, agef, agee, agex]) <= 1.0
    fresh &= np.minimum.reduce([age, age30, age60, agef, agee, agex]) >= 0.0
    features = BASELINE + WITHDRAWAL + AGGRESSION
    finite = np.isfinite(panel[features + ["future_return_bps", "entry_buy", "entry_sell", "exit_buy", "exit_sell"]]).all(axis=1)
    panel = panel.loc[fresh & finite].copy()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(OUTPUT / f"panel_{day}.parquet", index=False)
    return day, len(panel)


def model(columns: list[str]):
    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000, random_state=19))


def date_metric(frame: pd.DataFrame, target: str, baseline: str, augmented: str, metric) -> dict:
    return {
        day: {
            "n": len(group),
            "baseline": float(metric(group[target], group[baseline])) if group[target].nunique() == 2 else None,
            "augmented": float(metric(group[target], group[augmented])) if group[target].nunique() == 2 else None,
        }
        for day, group in frame.groupby("date")
    }


def evaluate(spec: dict, panels: pd.DataFrame) -> dict:
    train = panels[panels["date"].isin(spec["splits"]["train"])].copy()
    threshold = float(train["future_abs_return_bps"].quantile(0.9))
    panels = panels.copy()
    panels["jump"] = (panels["future_abs_return_bps"] > threshold).astype(int)
    panels["up"] = (panels["future_return_bps"] > 0).astype(int)
    result = {"jump_threshold_bps_train_only": threshold, "models": {}}

    for name, target, extra in (("withdrawal", "jump", WITHDRAWAL), ("aggression", "up", AGGRESSION)):
        base = model(BASELINE)
        plus = model(BASELINE + extra)
        eligible = panels if name == "withdrawal" else panels[panels["future_return_bps"] != 0]
        fit = eligible[eligible["date"].isin(spec["splits"]["train"])]
        base.fit(fit[BASELINE], fit[target])
        plus.fit(fit[BASELINE + extra], fit[target])
        sections = {}
        for split_name, dates in spec["splits"].items():
            section = eligible[eligible["date"].isin(dates)].copy()
            section["base_probability"] = base.predict_proba(section[BASELINE])[:, 1]
            section["plus_probability"] = plus.predict_proba(section[BASELINE + extra])[:, 1]
            metric = average_precision_score if name == "withdrawal" else roc_auc_score
            base_score = float(metric(section[target], section["base_probability"]))
            plus_score = float(metric(section[target], section["plus_probability"]))
            by_date = date_metric(section, target, "base_probability", "plus_probability", metric)
            positive_dates = sum(
                d["baseline"] is not None and d["augmented"] is not None and d["augmented"] > d["baseline"]
                for d in by_date.values()
            )
            summary = {
                "rows": len(section),
                "dates": len(by_date),
                "base_metric": base_score,
                "augmented_metric": plus_score,
                "metric_increment": plus_score - base_score,
                "base_brier": float(brier_score_loss(section[target], section["base_probability"])),
                "augmented_brier": float(brier_score_loss(section[target], section["plus_probability"])),
                "positive_date_increments": positive_dates,
                "by_date": by_date,
            }
            if name == "aggression":
                direction = np.where(section["plus_probability"].to_numpy() >= 0.5, 1.0, -1.0)
                entry = np.where(direction > 0, section["entry_buy"], section["entry_sell"])
                exit_ = np.where(direction > 0, section["exit_buy"], section["exit_sell"])
                gross = direction * (exit_ - entry) / entry * 10_000
                summary["execution"] = {
                    "mean_crossing_bps": float(np.mean(gross)),
                    "mean_after_5bps_per_side": float(np.mean(gross - 10)),
                    "mean_after_extra_5bps_per_side": float(np.mean(gross - 20)),
                    "positive_net_dates": int(sum(np.mean(gross[section["date"].to_numpy() == day] - 10) > 0 for day in by_date)),
                }
            sections[split_name] = summary
        test = sections["historical_test"]
        gate = (
            test["metric_increment"] > (0.02 if name == "withdrawal" else 0.01)
            and test["augmented_brier"] <= test["base_brier"]
            and test["positive_date_increments"] >= 6
        )
        result["models"][name] = {"metric": "average_precision" if name == "withdrawal" else "roc_auc", "sections": sections, "pass_gate": bool(gate)}
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    admission = json.loads(ADMISSION_PATH.read_text(encoding="utf-8"))
    dates = [day for split in spec["splits"].values() for day in split]
    assert len(dates) == len(set(dates)) == 17
    for day in dates:
        row = admission["dates"][day]
        assert row["archives"]["bookTicker"]["event_backtracks"] == 0
        assert row["archives"]["bookTicker"]["id_nonincreasing"] == 0
        assert row["archives"]["bookTicker"]["checksum_matches"]
        assert row["archives"]["aggTrades"]["checksum_matches"]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    missing = [day for day in dates if args.rebuild or not (OUTPUT / f"panel_{day}.parquet").exists()]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(build_day, day): day for day in missing}
        for future in as_completed(futures):
            day, count = future.result()
            print(f"built {day}: {count} eligible decisions", flush=True)
    panels = pd.concat([pd.read_parquet(OUTPUT / f"panel_{day}.parquet") for day in dates], ignore_index=True)
    results = evaluate(spec, panels)
    results["source"] = {
        "specification": str(SPEC_PATH),
        "admission": str(ADMISSION_PATH),
        "rows_total": len(panels),
        "eligible_rows_by_date": {day: int((panels["date"] == day).sum()) for day in dates},
        "historical_test_is_pristine": False,
    }
    (OUTPUT / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    for name, result in results["models"].items():
        test = result["sections"]["historical_test"]
        print(f"{name}: increment={test['metric_increment']:.5f}, pass={result['pass_gate']}", flush=True)


if __name__ == "__main__":
    main()
