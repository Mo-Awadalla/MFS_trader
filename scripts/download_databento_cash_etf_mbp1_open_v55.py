"""Acquire the authorized six-ETF opening MBP-1 package under a hard $30 cap.

The paid path is enabled only with ``--execute``. The script consumes the exact
per-weekday metadata ledger created by
``estimate_databento_cash_etf_mbp1_cost_v55.py`` and refuses to start unless a
25% protected estimate remains at or below the immutable $30 authorization.

Each nonzero-cost session is stored separately. Completed files are reused and
partial files stop a rerun, preventing automatic duplicate paid requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402

DATASET = "EQUS.MINI"
SCHEMA = "mbp-1"
SYMBOLS = ["SPY", "SSO", "UPRO", "SH", "SDS", "SPXU"]
SYMBOL_SET_NAME = "full_six_etf_ladder"
NY = ZoneInfo("America/New_York")
UTC_ZONE = ZoneInfo("UTC")
HARD_CAP_USD = Decimal("30.00")
PROTECTION_MULTIPLIER = Decimal("1.25")
DEFAULT_COST_LEDGER = (
    ROOT / "research_scout" / "databento_cash_etf_mbp1_exact_cost_20260729.json"
)
DEFAULT_OUTPUT = (
    ROOT / "external_artifacts" / "databento_cash_etf_mbp1_open_v55"
)
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


def _api_key(path: Path) -> str:
    value = os.environ.get("DATABENTO_API_KEY") or _read_dotenv(path).get(
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.partial")
    temporary.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _utc(day: date, value: time) -> str:
    return datetime.combine(day, value, tzinfo=NY).astimezone(UTC_ZONE).isoformat()


def _load_and_validate_cost_ledger(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("mode") != "METADATA_ONLY_NO_PURCHASE_OR_DOWNLOAD":
        raise RuntimeError("Cost ledger mode is not metadata-only")
    if payload.get("dataset") != DATASET or payload.get("schema") != SCHEMA:
        raise RuntimeError("Cost ledger dataset/schema does not match authorization")
    if payload.get("symbol_sets") != {SYMBOL_SET_NAME: SYMBOLS}:
        raise RuntimeError("Cost ledger symbol set does not match authorization")
    rows = payload.get("sampled_daily_opening_window_estimates")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Cost ledger has no per-weekday estimates")
    if payload.get("sampled_calendar_weekdays") != payload.get(
        "calendar_weekdays_in_projection"
    ):
        raise RuntimeError("Cost ledger is sampled rather than exact")
    expected_count = int(payload["calendar_weekdays_in_projection"])
    if len(rows) != expected_count:
        raise RuntimeError("Cost ledger weekday count is inconsistent")
    dates = [str(row["date"]) for row in rows]
    if len(dates) != len(set(dates)):
        raise RuntimeError("Cost ledger contains duplicate dates")
    return payload, rows


def _destination(output: Path, day: str) -> Path:
    return output / DATASET / SCHEMA / f"{day}.dbn.zst"


def _download_one(
    *,
    key: str,
    output: Path,
    row: dict[str, Any],
) -> dict[str, Any]:
    day_text = str(row["date"])
    estimated_cost = Decimal(str(row[f"{SYMBOL_SET_NAME}_usd"]))
    final = _destination(output, day_text)
    partial = final.with_name(f"{day_text}.partial.dbn.zst")
    final.parent.mkdir(parents=True, exist_ok=True)

    if final.exists():
        if final.stat().st_size == 0:
            raise RuntimeError(f"Existing final file is empty: {final}")
        return {
            "date": day_text,
            "status": "reused",
            "estimated_cost_usd": str(estimated_cost),
            "path": final.relative_to(ROOT).as_posix(),
            "bytes": final.stat().st_size,
            "sha256": _sha256(final),
        }
    if partial.exists():
        raise RuntimeError(
            f"Partial paid artifact exists; refusing automatic retry: {partial}"
        )

    day = date.fromisoformat(day_text)
    _client(key).timeseries.get_range(
        dataset=DATASET,
        schema=SCHEMA,
        symbols=SYMBOLS,
        stype_in="raw_symbol",
        start=_utc(day, time(9, 20)),
        end=_utc(day, time(9, 40)),
        path=str(partial),
    )
    if not partial.exists() or partial.stat().st_size == 0:
        raise RuntimeError(f"Databento returned an empty file: {partial}")
    os.replace(partial, final)
    return {
        "date": day_text,
        "status": "downloaded",
        "estimated_cost_usd": str(estimated_cost),
        "path": final.relative_to(ROOT).as_posix(),
        "bytes": final.stat().st_size,
        "sha256": _sha256(final),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--dotenv", type=Path, default=ROOT / ".env")
    parser.add_argument("--cost-ledger", type=Path, default=DEFAULT_COST_LEDGER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not 1 <= args.workers <= 10:
        raise ValueError("--workers must be between 1 and 10")
    cost_payload, rows = _load_and_validate_cost_ledger(args.cost_ledger)
    paid_rows = [
        row
        for row in rows
        if Decimal(str(row[f"{SYMBOL_SET_NAME}_usd"])) > Decimal("0")
    ]
    exact_estimate = sum(
        (Decimal(str(row[f"{SYMBOL_SET_NAME}_usd"])) for row in paid_rows),
        start=Decimal("0"),
    )
    protected_estimate = exact_estimate * PROTECTION_MULTIPLIER
    if protected_estimate > HARD_CAP_USD:
        raise RuntimeError(
            f"HARD_CAP_REFUSAL exact=${exact_estimate} "
            f"protected=${protected_estimate} cap=${HARD_CAP_USD}"
        )

    partials = list((args.output / DATASET / SCHEMA).glob("*.partial.dbn.zst"))
    if partials:
        raise RuntimeError(
            "Partial paid artifacts exist; refusing automatic retry: "
            + ", ".join(str(path) for path in partials[:5])
        )
    preflight = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "mode": "EXECUTE_AUTHORIZED_PAID_REQUESTS"
        if args.execute
        else "DRY_RUN_NO_PURCHASE",
        "authorization": {
            "hard_cap_usd": str(HARD_CAP_USD),
            "protection_multiplier": str(PROTECTION_MULTIPLIER),
            "exact_metadata_estimate_usd": str(exact_estimate),
            "protected_estimate_usd": str(protected_estimate),
        },
        "request": {
            "dataset": DATASET,
            "schema": SCHEMA,
            "symbols": SYMBOLS,
            "window": "09:20:00-09:40:00 America/New_York",
            "start_inclusive": cost_payload["start_inclusive"],
            "end_exclusive": cost_payload["end_exclusive"],
            "calendar_weekdays": len(rows),
            "nonzero_cost_sessions": len(paid_rows),
        },
        "cost_ledger": {
            "path": args.cost_ledger.relative_to(ROOT).as_posix(),
            "sha256": _sha256(args.cost_ledger),
            "created_at_utc": cost_payload["created_at_utc"],
        },
    }
    print(json.dumps(preflight, indent=2), flush=True)
    args.output.mkdir(parents=True, exist_ok=True)
    _atomic_json(args.output / "preflight.json", preflight)
    if not args.execute:
        return 0

    key = _api_key(args.dotenv)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                _download_one,
                key=key,
                output=args.output,
                row=row,
            ): str(row["date"])
            for row in paid_rows
        }
        for index, future in enumerate(as_completed(futures), start=1):
            day_text = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append(
                    {
                        "date": day_text,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
            if index % 25 == 0 or index == len(futures):
                progress = {
                    **preflight,
                    "mode": "ACQUISITION_IN_PROGRESS",
                    "updated_at_utc": datetime.now(UTC).isoformat(),
                    "completed_sessions": len(results),
                    "failed_sessions": len(errors),
                    "total_sessions": len(futures),
                    "results": sorted(results, key=lambda item: item["date"]),
                    "errors": sorted(errors, key=lambda item: item["date"]),
                }
                _atomic_json(args.output / "progress.json", progress)
                print(
                    f"progress {index}/{len(futures)} "
                    f"complete={len(results)} failed={len(errors)}",
                    flush=True,
                )

    results.sort(key=lambda item: item["date"])
    errors.sort(key=lambda item: item["date"])
    manifest = {
        **preflight,
        "mode": "ACQUISITION_COMPLETE" if not errors else "ACQUISITION_INCOMPLETE",
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "results": results,
        "errors": errors,
        "summary": {
            "downloaded_sessions": sum(
                row["status"] == "downloaded" for row in results
            ),
            "reused_sessions": sum(row["status"] == "reused" for row in results),
            "failed_sessions": len(errors),
            "compressed_bytes": sum(int(row["bytes"]) for row in results),
            "estimated_cost_usd": str(exact_estimate),
            "protected_estimate_usd": str(protected_estimate),
            "hard_cap_usd": str(HARD_CAP_USD),
        },
        "notes": [
            "No zero-cost holiday request was sent to the time-series endpoint.",
            "Each nonzero-cost session was requested at most once in this run.",
            "Existing final files were reused; partial files are never retried automatically.",
            "Databento bills actual outbound bytes; the 25% reserve protects the hard cap.",
        ],
    }
    _atomic_json(args.output / "manifest.json", manifest)
    print(json.dumps(manifest["summary"], indent=2), flush=True)
    if errors:
        raise RuntimeError(
            f"Acquisition incomplete: {len(errors)} session request(s) failed"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
