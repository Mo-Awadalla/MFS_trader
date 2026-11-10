"""Fetch six public top-five book samples with per-file and aggregate caps."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from research_scout.fetch_liquidation_samples_20260930 import OUTPUT, download_sample

DATES = [f"2024-{month:02d}-01" for month in range(7, 13)]
PER_FILE_CAP = 500_000_000
TOTAL_CAP = 2_000_000_000


def main():
    estimates = []
    session = requests.Session()
    session.trust_env = False
    for day in DATES:
        url = f"https://datasets.tardis.dev/v1/binance-futures/book_snapshot_5/{day.replace('-', '/')}/BTCUSDT.csv.gz"
        # Dataset routes support GET; HEAD returned 404 even for listed types.
        # Read only headers in this probe, then close without consuming the body.
        with session.get(url, stream=True, timeout=(15, 30)) as response:
            response.raise_for_status()
            length = int(response.headers["Content-Length"])
        if length > PER_FILE_CAP:
            raise ValueError("Sample exceeds fixed per-file budget")
        estimates.append({"date": day, "url": url, "bytes": length})
    total = sum(row["bytes"] for row in estimates)
    if total > TOTAL_CAP:
        raise ValueError("Sample set exceeds fixed aggregate budget")
    (OUTPUT / "book_acquisition_plan.json").write_text(json.dumps({"public_unauthenticated": True,
        "samples": estimates, "expected_bytes": total, "total_cap": TOTAL_CAP}, indent=2) + "\n")
    print(f"Six public book samples total {total:,} compressed bytes", flush=True)
    manifests = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(download_sample, "book_snapshot_5", day, cap_bytes=PER_FILE_CAP) for day in DATES]
        for job in as_completed(jobs):
            _, manifest = job.result()
            manifests.append(manifest)
            print(f"Downloaded {manifest['date']}: {manifest['bytes']:,} bytes", flush=True)
    (OUTPUT / "book_download_manifest.json").write_text(json.dumps(manifests, indent=2) + "\n")


if __name__ == "__main__":
    main()
