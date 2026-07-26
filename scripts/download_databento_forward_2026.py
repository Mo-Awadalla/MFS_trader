"""Guarded downloader for the preregistered 2026 forward ETF test."""

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
DEFAULT_ROOT = ROOT / "external_artifacts" / "databento_forward_2026"
ORIGINAL_AUTHORIZED_BUDGET = Decimal("50.00")
PRIOR_ESTIMATED_SPEND = Decimal("3.345466166734")
INCREMENTAL_CAP = Decimal("5.00")
PROTECTION_MULTIPLIER = Decimal("1.05")
START = "2026-01-02"
END = "2026-07-25"
REQUESTS = [
    {
        "dataset": "ARCX.PILLAR",
        "schema": "ohlcv-1m",
        "symbols": ["SPY", "UPRO", "SPXU"],
        "subdirectory": "bars",
        "filename": "spy_upro_spxu_ohlcv_1m_2026-01-02_2026-07-25.dbn.zst",
        "role": "prospective_signal_risk_and_benchmark_bars",
    },
    {
        "dataset": "ARCX.PILLAR",
        "schema": "bbo-1m",
        "symbols": ["UPRO", "SPXU"],
        "subdirectory": "bbo",
        "filename": "upro_spxu_bbo_1m_2026-01-02_2026-07-25.dbn.zst",
        "role": "prospective_executable_quotes",
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


def api_key(path: Path) -> str:
    key = os.environ.get("DATABENTO_API_KEY") or read_dotenv(path).get(
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
    results: list[dict[str, Any]] = []
    for request in REQUESTS:
        cost = client.metadata.get_cost(
            dataset=request["dataset"],
            symbols=request["symbols"],
            stype_in="raw_symbol",
            schema=request["schema"],
            start=START,
            end=END,
        )
        results.append({**request, "estimated_cost_usd": str(cost)})
    return results


def download(
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
            "path": final_path.relative_to(ROOT).as_posix(),
            "bytes": final_path.stat().st_size,
            "sha256": sha256(final_path),
        }
    if partial_path.exists():
        raise RuntimeError(f"Refusing retry with partial file present: {partial_path}")
    client.timeseries.get_range(
        dataset=request["dataset"],
        symbols=request["symbols"],
        stype_in="raw_symbol",
        stype_out="instrument_id",
        schema=request["schema"],
        start=START,
        end=END,
        path=partial_path,
    )
    if not partial_path.exists() or partial_path.stat().st_size == 0:
        raise RuntimeError(f"Databento returned an empty file: {partial_path}")
    os.replace(partial_path, final_path)
    return {
        "status": "downloaded",
        "path": final_path.relative_to(ROOT).as_posix(),
        "bytes": final_path.stat().st_size,
        "sha256": sha256(final_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dotenv", type=Path, default=ROOT / ".env")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    client = db.Historical(api_key(args.dotenv))
    estimates = estimate(client)
    incremental = sum(
        (Decimal(row["estimated_cost_usd"]) for row in estimates),
        start=Decimal("0"),
    )
    protected = incremental * PROTECTION_MULTIPLIER
    cumulative = PRIOR_ESTIMATED_SPEND + incremental
    preflight = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "mode": "EXECUTE" if args.execute else "DRY_RUN_NO_PURCHASE",
        "preregistration": (
            "research_scout/upro_spxu_density_invariant_sync_prereg_v6.json"
        ),
        "start": START,
        "end_exclusive": END,
        "incremental_cap_usd": str(INCREMENTAL_CAP),
        "original_authorized_budget_usd": str(ORIGINAL_AUTHORIZED_BUDGET),
        "prior_estimated_spend_usd": str(PRIOR_ESTIMATED_SPEND),
        "incremental_estimated_total_usd": str(incremental),
        "protected_incremental_estimate_usd": str(protected),
        "cumulative_estimated_spend_usd": str(cumulative),
        "estimated_remaining_original_budget_usd": str(
            ORIGINAL_AUTHORIZED_BUDGET - cumulative
        ),
        "requests": estimates,
    }
    print(json.dumps(preflight, indent=2), flush=True)
    if protected > INCREMENTAL_CAP:
        raise RuntimeError(
            f"Protected estimate ${protected} exceeds cap ${INCREMENTAL_CAP}"
        )
    if cumulative > ORIGINAL_AUTHORIZED_BUDGET:
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
        result = download(client, args.output_root, request)
        results.append(
            {
                "dataset": request["dataset"],
                "schema": request["schema"],
                "symbols": request["symbols"],
                "role": request["role"],
                "estimated_cost_usd": request["estimated_cost_usd"],
                **result,
            }
        )
        print(
            f"{request['schema']}: {result['status']} ({result['bytes']} bytes)",
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
