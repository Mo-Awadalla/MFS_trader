"""Build the frozen daily feature table for the ES close-flow hypothesis.

This is mechanical preprocessing only. It does not calculate performance
summaries or optimize parameters. The 2024-2025 holdout can therefore remain
unexamined until the separate evaluation command is run.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, time
from pathlib import Path
from typing import Any

VENDOR_DIR = Path(__file__).resolve().parents[1] / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

NY = "America/New_York"
TICK_SIZE = 0.25
MES_MULTIPLIER = 5.0
ROUND_TRIP_COMMISSION_USD = 1.24


def _bar_features(path: Path) -> pd.DataFrame:
    frame = db.read_dbn(path).to_df()
    local = pd.DatetimeIndex(frame.index).tz_convert(NY)
    frame = frame.assign(
        session_date=local.date,
        clock=local.time,
    )
    rth = frame[
        (frame["clock"] >= time(9, 30)) & (frame["clock"] < time(16, 0))
    ].copy()

    rows: list[dict[str, Any]] = []
    for session_date, group in rth.groupby("session_date", sort=True):
        opening = group[group["clock"] == time(9, 30)]
        preclose = group[group["clock"] == time(15, 29)]
        rows.append(
            {
                "date": str(session_date),
                "rth_bar_count": int(len(group)),
                "rth_open": (
                    float(opening.iloc[0]["open"]) if len(opening) == 1 else np.nan
                ),
                "preclose_price": (
                    float(preclose.iloc[0]["close"])
                    if len(preclose) == 1
                    else np.nan
                ),
                "bar_instrument_ids": sorted(
                    int(value) for value in group["instrument_id"].unique()
                ),
            }
        )
    result = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    result["rth_return"] = result["preclose_price"] / result["rth_open"] - 1.0
    return result


def _trade_features(path: Path) -> dict[str, Any]:
    frame = db.read_dbn(path).to_df()
    if frame.empty:
        return {
            "trade_rows": 0,
            "buy_volume": 0,
            "sell_volume": 0,
            "signed_volume": 0,
            "total_trade_volume": 0,
            "trade_instrument_ids": [],
            "trade_sides": [],
        }
    sides = frame["side"].astype(str)
    buy_volume = int(frame.loc[sides.eq("B"), "size"].sum())
    sell_volume = int(frame.loc[sides.eq("A"), "size"].sum())
    return {
        "trade_rows": int(len(frame)),
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "signed_volume": buy_volume - sell_volume,
        "total_trade_volume": buy_volume + sell_volume,
        "trade_instrument_ids": sorted(
            int(value) for value in frame["instrument_id"].unique()
        ),
        "trade_sides": sorted(sides.unique().tolist()),
    }


def _quote_features(path: Path, prefix: str, boundary: pd.Timestamp) -> dict[str, Any]:
    frame = db.read_dbn(path).to_df()
    if frame.empty:
        return {
            f"{prefix}_rows": 0,
            f"{prefix}_ts": None,
            f"{prefix}_delay_ms": np.nan,
            f"{prefix}_bid": np.nan,
            f"{prefix}_ask": np.nan,
            f"{prefix}_bid_size": np.nan,
            f"{prefix}_ask_size": np.nan,
            f"{prefix}_spread": np.nan,
            f"{prefix}_instrument_ids": [],
        }
    row = frame.iloc[0]
    timestamp = pd.Timestamp(frame.index[0])
    return {
        f"{prefix}_rows": int(len(frame)),
        f"{prefix}_ts": timestamp.isoformat(),
        f"{prefix}_delay_ms": float((timestamp - boundary).total_seconds() * 1000),
        f"{prefix}_bid": float(row["bid_px_00"]),
        f"{prefix}_ask": float(row["ask_px_00"]),
        f"{prefix}_bid_size": int(row["bid_sz_00"]),
        f"{prefix}_ask_size": int(row["ask_sz_00"]),
        f"{prefix}_spread": float(row["ask_px_00"] - row["bid_px_00"]),
        f"{prefix}_instrument_ids": sorted(
            int(value) for value in frame["instrument_id"].unique()
        ),
    }


def _extract_day(root: Path, value: str) -> dict[str, Any]:
    day = date.fromisoformat(value)
    day_root = root / "sessions" / str(day.year) / value
    entry_boundary = pd.Timestamp(value, tz=NY) + pd.Timedelta(
        hours=15, minutes=30, seconds=5
    )
    exit_boundary = pd.Timestamp(value, tz=NY) + pd.Timedelta(
        hours=15, minutes=59, seconds=45
    )
    result = {"date": value}
    result.update(_trade_features(day_root / "es_trades.dbn.zst"))
    result.update(
        _quote_features(
            day_root / "mes_entry_mbp1.dbn.zst",
            "entry",
            entry_boundary.tz_convert("UTC"),
        )
    )
    result.update(
        _quote_features(
            day_root / "mes_exit_mbp1.dbn.zst",
            "exit",
            exit_boundary.tz_convert("UTC"),
        )
    )
    return result


def _scalar_id(values: Any) -> int | None:
    if isinstance(values, np.ndarray):
        values = values.tolist()
    return int(values[0]) if len(values) == 1 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    bar_path = Path(audit["bars"]["path"])
    bars = _bar_features(bar_path)
    degraded = set(audit["weekday_degraded_exclusions"])
    bars["short_session"] = bars["rth_bar_count"].ne(390)
    bars["degraded"] = bars["date"].isin(degraded)
    bars["mechanically_eligible"] = (
        ~bars["short_session"]
        & ~bars["degraded"]
        & bars["rth_open"].notna()
        & bars["preclose_price"].notna()
    )
    bars["same_clock_sigma60"] = np.nan
    eligible_returns = bars.loc[bars["mechanically_eligible"], "rth_return"]
    bars.loc[bars["mechanically_eligible"], "same_clock_sigma60"] = (
        eligible_returns.rolling(60, min_periods=60).std(ddof=1).shift(1)
    )
    eligible_dates = bars.loc[bars["mechanically_eligible"], "date"].tolist()

    daily_rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_extract_day, args.root, value): value
            for value in eligible_dates
        }
        for index, future in enumerate(as_completed(futures), start=1):
            daily_rows.append(future.result())
            if index % 100 == 0 or index == len(futures):
                print(f"built {index}/{len(futures)} eligible sessions", flush=True)
    microstructure = pd.DataFrame(daily_rows)
    features = bars.merge(microstructure, on="date", how="left", validate="one_to_one")

    features["bar_instrument_id"] = features["bar_instrument_ids"].map(_scalar_id)
    features["trade_instrument_id"] = features["trade_instrument_ids"].map(
        lambda values: _scalar_id(values) if isinstance(values, (list, np.ndarray)) else None
    )
    features["entry_instrument_id"] = features["entry_instrument_ids"].map(
        lambda values: _scalar_id(values) if isinstance(values, (list, np.ndarray)) else None
    )
    features["exit_instrument_id"] = features["exit_instrument_ids"].map(
        lambda values: _scalar_id(values) if isinstance(values, (list, np.ndarray)) else None
    )
    features["es_roll_match"] = features["bar_instrument_id"].eq(
        features["trade_instrument_id"]
    )
    features["mes_roll_match"] = features["entry_instrument_id"].eq(
        features["exit_instrument_id"]
    )
    features["direction"] = np.sign(features["rth_return"]).astype("Int64")
    features["large_move"] = features["rth_return"].abs().ge(
        features["same_clock_sigma60"]
    )
    features["flow_aligned"] = (
        features["rth_return"] * features["signed_volume"]
    ).gt(0)
    features["entry_spread_ticks"] = features["entry_spread"] / TICK_SIZE
    features["spread_ok"] = features["entry_spread_ticks"].le(1.0 + 1e-12)
    features["quote_valid"] = (
        features["entry_rows"].gt(0)
        & features["exit_rows"].gt(0)
        & features["entry_ask"].ge(features["entry_bid"])
        & features["exit_ask"].ge(features["exit_bid"])
        & features["mes_roll_match"]
    )
    features["data_valid"] = (
        features["mechanically_eligible"]
        & features["quote_valid"]
        & features["es_roll_match"]
        & features["trade_rows"].gt(0)
        & features["same_clock_sigma60"].notna()
    )
    long_direction = features["direction"].eq(1).fillna(False)
    features["entry_fill"] = np.where(
        long_direction,
        features["entry_ask"],
        features["entry_bid"],
    )
    features["exit_fill"] = np.where(
        long_direction,
        features["exit_bid"],
        features["exit_ask"],
    )
    features["gross_points"] = (
        features["direction"] * (features["exit_fill"] - features["entry_fill"])
    )
    features["gross_usd"] = features["gross_points"] * MES_MULTIPLIER
    features["net_usd_1p24"] = features["gross_usd"] - ROUND_TRIP_COMMISSION_USD
    features["frozen_signal"] = (
        features["data_valid"]
        & features["large_move"]
        & features["flow_aligned"]
        & features["spread_ok"]
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(args.output, index=False)
    summary = {
        "output": args.output.as_posix(),
        "rows": int(len(features)),
        "mechanically_eligible": int(features["mechanically_eligible"].sum()),
        "data_valid_after_60_session_warmup": int(features["data_valid"].sum()),
        "short_sessions": int(features["short_session"].sum()),
        "degraded_weekdays": sorted(degraded),
        "es_roll_mismatches_on_eligible": int(
            (
                features["mechanically_eligible"]
                & ~features["es_roll_match"].fillna(False)
            ).sum()
        ),
        "mes_roll_mismatches_on_eligible": int(
            (
                features["mechanically_eligible"]
                & ~features["mes_roll_match"].fillna(False)
            ).sum()
        ),
        "frozen_parameters": {
            "large_move_threshold": "absolute RTH return >= trailing 60-session sigma",
            "flow": "ES buyer-aggressor volume minus seller-aggressor volume, 15:00-15:30 ET",
            "alignment": "sign(flow) equals sign(RTH return)",
            "entry_spread_max_ticks": 1,
            "entry": "first MES MBP-1 record at/after 15:30:05 ET",
            "exit": "first MES MBP-1 record at/after 15:59:45 ET",
            "mes_multiplier": MES_MULTIPLIER,
            "round_trip_commission_usd": ROUND_TRIP_COMMISSION_USD,
        },
    }
    summary_path = args.output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
