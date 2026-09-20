"""Guarded Databento downloader for the fractional SPY/SH research dataset.

The command is a metadata-only dry run unless ``--execute`` is provided. Before
each execution it obtains a fresh cost estimate and refuses to download when a
5% protected estimate exceeds the user-authorized budget.

Two one-minute OHLCV files are requested:

* ARCX.PILLAR for full 2021-2025 history from SPY/SH's primary exchange.
* EQUS.MINI for consolidated top-of-book-derived overlap from 2023-03-28.

Files are never retried over an existing partial download, preventing an
interrupted request from silently being purchased twice.
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

import databento as db  # noqa: E402

DEFAULT_ROOT = Path("external_artifacts/databento_fractional_etf")
DEFAULT_BUDGET = Decimal("50.00")
PROTECTION_MULTIPLIER = Decimal("1.05")
SYMBOLS = ["SPY", "SH"]
REQUESTS = [
    {
        "dataset": "ARCX.PILLAR",
        "start": "2021-01-01",
        "end": "2026-01-01",
        "filename": "spy_sh_ohlcv_1m_2021-01-01_2026-01-01.dbn.zst",
        "role": "full_history_primary_exchange_bars",
    },
    {
        "dataset": "EQUS.MINI",
        "start": "2023-03-28",
        "end": "2026-01-01",
        "filename": "spy_sh_ohlcv_1m_2023-03-28_2026-01-01.dbn.zst",
        "role": "consolidated_overlap_validation_bars",
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
            schema="ohlcv-1m",
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
        / "bars"
        / request["filename"]
    )
    final_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = final_path.with_name(
        f"{final_path.stem}.partial{final_path.suffix}"
    )
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
        schema="ohlcv-1m",
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
    parser.add_argument("--budget-usd", type=Decimal, default=DEFAULT_BUDGET)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if args.budget_usd <= 0 or args.budget_usd > DEFAULT_BUDGET:
        raise ValueError(
            f"--budget-usd must be above zero and at most {DEFAULT_BUDGET}"
        )

    client = db.Historical(api_key(args.dotenv))
    estimates = estimate(client)
    total = sum(
        (
            Decimal(item["estimated_cost_usd"])
            for item in estimates
        ),
        start=Decimal("0"),
    )
    protected = total * PROTECTION_MULTIPLIER
    preflight = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "mode": "EXECUTE" if args.execute else "DRY_RUN",
        "authorized_budget_usd": str(args.budget_usd),
        "protection_multiplier": str(PROTECTION_MULTIPLIER),
        "estimated_total_usd": str(total),
        "protected_estimate_usd": str(protected),
        "symbols": SYMBOLS,
        "schema": "ohlcv-1m",
        "requests": estimates,
    }
    print(json.dumps(preflight, indent=2), flush=True)
    if protected > args.budget_usd:
        raise RuntimeError(
            f"Protected estimate ${protected} exceeds authorized budget "
            f"${args.budget_usd}"
        )

    args.output_root.mkdir(parents=True, exist_ok=True)
    estimate_path = args.output_root / "cost_estimate.json"
    estimate_path.write_text(
        json.dumps(preflight, indent=2) + "\n", encoding="utf-8"
    )
    if not args.execute:
        return 0

    results = []
    for request in estimates:
        result = download_one(client, args.output_root, request)
        results.append(
            {
                "dataset": request["dataset"],
                "role": request["role"],
                "estimated_cost_usd": request["estimated_cost_usd"],
                **result,
            }
        )
        print(
            f"{request['dataset']}: {result['status']} "
            f"({result['bytes']} bytes)",
            flush=True,
        )

    ledger = {
        **preflight,
        "mode": "EXECUTED",
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "results": results,
        "unspent_authorized_budget_estimate_usd": str(
            args.budget_usd - total
        ),
    }
    ledger_path = args.output_root / "download_ledger.json"
    ledger_path.write_text(
        json.dumps(ledger, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"downloaded": results}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
