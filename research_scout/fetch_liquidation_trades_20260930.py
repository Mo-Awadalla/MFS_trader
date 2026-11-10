"""Bounded public trade samples for the fixed liquidation events; no paid API."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from research_scout.fetch_liquidation_samples_20260930 import download_sample

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_scout/liquidation_passive_20260930"
DATES = [f"2024-{month:02d}-01" for month in range(7, 13)]


def main():
    OUT.mkdir(exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    estimates = []
    for day in DATES:
        url = f"https://datasets.tardis.dev/v1/binance-futures/trades/{day.replace('-', '/')}/BTCUSDT.csv.gz"
        with session.get(url, stream=True, timeout=(15, 30)) as response:
            response.raise_for_status()
            size = int(response.headers["Content-Length"])
        if size > 250_000_000:
            raise ValueError("Per-file cap exceeded")
        estimates.append({"date": day, "bytes": size, "url": url})
    total = sum(x["bytes"] for x in estimates)
    if total > 1_000_000_000:
        raise ValueError("One-GB aggregate cap exceeded")
    plan = {"public_unauthenticated": True, "no_paid_fallback": True, "samples": estimates,
            "expected_bytes": total, "aggregate_cap": 1_000_000_000,
            "mechanism": "Provide passive liquidity at 8/16bp from the observed midpoint following the unchanged 124 recorded large-liquidation events. Both event direction and its opposite, 30/120-second holds. No event/threshold re-selection; development outcomes are already exposed.",
            "costs": "3bp maker entry, 6bp taker exit plus 1bp adverse exit cost; doubled fee stress and three-second outbound delay; exact partial inventory retained.",
            "limits": "Strict trade-through prints provide counterfactual fill evidence, not actual queue/fill validation. Fixed five-second order lifetime then cancel acknowledgement before holding and market exit. Any unpriceable submitted outcome invalidates the day."}
    (OUT / "acquisition_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(f"Six public trade samples total {total:,} compressed bytes", flush=True)
    manifests = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(download_sample, "trades", day, cap_bytes=250_000_000, output_base=OUT) for day in DATES]
        for job in as_completed(jobs):
            _, manifest = job.result()
            manifests.append(manifest)
            print(f"Downloaded {manifest['date']}: {manifest['bytes']:,} bytes", flush=True)
    (OUT / "download_manifest.json").write_text(json.dumps(manifests, indent=2) + "\n")


if __name__ == "__main__":
    main()
