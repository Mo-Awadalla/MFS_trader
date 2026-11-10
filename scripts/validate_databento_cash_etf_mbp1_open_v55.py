"""Offline integrity and execution-coverage audit for the V55 MBP-1 package."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402

DATA_ROOT = ROOT / "external_artifacts" / "databento_cash_etf_mbp1_open_v55"
FILES_ROOT = DATA_ROOT / "EQUS.MINI" / "mbp-1"
CACHE_ROOT = DATA_ROOT / "validation_cache"
MANIFEST = DATA_ROOT / "manifest.json"
COST_LEDGER = (
    ROOT / "research_scout" / "databento_cash_etf_mbp1_exact_cost_20260729.json"
)
PRIOR_AUDIT = ROOT / "research_scout" / "cash_etf_auction_research_results_v36.json"
OUTPUT = DATA_ROOT / "validation_report.json"
SYMBOLS = ["SPY", "SSO", "UPRO", "SH", "SDS", "SPXU"]
TARGETS = ["09:30:01", "09:30:05", "09:31:00", "09:35:00"]
NY = ZoneInfo("America/New_York")
UTC_ZONE = ZoneInfo("UTC")


def _utc(day: date, value: str) -> pd.Timestamp:
    parsed = time.fromisoformat(value)
    return pd.Timestamp(
        datetime.combine(day, parsed, tzinfo=NY).astimezone(UTC_ZONE)
    )


def _inspect(path: Path) -> dict[str, Any]:
    day = date.fromisoformat(path.name.removesuffix(".dbn.zst"))
    expected_start = _utc(day, "09:20:00")
    expected_end = _utc(day, "09:40:00")
    result: dict[str, Any] = {
        "date": day.isoformat(),
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
    }
    try:
        store = db.read_dbn(path)
        metadata_symbols = list(store.metadata.symbols)
        frame = store.to_df(map_symbols=True, tz="UTC").reset_index()
        if "ts_recv" not in frame:
            raise RuntimeError("Decoded frame has no ts_recv")
        frame["ts_recv"] = pd.to_datetime(frame["ts_recv"], utc=True)
        counts = Counter(frame["symbol"].astype(str))
        target_states: dict[str, dict[str, Any]] = {}
        for target in TARGETS:
            target_ts = _utc(day, target)
            per_symbol: dict[str, Any] = {}
            for symbol in SYMBOLS:
                eligible = frame[
                    (frame["symbol"] == symbol) & (frame["ts_recv"] <= target_ts)
                ]
                if eligible.empty:
                    per_symbol[symbol] = {"available": False}
                    continue
                row = eligible.iloc[-1]
                raw_bid = row["bid_px_00"]
                raw_ask = row["ask_px_00"]
                bid = float(raw_bid) if pd.notna(raw_bid) else None
                ask = float(raw_ask) if pd.notna(raw_ask) else None
                quote_ts = pd.Timestamp(row["ts_recv"])
                per_symbol[symbol] = {
                    "available": True,
                    "quote_ts_recv": quote_ts.isoformat(),
                    "quote_age_seconds": float((target_ts - quote_ts).total_seconds()),
                    "bid": bid,
                    "ask": ask,
                    "valid_positive_non_crossed": bid is not None
                    and ask is not None
                    and bid > 0
                    and ask > 0
                    and ask >= bid,
                }
            target_states[target] = per_symbol

        all_targets_all_symbols = all(
            target_states[target][symbol]["available"]
            and target_states[target][symbol]["valid_positive_non_crossed"]
            for target in TARGETS
            for symbol in SYMBOLS
        )
        result.update(
            {
                "status": "valid",
                "dataset": store.dataset,
                "schema": str(store.schema),
                "metadata_symbols": metadata_symbols,
                "metadata_start": pd.Timestamp(store.start)
                .tz_convert("UTC")
                .isoformat(),
                "metadata_end": pd.Timestamp(store.end).tz_convert("UTC").isoformat(),
                "metadata_window_exact": pd.Timestamp(store.start).tz_convert("UTC")
                == expected_start
                and pd.Timestamp(store.end).tz_convert("UTC") == expected_end,
                "rows": len(frame),
                "first_ts_recv": frame["ts_recv"].min().isoformat(),
                "last_ts_recv": frame["ts_recv"].max().isoformat(),
                "ts_recv_monotonic": bool(frame["ts_recv"].is_monotonic_increasing),
                "symbol_counts": dict(sorted(counts.items())),
                "all_six_symbols_present": all(counts[symbol] > 0 for symbol in SYMBOLS),
                "all_targets_all_symbols_valid": all_targets_all_symbols,
                "target_states": target_states,
            }
        )
    except Exception as exc:
        result.update(
            {
                "status": "invalid",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        raise ValueError("--workers must be between 1 and 8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ledger = json.loads(COST_LEDGER.read_text(encoding="utf-8"))
    prior = json.loads(PRIOR_AUDIT.read_text(encoding="utf-8"))
    files = sorted(FILES_ROOT.glob("*.dbn.zst"))
    partials = sorted(FILES_ROOT.glob("*.partial.dbn.zst"))
    files = [path for path in files if ".partial." not in path.name]
    if not files:
        raise RuntimeError(f"No completed DBN files found under {FILES_ROOT}")

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    uncached: list[Path] = []
    for path in files:
        cache = CACHE_ROOT / f"{path.name}.json"
        if cache.exists():
            summaries.append(json.loads(cache.read_text(encoding="utf-8")))
        else:
            uncached.append(path)
    if summaries:
        print(f"reused {len(summaries)} cached validations", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_inspect, path): path for path in uncached}
        for index, future in enumerate(as_completed(futures), start=1):
            item = future.result()
            summaries.append(item)
            cache = CACHE_ROOT / f"{Path(item['path']).name}.json"
            temporary_cache = cache.with_name(f"{cache.name}.partial")
            temporary_cache.write_text(
                json.dumps(item, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            temporary_cache.replace(cache)
            if index % 25 == 0 or index == len(futures):
                print(
                    f"validated {index}/{len(futures)} uncached files",
                    flush=True,
                )
    summaries.sort(key=lambda item: item["date"])

    expected_paid_dates = {
        str(row["date"])
        for row in ledger["sampled_daily_opening_window_estimates"]
        if float(row["full_six_etf_ladder_usd"]) > 0
    }
    completed_dates = {item["date"] for item in summaries}
    invalid = [item for item in summaries if item["status"] != "valid"]
    valid = [item for item in summaries if item["status"] == "valid"]
    target_complete = [
        item for item in valid if item["all_targets_all_symbols_valid"]
    ]
    quote_ages = {
        target: {
            symbol: [
                item["target_states"][target][symbol]["quote_age_seconds"]
                for item in valid
                if item["target_states"][target][symbol]["available"]
            ]
            for symbol in SYMBOLS
        }
        for target in TARGETS
    }
    age_summary = {
        target: {
            symbol: {
                "observations": len(values),
                "median_seconds": float(pd.Series(values).median())
                if values
                else None,
                "p95_seconds": float(pd.Series(values).quantile(0.95))
                if values
                else None,
                "max_seconds": max(values) if values else None,
            }
            for symbol, values in symbol_map.items()
        }
        for target, symbol_map in quote_ages.items()
    }
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "paid_api_calls_made": False,
        "source_manifest_mode": manifest["mode"],
        "files_found": len(files),
        "partial_files": [path.relative_to(ROOT).as_posix() for path in partials],
        "expected_nonzero_cost_sessions": len(expected_paid_dates),
        "completed_dates": len(completed_dates),
        "missing_dates": sorted(expected_paid_dates - completed_dates),
        "unexpected_dates": sorted(completed_dates - expected_paid_dates),
        "invalid_files": invalid,
        "all_files_decode": not invalid,
        "exact_metadata_windows": all(
            item.get("metadata_window_exact", False) for item in valid
        ),
        "all_files_monotonic": all(
            item.get("ts_recv_monotonic", False) for item in valid
        ),
        "all_files_contain_six_symbols": all(
            item.get("all_six_symbols_present", False) for item in valid
        ),
        "sessions_with_all_four_targets_all_six_valid": len(target_complete),
        "target_coverage_pct_of_completed": 100.0
        * len(target_complete)
        / len(valid),
        "quote_age_summary_seconds": age_summary,
        "known_degraded_dates_equs_mini": prior["technical_audit"][
            "degraded_dates"
        ]["EQUS.MINI"],
        "file_summaries": summaries,
    }
    temporary = OUTPUT.with_name(f"{OUTPUT.name}.partial")
    temporary.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print(
        json.dumps(
            {
                key: payload[key]
                for key in [
                    "files_found",
                    "partial_files",
                    "missing_dates",
                    "all_files_decode",
                    "exact_metadata_windows",
                    "all_files_monotonic",
                    "all_files_contain_six_symbols",
                    "sessions_with_all_four_targets_all_six_valid",
                    "target_coverage_pct_of_completed",
                    "quote_age_summary_seconds",
                    "known_degraded_dates_equs_mini",
                ]
            },
            indent=2,
            allow_nan=False,
        ),
        flush=True,
    )
    return 0 if not invalid and not partials else 1


if __name__ == "__main__":
    raise SystemExit(main())
