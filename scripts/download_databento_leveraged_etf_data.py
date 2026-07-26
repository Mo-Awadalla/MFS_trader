"""Guarded Databento downloader for UPRO/SPXU bars and one-minute BBO.

The command is metadata-only unless ``--execute`` is provided. It obtains a
fresh cost estimate, applies a 5% protection allowance, and enforces a small
incremental purchase cap before requesting any data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

VENDOR_DIR = Path(__file__).resolve().parents[1] / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402, I001


DEFAULT_ROOT = Path("external_artifacts/databento_leveraged_etf")
DEFAULT_INCREMENTAL_BUDGET = Decimal("5.00")
ORIGINAL_AUTHORIZED_BUDGET = Decimal("50.00")
PRIOR_ESTIMATED_SPEND = Decimal("1.198559224605")
PROTECTION_MULTIPLIER = Decimal("1.05")
SYMBOLS = ["UPRO", "SPXU"]
REQUESTS = [
    {
        "dataset": "ARCX.PILLAR",
        "schema": "ohlcv-1m",
        "start": "2021-01-01",
        "end": "2026-01-01",
        "subdirectory": "bars",
        "filename": "upro_spxu_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst",
        "role": "full_history_primary_exchange_bars",
    },
    {
        "dataset": "ARCX.PILLAR",
        "schema": "bbo-1m",
        "start": "2021-01-01",
        "end": "2026-01-01",
        "subdirectory": "bbo",
        "filename": "upro_spxu_bbo_1m_2021-01-01_2026-01-01.dbn.zst",
        "role": "full_history_primary_exchange_bbo",
    },
    {
        "dataset": "EQUS.MINI",
        "schema": "ohlcv-1m",
        "start": "2023-03-28",
        "end": "2026-01-01",
        "subdirectory": "bars",
        "filename": "upro_spxu_ohlcv_1m_2023-03-28_2026-01-01.dbn.zst",
        "role": "consolidated_overlap_bars",
    },
    {
        "dataset": "EQUS.MINI",
        "schema": "bbo-1m",
        "start": "2023-03-28",
        "end": "2026-01-01",
        "subdirectory": "bbo",
        "filename": "upro_spxu_bbo_1m_2023-03-28_2026-01-01.dbn.zst",
        "role": "consolidated_overlap_bbo",
    },
]


def read_dotenv(path: Path) -> dict[str, str]:
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


def api_key(dotenv_path: Path) -> str:
    key = os.environ.get("DATABENTO_API_KEY") or read_dotenv(dotenv_path).get(
        "DATABENTO_API_KEY"
    )
    if not key:
        raise RuntimeError("DATABENTO_API_KEY is not set")
    return key


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def estimate(client: db.Historical) -> list[dict[str, Any]]:
    estimates: list[dict[str, Any]] = []
    for request in REQUESTS:
        cost = client.metadata.get_cost(
            dataset=request["dataset"],
            symbols=SYMBOLS,
            stype_in="raw_symbol",
            schema=request["schema"],
            start=request["start"],
            end=request["end"],
        )
        estimates.append({**request, "estimated_cost_usd": str(cost)})
    return estimates


def download_one(
    client: db.Historical,
    output_root: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    final_path = (
        output_root
        / request["dataset"]
        / request["subdirectory"]
        / request["filename"]
    )
    final_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = final_path.with_name(f"{final_path.name}.partial")
    if final_path.exists():
        return {
            "status": "already_present",
            "path": final_path.as_posix(),
            "bytes": final_path.stat().st_size,
            "sha256": sha256(final_path),
        }
    if partial_path.exists():
        raise RuntimeError(
            f"Partial file exists; refusing automatic retry: {partial_path}"
        )
    client.timeseries.get_range(
        dataset=request["dataset"],
        symbols=SYMBOLS,
        stype_in="raw_symbol",
        stype_out="instrument_id",
        schema=request["schema"],
        start=request["start"],
        end=request["end"],
        path=partial_path,
    )
    if not partial_path.exists() or partial_path.stat().st_size == 0:
        raise RuntimeError(f"Databento returned an empty file: {partial_path}")
    os.replace(partial_path, final_path)
    return {
        "status": "downloaded",
        "path": final_path.as_posix(),
        "bytes": final_path.stat().st_size,
        "sha256": sha256(final_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dotenv", type=Path, default=Path(".env"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--incremental-budget-usd",
        type=Decimal,
        default=DEFAULT_INCREMENTAL_BUDGET,
    )
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if (
        args.incremental_budget_usd <= 0
        or args.incremental_budget_usd > DEFAULT_INCREMENTAL_BUDGET
    ):
        raise ValueError(
            "--incremental-budget-usd must be above zero and at most "
            f"{DEFAULT_INCREMENTAL_BUDGET}"
        )

    client = db.Historical(api_key(args.dotenv))
    estimates = estimate(client)
    incremental_total = sum(
        (Decimal(item["estimated_cost_usd"]) for item in estimates),
        start=Decimal("0"),
    )
    protected = incremental_total * PROTECTION_MULTIPLIER
    cumulative_estimate = PRIOR_ESTIMATED_SPEND + incremental_total
    preflight = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "mode": "EXECUTE" if args.execute else "DRY_RUN",
        "incremental_budget_usd": str(args.incremental_budget_usd),
        "original_authorized_budget_usd": str(ORIGINAL_AUTHORIZED_BUDGET),
        "prior_estimated_spend_usd": str(PRIOR_ESTIMATED_SPEND),
        "protection_multiplier": str(PROTECTION_MULTIPLIER),
        "incremental_estimated_total_usd": str(incremental_total),
        "protected_incremental_estimate_usd": str(protected),
        "cumulative_estimated_spend_usd": str(cumulative_estimate),
        "estimated_original_budget_remaining_usd": str(
            ORIGINAL_AUTHORIZED_BUDGET - cumulative_estimate
        ),
        "symbols": SYMBOLS,
        "requests": estimates,
    }
    print(json.dumps(preflight, indent=2), flush=True)
    if protected > args.incremental_budget_usd:
        raise RuntimeError(
            f"Protected estimate ${protected} exceeds incremental cap "
            f"${args.incremental_budget_usd}"
        )
    if cumulative_estimate > ORIGINAL_AUTHORIZED_BUDGET:
        raise RuntimeError("Cumulative estimate exceeds original authorization")

    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "cost_estimate.json").write_text(
        json.dumps(preflight, indent=2) + "\n",
        encoding="utf-8",
    )
    if not args.execute:
        return 0

    results = []
    for request in estimates:
        result = download_one(client, args.output_root, request)
        results.append(
            {
                "dataset": request["dataset"],
                "schema": request["schema"],
                "role": request["role"],
                "estimated_cost_usd": request["estimated_cost_usd"],
                **result,
            }
        )
        print(
            f"{request['dataset']} {request['schema']}: "
            f"{result['status']} ({result['bytes']} bytes)",
            flush=True,
        )

    ledger = {
        **preflight,
        "mode": "EXECUTED",
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "results": results,
    }
    (args.output_root / "download_ledger.json").write_text(
        json.dumps(ledger, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"results": results}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
