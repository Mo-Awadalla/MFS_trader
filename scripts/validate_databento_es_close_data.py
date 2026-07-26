"""Offline structural validation for the Databento ES close-flow artifact."""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

VENDOR_DIR = Path(__file__).resolve().parents[1] / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402
import pandas as pd  # noqa: E402

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
COMPONENTS = {
    "es_trades.dbn.zst": {
        "cost_key": "es_trades_1500_1530_usd",
        "start": time(15, 0),
        "end": time(15, 30),
        "required": {"ts_event", "instrument_id", "side", "price", "size", "sequence"},
    },
    "mes_entry_mbp1.dbn.zst": {
        "cost_key": "mes_mbp1_entry_10s_usd",
        "start": time(15, 30, 5),
        "end": time(15, 30, 15),
        "required": {
            "ts_event",
            "instrument_id",
            "bid_px_00",
            "ask_px_00",
            "bid_sz_00",
            "ask_sz_00",
            "sequence",
        },
    },
    "mes_exit_mbp1.dbn.zst": {
        "cost_key": "mes_mbp1_exit_10s_usd",
        "start": time(15, 59, 45),
        "end": time(15, 59, 55),
        "required": {
            "ts_event",
            "instrument_id",
            "bid_px_00",
            "ask_px_00",
            "bid_sz_00",
            "ask_sz_00",
            "sequence",
        },
    },
}


def _utc(day: date, value: time) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, value, tzinfo=NY).astimezone(UTC))


def _expected_files(
    manifests: list[Path], start: date, end: date, sessions_root: Path
) -> set[Path]:
    estimates: dict[str, dict[str, Any]] = {}
    for path in manifests:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload["daily_estimates"]:
            estimates[item["date"]] = item

    expected: set[Path] = set()
    cursor = start
    while cursor < end:
        item = estimates.get(cursor.isoformat())
        if cursor.weekday() < 5 and item is None:
            raise ValueError(f"Missing cost estimate for {cursor}")
        if item:
            root = sessions_root / str(cursor.year) / cursor.isoformat()
            for filename, spec in COMPONENTS.items():
                if float(item[spec["cost_key"]]) > 0:
                    expected.add((root / filename).resolve())
        cursor += pd.Timedelta(days=1).to_pytimedelta()
    return expected


def _validate_session_file(path: Path) -> dict[str, Any]:
    day = date.fromisoformat(path.parent.name)
    spec = COMPONENTS[path.name]
    store = db.read_dbn(path)
    frame = store.to_df()
    missing = sorted(set(spec["required"]).difference(frame.columns))
    start = _utc(day, spec["start"])
    end = _utc(day, spec["end"])
    if frame.empty:
        min_ts = max_ts = None
        outside = 0
        monotonic = True
        instrument_ids: list[int] = []
        sides: list[str] = []
        crossed_quotes = 0
        nonpositive_quotes = 0
    else:
        index = pd.DatetimeIndex(frame.index)
        min_ts = index.min().isoformat()
        max_ts = index.max().isoformat()
        outside = int(((index < start) | (index >= end)).sum())
        monotonic = bool(index.is_monotonic_increasing)
        instrument_ids = sorted(
            int(value) for value in frame["instrument_id"].dropna().unique()
        )
        sides = (
            sorted(frame["side"].astype(str).unique().tolist())
            if "side" in frame
            else []
        )
        if {"bid_px_00", "ask_px_00"}.issubset(frame.columns):
            crossed_quotes = int(frame["ask_px_00"].lt(frame["bid_px_00"]).sum())
            nonpositive_quotes = int(
                (
                    frame["ask_px_00"].le(0)
                    | frame["bid_px_00"].le(0)
                ).sum()
            )
        else:
            crossed_quotes = 0
            nonpositive_quotes = 0

    metadata = store.metadata
    return {
        "date": day.isoformat(),
        "component": path.name.removesuffix(".dbn.zst"),
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
        "rows": int(len(frame)),
        "min_ts": min_ts,
        "max_ts": max_ts,
        "outside_requested_window": outside,
        "monotonic": monotonic,
        "missing_columns": missing,
        "instrument_ids": instrument_ids,
        "sides": sides,
        "crossed_quotes": crossed_quotes,
        "nonpositive_quotes": nonpositive_quotes,
        "stype_in": str(metadata.stype_in),
        "stype_out": str(metadata.stype_out),
    }


