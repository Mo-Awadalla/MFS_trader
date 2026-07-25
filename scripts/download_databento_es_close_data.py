"""Guarded Databento downloader for the frozen ES close-flow data contract.

The command is dry-run by default. Billable requests require ``--execute`` and
three values copied from the Databento Billing page: remaining credits, the
historical monthly limit, and current-month historical usage. The preflight
refuses to run unless the complete conservative estimate fits inside both the
remaining credit and unused monthly limit.

Each intraday request is saved separately and is never retried automatically.
This avoids silently paying twice after an interrupted response.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta
from decimal import Decimal
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
DEFAULT_OUTPUT = Path("external_artifacts/databento_es_close")
MAX_ALLOWED_PORTAL_LIMIT = Decimal("100.00")
ESTIMATE_MULTIPLIER = Decimal("1.02")
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


def _utc(day: date, value: time) -> str:
    return datetime.combine(day, value, tzinfo=NY).astimezone(UTC).isoformat()


def _load_estimates(paths: list[Path], start: date, end: date) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("dataset") != DATASET:
            raise ValueError(f"Unexpected dataset in {path}")
        for item in payload["daily_estimates"]:
            by_date[item["date"]] = item

    expected: set[str] = set()
    cursor = start
    while cursor < end:
        if cursor.weekday() < 5:
            expected.add(cursor.isoformat())
        cursor += timedelta(days=1)
    missing = sorted(expected.difference(by_date))
    if missing:
        raise ValueError(
            f"Cost manifests do not cover {len(missing)} weekdays; first missing={missing[0]}"
        )
    return [by_date[value] for value in sorted(expected)]
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _client(key: str) -> db.Historical:
    client = getattr(_thread_local, "client", None)
    if client is None:
        client = db.Historical(key)
        _thread_local.client = client
    return client


def _download_one(
    key: str,
    final_path: Path,
    *,
    symbols: str,
    schema: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = final_path.with_name(f"{final_path.stem}.partial{final_path.suffix}")
    if final_path.exists():
        return {
            "status": "already_present",
            "path": final_path.as_posix(),
            "bytes": final_path.stat().st_size,
            "sha256": _sha256(final_path),
        }
    if partial_path.exists():
        raise RuntimeError(
            f"Partial file exists and will not be retried automatically: {partial_path}"
        )

    _client(key).timeseries.get_range(
        dataset=DATASET,
        symbols=symbols,
        stype_in="continuous",
        stype_out="instrument_id",
        schema=schema,
        start=start,
        end=end,
        path=partial_path,
    )
    if not partial_path.exists() or partial_path.stat().st_size == 0:
        raise RuntimeError(f"Databento returned an empty file: {partial_path}")
    os.replace(partial_path, final_path)
    return {
        "status": "downloaded",
        "path": final_path.as_posix(),
        "bytes": final_path.stat().st_size,
        "sha256": _sha256(final_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--cost-manifest", type=Path, action="append", required=True)
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--remaining-credit-usd", type=Decimal)
    parser.add_argument("--portal-limit-usd", type=Decimal)
    parser.add_argument("--month-usage-usd", type=Decimal)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if args.end <= args.start:
        raise ValueError("--end must be after --start")
    if not 1 <= args.workers <= 16:
        raise ValueError("--workers must be between 1 and 16")
    estimates = _load_estimates(args.cost_manifest, args.start, args.end)
    window_estimate = sum(
        (Decimal(str(item["total_usd"])) for item in estimates),
        start=Decimal("0"),
    )
    key = _api_key(args.dotenv)
    metadata_client = db.Historical(key)
    bar_estimate = Decimal(
        str(
            metadata_client.metadata.get_cost(
                dataset=DATASET,
                symbols="ES.v.0",
                stype_in="continuous",
                schema="ohlcv-1m",
                start=args.start.isoformat(),
                end=args.end.isoformat(),
            )
        )
    )
    total_estimate = window_estimate + bar_estimate
    protected_estimate = total_estimate * ESTIMATE_MULTIPLIER
    preflight = {
        "mode": "EXECUTE" if args.execute else "DRY_RUN",
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "session_window_estimate_usd": str(window_estimate),
        "minute_bar_estimate_usd": str(bar_estimate),
        "total_estimate_usd": str(total_estimate),
        "protected_estimate_usd": str(protected_estimate),
        "estimate_multiplier": str(ESTIMATE_MULTIPLIER),
    }
    print(json.dumps(preflight, indent=2), flush=True)
    if not args.execute:
        return 0

    billing_values = (
        args.remaining_credit_usd,
        args.portal_limit_usd,
        args.month_usage_usd,
    )
    if any(value is None for value in billing_values):
        raise RuntimeError(
            "--execute requires --remaining-credit-usd, --portal-limit-usd, "
            "and --month-usage-usd copied from the Billing page"
        )
    assert args.remaining_credit_usd is not None
    assert args.portal_limit_usd is not None
    assert args.month_usage_usd is not None
    if args.portal_limit_usd > MAX_ALLOWED_PORTAL_LIMIT:
        raise RuntimeError(
            f"Portal limit ${args.portal_limit_usd} exceeds hard ceiling "
            f"${MAX_ALLOWED_PORTAL_LIMIT}"
        )
    if args.portal_limit_usd > args.remaining_credit_usd:
        raise RuntimeError("Portal limit exceeds remaining credit")
    unused_limit = args.portal_limit_usd - args.month_usage_usd
    safe_capacity = min(args.remaining_credit_usd, unused_limit)
    if protected_estimate > safe_capacity:
        raise RuntimeError(
            f"Protected estimate ${protected_estimate} exceeds safe capacity "
            f"${safe_capacity}"
        )

    data_root = args.output_root / DATASET
    ledger_path = data_root / "download_ledger.jsonl"
    bar_result = _download_one(
        key,
        data_root
        / "bars"
        / f"es_ohlcv_1m_{args.start}_{args.end}.dbn.zst",
        symbols="ES.v.0",
        schema="ohlcv-1m",
        start=args.start.isoformat(),
        end=args.end.isoformat(),
    )
    with ledger_path.open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps({"component": "bars", **bar_result}) + "\n")

    tasks: list[dict[str, Any]] = []
    for item in estimates:
        day = date.fromisoformat(item["date"])
        day_root = data_root / "sessions" / str(day.year) / day.isoformat()
        requests_for_day = [
            (
                "es_trades",
                day_root / "es_trades.dbn.zst",
                "ES.v.0",
                "trades",
                _utc(day, time(15, 0)),
                _utc(day, time(15, 30)),
                Decimal(str(item["es_trades_1500_1530_usd"])),
            ),
            (
                "mes_entry",
                day_root / "mes_entry_mbp1.dbn.zst",
                "MES.v.0",
                "mbp-1",
                _utc(day, time(15, 30, 5)),
                _utc(day, time(15, 30, 15)),
                Decimal(str(item["mes_mbp1_entry_10s_usd"])),
            ),
            (
                "mes_exit",
                day_root / "mes_exit_mbp1.dbn.zst",
                "MES.v.0",
                "mbp-1",
                _utc(day, time(15, 59, 45)),
                _utc(day, time(15, 59, 55)),
                Decimal(str(item["mes_mbp1_exit_10s_usd"])),
            ),
        ]
        for (
            component,
            path,
            symbol,
            schema,
            request_start,
            request_end,
            estimate,
        ) in requests_for_day:
            if estimate == 0:
                with ledger_path.open("a", encoding="utf-8") as ledger:
                    ledger.write(
                        json.dumps(
                            {
                                "date": day.isoformat(),
                                "component": component,
                                "status": "skipped_zero_cost_estimate",
                            }
                        )
                        + "\n"
                    )
                continue
            tasks.append(
                {
                    "date": day.isoformat(),
                    "component": component,
                    "path": path,
                    "symbol": symbol,
                    "schema": schema,
                    "start": request_start,
                    "end": request_end,
                }
            )

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                _download_one,
                key,
                task["path"],
                symbols=task["symbol"],
                schema=task["schema"],
                start=task["start"],
                end=task["end"],
            ): task
            for task in tasks
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            task = futures[future]
            try:
                result = future.result()
            except Exception:
                for pending in futures:
                    pending.cancel()
                raise
            with ledger_path.open("a", encoding="utf-8") as ledger:
                ledger.write(
                    json.dumps(
                        {
                            "date": task["date"],
                            "component": task["component"],
                            **result,
                        }
                    )
                    + "\n"
                )
            if completed % 25 == 0 or completed == len(tasks):
                print(f"completed {completed}/{len(tasks)} session files", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
