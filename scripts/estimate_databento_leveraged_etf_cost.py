"""Query live Databento availability and cost for UPRO/SPXU without buying data."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VENDOR_DIR = Path(__file__).resolve().parents[1] / ".vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

import databento as db  # noqa: E402, I001


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "external_artifacts"
    / "databento_fractional_etf"
    / "leveraged_etf_cost_estimate.json"
)
SYMBOLS = ["UPRO", "SPXU"]
REQUESTS = [
    {
        "dataset": "ARCX.PILLAR",
        "start": "2021-01-01",
        "end": "2026-01-01",
        "role": "full_history_primary_exchange",
    },
    {
        "dataset": "EQUS.MINI",
        "start": "2023-03-28",
        "end": "2026-01-01",
        "role": "consolidated_overlap",
    },
]
SCHEMAS_TO_PRICE = ["ohlcv-1m", "bbo-1m", "bbo-1s", "mbp-1"]


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


def api_key() -> str:
    value = os.environ.get("DATABENTO_API_KEY") or read_dotenv(ROOT / ".env").get(
        "DATABENTO_API_KEY"
    )
    if not value:
        raise RuntimeError("DATABENTO_API_KEY is not set")
    return value


def main() -> int:
    client = db.Historical(api_key())
    results: list[dict[str, Any]] = []
    for request in REQUESTS:
        schemas = list(client.metadata.list_schemas(dataset=request["dataset"]))
        priced: dict[str, dict[str, str]] = {}
        for schema in SCHEMAS_TO_PRICE:
            if schema not in schemas:
                priced[schema] = {"status": "unavailable"}
                continue
            try:
                cost = client.metadata.get_cost(
                    dataset=request["dataset"],
                    symbols=SYMBOLS,
                    stype_in="raw_symbol",
                    schema=schema,
                    start=request["start"],
                    end=request["end"],
                )
                priced[schema] = {
                    "status": "available",
                    "estimated_cost_usd": str(cost),
                }
            except Exception as exc:  # Metadata errors are part of availability.
                priced[schema] = {
                    "status": "query_error",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
        results.append(
            {
                **request,
                "available_schemas": schemas,
                "priced_schemas": priced,
            }
        )

    payload = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "mode": "METADATA_ONLY_NO_PURCHASE",
        "symbols": SYMBOLS,
        "requests": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
