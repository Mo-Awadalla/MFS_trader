"""Download the frozen non-futures Databento package under a $40 cost cap."""

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
BUDGET_USD = 40.0
ESTIMATE_BUFFER = 1.05
SYMBOLS = ["SPY", "SSO", "SDS", "UPRO", "SPXU", "SH"]
REQUESTS = [
    {
        "name": "spy_imbalance",
        "dataset": "ARCX.PILLAR",
        "schema": "imbalance",
        "symbols": ["SPY"],
        "start": "2021-01-01",
        "end": "2026-07-27",
    },
    {
        "name": "cash_etf_statistics",
        "dataset": "ARCX.PILLAR",
        "schema": "statistics",
        "symbols": SYMBOLS,
        "start": "2021-01-01",
        "end": "2026-07-27",
    },
    {
        "name": "cash_etf_status",
        "dataset": "ARCX.PILLAR",
        "schema": "status",
        "symbols": SYMBOLS,
        "start": "2021-01-01",
        "end": "2026-07-27",
    },
    {
        "name": "cash_etf_arcx_definition",
        "dataset": "ARCX.PILLAR",
        "schema": "definition",
        "symbols": SYMBOLS,
        "start": "2021-01-01",
        "end": "2026-07-27",
    },
    {
        "name": "cash_etf_tbbo",
        "dataset": "EQUS.MINI",
        "schema": "tbbo",
        "symbols": SYMBOLS,
        "start": "2023-03-28",
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
    dotenv = ROOT / ".env"
    for raw in dotenv.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name, value = stripped.split("=", 1)
            if name.strip() == "DATABENTO_API_KEY":
                return value.strip().strip("\"'")
    raise RuntimeError("DATABENTO_API_KEY is unavailable")


def destination(request: dict[str, object]) -> Path:
    return (
        OUTPUT
        / str(request["dataset"])
        / str(request["schema"])
        / (
            f"{request['name']}_{request['start']}_{request['end']}"
            ".dbn.zst"
        )
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    client = db.Historical(api_key())
    estimates: list[float] = []
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

    total = sum(estimates)
    buffered = total * ESTIMATE_BUFFER
    if buffered > BUDGET_USD:
        raise RuntimeError(
            f"Budget guard refused: ${total:.6f} estimate, "
            f"${buffered:.6f} buffered, ${BUDGET_USD:.2f} cap"
        )
    print(
        f"BUDGET_GUARD_PASS estimate=${total:.6f} "
        f"buffered=${buffered:.6f} cap=${BUDGET_USD:.2f}",
        flush=True,
    )

    records: list[dict[str, object]] = []
    for request in REQUESTS:
        path = destination(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            partial = path.with_name(path.stem + ".partial.dbn.zst")
            if partial.exists():
                partial.unlink()
            print(
                f"DOWNLOAD {request['dataset']} {request['schema']} "
                f"estimated=${request['estimated_cost_usd']:.6f}",
                flush=True,
            )
            try:
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
            finally:
                if partial.exists():
                    partial.unlink()
        else:
            print(f"REUSE {path.relative_to(ROOT)}", flush=True)

        record = {
            **request,
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        records.append(record)
        print(
            f"VERIFIED_FILE {record['path']} bytes={record['bytes']} "
            f"sha256={record['sha256']}",
            flush=True,
        )

    manifest = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "hard_cap_usd": BUDGET_USD,
        "estimate_buffer_multiplier": ESTIMATE_BUFFER,
        "estimated_total_cost_usd": total,
        "buffered_estimated_total_usd": buffered,
        "requests": records,
        "notes": [
            "Paid requests were cost-estimated immediately before download.",
            "EQUS.MINI is a derived anonymized multi-venue feed, not documented as official SIP NBBO.",
            "Vendor-native fields and timestamps are retained in DBN.",
        ],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "manifest.json"
    partial_manifest = OUTPUT / "manifest.partial.json"
    partial_manifest.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(partial_manifest, target)
    print(json.dumps({"status": "complete", **manifest}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
