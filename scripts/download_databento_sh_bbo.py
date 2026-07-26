"""Guarded SH BBO downloader for the sensor–actuator separation test."""

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


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "external_artifacts" / "databento_sh_bbo"
ORIGINAL_AUTHORIZED_BUDGET = Decimal("50.00")
PRIOR_ESTIMATED_SPEND = Decimal("3.615378528832")
INCREMENTAL_CAP = Decimal("5.00")
PROTECTION_MULTIPLIER = Decimal("1.05")
REQUESTS = [
    {
        "dataset": "ARCX.PILLAR",
        "schema": "bbo-1m",
        "symbols": ["SH"],
        "start": "2021-01-01",
        "end": "2026-07-25",
        "filename": "sh_bbo_1m_2021-01-01_2026-07-25.dbn.zst",
        "role": "full_period_primary_execution",
    },
    {
        "dataset": "EQUS.MINI",
        "schema": "bbo-1m",
        "symbols": ["SH"],
        "start": "2023-03-28",
        "end": "2026-07-25",
        "filename": "sh_bbo_1m_2023-03-28_2026-07-25.dbn.zst",
        "role": "consolidated_overlap_audit",
    },
]


def dotenv(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def api_key(path: Path) -> str:
    key = os.environ.get("DATABENTO_API_KEY") or dotenv(path).get(
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


def estimates(client: db.Historical) -> list[dict[str, Any]]:
    output = []
    for request in REQUESTS:
        cost = client.metadata.get_cost(
            dataset=request["dataset"],
            symbols=request["symbols"],
            stype_in="raw_symbol",
            schema=request["schema"],
            start=request["start"],
            end=request["end"],
        )
        output.append({**request, "estimated_cost_usd": str(cost)})
    return output


def download(
    client: db.Historical,
    output_root: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    final = output_root / request["dataset"] / "bbo" / request["filename"]
    final.parent.mkdir(parents=True, exist_ok=True)
    partial = final.with_name(f"{final.name}.partial")
    if final.exists():
        return {
            "status": "already_present",
            "path": final.relative_to(ROOT).as_posix(),
            "bytes": final.stat().st_size,
            "sha256": sha256(final),
        }
    if partial.exists():
        raise RuntimeError(f"Refusing retry with partial file present: {partial}")
    client.timeseries.get_range(
        dataset=request["dataset"],
        symbols=request["symbols"],
        stype_in="raw_symbol",
        stype_out="instrument_id",
        schema=request["schema"],
        start=request["start"],
        end=request["end"],
        path=partial,
    )
    if not partial.exists() or partial.stat().st_size == 0:
        raise RuntimeError(f"Databento returned an empty file: {partial}")
    os.replace(partial, final)
    return {
        "status": "downloaded",
        "path": final.relative_to(ROOT).as_posix(),
        "bytes": final.stat().st_size,
        "sha256": sha256(final),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dotenv", type=Path, default=ROOT / ".env")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    client = db.Historical(api_key(args.dotenv))
    priced = estimates(client)
    incremental = sum(
        (Decimal(row["estimated_cost_usd"]) for row in priced),
        start=Decimal("0"),
    )
    protected = incremental * PROTECTION_MULTIPLIER
    cumulative = PRIOR_ESTIMATED_SPEND + incremental
    preflight = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "mode": "EXECUTE" if args.execute else "DRY_RUN_NO_PURCHASE",
        "preregistration": "research_scout/upro_sh_sensor_actuator_prereg_v8.json",
        "incremental_cap_usd": str(INCREMENTAL_CAP),
        "original_authorized_budget_usd": str(ORIGINAL_AUTHORIZED_BUDGET),
        "prior_estimated_spend_usd": str(PRIOR_ESTIMATED_SPEND),
        "incremental_estimated_total_usd": str(incremental),
        "protected_incremental_estimate_usd": str(protected),
        "cumulative_estimated_spend_usd": str(cumulative),
        "estimated_remaining_original_budget_usd": str(
            ORIGINAL_AUTHORIZED_BUDGET - cumulative
        ),
        "requests": priced,
    }
    print(json.dumps(preflight, indent=2), flush=True)
    if protected > INCREMENTAL_CAP:
        raise RuntimeError("Protected incremental estimate exceeds cap")
    if cumulative > ORIGINAL_AUTHORIZED_BUDGET:
        raise RuntimeError("Cumulative estimate exceeds authorization")
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "cost_estimate.json").write_text(
        json.dumps(preflight, indent=2) + "\n",
        encoding="utf-8",
    )
    if not args.execute:
        return 0
    results = []
    for request in priced:
        result = download(client, args.output_root, request)
        results.append({**request, **result})
        print(
            f"{request['dataset']}: {result['status']} ({result['bytes']} bytes)",
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
    print(json.dumps({"results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
