"""Estimate (but never download) Databento data for the ES close-flow study.

This script calls only ``Historical.metadata.get_cost``. Databento documents
metadata calls as free. It intentionally has no code path to the time-series
or batch-download APIs.

The quote request is restricted to two ten-second MBP-1 windows per session:
one around the frozen entry and one around the frozen exit. This provides an
exact top-of-book update at each execution boundary without buying unused
second-by-second quotes for the whole last half-hour.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

VENDOR_DIR = Path(__file__).resolve().parents[1] / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402

DATASET = "GLBX.MDP3"
NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
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
    key = os.environ.get("DATABENTO_API_KEY") or _read_dotenv(dotenv_path).get(
        "DATABENTO_API_KEY"
    )
    if not key:
        raise RuntimeError("DATABENTO_API_KEY is not set")
    return key


def _client(key: str) -> db.Historical:
    client = getattr(_thread_local, "client", None)
    if client is None:
        client = db.Historical(key)
        _thread_local.client = client
    return client


def _utc(day: date, value: time) -> str:
    return datetime.combine(day, value, tzinfo=NY).astimezone(UTC).isoformat()


def _weekdays(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor < end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _session_cost(day: date, key: str) -> dict[str, Any]:
    client = _client(key)
    shared = {
        "dataset": DATASET,
        "stype_in": "continuous",
    }
    trades = client.metadata.get_cost(
        **shared,
        symbols="ES.v.0",
        schema="trades",
        start=_utc(day, time(15, 0)),
        end=_utc(day, time(15, 30)),
    )
    entry = client.metadata.get_cost(
        **shared,
        symbols="MES.v.0",
        schema="mbp-1",
        start=_utc(day, time(15, 30, 5)),
        end=_utc(day, time(15, 30, 15)),
    )
    exit_ = client.metadata.get_cost(
        **shared,
        symbols="MES.v.0",
        schema="mbp-1",
        start=_utc(day, time(15, 59, 45)),
        end=_utc(day, time(15, 59, 55)),
    )
    return {
        "date": day.isoformat(),
        "es_trades_1500_1530_usd": trades,
        "mes_mbp1_entry_10s_usd": entry,
        "mes_mbp1_exit_10s_usd": exit_,
        "total_usd": trades + entry + exit_,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.end <= args.start:
        raise ValueError("--end must be after --start")
    if not 1 <= args.workers <= 16:
        raise ValueError("--workers must be between 1 and 16")

    key = _api_key(args.dotenv)
    sessions = _weekdays(args.start, args.end)
    estimates: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(_session_cost, session, key): session for session in sessions
        }
        for index, future in enumerate(as_completed(futures), start=1):
            estimates.append(future.result())
            if index % 50 == 0 or index == len(sessions):
                print(f"estimated {index}/{len(sessions)} weekdays", flush=True)

    estimates.sort(key=lambda item: item["date"])
    component_keys = [
        "es_trades_1500_1530_usd",
        "mes_mbp1_entry_10s_usd",
        "mes_mbp1_exit_10s_usd",
    ]
    summary = {
        key_: sum(float(item[key_]) for item in estimates) for key_ in component_keys
    }
    summary["session_windows_total_usd"] = sum(
        float(item["total_usd"]) for item in estimates
    )
    summary["calendar_weekdays"] = len(estimates)
    summary["zero_cost_weekdays"] = sum(
        float(item["total_usd"]) == 0.0 for item in estimates
    )
    payload = {
        "purpose": "Free metadata-only Databento cost estimate; no market data requested",
        "dataset": DATASET,
        "start_inclusive": args.start.isoformat(),
        "end_exclusive": args.end.isoformat(),
        "requests": {
            "flow": "ES.v.0 trades 15:00:00-15:30:00 America/New_York",
            "entry": "MES.v.0 MBP-1 15:30:05-15:30:15 America/New_York",
            "exit": "MES.v.0 MBP-1 15:59:45-15:59:55 America/New_York",
        },
        "summary": summary,
        "daily_estimates": estimates,
    }
    rendered = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
