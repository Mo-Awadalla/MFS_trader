"""Estimate the Databento cost of complete cash-ETF top-of-book updates.

This script is deliberately metadata-only. It has no time-series, batch,
download, or order code path, so running it cannot acquire market data.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

VENDOR_DIR = Path(__file__).resolve().parents[1] / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATASET = "EQUS.MINI"
SCHEMA = "mbp-1"
NY = ZoneInfo("America/New_York")
UTC_ZONE = ZoneInfo("UTC")
SYMBOL_SETS = {
    "minimal_actuators": ["UPRO", "SPXU"],
    "full_six_etf_ladder": ["SPY", "SSO", "UPRO", "SH", "SDS", "SPXU"],
}
_thread_local = threading.local()


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _api_key(dotenv_path: Path) -> str:
    value = os.environ.get("DATABENTO_API_KEY") or _read_dotenv(dotenv_path).get(
        "DATABENTO_API_KEY"
    )
    if not value:
        raise RuntimeError("DATABENTO_API_KEY is not set")
    return value


def _client(key: str) -> db.Historical:
    client = getattr(_thread_local, "client", None)
    if client is None:
        client = db.Historical(key)
        _thread_local.client = client
    return client


def _utc(day: date, value: time) -> str:
    return datetime.combine(day, value, tzinfo=NY).astimezone(UTC_ZONE).isoformat()


def _weekdays(start: date, end: date) -> list[date]:
    result: list[date] = []
    cursor = start
    while cursor < end:
        if cursor.weekday() < 5:
            result.append(cursor)
        cursor += timedelta(days=1)
    return result


def _opening_window_cost(
    day: date,
    key: str,
    symbol_sets: dict[str, list[str]],
) -> dict[str, Any]:
    client = _client(key)
    result: dict[str, Any] = {"date": day.isoformat()}
    for name, symbols in symbol_sets.items():
        result[f"{name}_usd"] = float(
            client.metadata.get_cost(
                dataset=DATASET,
                symbols=symbols,
                stype_in="raw_symbol",
                schema=SCHEMA,
                start=_utc(day, time(9, 20)),
                end=_utc(day, time(9, 40)),
            )
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2023, 3, 28))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 7, 29))
    parser.add_argument("--dotenv", type=Path, default=ROOT / ".env")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=60,
        help="Random weekdays used to estimate the recurring 20-minute window.",
    )
    parser.add_argument(
        "--only",
        choices=["all", *SYMBOL_SETS],
        default="all",
        help="Restrict pricing to one named symbol set.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "research_scout"
        / "databento_cash_etf_mbp1_cost_estimate_20260729.json",
    )
    args = parser.parse_args()

    if args.end <= args.start:
        raise ValueError("--end must be after --start")
    if not 1 <= args.workers <= 12:
        raise ValueError("--workers must be between 1 and 12")

    key = _api_key(args.dotenv)
    selected_sets = (
        SYMBOL_SETS
        if args.only == "all"
        else {args.only: SYMBOL_SETS[args.only]}
    )
    client = db.Historical(key)
    available_schemas = list(client.metadata.list_schemas(dataset=DATASET))
    if SCHEMA not in available_schemas:
        raise RuntimeError(f"{SCHEMA} is unavailable for {DATASET}")

    full_stream_estimates: dict[str, float] = {}
    for name, symbols in selected_sets.items():
        full_stream_estimates[name] = float(
            client.metadata.get_cost(
                dataset=DATASET,
                symbols=symbols,
                stype_in="raw_symbol",
                schema=SCHEMA,
                start=args.start.isoformat(),
                end=args.end.isoformat(),
            )
        )
    print(
        "continuous full-range estimates: "
        + json.dumps(full_stream_estimates, sort_keys=True),
        flush=True,
    )

    sessions = _weekdays(args.start, args.end)
    if not 1 <= args.sample_size <= len(sessions):
        raise ValueError("--sample-size must be between 1 and the weekday count")
    sampled_sessions = sorted(random.Random(20260729).sample(sessions, args.sample_size))
    daily: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_opening_window_cost, session, key, selected_sets): session
            for session in sampled_sessions
        }
        for index, future in enumerate(as_completed(futures), start=1):
            daily.append(future.result())
            if index % 10 == 0 or index == len(sampled_sessions):
                print(
                    f"estimated {index}/{len(sampled_sessions)} sampled weekdays",
                    flush=True,
                )
    daily.sort(key=lambda row: row["date"])

    opening_estimates: dict[str, dict[str, float]] = {}
    for name in selected_sets:
        values = [row[f"{name}_usd"] for row in daily]
        mean = statistics.mean(values)
        standard_error = (
            statistics.stdev(values) / (len(values) ** 0.5) if len(values) > 1 else 0.0
        )
        opening_estimates[name] = {
            "sample_mean_per_calendar_weekday": mean,
            "projected_total": mean * len(sessions),
            "approximate_95pct_low": max(
                0.0, (mean - 1.96 * standard_error) * len(sessions)
            ),
            "approximate_95pct_high": (
                mean + 1.96 * standard_error
            )
            * len(sessions),
        }
    nonzero_days = {
        name: sum(row[f"{name}_usd"] > 0.0 for row in daily)
        for name in selected_sets
    }
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "mode": "METADATA_ONLY_NO_PURCHASE_OR_DOWNLOAD",
        "dataset": DATASET,
        "schema": SCHEMA,
        "start_inclusive": args.start.isoformat(),
        "end_exclusive": args.end.isoformat(),
        "available_schemas": available_schemas,
        "symbol_sets": selected_sets,
        "estimates_usd": {
            "continuous_full_range": full_stream_estimates,
            "projected_session_0920_0940_america_new_york": opening_estimates,
        },
        "calendar_weekdays_in_projection": len(sessions),
        "sampled_calendar_weekdays": len(sampled_sessions),
        "sampling_seed": 20260729,
        "nonzero_cost_days": nonzero_days,
        "method_notes": [
            "All values came from Historical.metadata.get_cost.",
            "No time-series or batch endpoint was called.",
            "The 20-minute window is a discrete multiple of 10 minutes.",
            "Weekdays include exchange holidays; zero-cost days contribute zero.",
            "The full-range estimate includes all messages, including extended hours.",
            "The recurring-window total is projected from a deterministic random weekday sample.",
            "The approximate 95% interval reflects day-to-day cost variation, not API-estimate error.",
        ],
        "sampled_daily_opening_window_estimates": daily,
    }
    rendered = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps(payload["estimates_usd"], indent=2))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
