"""Estimate a bounded QQQ full-depth pilot without downloading market data."""

from __future__ import annotations

import argparse
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

import databento as db
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout" / "navier_stokes_liquidity_v2" / "cost_estimate.json"
DATASET = "XNAS.ITCH"
SYMBOL = "QQQ"
SCHEMAS = ("mbp-10", "mbo")
NY = ZoneInfo("America/New_York")
UTC_ZONE = ZoneInfo("UTC")


def weekdays(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while cursor < end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def utc(day: date, clock: time) -> str:
    return datetime.combine(day, clock, tzinfo=NY).astimezone(UTC_ZONE).isoformat()


def estimate(day: date, schema: str, key: str) -> dict[str, object]:
    try:
        cost = db.Historical(key).metadata.get_cost(
            dataset=DATASET,
            schema=schema,
            symbols=[SYMBOL],
            stype_in="raw_symbol",
            start=utc(day, time(9, 20)),
            end=utc(day, time(9, 35)),
        )
        return {"date": day.isoformat(), "schema": schema, "cost_usd": float(cost)}
    except Exception as exc:
        return {
            "date": day.isoformat(),
            "schema": schema,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2025, 1, 2))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 9, 12))
    parser.add_argument("--sample-size", type=int, default=20)
    parser.add_argument("--target-sessions", type=int, default=80)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.end <= args.start:
        raise ValueError("--end must be after --start")
    if not 1 <= args.workers <= 12:
        raise ValueError("--workers must be between 1 and 12")
    candidates = weekdays(args.start, args.end)
    if not 1 <= args.sample_size <= len(candidates):
        raise ValueError("invalid --sample-size")

    load_dotenv(ROOT / ".env")
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise RuntimeError("DATABENTO_API_KEY is not configured")
    client = db.Historical(key)
    available = list(client.metadata.list_schemas(dataset=DATASET))
    if not set(SCHEMAS).issubset(available):
        raise RuntimeError(f"required schemas unavailable: {available}")

    sampled = sorted(random.Random(20260913).sample(candidates, args.sample_size))
    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(estimate, day, schema, key)
            for day in sampled
            for schema in SCHEMAS
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if index % 10 == 0 or index == len(futures):
                print(f"estimated {index}/{len(futures)} windows", flush=True)
    rows.sort(key=lambda row: (str(row["schema"]), str(row["date"])))

    projections: dict[str, object] = {}
    for schema in SCHEMAS:
        valid = [float(row["cost_usd"]) for row in rows if row["schema"] == schema and "cost_usd" in row]
        errors = [row for row in rows if row["schema"] == schema and "error" in row]
        per_session = mean(valid) if valid else None
        projections[schema] = {
            "successful_estimates": len(valid),
            "errors": len(errors),
            "mean_cost_per_15_minute_session_usd": per_session,
            "target_sessions": args.target_sessions,
            "projected_cost_usd": per_session * args.target_sessions if per_session is not None else None,
            "protected_125pct_cost_usd": per_session * args.target_sessions * 1.25
            if per_session is not None
            else None,
        }
    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "mode": "METADATA_ONLY_NO_PURCHASE_OR_DOWNLOAD",
        "dataset": DATASET,
        "symbol": SYMBOL,
        "window_et": "09:20:00-09:35:00",
        "candidate_range": {"start_inclusive": args.start.isoformat(), "end_exclusive": args.end.isoformat()},
        "sampling_seed": 20260913,
        "sampled_dates": [day.isoformat() for day in sampled],
        "available_schemas": available,
        "projections": projections,
        "estimates": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(projections, indent=2, allow_nan=False), flush=True)
    return 0 if all(projections[schema]["successful_estimates"] for schema in SCHEMAS) else 1  # type: ignore[index]


if __name__ == "__main__":
    raise SystemExit(main())
