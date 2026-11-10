"""Bounded public Bybit samples matching the already cached Binance dates."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import requests

from research_scout.fetch_liquidation_samples_20260930 import download_sample

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_scout/cross_venue_20260930"
DATES = [f"2024-{month:02d}-01" for month in range(7, 13)]
PER_FILE_CAP, TOTAL_CAP = 500_000_000, 2_000_000_000


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    response = session.get("https://api.tardis.dev/v1/exchanges/bybit", timeout=(15, 45))
    response.raise_for_status()
    metadata = response.json()
    contract = next(item for item in metadata["datasets"]["symbols"] if item["id"] == "BTCUSDT")
    if "book_snapshot_5" not in contract["dataTypes"] or contract["type"] != "perpetual":
        raise ValueError("Expected public Bybit perpetual book type is unavailable")
    estimates = []
    for day in DATES:
        url = f"https://datasets.tardis.dev/v1/bybit/book_snapshot_5/{day.replace('-', '/')}/BTCUSDT.csv.gz"
        with session.get(url, stream=True, timeout=(15, 45)) as response:
            response.raise_for_status()
            length = int(response.headers["Content-Length"])
        if length > PER_FILE_CAP:
            raise ValueError("Sample exceeds per-file cap")
        estimates.append({"date": day, "url": url, "bytes": length})
    if sum(item["bytes"] for item in estimates) > TOTAL_CAP:
        raise ValueError("Samples exceed aggregate cap")
    plan = {"created_at_utc": datetime.now(UTC).isoformat(), "contract": contract,
            "samples": estimates, "bytes": sum(item["bytes"] for item in estimates),
            "aggregate_cap": TOTAL_CAP, "authenticated": False, "paid_fallback": False}
    (OUTPUT / "acquisition_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(f"Bybit BTCUSDT metadata verified; six files total {plan['bytes']:,} compressed bytes", flush=True)
    manifests = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(download_sample, "book_snapshot_5", day, cap_bytes=PER_FILE_CAP,
                            exchange="bybit", output_base=OUTPUT / "bybit") for day in DATES]
        for job in as_completed(jobs):
            _, manifest = job.result()
            manifests.append(manifest)
            print(f"Bybit {manifest['date']}: {manifest['bytes']:,} bytes", flush=True)
    (OUTPUT / "download_manifest.json").write_text(json.dumps(manifests, indent=2) + "\n")


if __name__ == "__main__":
    main()
