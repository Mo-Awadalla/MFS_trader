"""Returns-blind integrity and availability audit for shared BTCUSDT sample dates."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = (
    ROOT
    / "research_scout"
    / "navier_stokes_liquidity_v2"
    / "free_data"
    / "binance-public"
    / "futures-um"
    / "BTCUSDT"
)
OI_PATH = (
    ROOT
    / "data"
    / "parquet"
    / "binance_bitcoin_derivatives_public_v1"
    / "normalized"
    / "futures_metrics_5m.parquet"
)
OUTPUT = ROOT / "research_scout" / "btc_microstructure_admission_20260925.json"
HEADERS = {
    "aggTrades": b"agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker",
    "bookTicker": b"update_id,best_bid_price,best_bid_qty,best_ask_price,best_ask_qty,transaction_time,event_time",
    "bookDepth": b"timestamp,percentage,depth,notional",
    "metrics": b"create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio",
}


def checksum(path: Path) -> dict:
    checksum_path = Path(str(path) + ".CHECKSUM")
    expected, named_file = checksum_path.read_text(encoding="utf-8").strip().split(maxsplit=1)
    if named_file != path.name:
        raise ValueError(f"checksum filename mismatch: {checksum_path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    actual = digest.hexdigest()
    return {"sha256": actual, "checksum_matches": actual == expected, "compressed_bytes": path.stat().st_size}


def scan_archive(path: Path, kind: str, day: str) -> dict:
    result = checksum(path)
    result.update(
        rows=0,
        malformed_rows=0,
        out_of_date_rows=0,
        event_backtracks=0,
        event_duplicate_timestamps=0,
        id_nonincreasing=0,
        invalid_quotes=0,
        locked_quotes=0,
        invalid_trades=0,
        trade_id_range_errors=0,
        timestamp_inversions=0,
        gap_over_1s=0,
        gap_over_5s=0,
        gap_over_30s=0,
        max_forward_gap_ms=0,
    )
    lower = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)
    upper = lower + 86_400_000
    prior_event = None
    prior_id = None
    minimum = None
    maximum = None
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 1 or names[0] != path.stem + ".csv":
            raise ValueError(f"unexpected ZIP contents: {path}: {names}")
        with archive.open(names[0]) as stream:
            header = stream.readline().rstrip(b"\r\n")
            if header != HEADERS[kind]:
                raise ValueError(f"unexpected {kind} schema: {path}: {header!r}")
            for raw in stream:
                fields = raw.rstrip(b"\r\n").split(b",")
                if len(fields) != len(HEADERS[kind].split(b",")):
                    result["malformed_rows"] += 1
                    continue
                try:
                    if kind == "bookTicker":
                        ident = int(fields[0])
                        transaction_ms = int(fields[5])
                        event_ms = int(fields[6])
                        bid, bid_qty, ask, ask_qty = map(float, fields[1:5])
                        result["invalid_quotes"] += int(
                            bid <= 0 or ask <= 0 or bid_qty < 0 or ask_qty < 0 or bid > ask
                        )
                        result["locked_quotes"] += int(bid == ask)
                        result["timestamp_inversions"] += int(transaction_ms > event_ms)
                    elif kind == "aggTrades":
                        ident = int(fields[0])
                        event_ms = int(fields[5])
                        first_id, last_id = int(fields[3]), int(fields[4])
                        result["trade_id_range_errors"] += int(first_id > last_id)
                        result["invalid_trades"] += int(
                            float(fields[1]) <= 0 or float(fields[2]) <= 0 or fields[6] not in (b"True", b"False", b"true", b"false")
                        )
                    elif kind == "bookDepth":
                        ident = None
                        event_ms = int(fields[0])
                    else:
                        ident = None
                        event_ms = int(datetime.fromisoformat(fields[0].decode()).replace(tzinfo=UTC).timestamp() * 1000)
                except (ValueError, OverflowError, UnicodeDecodeError):
                    result["malformed_rows"] += 1
                    continue
                result["rows"] += 1
                result["out_of_date_rows"] += int(not lower <= event_ms < upper)
                minimum = event_ms if minimum is None else min(minimum, event_ms)
                maximum = event_ms if maximum is None else max(maximum, event_ms)
                if prior_event is not None:
                    delta = event_ms - prior_event
                    result["event_backtracks"] += int(delta < 0)
                    result["event_duplicate_timestamps"] += int(delta == 0)
                    if kind == "bookTicker" and delta > 0:
                        result["gap_over_1s"] += int(delta > 1_000)
                        result["gap_over_5s"] += int(delta > 5_000)
                        result["gap_over_30s"] += int(delta > 30_000)
                        result["max_forward_gap_ms"] = max(result["max_forward_gap_ms"], delta)
                if ident is not None and prior_id is not None:
                    result["id_nonincreasing"] += int(ident <= prior_id)
                prior_event, prior_id = event_ms, ident
    result["first_event_utc"] = datetime.fromtimestamp(minimum / 1000, UTC).isoformat() if minimum is not None else None
    result["last_event_utc"] = datetime.fromtimestamp(maximum / 1000, UTC).isoformat() if maximum is not None else None
    return result


def oi_availability(dates: list[str]) -> dict[str, dict]:
    frame = pd.read_parquet(OI_PATH, columns=["create_time", "sum_open_interest"])
    frame = frame.dropna().sort_values("create_time")
    stamps = frame["create_time"].dt.as_unit("ms").astype("int64").to_numpy(dtype=np.int64)
    values = frame["sum_open_interest"].to_numpy(dtype=float)
    result = {}
    for day in dates:
        start = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)
        decisions = start + np.arange(288, dtype=np.int64) * 300_000
        # Five-minute conservative publication lag, then at most ten minutes stale.
        eligible = np.searchsorted(stamps + 300_000, decisions, side="right") - 1
        valid = eligible >= 0
        ages = np.full(len(decisions), np.nan)
        ages[valid] = (decisions[valid] - stamps[eligible[valid]] - 300_000) / 60_000
        fresh = valid & (ages <= 10) & (values[np.maximum(eligible, 0)] > 0)
        on_day = (stamps >= start) & (stamps < start + 86_400_000)
        day_stamps = stamps[on_day]
        result[day] = {
            "oi_rows_on_date": int(on_day.sum()),
            "five_minute_decisions": 288,
            "fresh_oi_decisions": int(fresh.sum()),
            "fresh_oi_fraction": float(fresh.mean()),
            "max_oi_observation_gap_minutes": float(np.diff(day_stamps).max() / 60_000) if len(day_stamps) > 1 else None,
            "first_oi_observation_utc": datetime.fromtimestamp(day_stamps[0] / 1000, UTC).isoformat() if len(day_stamps) else None,
            "last_oi_observation_utc": datetime.fromtimestamp(day_stamps[-1] / 1000, UTC).isoformat() if len(day_stamps) else None,
        }
    return result


def audit_day(day: str) -> tuple[str, dict]:
    archives = {}
    for path in sorted((ARCHIVES / day).glob("*.zip")):
        kind = path.name.split("-")[1]
        archives[kind] = scan_archive(path, kind, day)
    return day, archives


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="*", help="Optional dates for a bounded pilot")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--oi-only", action="store_true", help="Refresh OI availability in an existing archive report")
    args = parser.parse_args()
    dates = sorted(p.name for p in ARCHIVES.iterdir() if p.is_dir() and any(p.glob("*.zip")))
    if args.dates:
        missing = sorted(set(args.dates) - set(dates))
        if missing:
            raise ValueError(f"dates not found: {missing}")
        dates = sorted(set(args.dates))
    oi = oi_availability(dates)
    if args.oi_only:
        saved = json.loads(OUTPUT.read_text(encoding="utf-8"))
        saved["dates"] = {day: value for day, value in saved["dates"].items() if value["archives"]}
        for day in saved["dates"]:
            saved["dates"][day]["oi"] = oi[day]
        OUTPUT.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")
        print(f"updated OI availability for {len(saved['dates'])} audited dates", flush=True)
        return
    result = {
        "schema": "btc_microstructure_admission:v1",
        "returns_inspected": False,
        "source_root": str(ARCHIVES),
        "oi_source": str(OI_PATH),
        "oi_policy": "create_time + 5 minutes <= decision; available observation no more than 10 minutes old",
        "dates": {},
    }
    if args.workers < 1:
        raise ValueError("workers must be positive")
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(audit_day, day): day for day in dates}
        for future in as_completed(futures):
            day, archives = future.result()
            result["dates"][day] = {"oi": oi[day], "archives": archives}
            result["dates"] = dict(sorted(result["dates"].items()))
            OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(f"audited {day}: {', '.join(archives)}", flush=True)


if __name__ == "__main__":
    main()