def _validate_bars(path: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    store = db.read_dbn(path)
    frame = store.to_df()
    required = {"instrument_id", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    index = pd.DatetimeIndex(frame.index)
    local = index.tz_convert(NY)
    rth_mask = (local.time >= time(9, 30)) & (local.time < time(16, 0))
    rth = frame.loc[rth_mask].copy()
    rth["session_date"] = local[rth_mask].date
    counts = rth.groupby("session_date").size()
    short = {
        str(day): int(count) for day, count in counts[counts.lt(390)].items()
    }
    summary = {
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
        "rows": int(len(frame)),
        "start": index.min().isoformat(),
        "end": index.max().isoformat(),
        "duplicate_timestamps": int(index.duplicated().sum()),
        "missing_columns": missing,
        "null_ohlcv": {
            column: int(frame[column].isna().sum())
            for column in ["open", "high", "low", "close", "volume"]
        },
        "rth_session_dates": int(len(counts)),
        "full_390_minute_rth_sessions": int(counts.eq(390).sum()),
        "short_rth_sessions": short,
        "instrument_ids": sorted(
            int(value) for value in frame["instrument_id"].dropna().unique()
        ),
        "stype_in": str(store.metadata.stype_in),
        "stype_out": str(store.metadata.stype_out),
    }
    daily_ids = (
        rth.groupby("session_date")["instrument_id"]
        .agg(lambda values: sorted(int(value) for value in values.unique()))
        .rename("bar_instrument_ids")
        .reset_index()
    )
    daily_ids["session_date"] = daily_ids["session_date"].astype(str)
    return summary, daily_ids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--cost-manifest", type=Path, action="append", required=True)
    parser.add_argument("--condition-json", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sessions_root = args.root / "sessions"
    actual = {
        path.resolve() for path in sessions_root.rglob("*.dbn.zst") if path.is_file()
    }
    expected = _expected_files(
        args.cost_manifest, args.start, args.end, sessions_root
    )
    partials = sorted(path.as_posix() for path in sessions_root.rglob("*partial*"))
    missing_files = sorted(path.as_posix() for path in expected.difference(actual))
    unexpected_files = sorted(path.as_posix() for path in actual.difference(expected))
    if partials or missing_files:
        raise ValueError(
            f"Incomplete artifact: partials={len(partials)}, missing={len(missing_files)}"
        )

    summaries: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_validate_session_file, path): path for path in actual
        }
        for index, future in enumerate(as_completed(futures), start=1):
            summaries.append(future.result())
            if index % 250 == 0 or index == len(futures):
                print(f"validated {index}/{len(futures)} session files", flush=True)
    summaries.sort(key=lambda item: (item["date"], item["component"]))
    detail = pd.DataFrame(summaries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    detail_path = args.output.with_name(f"{args.output.stem}_files.parquet")
    detail.to_parquet(detail_path, index=False)

    bar_path = args.root / "bars" / f"es_ohlcv_1m_{args.start}_{args.end}.dbn.zst"
    bar_summary, daily_ids = _validate_bars(bar_path)
    daily_ids_path = args.output.with_name(
        f"{args.output.stem}_bar_instrument_ids.parquet"
    )
    daily_ids.to_parquet(daily_ids_path, index=False)

    condition_payload = json.loads(args.condition_json.read_text(encoding="utf-8"))
    non_available = [
        item
        for item in condition_payload["conditions"]
        if item["condition"] != "available"
    ]
    weekday_degraded = [
        item["date"]
        for item in non_available
        if args.start <= date.fromisoformat(item["date"]) < args.end
        and date.fromisoformat(item["date"]).weekday() < 5
    ]
    invalid_rows = detail[
        detail["rows"].le(0)
        | detail["outside_requested_window"].gt(0)
        | ~detail["monotonic"]
        | detail["missing_columns"].map(bool)
        | detail["crossed_quotes"].gt(0)
        | detail["nonpositive_quotes"].gt(0)
    ]
    excluded_dates = set(bar_summary["short_rth_sessions"]).union(weekday_degraded)
    invalid_nonexcluded = invalid_rows[
        ~invalid_rows["date"].isin(excluded_dates)
    ]
    audit = {
        "root": args.root.as_posix(),
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "expected_session_files": len(expected),
        "actual_session_files": len(actual),
        "unexpected_session_files": unexpected_files,
        "partial_files": partials,
        "total_session_rows": int(detail["rows"].sum()),
        "rows_by_component": {
            str(key): int(value)
            for key, value in detail.groupby("component")["rows"].sum().items()
        },
        "invalid_session_files_total": int(len(invalid_rows)),
        "invalid_session_files_on_excluded_dates": int(
            len(invalid_rows) - len(invalid_nonexcluded)
        ),
        "invalid_nonexcluded_session_files": int(len(invalid_nonexcluded)),
        "condition_non_available": non_available,
        "weekday_degraded_exclusions": weekday_degraded,
        "bars": bar_summary,
        "detail_path": detail_path.as_posix(),
        "daily_bar_instrument_ids_path": daily_ids_path.as_posix(),
    }
    args.output.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))
    return 0 if invalid_nonexcluded.empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
