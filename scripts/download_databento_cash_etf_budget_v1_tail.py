"""Complete the interrupted EQUS.MINI TBBO package without repurchasing its prefix."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / ".vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))

import databento as db  # noqa: E402

OUTPUT = ROOT / "external_artifacts" / "databento_cash_etf_budget_v1"
OBSERVED_USAGE_BEFORE_USD = 26.37
HARD_CAP_USD = 40.0
ESTIMATE_BUFFER = 1.10
SYMBOLS = ["SPY", "SSO", "SDS", "UPRO", "SPXU", "SH"]
REQUESTS = [
    {
        "name": "cash_etf_tbbo_tail",
        "dataset": "EQUS.MINI",
        "schema": "tbbo",
        "symbols": SYMBOLS,
        "start": "2024-10-03",
        "end": "2026-07-27",
    },
    {
        "name": "cash_etf_equs_definition",
        "dataset": "EQUS.MINI",
        "schema": "definition",
        "symbols": SYMBOLS,
        "start": "2023-03-28",
        "end": "2026-07-27",
    },
]


def api_key() -> str:
    key = os.environ.get("DATABENTO_API_KEY")
    if key:
        return key
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, value = stripped.split("=", 1)
            if name.strip() == "DATABENTO_API_KEY":
                return value.strip().strip("\"'")
    raise RuntimeError("DATABENTO_API_KEY is unavailable")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def destination(request: dict[str, object]) -> Path:
    return (
        OUTPUT
        / str(request["dataset"])
        / str(request["schema"])
        / f"{request['name']}_{request['start']}_{request['end']}.dbn.zst"
    )


def main() -> int:
    client = db.Historical(api_key())
    estimates = []
    for request in REQUESTS:
        estimate = float(
            client.metadata.get_cost(
                dataset=request["dataset"],
                schema=request["schema"],
                symbols=request["symbols"],
                stype_in="raw_symbol",
                start=request["start"],
                end=request["end"],
            )
        )
        request["estimated_cost_usd"] = estimate
        estimates.append(estimate)

    incremental = sum(estimates)
    buffered_incremental = incremental * ESTIMATE_BUFFER
    buffered_total = OBSERVED_USAGE_BEFORE_USD + buffered_incremental
    if buffered_total > HARD_CAP_USD:
        raise RuntimeError(
            f"Budget guard refused: observed ${OBSERVED_USAGE_BEFORE_USD:.2f} + "
            f"buffered request ${buffered_incremental:.6f} = "
            f"${buffered_total:.6f}, cap ${HARD_CAP_USD:.2f}"
        )
    print(
        f"BUDGET_GUARD_PASS observed=${OBSERVED_USAGE_BEFORE_USD:.2f} "
        f"incremental_estimate=${incremental:.6f} "
        f"buffered_total=${buffered_total:.6f} cap=${HARD_CAP_USD:.2f}",
        flush=True,
    )

    records = []
    for request in REQUESTS:
        path = destination(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite paid artifact: {path}")
        partial = path.with_name(path.stem + ".partial.dbn.zst")
        if partial.exists():
            raise RuntimeError(f"Refusing to delete existing partial artifact: {partial}")
        print(
            f"DOWNLOAD {request['dataset']} {request['schema']} "
            f"{request['start']}..{request['end']} "
            f"estimated=${request['estimated_cost_usd']:.6f}",
            flush=True,
        )
        client.timeseries.get_range(
            dataset=request["dataset"],
            schema=request["schema"],
            symbols=request["symbols"],
            stype_in="raw_symbol",
            start=request["start"],
            end=request["end"],
            path=str(partial),
        )
        if not partial.exists() or partial.stat().st_size == 0:
            raise RuntimeError(f"Empty download: {partial}")
        os.replace(partial, path)
        record = {
            **request,
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        records.append(record)
        print(f"WROTE {record['path']} bytes={record['bytes']}", flush=True)

    manifest = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "observed_usage_before_usd": OBSERVED_USAGE_BEFORE_USD,
        "hard_cap_usd": HARD_CAP_USD,
        "estimate_buffer_multiplier": ESTIMATE_BUFFER,
        "incremental_estimated_cost_usd": incremental,
        "buffered_total_usage_usd": buffered_total,
        "requests": records,
    }
    target = OUTPUT / "tail_download_manifest.json"
    temporary = target.with_suffix(".partial.json")
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    print(json.dumps(manifest, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
